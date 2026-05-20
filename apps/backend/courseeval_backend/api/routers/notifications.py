from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, desc, false, func, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import ObjectDeletedError

from apps.backend.courseeval_backend.attachments import delete_attachment_file_if_unreferenced
from apps.backend.courseeval_backend.domains.appeal_notifications import resolve_notification_appeal_status
from apps.backend.courseeval_backend.core.auth import get_current_active_user
from apps.backend.courseeval_backend.domains.courses.access import (
    ensure_course_access_http,
    get_student_profile_for_user,
    is_course_instructor,
    prepare_student_course_context,
    subject_linked_class_ids,
)
from apps.backend.courseeval_backend.domains.text_content_format import normalize_content_format
from apps.backend.courseeval_backend.db.database import get_db
from apps.backend.courseeval_backend.db.models import (
    Class,
    CourseEnrollment,
    Notification,
    NotificationRead,
    Student,
    User,
    UserRole,
)
from apps.backend.courseeval_backend.domains.courses.class_scope import get_accessible_class_ids
from apps.backend.courseeval_backend.api.schemas import (
    NotificationCreate,
    NotificationListResponse,
    NotificationResponse,
    NotificationSyncStatus,
    NotificationUpdate,
)


router = APIRouter(prefix="/api/notifications", tags=["通知管理"])


def is_admin(user: User) -> bool:
    return user.role == UserRole.ADMIN


def is_admin_or_teacher(user: User) -> bool:
    return user.role in [UserRole.ADMIN, UserRole.CLASS_TEACHER, UserRole.TEACHER]


def _ensure_notification_course_publish_access(user: User, course) -> None:
    if not is_course_instructor(user, course):
        raise HTTPException(status_code=403, detail="Only the assigned course teacher can publish course notifications.")


def _notification_subject_allows_class(db: Session, course, class_id: int) -> bool:
    linked = set(subject_linked_class_ids(db, course.id))
    if linked:
        return int(class_id) in linked
    if course.class_id:
        return int(course.class_id) == int(class_id)
    return True


def _ensure_notification_write_scope(user: User, subject_id: Optional[int], class_id: Optional[int]) -> None:
    if is_admin(user):
        return
    if subject_id is None and (class_id is None or class_id == 0):
        raise HTTPException(status_code=403, detail="Only administrators can publish global notifications.")


def _ensure_notification_target_scope(
    db: Session,
    user: User,
    subject_id: Optional[int],
    class_id: Optional[int],
    target_student_id: Optional[int],
    target_user_id: Optional[int],
) -> None:
    if target_student_id is not None and target_user_id is not None:
        raise HTTPException(status_code=400, detail="A notification cannot target both a student and a user.")

    if target_user_id is not None:
        target_user = db.query(User).filter(User.id == target_user_id).first()
        if not target_user:
            raise HTTPException(status_code=404, detail="Target user not found.")
        if not is_admin(user) and int(target_user_id) != int(user.id):
            raise HTTPException(status_code=403, detail="You can only target notifications to yourself.")

    if target_student_id is None:
        return

    target_student = db.query(Student).filter(Student.id == target_student_id).first()
    if not target_student:
        raise HTTPException(status_code=404, detail="Target student not found.")

    if class_id is not None and int(target_student.class_id) != int(class_id):
        raise HTTPException(status_code=400, detail="Target student must belong to the notification class.")

    if subject_id is not None:
        enrolled = (
            db.query(CourseEnrollment.id)
            .filter(
                CourseEnrollment.subject_id == subject_id,
                CourseEnrollment.student_id == target_student_id,
            )
            .first()
        )
        if not enrolled:
            raise HTTPException(status_code=400, detail="Target student must be enrolled in the notification course.")


