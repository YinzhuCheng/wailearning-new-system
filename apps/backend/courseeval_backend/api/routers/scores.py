from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.core.auth import get_current_active_user
from apps.backend.courseeval_backend.domains.courses.access import (
    ensure_course_access_http,
    get_enrolled_students,
    get_student_profile_for_user,
    is_course_instructor,
    subject_linked_class_ids,
)
from apps.backend.courseeval_backend.db.database import get_db
from apps.backend.courseeval_backend.db.models import CourseEnrollment, CourseExamWeight, CourseGradeScheme, Homework, HomeworkSubmission, Score, ScoreGradeAppeal, Student, Subject, User, UserRole
from apps.backend.courseeval_backend.core.permissions import is_student
from apps.backend.courseeval_backend.domains.courses.class_scope import apply_class_id_filter, get_accessible_class_ids
from apps.backend.courseeval_backend.domains.scores.composition import OTHER_DAILY_EXAM_TYPE, build_composition_for_student, get_scheme_dto, upsert_scheme
from apps.backend.courseeval_backend.domains.appeal_notifications import can_transition_score_appeal_status, normalize_appeal_status
from apps.backend.courseeval_backend.domains.scores.appeals import mark_score_appeal_notifications_handled, notify_teachers_score_grade_appeal
from apps.backend.courseeval_backend.api.schemas import (
    CourseExamWeightResponse,
    CourseExamWeightUpdateRequest,
    CourseGradeSchemeResponse,
    CourseGradeSchemeUpdate,
    ScoreCompositionResponse,
    ScoreCreate,
    ScoreGradeAppealCreate,
    ScoreGradeAppealResponse,
    ScoreGradeAppealTeacherUpdate,
    ScoreListResponse,
    ScoreResponse,
    ScoreUpdate,
)


router = APIRouter(prefix="/api/scores", tags=["成绩管理"])


def _score_subject_allows_class(db: Session, subject: Subject, class_id: int) -> bool:
    linked = set(subject_linked_class_ids(db, subject.id))
    if linked:
        return int(class_id) in linked
    if subject.class_id:
        return int(subject.class_id) == int(class_id)
    return True


def _ensure_score_write_access(current_user: User):
    if current_user.role == UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Students cannot modify scores.")


def _ensure_score_course_write_access(current_user: User, course: Subject):
    if not is_course_instructor(current_user, course):
        raise HTTPException(status_code=403, detail="Only the assigned course teacher can modify course scores.")


def _serialize_score(score: Score) -> ScoreResponse:
    return ScoreResponse(
        id=score.id,
        student_id=score.student_id,
        subject_id=score.subject_id,
        class_id=score.class_id,
        score=score.score,
        exam_type=score.exam_type,
        exam_date=score.exam_date,
        semester=score.semester,
        created_at=score.created_at,
        student_name=score.student.name if score.student else None,
        subject_name=score.subject.name if score.subject else None,
        class_name=score.class_obj.name if score.class_obj else None,
    )


def _serialize_exam_weight(item: CourseExamWeight) -> CourseExamWeightResponse:
    return CourseExamWeightResponse(
        id=item.id,
        subject_id=item.subject_id,
        exam_type=item.exam_type,
        weight=item.weight,
    )


def _serialize_score_appeal(db: Session, appeal: ScoreGradeAppeal) -> ScoreGradeAppealResponse:
    st = db.query(Student).filter(Student.id == appeal.student_id).first()
    target_component = (appeal.target_component or "").strip()
    homework_id = None
    homework_title = None
    if target_component.startswith("homework:"):
        try:
            homework_id = int(target_component.split(":", 1)[1])
        except (TypeError, ValueError):
            homework_id = None
        if homework_id:
            homework = db.query(Homework).filter(Homework.id == homework_id).first()
            homework_title = homework.title if homework else None
        target_component = "homework"
    return ScoreGradeAppealResponse(
        id=appeal.id,
        subject_id=appeal.subject_id,
        student_id=appeal.student_id,
        student_name=st.name if st else None,
        homework_id=homework_id,
        homework_title=homework_title,
        score_id=appeal.score_id,
        semester=appeal.semester,
        target_component=target_component,
        reason_text=appeal.reason_text,
        status=appeal.status,
        teacher_response=appeal.teacher_response,
        created_at=appeal.created_at,
    )


