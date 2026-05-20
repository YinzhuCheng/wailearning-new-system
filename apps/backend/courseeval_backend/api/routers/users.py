from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.domains.roster.reconciliation import sync_student_roster_from_user_accounts

from apps.backend.courseeval_backend.attachments import delete_attachment_file_if_unreferenced
from apps.backend.courseeval_backend.core.auth import get_current_active_user, get_password_hash
from apps.backend.courseeval_backend.db.database import get_db
from apps.backend.courseeval_backend.db.models import (
    Class,
    CourseEnrollment,
    CourseMaterial,
    Homework,
    HomeworkAttempt,
    HomeworkGradingTask,
    HomeworkScoreCandidate,
    LLMQuotaReservation,
    LLMTokenUsageLog,
    Notification,
    NotificationRead,
    OperationLog,
    PointExchange,
    PointRecord,
    Student,
    Subject,
    User,
    UserRole,
)
from apps.backend.courseeval_backend.api.schemas import (
    AdminResetUserPasswordRequest,
    MessageResponse,
    StudentRosterUpsertFromUsersRequest,
    StudentRosterUpsertFromUsersResponse,
    UserBatchSetClassError,
    UserBatchSetClassRequest,
    UserBatchSetClassResponse,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from apps.backend.courseeval_backend.domains.courses.access import prepare_student_course_context, sync_student_course_enrollments
from apps.backend.courseeval_backend.domains.roster.identity import ensure_student_class_id, get_bound_student_for_user
from apps.backend.courseeval_backend.services.logging import LogService
from apps.backend.courseeval_backend.core.permissions import is_admin

router = APIRouter(prefix="/api/users", tags=["用户管理"])


def normalize_managed_class_id(role: Optional[str], class_id: Optional[int]) -> Optional[int]:
    if role == UserRole.TEACHER.value:
        return None
    return class_id


def validate_class_exists(class_id: Optional[int], db: Session) -> None:
    if not class_id:
        return

    class_obj = db.query(Class).filter(Class.id == class_id).first()
    if not class_obj:
        raise HTTPException(status_code=400, detail="班级不存在")


def validate_role_class_contract(role: Optional[str], class_id: Optional[int]) -> None:
    if role == UserRole.CLASS_TEACHER.value and class_id is None:
        raise HTTPException(status_code=400, detail="班主任账号必须绑定班级")


def sync_student_account_or_raise(db: Session, user: User) -> None:
    result = sync_student_roster_from_user_accounts(db, [user.id])
    if result.errors:
        db.rollback()
        raise HTTPException(status_code=400, detail=result.errors[0].reason)


def delete_user_homeworks(user_id: int, db: Session) -> None:
    homeworks = db.query(Homework).filter(Homework.created_by == user_id).all()
    for homework in homeworks:
        attempts = db.query(HomeworkAttempt).filter(HomeworkAttempt.homework_id == homework.id).all()
        for attempt in attempts:
            if attempt.attachment_url:
                attempt.attachment_url = None
            task_ids = [
                task_id
                for (task_id,) in db.query(HomeworkGradingTask.id)
                .filter(HomeworkGradingTask.attempt_id == attempt.id)
                .all()
            ]
            if task_ids:
                db.query(LLMQuotaReservation).filter(LLMQuotaReservation.task_id.in_(task_ids)).delete(
                    synchronize_session=False
                )
                db.query(LLMTokenUsageLog).filter(LLMTokenUsageLog.task_id.in_(task_ids)).delete(
                    synchronize_session=False
                )
                db.query(HomeworkGradingTask).filter(HomeworkGradingTask.id.in_(task_ids)).delete(
                    synchronize_session=False
                )
            db.query(HomeworkScoreCandidate).filter(HomeworkScoreCandidate.attempt_id == attempt.id).delete(
                synchronize_session=False
            )
            db.delete(attempt)
        for submission in list(homework.submissions):
            submission.attachment_url = None
            db.delete(submission)
        homework.attachment_url = None
        db.delete(homework)


def delete_user_notifications(user_id: int, db: Session) -> None:
    notifications = db.query(Notification).filter(Notification.created_by == user_id).all()
    for notification in notifications:
        delete_attachment_file_if_unreferenced(db, notification.attachment_url)
        db.query(NotificationRead).filter(NotificationRead.notification_id == notification.id).delete(
            synchronize_session=False
        )
        db.delete(notification)


def delete_user_materials(user_id: int, db: Session) -> None:
    materials = db.query(CourseMaterial).filter(CourseMaterial.created_by == user_id).all()
    for material in materials:
        delete_attachment_file_if_unreferenced(db, material.attachment_url)
        db.delete(material)


@router.get("", response_model=List[UserResponse])
def get_users(
    role: Optional[str] = None,
    class_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not is_admin(current_user):
        raise HTTPException(status_code=403, detail="只有管理员可以查看用户列表")

    query = db.query(User)

    if role:
        query = query.filter(User.role == role)
    if class_id:
        query = query.filter(User.class_id == class_id)

    return query.all()


@router.post("/batch-set-class", response_model=UserBatchSetClassResponse)
def batch_set_user_class(
    payload: UserBatchSetClassRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Move student accounts and their bound canonical Student rows to one class."""
    if not is_admin(current_user):
        raise HTTPException(status_code=403, detail="只有管理员可以批量调整班级")

    validate_class_exists(payload.class_id, db)

    user_ids = list(dict.fromkeys(payload.user_ids))
    if not user_ids:
        return UserBatchSetClassResponse()

    users = db.query(User).filter(User.id.in_(user_ids)).all()
    user_map = {u.id: u for u in users}

    updated = 0
    errors: list[UserBatchSetClassError] = []

    for uid in user_ids:
        user = user_map.get(uid)
        if not user:
            errors.append(UserBatchSetClassError(user_id=uid, reason="用户不存在"))
            continue
        if (user.role or "").strip() != UserRole.STUDENT.value:
            errors.append(UserBatchSetClassError(user_id=uid, reason="仅支持学生账号批量调班"))
            continue
        if user.class_id == payload.class_id:
            continue
        if user.student_id is None and user.username:
            sync_student_roster_from_user_accounts(db, [user.id])
            db.flush()
        roster = get_bound_student_for_user(user, db)
        if roster and roster.class_id != payload.class_id:
            db.query(CourseEnrollment).filter(CourseEnrollment.student_id == roster.id).delete(
                synchronize_session=False
            )
            roster.class_id = payload.class_id
            db.flush()
            sync_student_course_enrollments(roster, db)
        user.class_id = payload.class_id
        if user.username and (user.role or "").strip() == UserRole.STUDENT.value:
            prepare_student_course_context(user, db)
        updated += 1

    moved_user_ids = [u.id for u in users if (u.role or "").strip() == UserRole.STUDENT.value and u.class_id]
    if moved_user_ids:
        sync_student_roster_from_user_accounts(db, moved_user_ids)

    db.commit()

    return UserBatchSetClassResponse(updated=updated, errors=errors)


@router.post("/student-roster/from-users", response_model=StudentRosterUpsertFromUsersResponse)
def upsert_student_roster_from_student_users(
    payload: StudentRosterUpsertFromUsersRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    For admin: ensure selected student accounts have canonical Student rows and
    explicit users.student_id bindings. Username is used only as the initial
    student_no for user-first accounts that do not yet have a Student row.
    """
    if not is_admin(current_user):
        raise HTTPException(status_code=403, detail="只有管理员可以同步学生花名册")

    user_ids = list(dict.fromkeys(payload.user_ids))
    if not user_ids:
        return StudentRosterUpsertFromUsersResponse(
            total=0, created=0, updated=0, skipped=0, errors=[]
        )

    result = sync_student_roster_from_user_accounts(db, user_ids)
    db.commit()
    return result


@router.post("", response_model=UserResponse)
def create_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not is_admin(current_user):
        raise HTTPException(status_code=403, detail="只有管理员可以创建用户")

    existing = db.query(User).filter(User.username == user_data.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")

    managed_class_id = normalize_managed_class_id(user_data.role, user_data.class_id)
    linked_student = None
    if user_data.student_id is not None:
        linked_student = db.query(Student).filter(Student.id == user_data.student_id).first()
        if not linked_student:
            raise HTTPException(status_code=400, detail="绑定的学生不存在")
        if user_data.role != UserRole.STUDENT.value:
            raise HTTPException(status_code=400, detail="只有学生账号可以绑定学生档案")
        existing_binding = db.query(User).filter(User.student_id == linked_student.id).first()
        if existing_binding:
            raise HTTPException(status_code=400, detail="该学生档案已绑定账号")
        linked_student.class_id = ensure_student_class_id(db, linked_student.class_id)
        managed_class_id = linked_student.class_id
    elif user_data.role == UserRole.STUDENT.value:
        managed_class_id = ensure_student_class_id(db, managed_class_id)
    validate_role_class_contract(user_data.role, managed_class_id)
    validate_class_exists(managed_class_id, db)

    user = User(
        username=user_data.username,
        hashed_password=get_password_hash(user_data.password),
        real_name=user_data.real_name,
        role=user_data.role,
        class_id=managed_class_id,
        student_id=linked_student.id if linked_student else None,
    )
    db.add(user)
    db.flush()
    if user.role == UserRole.STUDENT.value:
        sync_student_account_or_raise(db, user)
    db.commit()
    db.refresh(user)

    LogService.log_create(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        target_type="用户",
        target_id=user.id,
        target_name=f"{user.real_name}({user.username})",
    )

    return user


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not is_admin(current_user) and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="无权查看该用户")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    return user


@router.post("/{user_id}/reset-password", response_model=MessageResponse)
def admin_reset_user_password(
    user_id: int,
    payload: AdminResetUserPasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not is_admin(current_user):
        raise HTTPException(status_code=403, detail="只有管理员可以重置用户密码")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    role = (user.role or "").strip()
    explicit = (payload.new_password or "").strip() if payload.new_password else ""

    if role == UserRole.ADMIN.value:
        if not explicit:
            raise HTTPException(status_code=400, detail="重置其他管理员密码时必须填写新密码")
        new_plain = explicit
    elif role == UserRole.STUDENT.value:
        new_plain = explicit or (user.username or "").strip()
        if not new_plain:
            raise HTTPException(status_code=400, detail="学生用户名缺失，无法使用默认密码规则")
    else:
        new_plain = explicit or "111111"

    user.hashed_password = get_password_hash(new_plain)
    user.token_version = int(getattr(user, "token_version", 0) or 0) + 1
    db.add(user)
    db.commit()

    LogService.log_update(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        target_type="用户",
        target_id=user.id,
        target_name=f"{user.real_name}({user.username})",
        changes="密码已由管理员重置",
    )
    return {"message": "密码已重置"}


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not is_admin(current_user) and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="无权修改该用户")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    requested_role_change = "role" in user_data.model_fields_set
    requested_class_change = "class_id" in user_data.model_fields_set
    requested_student_binding_change = "student_id" in user_data.model_fields_set

    if not is_admin(current_user) and (requested_role_change or requested_class_change or requested_student_binding_change):
        raise HTTPException(status_code=403, detail="无权修改权限或班级")

    next_role = user_data.role if requested_role_change else user.role
    next_class_id = (
        normalize_managed_class_id(next_role, user_data.class_id)
        if requested_class_change or next_role == UserRole.TEACHER.value
        else user.class_id
    )
    linked_student = None
    if requested_student_binding_change:
        if user_data.student_id is not None:
            linked_student = db.query(Student).filter(Student.id == user_data.student_id).first()
            if not linked_student:
                raise HTTPException(status_code=400, detail="绑定的学生不存在")
            if next_role != UserRole.STUDENT.value:
                raise HTTPException(status_code=400, detail="只有学生账号可以绑定学生档案")
            existing_binding = (
                db.query(User)
                .filter(User.student_id == linked_student.id, User.id != user.id)
                .first()
            )
            if existing_binding:
                raise HTTPException(status_code=400, detail="该学生档案已绑定账号")
            linked_student.class_id = ensure_student_class_id(db, linked_student.class_id)
            next_class_id = linked_student.class_id
        else:
            linked_student = None
    elif next_role == UserRole.STUDENT.value:
        next_class_id = ensure_student_class_id(db, next_class_id)
    validate_role_class_contract(next_role, next_class_id)
    validate_class_exists(next_class_id, db)

    changes = []
    if user_data.username is not None:
        existing = (
            db.query(User)
            .filter(User.username == user_data.username, User.id != user_id)
            .first()
        )
        if existing:
            raise HTTPException(status_code=400, detail="用户名已存在")
        changes.append(f"用户名: {user.username} -> {user_data.username}")
        user.username = user_data.username

    if user_data.real_name is not None:
        changes.append(f"姓名: {user.real_name} -> {user_data.real_name}")
        user.real_name = user_data.real_name

    if requested_role_change and is_admin(current_user) and user.role != next_role:
        changes.append(f"角色: {user.role} -> {next_role}")
        user.role = next_role
        if next_role != UserRole.STUDENT.value and user.student_id is not None:
            changes.append(f"学生档案ID: {user.student_id} -> None")
            user.student_id = None

    if requested_student_binding_change and is_admin(current_user):
        old_student_id = user.student_id
        user.student_id = linked_student.id if linked_student else None
        changes.append(f"学生档案ID: {old_student_id} -> {user.student_id}")
        if linked_student:
            next_class_id = linked_student.class_id

    if is_admin(current_user) and user.class_id != next_class_id:
        changes.append(f"班级ID: {user.class_id} -> {next_class_id}")
        if user.role == UserRole.STUDENT.value:
            if user.student_id is None:
                sync_student_account_or_raise(db, user)
                db.flush()
            roster = get_bound_student_for_user(user, db)
            if roster:
                db.query(CourseEnrollment).filter(CourseEnrollment.student_id == roster.id).delete(
                    synchronize_session=False
                )
                roster.class_id = next_class_id
                db.flush()
                sync_student_course_enrollments(roster, db)
                db.flush()
        user.class_id = next_class_id

    if user_data.is_active is not None and is_admin(current_user):
        changes.append(f"状态: {user.is_active} -> {user_data.is_active}")
        user.is_active = user_data.is_active

    if user.role == UserRole.STUDENT.value and user.username:
        sync_student_account_or_raise(db, user)

    db.commit()
    db.refresh(user)

    if changes:
        LogService.log_update(
            db=db,
            user_id=current_user.id,
            username=current_user.username,
            target_type="用户",
            target_id=user.id,
            target_name=f"{user.real_name}({user.username})",
            changes=", ".join(changes),
        )

    return user


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not is_admin(current_user):
        raise HTTPException(status_code=403, detail="只有管理员可以删除用户")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="不能删除自己的账号")

    if user.role == UserRole.ADMIN.value:
        raise HTTPException(status_code=400, detail="管理员账号不能删除")

    user_info = f"{user.real_name}({user.username})"

    db.query(Student).filter(Student.teacher_id == user.id).update(
        {Student.teacher_id: None},
        synchronize_session=False,
    )
    db.query(Subject).filter(Subject.teacher_id == user.id).update(
        {Subject.teacher_id: None},
        synchronize_session=False,
    )
    db.query(PointRecord).filter(PointRecord.operator_id == user.id).update(
        {PointRecord.operator_id: None},
        synchronize_session=False,
    )
    db.query(PointExchange).filter(PointExchange.operator_id == user.id).update(
        {PointExchange.operator_id: None},
        synchronize_session=False,
    )
    db.query(OperationLog).filter(OperationLog.user_id == user.id).update(
        {OperationLog.user_id: None},
        synchronize_session=False,
    )

    db.query(NotificationRead).filter(NotificationRead.user_id == user.id).delete(synchronize_session=False)
    delete_user_homeworks(user.id, db)
    delete_user_notifications(user.id, db)
    delete_user_materials(user.id, db)

    db.delete(user)
    db.commit()

    LogService.log_delete(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        target_type="用户",
        target_id=user_id,
        target_name=user_info,
    )

    return {"message": "用户删除成功"}