def _course_class_ids_for_course_wide_notification_view(current_user: User, db: Session, course) -> list[int]:
    """Class ids visible for course-scoped notification rows in the current role.

    Admins and assigned course teachers see the whole course, including every
    linked administrative class. Students and non-instructor class teachers see
    only their own class even when the course spans multiple classes.
    """
    if is_admin(current_user) or is_course_instructor(current_user, course):
        ids = subject_linked_class_ids(db, course.id)
        if course.class_id:
            ids.append(int(course.class_id))
        return sorted(set(ids))

    if current_user.role == UserRole.STUDENT:
        prepare_student_course_context(current_user, db)
        student = get_student_profile_for_user(current_user, db)
        if student and student.class_id:
            return [int(student.class_id)]
        if current_user.class_id:
            return [int(current_user.class_id)]
        return []

    if current_user.role == UserRole.CLASS_TEACHER and current_user.class_id:
        return [int(current_user.class_id)]

    return []


def _notification_class_ids_for_unscoped_view(current_user: User, db: Session) -> list[int]:
    if current_user.role == UserRole.STUDENT:
        prepare_student_course_context(current_user, db)
        student = get_student_profile_for_user(current_user, db)
        if student and student.class_id:
            return [int(student.class_id)]
        if current_user.class_id:
            return [int(current_user.class_id)]
        return []
    if current_user.role == UserRole.CLASS_TEACHER:
        return [int(current_user.class_id)] if current_user.class_id else []
    return get_accessible_class_ids(current_user, db)


def _visible_notifications_query(current_user: User, db: Session, subject_id: Optional[int] = None):
    query = db.query(Notification)

    if subject_id:
        course = ensure_course_access_http(subject_id, current_user, db)
        course_class_ids = _course_class_ids_for_course_wide_notification_view(current_user, db, course)
        course_class_scope = Notification.class_id.is_(None)
        if course_class_ids:
            course_class_scope = or_(course_class_scope, Notification.class_id.in_(course_class_ids))
        query = query.filter(
            or_(
                and_(Notification.subject_id == course.id, course_class_scope),
                and_(Notification.subject_id.is_(None), course_class_scope),
            )
        )

    if current_user.role == UserRole.STUDENT:
        prepare_student_course_context(current_user, db)
        student = get_student_profile_for_user(current_user, db)
        if not student:
            return query.filter(false())
        enrolled_subject_ids = [
            int(row[0])
            for row in db.query(CourseEnrollment.subject_id)
            .filter(CourseEnrollment.student_id == student.id)
            .all()
        ]
        query = query.filter(
            Notification.target_user_id.is_(None),
            or_(Notification.target_student_id.is_(None), Notification.target_student_id == student.id),
        )
        if enrolled_subject_ids:
            query = query.filter(or_(Notification.subject_id.is_(None), Notification.subject_id.in_(enrolled_subject_ids)))
        else:
            query = query.filter(Notification.subject_id.is_(None))

    if current_user.role != UserRole.ADMIN:
        query = query.filter(
            or_(
                Notification.notification_kind.is_(None),
                Notification.notification_kind != "password_reset_request",
            )
        )

    if current_user.role in (UserRole.TEACHER, UserRole.CLASS_TEACHER):
        query = query.filter(
            or_(Notification.target_user_id.is_(None), Notification.target_user_id == current_user.id)
        )

    if current_user.role != UserRole.ADMIN and subject_id is None:
        class_ids = _notification_class_ids_for_unscoped_view(current_user, db)
        if class_ids:
            query = query.filter(or_(Notification.class_id.is_(None), Notification.class_id.in_(class_ids)))
        else:
            query = query.filter(Notification.class_id.is_(None))
    return query


