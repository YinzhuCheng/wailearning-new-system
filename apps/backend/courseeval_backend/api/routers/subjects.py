from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.core.auth import get_current_active_user
from apps.backend.courseeval_backend.domains.courses.access import (
    ensure_course_access_http,
    get_accessible_courses_query,
    get_enrolled_students,
    get_student_course_catalog_query,
    get_student_elective_catalog_query,
    get_student_profile_for_user,
    is_course_instructor,
    prepare_student_course_context,
    remove_course_enrollment,
    refresh_subject_primary_class_id,
    subject_linked_class_ids,
    sync_course_enrollments,
)
from apps.backend.courseeval_backend.attachments import delete_attachment_file_if_unreferenced
from apps.backend.courseeval_backend.db.database import get_db
from apps.backend.courseeval_backend.db.models import (
    Attendance,
    Class,
    CourseDiscussionEntry,
    CourseEnrollment,
    CourseEnrollmentBlock,
    CourseExamWeight,
    CourseGradeScheme,
    CourseLLMConfig,
    CourseMaterial,
    CourseMaterialChapter,
    CourseMaterialHomeworkLink,
    CourseMaterialSection,
    DiscussionLLMJob,
    Homework,
    HomeworkGradeAppeal,
    Notification,
    NotificationRead,
    Score,
    ScoreGradeAppeal,
    Student,
    Subject,
    SubjectClassLink,
    User,
    UserRole,
)
from apps.backend.courseeval_backend.domains.homework.cleanup import purge_homework_row
from apps.backend.courseeval_backend.domains.courses.metadata import (
    resolve_course_times,
    resolve_semester,
    serialize_course,
    serialize_course_times_for_storage,
    serialize_student_course_catalog_item,
)
from apps.backend.courseeval_backend.domains.courses.class_links import (
    can_create_course,
    normalize_course_class_name,
    replace_subject_class_links,
    required_course_duplicate,
)
from apps.backend.courseeval_backend.domains.courses.enrollment import (
    create_roster_students,
    enroll_roster_students_for_course,
    serialize_enrollment,
)
from apps.backend.courseeval_backend.api.schemas import (
    AttachmentUploadResponse,
    CourseEnrollmentResponse,
    CourseEnrollmentTypeUpdate,
    StudentCourseCatalogItem,
    StudentElectiveSelfDropResult,
    StudentElectiveSelfEnrollResult,
    SubjectCreate,
    SubjectResponse,
    SubjectUpdate,
    SubjectRosterEnrollRequest,
    SubjectRosterEnrollResult,
)


router = APIRouter(prefix="/api/subjects", tags=["课程管理"])


def _ensure_course_management_access(user: User, course: Subject) -> None:
    if not is_course_instructor(user, course):
        raise HTTPException(status_code=403, detail="Only the assigned course teacher can manage this course.")


@router.get("", response_model=List[SubjectResponse])
def get_subjects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    courses = (
        get_accessible_courses_query(current_user, db)
        .order_by(Subject.status.asc(), Subject.created_at.desc())
        .all()
    )
    counts: dict[int, int] = {}
    if courses:
        ids = [c.id for c in courses]
        rows = (
            db.query(CourseEnrollment.subject_id, func.count(CourseEnrollment.id))
            .filter(CourseEnrollment.subject_id.in_(ids))
            .group_by(CourseEnrollment.subject_id)
            .all()
        )
        counts = {int(sid): int(cnt or 0) for sid, cnt in rows}
    return [serialize_course(course, db, student_count=counts.get(course.id, 0)) for course in courses]