def _validate_score_uniqueness(
    db: Session,
    *,
    student_id: int,
    subject_id: int,
    semester: str,
    exam_type: str,
    exclude_score_id: Optional[int] = None,
) -> None:
    query = db.query(Score).filter(
        Score.student_id == student_id,
        Score.subject_id == subject_id,
        Score.semester == semester,
        Score.exam_type == exam_type,
    )
    if exclude_score_id is not None:
        query = query.filter(Score.id != exclude_score_id)

    existing = query.first()
    if existing:
        raise HTTPException(status_code=400, detail="同一学生在该课程下的同一考试类型成绩不能重复录入。")


@router.get("", response_model=ScoreListResponse)
def get_scores(
    class_id: Optional[int] = None,
    student_id: Optional[int] = None,
    subject_id: Optional[int] = None,
    semester: Optional[str] = None,
    exam_type: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if subject_id:
        ensure_course_access_http(subject_id, current_user, db)
        query = db.query(Score).filter(Score.subject_id == subject_id)
    else:
        class_ids = get_accessible_class_ids(current_user, db)
        query = apply_class_id_filter(db.query(Score), Score.class_id, class_ids)

    if class_id:
        if not subject_id:
            class_ids = get_accessible_class_ids(current_user, db)
            if class_id not in class_ids:
                raise HTTPException(status_code=403, detail="You do not have access to this class.")
        query = query.filter(Score.class_id == class_id)
    if student_id:
        query = query.filter(Score.student_id == student_id)
    if semester:
        query = query.filter(Score.semester == semester)
    if exam_type:
        query = query.filter(Score.exam_type == exam_type)

    total = query.count()
    scores = query.order_by(Score.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return ScoreListResponse(total=total, data=[_serialize_score(score) for score in scores])


@router.post("", response_model=ScoreResponse)
def create_score(
    score_data: ScoreCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _ensure_score_write_access(current_user)
    class_ids = get_accessible_class_ids(current_user, db)
    if score_data.class_id not in class_ids:
        raise HTTPException(status_code=403, detail="You do not have access to this class.")

    student = db.query(Student).filter(Student.id == score_data.student_id).first()
    if not student or student.class_id != score_data.class_id:
        raise HTTPException(status_code=400, detail="Student not found in the selected class.")

    subject = db.query(Subject).filter(Subject.id == score_data.subject_id).first()
    if not subject:
        raise HTTPException(status_code=400, detail="Course not found.")
    if not _score_subject_allows_class(db, subject, score_data.class_id):
        raise HTTPException(status_code=400, detail="The selected course does not belong to this class.")
    _ensure_score_course_write_access(current_user, subject)

    _validate_score_uniqueness(
        db,
        student_id=score_data.student_id,
        subject_id=score_data.subject_id,
        semester=score_data.semester,
        exam_type=score_data.exam_type,
    )

    score = Score(
        student_id=score_data.student_id,
        subject_id=score_data.subject_id,
        class_id=score_data.class_id,
        score=score_data.score,
        exam_type=score_data.exam_type,
        exam_date=score_data.exam_date,
        semester=score_data.semester,
    )
    db.add(score)
    db.commit()
    db.refresh(score)
    return _serialize_score(score)


@router.get("/weights/{subject_id}", response_model=list[CourseExamWeightResponse])
def get_course_exam_weights(
    subject_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    ensure_course_access_http(subject_id, current_user, db)
    items = (
        db.query(CourseExamWeight)
        .filter(CourseExamWeight.subject_id == subject_id)
        .order_by(CourseExamWeight.exam_type.asc())
        .all()
    )
    return [_serialize_exam_weight(item) for item in items]


@router.put("/weights/{subject_id}", response_model=list[CourseExamWeightResponse])
def update_course_exam_weights(
    subject_id: int,
    payload: CourseExamWeightUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _ensure_score_write_access(current_user)
    course = ensure_course_access_http(subject_id, current_user, db)
    _ensure_score_course_write_access(current_user, course)

    if not payload.items:
        db.query(CourseExamWeight).filter(CourseExamWeight.subject_id == subject_id).delete()
        db.commit()
        return []

    seen_exam_types = set()
    total_weight = 0.0
    normalized_items = []
    for item in payload.items:
        exam_type = item.exam_type.strip()
        if not exam_type:
            raise HTTPException(status_code=400, detail="考试类型不能为空。")
        normalized_key = exam_type.lower()
        if normalized_key in seen_exam_types:
            raise HTTPException(status_code=400, detail="考试类型不能重复。")
        if item.weight <= 0:
            raise HTTPException(status_code=400, detail="考试占比必须大于 0。")
        seen_exam_types.add(normalized_key)
        total_weight += item.weight
        normalized_items.append((exam_type, item.weight))

    if round(total_weight, 2) > 100:
        raise HTTPException(
            status_code=400,
            detail="考试占比总和不能超过 100（需为「作业平时分」「其他平时分」预留比例，三者之和为 100）。",
        )

    scheme = get_scheme_dto(db, subject_id)
    if round(float(scheme.homework_weight) + float(scheme.extra_daily_weight) + total_weight, 2) > 100:
        raise HTTPException(
            status_code=400,
            detail="作业平时分 + 其他平时分 + 各次考试占比之和不能超过 100。请下调考试占比或平时分占比。",
        )

    db.query(CourseExamWeight).filter(CourseExamWeight.subject_id == subject_id).delete()
    for exam_type, weight in normalized_items:
        db.add(CourseExamWeight(subject_id=subject_id, exam_type=exam_type, weight=weight))
    db.commit()

    items = (
        db.query(CourseExamWeight)
        .filter(CourseExamWeight.subject_id == subject_id)
        .order_by(CourseExamWeight.exam_type.asc())
        .all()
    )
    return [_serialize_exam_weight(item) for item in items]


@router.get("/grade-scheme/{subject_id}", response_model=CourseGradeSchemeResponse)
def get_course_grade_scheme(
    subject_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    ensure_course_access_http(subject_id, current_user, db)
    row = db.query(CourseGradeScheme).filter(CourseGradeScheme.subject_id == subject_id).first()
    hw = float(row.homework_weight) if row else 30.0
    ex = float(row.extra_daily_weight) if row else 20.0
    return CourseGradeSchemeResponse(subject_id=subject_id, homework_weight=hw, extra_daily_weight=ex)


@router.put("/grade-scheme/{subject_id}", response_model=CourseGradeSchemeResponse)
def update_course_grade_scheme(
    subject_id: int,
    payload: CourseGradeSchemeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _ensure_score_write_access(current_user)
    course = ensure_course_access_http(subject_id, current_user, db)
    _ensure_score_course_write_access(current_user, course)
    hw = float(payload.homework_weight)
    ex = float(payload.extra_daily_weight)
    if hw < 0 or ex < 0 or hw + ex > 100:
        raise HTTPException(status_code=400, detail="作业平时分与其他平时分占比须在 0–100 之间且两者之和不超过 100。")
    exam_sum = (
        db.query(func.sum(CourseExamWeight.weight)).filter(CourseExamWeight.subject_id == subject_id).scalar() or 0
    )
    if round(float(exam_sum) + hw + ex, 2) > 100:
        raise HTTPException(
            status_code=400,
            detail="作业平时分 + 其他平时分 + 各次考试占比之和不能超过 100。请下调考试占比或平时分占比。",
        )
    upsert_scheme(db, subject_id, hw, ex)
    db.commit()
    return CourseGradeSchemeResponse(subject_id=subject_id, homework_weight=hw, extra_daily_weight=ex)


@router.get("/composition/class", response_model=list[ScoreCompositionResponse])
def list_class_score_compositions(
    subject_id: int,
    semester: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if is_student(current_user):
        raise HTTPException(status_code=403, detail="仅教师可查看全班成绩构成。")
    ensure_course_access_http(subject_id, current_user, db)

    enrollments = get_enrolled_students(subject_id, db)
    out: list[ScoreCompositionResponse] = []
    for en in enrollments:
        sid = en.student_id
        stu_name = en.student.name if en.student else None
        out.append(
            ScoreCompositionResponse(
                **build_composition_for_student(
                    db, student_id=sid, subject_id=subject_id, semester=semester, student_name=stu_name
                )
            )
        )
    return out


@router.get("/composition/me", response_model=ScoreCompositionResponse)
def get_my_score_composition(
    subject_id: int,
    semester: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not is_student(current_user):
        raise HTTPException(status_code=403, detail="仅学生可查看本人的成绩构成。")
    student = get_student_profile_for_user(current_user, db)
    if not student:
        raise HTTPException(status_code=400, detail="未找到与账号绑定的学生档案。")
    ensure_course_access_http(subject_id, current_user, db)
    return ScoreCompositionResponse(
        **build_composition_for_student(
            db, student_id=student.id, subject_id=subject_id, semester=semester, student_name=student.name
        )
    )


@router.get("/composition/{student_id}", response_model=ScoreCompositionResponse)
def get_student_score_composition(
    student_id: int,
    subject_id: int,
    semester: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if is_student(current_user):
        raise HTTPException(status_code=403, detail="教师或教务可查看学生成绩构成。")
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")
    ensure_course_access_http(subject_id, current_user, db)
    if not db.query(CourseEnrollment).filter(
        CourseEnrollment.subject_id == subject_id,
        CourseEnrollment.student_id == student_id,
    ).first():
        class_ids = get_accessible_class_ids(current_user, db)
        if student.class_id not in class_ids:
            raise HTTPException(status_code=403, detail="You do not have access to this student.")
    return ScoreCompositionResponse(
        **build_composition_for_student(
            db, student_id=student_id, subject_id=subject_id, semester=semester, student_name=student.name
        )
    )


@router.post("/appeals", response_model=ScoreGradeAppealResponse)
def create_score_grade_appeal(
    subject_id: int,
    payload: ScoreGradeAppealCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not is_student(current_user):
        raise HTTPException(status_code=403, detail="仅学生可提交成绩申诉。")
    student = get_student_profile_for_user(current_user, db)
    if not student:
        raise HTTPException(status_code=400, detail="未找到与账号绑定的学生档案。")
    ensure_course_access_http(subject_id, current_user, db)

    allowed = {"total", "homework_avg", OTHER_DAILY_EXAM_TYPE}
    exam_types = {r.exam_type for r in db.query(CourseExamWeight).filter(CourseExamWeight.subject_id == subject_id).all()}
    raw_target_component = payload.target_component.strip()
    if raw_target_component not in allowed and raw_target_component not in exam_types and raw_target_component != "homework":
        raise HTTPException(status_code=400, detail="无效的申诉对象。")

    internal_target_component = raw_target_component
    related_homework_id = None
    if raw_target_component == "homework":
        if payload.homework_id is None:
            raise HTTPException(status_code=400, detail="请选择要申诉的作业。")
        homework = db.query(Homework).filter(Homework.id == payload.homework_id).first()
        if not homework or homework.subject_id != subject_id:
            raise HTTPException(status_code=400, detail="homework_id 与当前课程不符。")
        submission = (
            db.query(HomeworkSubmission)
            .filter(
                HomeworkSubmission.homework_id == homework.id,
                HomeworkSubmission.student_id == student.id,
            )
            .first()
        )
        if not submission or submission.review_score is None:
            raise HTTPException(status_code=400, detail="该作业尚无可申诉的评分结果。")
        related_homework_id = homework.id
        internal_target_component = f"homework:{homework.id}"

    if payload.score_id is not None:
        sc = db.query(Score).filter(Score.id == payload.score_id).first()
        if not sc or sc.student_id != student.id or sc.subject_id != subject_id or sc.semester != payload.semester:
            raise HTTPException(status_code=400, detail="score_id 与课程或学期不符。")
        if raw_target_component == "homework":
            raise HTTPException(status_code=400, detail="作业申诉不需要关联成绩 ID。")
        if raw_target_component == OTHER_DAILY_EXAM_TYPE and sc.exam_type != OTHER_DAILY_EXAM_TYPE:
            raise HTTPException(status_code=400, detail="score_id 与申诉对象不符。")
        if raw_target_component in exam_types and sc.exam_type != raw_target_component:
            raise HTTPException(status_code=400, detail="score_id 与申诉对象不符。")

    dup = (
        db.query(ScoreGradeAppeal)
        .filter(
            ScoreGradeAppeal.student_id == student.id,
            ScoreGradeAppeal.subject_id == subject_id,
            ScoreGradeAppeal.semester == payload.semester.strip(),
            ScoreGradeAppeal.target_component == internal_target_component,
            ScoreGradeAppeal.status == "pending",
        )
        .first()
    )
    if dup:
        raise HTTPException(status_code=400, detail="该申诉对象已有一条待处理申诉，请勿重复提交。")

    appeal = ScoreGradeAppeal(
        subject_id=subject_id,
        student_id=student.id,
        score_id=None if raw_target_component == "homework" else payload.score_id,
        semester=payload.semester.strip(),
        target_component=internal_target_component,
        reason_text=payload.reason_text.strip(),
        status="pending",
    )
    try:
        db.add(appeal)
        db.flush()
        notify_teachers_score_grade_appeal(
            db,
            appeal=appeal,
            student_name=student.name or "",
            creator_user_id=current_user.id,
            related_homework_id=related_homework_id,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="A pending appeal for this component already exists.") from exc
    db.refresh(appeal)
    return _serialize_score_appeal(db, appeal)


@router.get("/appeals", response_model=list[ScoreGradeAppealResponse])
def list_score_grade_appeals(
    subject_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if is_student(current_user):
        raise HTTPException(status_code=403, detail="仅教师可查看申诉列表。")
    q = db.query(ScoreGradeAppeal).join(Subject, Subject.id == ScoreGradeAppeal.subject_id)
    if subject_id is not None:
        ensure_course_access_http(subject_id, current_user, db)
        q = q.filter(ScoreGradeAppeal.subject_id == subject_id)
    else:
        class_ids = get_accessible_class_ids(current_user, db)
        if not class_ids:
            return []
        q = q.filter(Subject.class_id.in_(class_ids))
    if status:
        q = q.filter(ScoreGradeAppeal.status == status)
    rows = q.order_by(ScoreGradeAppeal.created_at.desc()).limit(200).all()
    return [_serialize_score_appeal(db, a) for a in rows]


@router.put("/appeals/{appeal_id}", response_model=ScoreGradeAppealResponse)
def respond_score_grade_appeal(
    appeal_id: int,
    payload: ScoreGradeAppealTeacherUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if is_student(current_user):
        raise HTTPException(status_code=403, detail="Only teachers can handle appeals.")
    appeal = db.query(ScoreGradeAppeal).filter(ScoreGradeAppeal.id == appeal_id).first()
    if not appeal:
        raise HTTPException(status_code=404, detail="Appeal not found.")
    course = ensure_course_access_http(appeal.subject_id, current_user, db)
    _ensure_score_course_write_access(current_user, course)
    next_status = (payload.status or "resolved").strip()
    next_status_normalized = normalize_appeal_status(next_status)
    next_teacher_response = payload.teacher_response.strip()
    allowed, reason = can_transition_score_appeal_status(
        appeal.status,
        next_status_normalized,
        has_teacher_response=bool(next_teacher_response),
    )
    if not allowed and reason == "invalid_status":
        raise HTTPException(status_code=400, detail="Invalid appeal status.")
    if not allowed and reason == "pending_with_response":
        raise HTTPException(status_code=400, detail="A teacher response must resolve or reject the appeal; it cannot remain pending.")
    current_status = normalize_appeal_status(appeal.status)
    current_teacher_response = (appeal.teacher_response or "").strip()
    if current_status == next_status_normalized and current_teacher_response == next_teacher_response:
        return _serialize_score_appeal(db, appeal)
    if not allowed and reason == "finalized":
        raise HTTPException(status_code=409, detail="This appeal has already been finalized and cannot be changed.")

    updated_rows = db.execute(
        update(ScoreGradeAppeal)
        .where(
            ScoreGradeAppeal.id == appeal.id,
            ScoreGradeAppeal.status == appeal.status,
        )
        .values(
            teacher_response=next_teacher_response,
            status=next_status_normalized,
        )
    ).rowcount
    if updated_rows != 1:
        db.rollback()
        fresh = db.query(ScoreGradeAppeal).filter(ScoreGradeAppeal.id == appeal.id).first()
        if not fresh:
            raise HTTPException(status_code=404, detail="Appeal not found.")
        fresh_allowed, fresh_reason = can_transition_score_appeal_status(
            fresh.status,
            next_status_normalized,
            has_teacher_response=bool(next_teacher_response),
        )
        if not fresh_allowed and fresh_reason == "finalized":
            raise HTTPException(status_code=409, detail="This appeal has already been finalized and cannot be changed.")
        if not fresh_allowed and fresh_reason == "pending_with_response":
            raise HTTPException(status_code=400, detail="A teacher response must resolve or reject the appeal; it cannot remain pending.")
        raise HTTPException(status_code=409, detail="This appeal changed during processing; please refresh and retry.")

    appeal.teacher_response = next_teacher_response
    appeal.status = next_status_normalized
    mark_score_appeal_notifications_handled(db, appeal.id, appeal.status)
    db.commit()
    db.refresh(appeal)
    return _serialize_score_appeal(db, appeal)
@router.put("/{score_id}", response_model=ScoreResponse)
def update_score(
    score_id: int,
    score_data: ScoreUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _ensure_score_write_access(current_user)
    score = db.query(Score).filter(Score.id == score_id).first()
    if not score:
        raise HTTPException(status_code=404, detail="Score not found.")

    class_ids = get_accessible_class_ids(current_user, db)
    if score.class_id not in class_ids:
        raise HTTPException(status_code=403, detail="You do not have access to this score.")
    if score.subject_id:
        course = ensure_course_access_http(score.subject_id, current_user, db)
        _ensure_score_course_write_access(current_user, course)

    if score_data.score is not None:
        score.score = score_data.score
    next_exam_type = score_data.exam_type if score_data.exam_type is not None else score.exam_type
    next_semester = score_data.semester if score_data.semester is not None else score.semester

    _validate_score_uniqueness(
        db,
        student_id=score.student_id,
        subject_id=score.subject_id,
        semester=next_semester,
        exam_type=next_exam_type,
        exclude_score_id=score.id,
    )

    if score_data.exam_type is not None:
        score.exam_type = score_data.exam_type
    if score_data.semester is not None:
        score.semester = score_data.semester
    if score_data.exam_date is not None:
        score.exam_date = score_data.exam_date

    db.commit()
    db.refresh(score)
    return _serialize_score(score)


@router.delete("/{score_id}")
def delete_score(
    score_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _ensure_score_write_access(current_user)
    score = db.query(Score).filter(Score.id == score_id).first()
    if not score:
        raise HTTPException(status_code=404, detail="Score not found.")

    class_ids = get_accessible_class_ids(current_user, db)
    if score.class_id not in class_ids:
        raise HTTPException(status_code=403, detail="You do not have access to this score.")
    if score.subject_id:
        course = ensure_course_access_http(score.subject_id, current_user, db)
        _ensure_score_course_write_access(current_user, course)

    db.delete(score)
    db.commit()
    return {"message": "Score deleted successfully."}


@router.get("/student/{student_id}")
def get_student_scores(
    student_id: int,
    semester: Optional[str] = None,
    subject_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")

    class_ids = get_accessible_class_ids(current_user, db)
    if student.class_id not in class_ids:
        raise HTTPException(status_code=403, detail="You do not have access to this student.")

    query = db.query(Score).filter(Score.student_id == student_id)
    if semester:
        query = query.filter(Score.semester == semester)
    if subject_id:
        ensure_course_access_http(subject_id, current_user, db)
        query = query.filter(Score.subject_id == subject_id)

    scores = query.all()
    return [
        {
            "id": score.id,
            "subject_id": score.subject_id,
            "subject_name": score.subject.name if score.subject else None,
            "score": score.score,
            "exam_type": score.exam_type,
            "semester": score.semester,
        }
        for score in scores
    ]


@router.post("/batch")
async def create_scores_batch(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _ensure_score_write_access(current_user)
    import json

    body = await request.body()
    body_str = body.decode("utf-8").replace("\x00", "").replace("\ufeff", "")

    try:
        data = json.loads(body_str)
        scores_list = data.get("scores", []) if isinstance(data, dict) else data
    except Exception as exc:
        return {"success": 0, "failed": 1, "errors": [f"JSON parse error: {exc}"]}

    if not scores_list:
        return {"success": 0, "failed": 0, "errors": ["No valid score data found."]}

    class_ids = get_accessible_class_ids(current_user, db)
    results = []
    errors = []
    seen_keys = set()

    for index, score_data in enumerate(scores_list, 1):
        if not isinstance(score_data, dict):
            errors.append(f"Row {index}: invalid record format.")
            continue

        class_id = score_data.get("class_id")
        if class_id not in class_ids:
            errors.append(f"Row {index}: no access to the selected class.")
            continue

        student_no = score_data.get("student_no")
        subject_id = score_data.get("subject_id")
        if not student_no:
            errors.append(f"Row {index}: missing student number.")
            continue
        if not subject_id:
            errors.append(f"Row {index}: missing course ID.")
            continue

        student = db.query(Student).filter(Student.student_no == student_no, Student.class_id == class_id).first()
        if not student:
            errors.append(f"Row {index}: student {student_no} not found in class.")
            continue

        subject = db.query(Subject).filter(Subject.id == subject_id).first()
        if not subject:
            errors.append(f"Row {index}: course not found.")
            continue
        if not _score_subject_allows_class(db, subject, class_id):
            errors.append(f"Row {index}: selected course does not belong to this class.")
            continue

        exam_type = score_data.get("exam_type", "期中考试")
        if not is_course_instructor(current_user, subject):
            errors.append(f"Row {index}: only the assigned course teacher can modify course scores.")
            continue

        semester = score_data.get("semester", "")
        dedupe_key = (student.id, subject_id, semester, exam_type)
        if dedupe_key in seen_keys:
            errors.append(f"Row {index}: duplicate score for the same student and exam type in this batch.")
            continue

        try:
            _validate_score_uniqueness(
                db,
                student_id=student.id,
                subject_id=subject_id,
                semester=semester,
                exam_type=exam_type,
            )
        except HTTPException as exc:
            errors.append(f"Row {index}: {exc.detail}")
            continue

        try:
            score_value = float(score_data.get("score"))
        except (TypeError, ValueError):
            errors.append(f"Row {index}: invalid score value.")
            continue

        if score_value < 0 or score_value > 100:
            errors.append(f"Row {index}: score must be between 0 and 100.")
            continue

        exam_date = score_data.get("exam_date")
        if isinstance(exam_date, str) and exam_date:
            try:
                exam_date = datetime.fromisoformat(exam_date.replace("Z", "+00:00"))
            except ValueError:
                exam_date = None

        db.add(
            Score(
                student_id=student.id,
                subject_id=subject_id,
                class_id=class_id,
                score=score_value,
                exam_type=exam_type,
                exam_date=exam_date,
                semester=semester,
            )
        )
        seen_keys.add(dedupe_key)
        results.append(f"{student.name}-{subject.name}")

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        errors.append(f"Database error: {exc}")

    return {"success": len(results), "failed": len(errors), "errors": errors}