def _build_notification_response(notification: Notification, current_user: User, db: Session) -> NotificationResponse:
    read_record = db.query(NotificationRead).filter(
        NotificationRead.notification_id == notification.id,
        NotificationRead.user_id == current_user.id,
    ).first()
    return NotificationResponse(
        id=notification.id,
        title=notification.title,
        content=notification.content,
        content_format=normalize_content_format(getattr(notification, "content_format", None)),
        attachment_name=notification.attachment_name,
        attachment_url=notification.attachment_url,
        priority=notification.priority,
        is_pinned=notification.is_pinned,
        class_id=notification.class_id,
        subject_id=notification.subject_id,
        target_student_id=notification.target_student_id,
        related_homework_id=notification.related_homework_id,
        related_student_id=notification.related_student_id,
        related_appeal_id=notification.related_appeal_id,
        related_score_appeal_id=notification.related_score_appeal_id,
        appeal_status=resolve_notification_appeal_status(notification, db),
        target_user_id=notification.target_user_id,
        notification_kind=notification.notification_kind or "general",
        created_by=notification.created_by,
        created_at=notification.created_at,
        updated_at=notification.updated_at,
        creator_name=notification.creator.real_name if notification.creator else None,
        class_name=notification.class_obj.name if notification.class_obj else None,
        subject_name=notification.subject.name if notification.subject else None,
        is_read=read_record.is_read if read_record else False,
    )