@router.get("/course-catalog", response_model=List[StudentCourseCatalogItem])
def list_student_course_catalog(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Active courses for students: 必修/选修 labels; electives are school-wide self-enroll (not class-bound)."""
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Only students can browse the course catalog.")

    prepare_student_course_context(current_user, db)
    db.commit()
    student = get_student_profile_for_user(current_user, db)
    if not student:
        raise HTTPException(status_code=400, detail="未找到与账号匹配的花名册，无法浏览选课目录。")

    enrolled_ids = {
        row[0]
        for row in db.query(CourseEnrollment.subject_id)
        .filter(CourseEnrollment.student_id == student.id)
        .all()
    }
    courses = get_student_course_catalog_query(current_user, db).order_by(Subject.created_at.desc()).all()
    return [serialize_student_course_catalog_item(c, db, student=student, enrolled_subject_ids=enrolled_ids) for c in courses]


@router.get("/elective-catalog", response_model=List[SubjectResponse])
def list_elective_catalog_for_student(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Active elective courses available for voluntary student self-enrollment."""
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Only students can browse the elective catalog.")

    courses = (
        get_student_elective_catalog_query(current_user, db)
        .order_by(Subject.created_at.desc())
        .all()
    )
    counts: dict[int, int] = {}
    if courses:
        ids = [c.id for c in courses]
        rows = (
            db.query(CourseEnrollment.subject_id, func.count(CourseEnrollment.id))
            .filter(CourseEnrollment.subject_id.in_(ids))
            .group_by(CourseEnrollment.subject_id)
            .all()
        )
        counts = {int(sid): int(cnt or 0) for sid, cnt in rows}
    return [serialize_course(course, db, student_count=counts.get(course.id, 0)) for course in courses]


@router.post("/{subject_id}/student-self-enroll", response_model=StudentElectiveSelfEnrollResult)
def student_self_enroll_elective(
    subject_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Only students can self-enroll.")

    prepare_student_course_context(current_user, db)
    db.commit()
    student = get_student_profile_for_user(current_user, db)
    if not student:
        raise HTTPException(status_code=400, detail="未找到与账号匹配的花名册，无法选课。")
    if not student.class_id:
        raise HTTPException(status_code=400, detail="账号未绑定行政班，无法选课（选课记录需归档班级）。")

    course = db.query(Subject).filter(Subject.id == subject_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")
    if (course.status or "").strip() != "active":
        raise HTTPException(status_code=400, detail="课程未开放选课。")
    if (course.course_type or "").strip() != "elective":
        raise HTTPException(status_code=400, detail="仅选修课支持学生自主选课。")

    existing = (
        db.query(CourseEnrollment)
        .filter(CourseEnrollment.subject_id == course.id, CourseEnrollment.student_id == student.id)
        .first()
    )
    if existing:
        return StudentElectiveSelfEnrollResult(subject_id=course.id, created=False, already_enrolled=True)

    try:
        db.query(CourseEnrollmentBlock).filter(
            CourseEnrollmentBlock.subject_id == course.id,
            CourseEnrollmentBlock.student_id == student.id,
        ).delete(synchronize_session=False)
        db.add(
            CourseEnrollment(
                subject_id=course.id,
                student_id=student.id,
                class_id=student.class_id,
                enrollment_type="elective",
                can_remove=True,
            )
        )
        db.commit()
        return StudentElectiveSelfEnrollResult(subject_id=course.id, created=True, already_enrolled=False)
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(CourseEnrollment)
            .filter(CourseEnrollment.subject_id == course.id, CourseEnrollment.student_id == student.id)
            .first()
        )
        if existing:
            return StudentElectiveSelfEnrollResult(subject_id=course.id, created=False, already_enrolled=True)
        raise


@router.post("/{subject_id}/student-self-drop", response_model=StudentElectiveSelfDropResult)
def student_self_drop_elective(
    subject_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Only students can drop electives.")

    prepare_student_course_context(current_user, db)
    db.commit()
    student = get_student_profile_for_user(current_user, db)
    if not student:
        raise HTTPException(status_code=400, detail="未找到与账号匹配的花名册。")

    enrollment = (
        db.query(CourseEnrollment)
        .filter(CourseEnrollment.subject_id == subject_id, CourseEnrollment.student_id == student.id)
        .first()
    )
    if not enrollment:
        return StudentElectiveSelfDropResult(subject_id=subject_id, removed=False)

    et = (enrollment.enrollment_type or "").strip().lower()
    if et != "elective" and not enrollment.can_remove:
        raise HTTPException(status_code=400, detail="必修课不可退选。")

    try:
        db.delete(enrollment)
        if not db.query(CourseEnrollmentBlock).filter(
            CourseEnrollmentBlock.subject_id == subject_id,
            CourseEnrollmentBlock.student_id == student.id,
        ).first():
            db.add(CourseEnrollmentBlock(subject_id=subject_id, student_id=student.id))
        db.commit()
        return StudentElectiveSelfDropResult(subject_id=subject_id, removed=True)
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(CourseEnrollment)
            .filter(CourseEnrollment.subject_id == subject_id, CourseEnrollment.student_id == student.id)
            .first()
        )
        if not existing:
            return StudentElectiveSelfDropResult(subject_id=subject_id, removed=False)
        raise


@router.get("/{subject_id}", response_model=SubjectResponse)
def get_subject(
    subject_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        course = ensure_course_access_http(subject_id, current_user, db)
    except ValueError:
        raise HTTPException(status_code=404, detail="Course not found.")
    except PermissionError:
        raise HTTPException(status_code=403, detail="You do not have access to this course.")

    return serialize_course(course, db)


@router.post("", response_model=SubjectResponse)
def create_subject(
    subject_data: SubjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not can_create_course(current_user):
        raise HTTPException(status_code=403, detail="You do not have permission to create courses.")

    target_teacher_id: Optional[int] = subject_data.teacher_id
    if current_user.role != UserRole.ADMIN:
        target_teacher_id = current_user.id

    course_type = (subject_data.course_type or "required").strip().lower()

    semester_obj = resolve_semester(
        db,
        semester_id=subject_data.semester_id,
        semester_name=subject_data.semester,
    )
    semester_label = semester_obj.name if semester_obj else None
    course_times = resolve_course_times(subject_data.course_times)

    if course_type == "elective":
        if subject_data.students:
            raise HTTPException(status_code=400, detail="选修课不支持随课程创建花名册或导入学生。")
        if subject_data.class_links:
            raise HTTPException(status_code=400, detail="选修课不需要配置行政班级关联。")
        if subject_data.class_id is not None:
            raise HTTPException(status_code=400, detail="选修课不应绑定行政班级，请将所属班级留空。")

        dupe = (
            db.query(Subject)
            .filter(
                Subject.name == subject_data.name,
                Subject.semester_id == (semester_obj.id if semester_obj else None),
                Subject.course_type == "elective",
            )
            .first()
        )
        if dupe:
            raise HTTPException(status_code=400, detail="同学期已存在同名的选修课程。")

        course = Subject(
            name=subject_data.name,
            teacher_id=target_teacher_id,
            class_id=None,
            semester_id=semester_obj.id if semester_obj else None,
            course_type="elective",
            status=subject_data.status,
            semester=semester_label,
            course_times=serialize_course_times_for_storage(course_times),
            description=subject_data.description,
        )
        db.add(course)
        db.commit()
        db.refresh(course)
        return serialize_course(course, db)

    link_plan: list[tuple[int, str]] = []
    if subject_data.class_links:
        link_plan = [(int(item.class_id), item.enrollment_mode) for item in subject_data.class_links]

    class_obj: Optional[Class] = None
    if subject_data.class_id is not None and not link_plan:
        class_obj = db.query(Class).filter(Class.id == subject_data.class_id).first()
        if not class_obj:
            raise HTTPException(status_code=400, detail="Class not found.")
        link_plan = [(class_obj.id, "all_in_class")]

    if not link_plan:
        if not subject_data.students:
            raise HTTPException(status_code=400, detail="必修课请选择班级（或多班级），或上传花名册创建班级。")
        class_obj = Class(
            name=normalize_course_class_name(
                course_name=subject_data.name,
                class_name=subject_data.class_name,
            ),
            grade=1,
        )
        db.add(class_obj)
        db.flush()
        link_plan = [(class_obj.id, "all_in_class")]

    sorted_ids = tuple(sorted({int(cid) for cid, _ in link_plan}))
    if current_user.role == UserRole.CLASS_TEACHER:
        allowed_class_id = int(current_user.class_id or 0)
        if not allowed_class_id or any(cid != allowed_class_id for cid in sorted_ids):
            raise HTTPException(status_code=403, detail="Class teachers can only create courses for their own class.")

    if required_course_duplicate(
        db,
        name=subject_data.name,
        semester_id=semester_obj.id if semester_obj else None,
        sorted_class_ids=sorted_ids,
    ):
        raise HTTPException(status_code=400, detail="同学期已存在绑定相同班级集合的同名必修课程。")

    primary_cid = link_plan[0][0]
    course = Subject(
        name=subject_data.name,
        teacher_id=target_teacher_id,
        class_id=primary_cid,
        semester_id=semester_obj.id if semester_obj else None,
        course_type="required",
        status=subject_data.status,
        semester=semester_label,
        course_times=serialize_course_times_for_storage(course_times),
        description=subject_data.description,
    )
    db.add(course)
    db.flush()

    replace_subject_class_links(db, course, link_plan)

    enrollment_overrides: list[tuple[Student, str]] = []
    if subject_data.students:
        enrollment_overrides = create_roster_students(course, subject_data.students, db, current_user)
        db.flush()

    sync_course_enrollments(course, db)
    if enrollment_overrides:
        db.flush()
        for student, enrollment_type in enrollment_overrides:
            if not student.id:
                continue
            enrollment = (
                db.query(CourseEnrollment)
                .filter(
                    CourseEnrollment.subject_id == course.id,
                    CourseEnrollment.student_id == student.id,
                )
                .first()
            )
            if enrollment:
                normalized_enrollment_type = enrollment_type.strip().lower()
                enrollment.enrollment_type = normalized_enrollment_type
                enrollment.can_remove = normalized_enrollment_type == "elective"
    db.commit()
    db.refresh(course)
    return serialize_course(course, db)


@router.put("/{subject_id}", response_model=SubjectResponse)
def update_subject(
    subject_id: int,
    subject_data: SubjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if current_user.role == UserRole.ADMIN:
        pass
    else:
        try:
            ensure_course_access_http(subject_id, current_user, db)
        except ValueError:
            raise HTTPException(status_code=404, detail="Course not found.")
        except PermissionError:
            raise HTTPException(status_code=403, detail="You do not have access to this course.")

    course = db.query(Subject).filter(Subject.id == subject_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")

    if current_user.role != UserRole.ADMIN and int(course.teacher_id or 0) != int(current_user.id or 0):
        raise HTTPException(status_code=403, detail="Only the assigned course teacher can update this course.")

    original_link_ids = set(subject_linked_class_ids(db, course.id))
    if not original_link_ids and course.class_id:
        original_link_ids = {int(course.class_id)}

    if current_user.role != UserRole.ADMIN and subject_data.teacher_id is not None and subject_data.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only assign yourself as the course teacher.")

    if current_user.role != UserRole.ADMIN:
        subject_data.teacher_id = current_user.id

    for field in ["name", "teacher_id", "status", "description"]:
        value = getattr(subject_data, field)
        if value is not None:
            setattr(course, field, value)

    if subject_data.course_type is not None:
        next_course_type = (subject_data.course_type or "required").strip().lower()
        if current_user.role == UserRole.CLASS_TEACHER and next_course_type == "elective":
            raise HTTPException(status_code=403, detail="Class teachers cannot convert courses to electives.")
        course.course_type = subject_data.course_type

    if subject_data.remove_cover_image:
        prev = course.cover_image_url
        course.cover_image_url = None
        if prev:
            delete_attachment_file_if_unreferenced(db, prev)
    elif subject_data.cover_image_url is not None:
        new_url = (subject_data.cover_image_url or "").strip() or None
        prev = course.cover_image_url
        if prev and prev != new_url:
            delete_attachment_file_if_unreferenced(db, prev)
        course.cover_image_url = new_url

    if subject_data.course_times is not None:
        course_times = resolve_course_times(subject_data.course_times)
        course.course_times = serialize_course_times_for_storage(course_times)

    if subject_data.semester_id is not None or subject_data.semester is not None:
        semester_obj = resolve_semester(
            db,
            semester_id=subject_data.semester_id,
            semester_name=subject_data.semester,
        )
        course.semester_id = semester_obj.id if semester_obj else None
        course.semester = semester_obj.name if semester_obj else None

    ct = (course.course_type or "required").strip().lower()

    if ct == "elective":
        db.query(SubjectClassLink).filter(SubjectClassLink.subject_id == course.id).delete(synchronize_session=False)
        course.class_id = None
        if subject_data.class_links is not None:
            raise HTTPException(status_code=400, detail="选修课不能配置行政班级关联。")
        if subject_data.class_id is not None:
            raise HTTPException(status_code=400, detail="选修课不能绑定行政班级。")
    else:
        if subject_data.class_links is not None:
            pairs = [(int(x.class_id), x.enrollment_mode) for x in subject_data.class_links]
            if current_user.role == UserRole.CLASS_TEACHER:
                allowed_class_id = int(current_user.class_id or 0)
                if not allowed_class_id or any(cid != allowed_class_id for cid, _ in pairs):
                    raise HTTPException(status_code=403, detail="Class teachers can only bind courses to their own class.")
            replace_subject_class_links(db, course, pairs)
        elif subject_data.class_id is not None:
            if current_user.role == UserRole.CLASS_TEACHER:
                allowed_class_id = int(current_user.class_id or 0)
                if not allowed_class_id or int(subject_data.class_id) != allowed_class_id:
                    raise HTTPException(status_code=403, detail="Class teachers can only bind courses to their own class.")
            replace_subject_class_links(db, course, [(int(subject_data.class_id), "all_in_class")])
        else:
            refresh_subject_primary_class_id(course, db)

        if not subject_linked_class_ids(db, course.id):
            raise HTTPException(status_code=400, detail="必修课至少需要绑定一个行政班级。")

        new_link_ids = set(subject_linked_class_ids(db, course.id))
        if tuple(sorted(new_link_ids)) != tuple(sorted(original_link_ids)):
            db.query(CourseEnrollment).filter(CourseEnrollment.subject_id == course.id).delete(synchronize_session=False)

    sync_course_enrollments(course, db)
    db.commit()
    db.refresh(course)
    return serialize_course(course, db)


@router.post("/{subject_id}/cover-image", response_model=AttachmentUploadResponse)
async def upload_subject_cover_image(
    subject_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if current_user.role == UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Students cannot upload course covers.")

    if current_user.role == UserRole.ADMIN:
        pass
    else:
        try:
            ensure_course_access_http(subject_id, current_user, db)
        except ValueError:
            raise HTTPException(status_code=404, detail="Course not found.")
        except PermissionError:
            raise HTTPException(status_code=403, detail="You do not have access to this course.")

    course = db.query(Subject).filter(Subject.id == subject_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")
    _ensure_course_management_access(current_user, course)

    from apps.backend.courseeval_backend.attachments import save_course_cover_image

    uploaded = await save_course_cover_image(file, request)
    prev = course.cover_image_url
    course.cover_image_url = str(uploaded["attachment_url"])
    if prev and prev != course.cover_image_url:
        delete_attachment_file_if_unreferenced(db, prev)
    db.commit()
    db.refresh(course)
    return AttachmentUploadResponse(**uploaded)


@router.delete("/{subject_id}")
def delete_subject(
    subject_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if current_user.role == UserRole.ADMIN:
        pass
    else:
        try:
            ensure_course_access_http(subject_id, current_user, db)
        except ValueError:
            raise HTTPException(status_code=404, detail="Course not found.")
        except PermissionError:
            raise HTTPException(status_code=403, detail="You do not have access to this course.")

    course = db.query(Subject).filter(Subject.id == subject_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")
    _ensure_course_management_access(current_user, course)

    cover_url = course.cover_image_url

    hw_ids = [row[0] for row in db.query(Homework.id).filter(Homework.subject_id == subject_id).all()]
    hw_appeal_ids = []
    if hw_ids:
        hw_appeal_ids = [
            row[0]
            for row in db.query(HomeworkGradeAppeal.id).filter(HomeworkGradeAppeal.homework_id.in_(hw_ids)).all()
        ]
    appeal_ids = [
        row[0]
        for row in db.query(ScoreGradeAppeal.id).filter(ScoreGradeAppeal.subject_id == subject_id).all()
    ]

    notif_filters = [Notification.subject_id == subject_id]
    if hw_ids:
        notif_filters.append(Notification.related_homework_id.in_(hw_ids))
    if hw_appeal_ids:
        notif_filters.append(Notification.related_appeal_id.in_(hw_appeal_ids))
    if appeal_ids:
        notif_filters.append(Notification.related_score_appeal_id.in_(appeal_ids))
    notif_filter = or_(*notif_filters) if len(notif_filters) > 1 else notif_filters[0]

    notif_ids = [row[0] for row in db.query(Notification.id).filter(notif_filter).all()]
    if notif_ids:
        db.query(NotificationRead).filter(NotificationRead.notification_id.in_(notif_ids)).delete(
            synchronize_session=False
        )
        db.query(Notification).filter(Notification.id.in_(notif_ids)).delete(synchronize_session=False)

    for hw in db.query(Homework).filter(Homework.subject_id == subject_id).all():
        purge_homework_row(db, hw)

    db.query(DiscussionLLMJob).filter(DiscussionLLMJob.subject_id == subject_id).delete(synchronize_session=False)

    db.query(CourseDiscussionEntry).filter(CourseDiscussionEntry.subject_id == subject_id).delete(
        synchronize_session=False
    )

    for mat in db.query(CourseMaterial).filter(CourseMaterial.subject_id == subject_id).all():
        db.delete(mat)

    chapter_id_rows = (
        db.query(CourseMaterialChapter.id).filter(CourseMaterialChapter.subject_id == subject_id).all()
    )
    chapter_ids = [row[0] for row in chapter_id_rows]
    if chapter_ids:
        db.query(CourseMaterialChapter).filter(CourseMaterialChapter.subject_id == subject_id).update(
            {CourseMaterialChapter.parent_id: None},
            synchronize_session=False,
        )
        db.query(CourseMaterialSection).filter(CourseMaterialSection.chapter_id.in_(chapter_ids)).delete(
            synchronize_session=False
        )
        db.query(CourseMaterialHomeworkLink).filter(CourseMaterialHomeworkLink.chapter_id.in_(chapter_ids)).delete(
            synchronize_session=False
        )
        db.query(CourseMaterialChapter).filter(CourseMaterialChapter.subject_id == subject_id).delete(
            synchronize_session=False
        )

    db.query(CourseExamWeight).filter(CourseExamWeight.subject_id == subject_id).delete(synchronize_session=False)
    db.query(CourseGradeScheme).filter(CourseGradeScheme.subject_id == subject_id).delete(synchronize_session=False)
    db.query(ScoreGradeAppeal).filter(ScoreGradeAppeal.subject_id == subject_id).delete(synchronize_session=False)
    db.query(Score).filter(Score.subject_id == subject_id).delete(synchronize_session=False)
    db.query(Attendance).filter(Attendance.subject_id == subject_id).delete(synchronize_session=False)

    llm_cfg = db.query(CourseLLMConfig).filter(CourseLLMConfig.subject_id == subject_id).first()
    if llm_cfg:
        db.delete(llm_cfg)

    db.query(CourseEnrollmentBlock).filter(CourseEnrollmentBlock.subject_id == subject_id).delete(
        synchronize_session=False
    )
    db.query(CourseEnrollment).filter(CourseEnrollment.subject_id == subject_id).delete(synchronize_session=False)
    db.delete(course)
    db.commit()
    if cover_url:
        delete_attachment_file_if_unreferenced(db, cover_url)
    return {"message": "Course deleted successfully."}


@router.get("/{subject_id}/students", response_model=List[CourseEnrollmentResponse])
def get_subject_students(
    subject_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        ensure_course_access_http(subject_id, current_user, db)
    except ValueError:
        raise HTTPException(status_code=404, detail="Course not found.")
    except PermissionError:
        raise HTTPException(status_code=403, detail="You do not have access to this course.")

    enrollments = get_enrolled_students(subject_id, db)
    return [serialize_enrollment(enrollment, db) for enrollment in enrollments]


@router.post("/{subject_id}/sync-enrollments")
def sync_subject_enrollments(
    subject_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Reconcile course_enrollments with the course class roster (idempotent)."""
    if current_user.role == UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Students cannot modify course rosters.")

    try:
        course = ensure_course_access_http(subject_id, current_user, db)
    except ValueError:
        raise HTTPException(status_code=404, detail="Course not found.")
    except PermissionError:
        raise HTTPException(status_code=403, detail="You do not have access to this course.")

    _ensure_course_management_access(current_user, course)
    created = sync_course_enrollments(course, db)
    db.commit()
    db.refresh(course)
    return {
        "message": "Course enrollments synchronized.",
        "created": created,
        "student_count": db.query(CourseEnrollment).filter(CourseEnrollment.subject_id == course.id).count(),
    }


@router.post("/{subject_id}/roster-enroll", response_model=SubjectRosterEnrollResult)
def enroll_roster_students_on_subject(
    subject_id: int,
    payload: SubjectRosterEnrollRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Add CourseEnrollment rows only for students who already belong to the course's class roster.
    Does not create Student rows or move students between classes — use roster / 调班 flows first.
    """
    if current_user.role == UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Students cannot modify course rosters.")

    try:
        course = ensure_course_access_http(subject_id, current_user, db)
    except ValueError:
        raise HTTPException(status_code=404, detail="Course not found.")
    except PermissionError:
        raise HTTPException(status_code=403, detail="You do not have access to this course.")

    _ensure_course_management_access(current_user, course)
    return enroll_roster_students_for_course(course, payload.student_ids, db)


@router.put("/{subject_id}/students/{student_id}/enrollment-type", response_model=CourseEnrollmentResponse)
def update_subject_student_enrollment_type(
    subject_id: int,
    student_id: int,
    payload: CourseEnrollmentTypeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if current_user.role == UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Students cannot modify course enrollment types.")

    try:
        course = ensure_course_access_http(subject_id, current_user, db)
    except ValueError:
        raise HTTPException(status_code=404, detail="Course not found.")
    except PermissionError:
        raise HTTPException(status_code=403, detail="You do not have access to this course.")

    _ensure_course_management_access(current_user, course)
    enrollment_type = payload.enrollment_type.strip().lower()
    if enrollment_type not in {"required", "elective"}:
        raise HTTPException(status_code=400, detail="Enrollment type must be required or elective.")

    enrollment = (
        db.query(CourseEnrollment)
        .filter(
            CourseEnrollment.subject_id == subject_id,
            CourseEnrollment.student_id == student_id,
        )
        .first()
    )
    if not enrollment:
        raise HTTPException(status_code=404, detail="Course student not found.")

    enrollment.enrollment_type = enrollment_type
    enrollment.can_remove = enrollment_type == "elective"
    db.commit()
    db.refresh(enrollment)
    return serialize_enrollment(enrollment, db)


@router.delete("/{subject_id}/students/{student_id}")
def remove_subject_student(
    subject_id: int,
    student_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if current_user.role == UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Students cannot modify course rosters.")

    try:
        course = ensure_course_access_http(subject_id, current_user, db)
    except ValueError:
        raise HTTPException(status_code=404, detail="Course not found.")
    except PermissionError:
        raise HTTPException(status_code=403, detail="You do not have access to this course.")

    _ensure_course_management_access(current_user, course)
    removed = remove_course_enrollment(subject_id, student_id, db)
    if not removed:
        raise HTTPException(status_code=404, detail="Course student not found.")

    db.commit()
    return {"message": "Student removed from course successfully."}