@router.get("", response_model=NotificationListResponse)
def get_notifications(
    subject_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    query = _visible_notifications_query(current_user, db, subject_id)

    query = query.order_by(desc(Notification.is_pinned), desc(Notification.created_at))
    total = query.count()
    notifications = query.offset((page - 1) * page_size).limit(page_size).all()

    visible_notifications = _visible_notifications_query(current_user, db, subject_id).all()
    unread_count = 0
    for notification in visible_notifications:
        read_record = db.query(NotificationRead).filter(
            NotificationRead.notification_id == notification.id,
            NotificationRead.user_id == current_user.id,
        ).first()
        if not read_record or not read_record.is_read:
            unread_count += 1

    out = []
    for notification in notifications:
        try:
            out.append(_build_notification_response(notification, current_user, db))
        except ObjectDeletedError:
            # Concurrent DELETE can expire ORM rows between OFFSET/LIMIT fetch and serialization (SQLite E2E stress).
            continue

    return NotificationListResponse(
        total=total,
        unread_count=unread_count,
        data=out,
    )


def _sync_status_for_user(current_user: User, db: Session, subject_id: Optional[int] = None) -> NotificationSyncStatus:
    query = _visible_notifications_query(current_user, db, subject_id)
    total = query.count()
    latest_updated_at = query.with_entities(func.max(Notification.updated_at)).scalar()

    visible_notifications = _visible_notifications_query(current_user, db, subject_id).all()
    unread_count = 0
    for notification in visible_notifications:
        read_record = db.query(NotificationRead).filter(
            NotificationRead.notification_id == notification.id,
            NotificationRead.user_id == current_user.id,
        ).first()
        if not read_record or not read_record.is_read:
            unread_count += 1

    return NotificationSyncStatus(
        total=total,
        unread_count=unread_count,
        latest_updated_at=latest_updated_at,
    )


@router.get("/sync-status", response_model=NotificationSyncStatus)
def get_notifications_sync_status(
    subject_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Poll-friendly snapshot; same visibility rules as the list endpoint."""
    return _sync_status_for_user(current_user, db, subject_id)


@router.get("/{notification_id}", response_model=NotificationResponse)
def get_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found.")

    if (notification.notification_kind or "") == "password_reset_request" and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="You do not have access to this notification.")

    if notification.subject_id:
        course = ensure_course_access_http(notification.subject_id, current_user, db)
        if current_user.role != UserRole.ADMIN and notification.class_id is not None:
            class_ids = _course_class_ids_for_course_wide_notification_view(current_user, db, course)
            if int(notification.class_id) not in class_ids:
                raise HTTPException(status_code=403, detail="You do not have access to this notification.")
    else:
        class_ids = _notification_class_ids_for_unscoped_view(current_user, db)
        if current_user.role != UserRole.ADMIN and notification.class_id and notification.class_id not in class_ids:
            raise HTTPException(status_code=403, detail="You do not have access to this notification.")

    if current_user.role == UserRole.STUDENT:
        prepare_student_course_context(current_user, db)
        student = get_student_profile_for_user(current_user, db)
        if notification.target_student_id and (
            not student or int(notification.target_student_id) != int(student.id)
        ):
            raise HTTPException(status_code=403, detail="You do not have access to this notification.")
        if notification.target_user_id is not None:
            raise HTTPException(status_code=403, detail="You do not have access to this notification.")

    if current_user.role in (UserRole.TEACHER, UserRole.CLASS_TEACHER):
        if notification.target_user_id is not None and int(notification.target_user_id) != int(current_user.id):
            raise HTTPException(status_code=403, detail="You do not have access to this notification.")

    return _build_notification_response(notification, current_user, db)


@router.post("", response_model=NotificationResponse)
def create_notification(
    data: NotificationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not is_admin_or_teacher(current_user):
        raise HTTPException(status_code=403, detail="Only teachers can publish notifications.")

    effective_class_id = None if data.class_id == 0 else data.class_id

    if effective_class_id:
        class_obj = db.query(Class).filter(Class.id == effective_class_id).first()
        if not class_obj:
            raise HTTPException(status_code=404, detail="Class not found.")

    _ensure_notification_write_scope(current_user, data.subject_id, effective_class_id)
    _ensure_notification_target_scope(
        db,
        current_user,
        data.subject_id,
        effective_class_id,
        data.target_student_id,
        data.target_user_id,
    )

    if data.subject_id:
        course = ensure_course_access_http(data.subject_id, current_user, db)
        _ensure_notification_course_publish_access(current_user, course)
        if effective_class_id and not _notification_subject_allows_class(db, course, effective_class_id):
            raise HTTPException(status_code=400, detail="The selected course does not belong to this class.")
    elif effective_class_id:
        class_ids = get_accessible_class_ids(current_user, db)
        if not is_admin(current_user) and effective_class_id not in class_ids:
            raise HTTPException(status_code=403, detail="You can only publish notifications for accessible classes.")

    kind = (data.notification_kind or "general").strip()
    if kind == "password_reset_request":
        raise HTTPException(status_code=403, detail="This notification kind is reserved for the system.")

    notification = Notification(
        title=data.title,
        content=data.content,
        content_format=normalize_content_format(getattr(data, "content_format", None)),
        attachment_name=data.attachment_name,
        attachment_url=data.attachment_url,
        priority=data.priority,
        is_pinned=data.is_pinned,
        class_id=effective_class_id,
        subject_id=data.subject_id,
        target_student_id=data.target_student_id,
        related_homework_id=data.related_homework_id,
        related_student_id=data.related_student_id,
        related_appeal_id=data.related_appeal_id,
        related_score_appeal_id=data.related_score_appeal_id,
        target_user_id=data.target_user_id,
        notification_kind=data.notification_kind or "general",
        created_by=current_user.id,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return _build_notification_response(notification, current_user, db)


@router.put("/{notification_id}", response_model=NotificationResponse)
def update_notification(
    notification_id: int,
    data: NotificationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not is_admin_or_teacher(current_user):
        raise HTTPException(status_code=403, detail="Only teachers can update notifications.")

    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found.")

    if (notification.notification_kind or "") == "password_reset_request" and not is_admin(current_user):
        raise HTTPException(status_code=403, detail="You do not have access to this notification.")

    if not is_admin(current_user) and notification.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="You can only edit your own notifications.")

    requested_fields = data.model_fields_set

    if "class_id" in requested_fields and data.class_id is not None and data.class_id != 0:
        class_obj = db.query(Class).filter(Class.id == data.class_id).first()
        if not class_obj:
            raise HTTPException(status_code=404, detail="Class not found.")

    effective_subject_id = data.subject_id if "subject_id" in requested_fields else notification.subject_id
    effective_class_id = notification.class_id
    if "class_id" in requested_fields:
        effective_class_id = None if data.class_id in (None, 0) else data.class_id
    _ensure_notification_write_scope(current_user, effective_subject_id, effective_class_id)
    effective_target_student_id = (
        data.target_student_id if "target_student_id" in requested_fields else notification.target_student_id
    )
    effective_target_user_id = (
        data.target_user_id if "target_user_id" in requested_fields else notification.target_user_id
    )
    _ensure_notification_target_scope(
        db,
        current_user,
        effective_subject_id,
        effective_class_id,
        effective_target_student_id,
        effective_target_user_id,
    )

    if effective_subject_id is not None:
        course = ensure_course_access_http(effective_subject_id, current_user, db)
        _ensure_notification_course_publish_access(current_user, course)
        target_class_id = effective_class_id
        if target_class_id and not _notification_subject_allows_class(db, course, target_class_id):
            raise HTTPException(status_code=400, detail="The selected course does not belong to this class.")
    elif "class_id" in requested_fields and data.class_id is not None and data.class_id != 0:
        class_ids = get_accessible_class_ids(current_user, db)
        if not is_admin(current_user) and data.class_id not in class_ids:
            raise HTTPException(status_code=403, detail="You can only publish notifications for accessible classes.")

    if data.title is not None:
        notification.title = data.title
    if data.content is not None:
        notification.content = data.content
    if data.content_format is not None:
        notification.content_format = normalize_content_format(data.content_format)
    if data.remove_attachment:
        notification.attachment_name = None
        notification.attachment_url = None
    elif data.attachment_url is not None:
        old_attachment_url = notification.attachment_url
        notification.attachment_name = data.attachment_name
        notification.attachment_url = data.attachment_url
        if old_attachment_url and old_attachment_url != notification.attachment_url:
            delete_attachment_file_if_unreferenced(db, old_attachment_url)
    if data.priority is not None:
        notification.priority = data.priority
    if data.is_pinned is not None:
        notification.is_pinned = data.is_pinned
    if "class_id" in requested_fields:
        notification.class_id = None if data.class_id in (None, 0) else data.class_id
    if "subject_id" in requested_fields:
        notification.subject_id = data.subject_id
    if "target_student_id" in requested_fields:
        notification.target_student_id = data.target_student_id
    if "target_user_id" in requested_fields:
        notification.target_user_id = data.target_user_id
    if "related_appeal_id" in requested_fields:
        notification.related_appeal_id = data.related_appeal_id
    if "related_score_appeal_id" in requested_fields:
        notification.related_score_appeal_id = data.related_score_appeal_id
    if data.notification_kind is not None:
        nk = (data.notification_kind or "").strip()
        if nk == "password_reset_request":
            raise HTTPException(status_code=403, detail="This notification kind is reserved for the system.")
        notification.notification_kind = nk or "general"

    notification.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(notification)
    return _build_notification_response(notification, current_user, db)


@router.delete("/{notification_id}")
def delete_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not is_admin_or_teacher(current_user):
        raise HTTPException(status_code=403, detail="Only teachers can delete notifications.")

    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found.")

    if (notification.notification_kind or "") == "password_reset_request" and not is_admin(current_user):
        raise HTTPException(status_code=403, detail="You do not have access to this notification.")

    if not is_admin(current_user) and notification.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="You can only delete your own notifications.")

    attachment_url = notification.attachment_url
    db.query(NotificationRead).filter(NotificationRead.notification_id == notification_id).delete()
    db.delete(notification)
    db.commit()
    delete_attachment_file_if_unreferenced(db, attachment_url)
    return {"message": "Notification deleted successfully."}


@router.post("/{notification_id}/read")
def mark_as_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    exists = db.query(Notification.id).filter(Notification.id == notification_id).first()
    if not exists:
        raise HTTPException(status_code=404, detail="Notification not found.")

    notification = _visible_notifications_query(current_user, db).filter(Notification.id == notification_id).first()
    if not notification:
        raise HTTPException(status_code=403, detail="You do not have access to this notification.")

    read_record = db.query(NotificationRead).filter(
        NotificationRead.notification_id == notification_id,
        NotificationRead.user_id == current_user.id,
    ).first()

    if not read_record:
        read_record = NotificationRead(
            notification_id=notification_id,
            user_id=current_user.id,
            is_read=True,
            read_at=datetime.now(timezone.utc),
        )
        db.add(read_record)
    else:
        read_record.is_read = True
        read_record.read_at = datetime.now(timezone.utc)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(NotificationRead).filter(
            NotificationRead.notification_id == notification_id,
            NotificationRead.user_id == current_user.id,
        ).first()
        if existing:
            existing.is_read = True
            existing.read_at = datetime.now(timezone.utc)
            db.commit()
        else:
            raise
    return {"message": "Notification marked as read."}


def _bulk_upsert_notification_reads_mark_read(
    db: Session, notification_ids: list[int], user_id: int, read_at: datetime
) -> None:
    """Idempotently mark many notifications read for one user (concurrency-safe).

    Uses INSERT .. ON CONFLICT DO UPDATE on the composite unique key
    ``(notification_id, user_id)`` so parallel mark-all-read / mark-read calls
    cannot fail with IntegrityError on the unique index.
    """
    if not notification_ids:
        return
    values = [
        {
            "notification_id": nid,
            "user_id": user_id,
            "is_read": True,
            "read_at": read_at,
        }
        for nid in notification_ids
    ]
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        ins = pg_insert(NotificationRead).values(values)
        ins = ins.on_conflict_do_update(
            index_elements=[NotificationRead.notification_id, NotificationRead.user_id],
            set_={
                "is_read": ins.excluded.is_read,
                "read_at": ins.excluded.read_at,
            },
        )
        db.execute(ins)
        return
    if dialect == "sqlite":
        ins = sqlite_insert(NotificationRead).values(values)
        ins = ins.on_conflict_do_update(
            index_elements=[NotificationRead.notification_id, NotificationRead.user_id],
            set_={
                "is_read": ins.excluded.is_read,
                "read_at": ins.excluded.read_at,
            },
        )
        db.execute(ins)
        return
    # Other dialects: best-effort row-by-row (tests use SQLite/PostgreSQL only).
    for nid in notification_ids:
        record = (
            db.query(NotificationRead)
            .filter(
                NotificationRead.notification_id == nid,
                NotificationRead.user_id == user_id,
            )
            .first()
        )
        if not record:
            db.add(
                NotificationRead(
                    notification_id=nid,
                    user_id=user_id,
                    is_read=True,
                    read_at=read_at,
                )
            )
        else:
            record.is_read = True
            record.read_at = read_at


@router.post("/mark-all-read")
def mark_all_as_read(
    subject_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    notifications = _visible_notifications_query(current_user, db, subject_id).all()
    if not notifications:
        return {"message": "Marked 0 notifications as read."}

    ids = [int(n.id) for n in notifications]
    read_at = datetime.now(timezone.utc)

    updated = (
        db.query(func.count(Notification.id))
        .outerjoin(
            NotificationRead,
            and_(
                NotificationRead.notification_id == Notification.id,
                NotificationRead.user_id == current_user.id,
            ),
        )
        .filter(Notification.id.in_(ids))
        .filter(or_(NotificationRead.id.is_(None), NotificationRead.is_read.is_(False)))
        .scalar()
    )
    updated = int(updated or 0)

    _bulk_upsert_notification_reads_mark_read(db, ids, int(current_user.id), read_at)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        _bulk_upsert_notification_reads_mark_read(db, ids, int(current_user.id), read_at)
        db.commit()
    return {"message": f"Marked {updated} notifications as read."}
