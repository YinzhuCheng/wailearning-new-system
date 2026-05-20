import io
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from apps.backend.courseeval_backend.attachments import (
    delete_attachment_file,
    delete_attachment_file_if_unreferenced,
    get_attachment_file_path,
)
from apps.backend.courseeval_backend.core.auth import get_current_active_user
from apps.backend.courseeval_backend.domains.courses.access import (
    ensure_course_access_http,
    get_enrolled_students,
    get_student_profile_for_user,
    is_course_instructor,
    prepare_student_course_context,
    subject_linked_class_ids,
)
from apps.backend.courseeval_backend.db.database import get_db
from apps.backend.courseeval_backend.domains.homework.cleanup import purge_homework_row
from apps.backend.courseeval_backend.domains.homework.appeals import (
    mark_appeal_notifications_acknowledged,
    mark_appeal_notifications_handled,
    mark_appeal_notifications_resolved,
    notify_teachers_grade_appeal,
)
from apps.backend.courseeval_backend.domains.appeal_notifications import can_transition_homework_appeal_status, normalize_appeal_status
from apps.backend.courseeval_backend.domains.homework.notifications import notify_student_homework_graded
from apps.backend.courseeval_backend.domains.homework.serialization import preview_text, task_call_log
from apps.backend.courseeval_backend.domains.homework.submission_rules import (
    attempt_counts_toward_final_score,
    attempt_is_late,
)
from apps.backend.courseeval_backend.domains.text_content_format import normalize_content_format
from apps.backend.courseeval_backend.llm_grading import (
    effective_score_display_zh,
    normalize_score_for_homework,
    queue_grading_task,
    refresh_submission_summary,
)
from apps.backend.courseeval_backend.db.models import (
    Class,
    CourseEnrollment,
    Homework,
    HomeworkAttempt,
    HomeworkGradeAppeal,
    HomeworkGradingTask,
    HomeworkScoreCandidate,
    HomeworkSubmission,
    Student,
    Subject,
    User,
    UserRole,
)
from apps.backend.courseeval_backend.domains.courses.class_scope import get_accessible_class_ids
from apps.backend.courseeval_backend.api.schemas import (
    HomeworkAttemptResponse,
    HomeworkBatchLateSubmissionUpdate,
    HomeworkBatchRegradeItemResult,
    HomeworkBatchRegradeRequest,
    HomeworkBatchRegradeResponse,
    HomeworkCreate,
    HomeworkGradeAppealCreate,
    HomeworkGradeAppealResponse,
    HomeworkGradeAppealTeacherUpdate,
    HomeworkListResponse,
    HomeworkRegradeRequest,
    HomeworkResponse,
    HomeworkSubmissionCreate,
    HomeworkSubmissionDownloadRequest,
    HomeworkSubmissionHistoryResponse,
    HomeworkSubmissionReviewUpdate,
    HomeworkSubmissionResponse,
    HomeworkSubmissionStatusListResponse,
    HomeworkSubmissionStatusResponse,
    HomeworkUpdate,
    StudentHomeworkListResponse,
    StudentHomeworkRowResponse,
)


router = APIRouter(prefix="/api/homeworks", tags=["作业管理"])


def is_teacher(user: User) -> bool:
    return user.role in [UserRole.ADMIN, UserRole.CLASS_TEACHER, UserRole.TEACHER]


def _ensure_course_homework_status_access(subject_id: int, user: User, db: Session) -> Subject:
    if not is_teacher(user):
        raise HTTPException(status_code=403, detail="Only teachers can view this list.")
    course = ensure_course_access_http(subject_id, user, db)
    if not is_course_instructor(user, course):
        raise HTTPException(status_code=403, detail="Only the course instructor can view student homework status.")
    return course


def _ensure_homework_course_write_access(current_user: User, homework: Homework, db: Session) -> None:
    if homework.subject_id is None:
        return
    course = ensure_course_access_http(homework.subject_id, current_user, db)
    if not is_course_instructor(current_user, course):
        raise HTTPException(status_code=403, detail="Only the assigned course teacher can update homework.")


def _ensure_homework_submission_management_access(
    current_user: User,
    homework: Homework,
    db: Session,
    *,
    detail: str,
) -> None:
    if homework.subject_id is None:
        return
    course = ensure_course_access_http(homework.subject_id, current_user, db)
    if not is_course_instructor(current_user, course):
        raise HTTPException(status_code=403, detail=detail)


def _homework_subject_allows_class(db: Session, course: Subject, class_id: int) -> bool:
    linked = set(subject_linked_class_ids(db, course.id))
    if linked:
        return int(class_id) in linked
    if course.class_id:
        return int(course.class_id) == int(class_id)
    return True


def _get_homework_or_404(homework_id: int, db: Session) -> Homework:
    homework = db.query(Homework).filter(Homework.id == homework_id).first()
    if not homework:
        raise HTTPException(status_code=404, detail="Homework not found.")
    return homework


def _ensure_homework_access(homework: Homework, current_user: User, db: Session) -> Homework:
    if current_user.role == UserRole.STUDENT and homework.subject_id:
        prepare_student_course_context(current_user, db)
        db.commit()

    allowed_class_ids = get_accessible_class_ids(current_user, db)
    if homework.subject_id:
        course_row = db.query(Subject).filter(Subject.id == homework.subject_id).first()
        if course_row and homework.class_id is not None and not _homework_subject_allows_class(db, course_row, homework.class_id):
            raise HTTPException(
                status_code=403,
                detail="Homework class does not match its course class (data integrity issue).",
            )
        if current_user.role == UserRole.STUDENT:
            _resolve_student_for_user(homework, current_user, db)
        ensure_course_access_http(homework.subject_id, current_user, db)
    elif current_user.role != UserRole.ADMIN and homework.class_id not in allowed_class_ids:
        raise HTTPException(status_code=403, detail="You do not have access to this homework.")

    return homework


def _match_student_for_user(student_query, current_user: User) -> Optional[Student]:
    """Map login user -> Student via canonical binding, constrained by the caller's query."""
    student = get_student_profile_for_user(current_user, student_query.session)
    if not student:
        return None
    return student_query.filter(Student.id == student.id).first()


def _resolve_student_for_user(homework: Homework, current_user: User, db: Session) -> Student:
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Only students can submit homework.")

    roster = get_student_profile_for_user(current_user, db)
    if not roster:
        raise HTTPException(
            status_code=404,
            detail="未找到与当前账号绑定的学生档案，请联系管理员。",
        )

    if roster.class_id != homework.class_id:
        raise HTTPException(
            status_code=404,
            detail="该作业所属班级与花名册班级不一致，无法以当前账号提交。请管理员核对作业班级或花名册班级。",
        )

    student = roster

    if homework.subject_id:
        enrollment = (
            db.query(CourseEnrollment)
            .filter(
                CourseEnrollment.subject_id == homework.subject_id,
                CourseEnrollment.student_id == student.id,
            )
            .first()
        )
        if not enrollment:
            raise HTTPException(
                status_code=403,
                detail="未加入该课程的选课名单，无法提交。请任课教师在课程学生名单中同步或联系管理员。",
            )

    return student


def _grade_rule_hint(homework: Homework) -> str:
    cap = homework.max_submissions
    cap_part = f"每人最多提交 {int(cap)} 次。" if cap is not None else "提交次数不限（未设置上限）。"
    return (
        "「有效成绩」取截止时间前提交的尝试，以及虽已迟交但仍计入总评的尝试（课程允许迟交且未启用「迟交影响评分」时）之中的最高分；"
        f"{cap_part}"
        f"迟交规则：默认{'影响' if homework.late_submission_affects_score else '不影响'}评分（影响时迟交尝试不参与最高分比较），系统会标记每次尝试是否迟交。"
    )


def _effective_score_ui_payload(db: Session, submission: HomeworkSubmission) -> tuple[Optional[int], str]:
    hw = db.query(Homework).filter(Homework.id == submission.homework_id).first()
    seq = getattr(submission, "_effective_win_attempt_seq", None)
    if not hw:
        return seq, ""
    return seq, effective_score_display_zh(hw, seq)


def _is_homework_submission_closed(homework: Homework) -> bool:
    if not homework.due_date:
        return False
    current_time = datetime.now(homework.due_date.tzinfo) if homework.due_date.tzinfo else datetime.now()
    return current_time > homework.due_date


def _ensure_homework_submission_open(
    homework: Homework,
    payload: HomeworkSubmissionCreate,
    submission: Optional[HomeworkSubmission] = None,
) -> None:
    if not _is_homework_submission_closed(homework) or homework.allow_late_submission:
        return

    if payload.attachment_url and (not submission or payload.attachment_url != submission.attachment_url):
        delete_attachment_file(payload.attachment_url)
    raise HTTPException(status_code=400, detail="已超过作业截止时间，不能再提交或修改。")


def _latest_task_for_attempt(db: Session, attempt_id: Optional[int]) -> Optional[HomeworkGradingTask]:
    if not attempt_id:
        return None
    return (
        db.query(HomeworkGradingTask)
        .filter(HomeworkGradingTask.attempt_id == attempt_id)
        .order_by(HomeworkGradingTask.created_at.desc(), HomeworkGradingTask.id.desc())
        .first()
    )


def _task_for_error_and_log(
    db: Session, attempt_id: Optional[int], latest: Optional[HomeworkGradingTask]
) -> Optional[HomeworkGradingTask]:
    """While a retry is queued/processing, surface the most recent failed task for diagnostics."""
    if not attempt_id or not latest:
        return latest
    if latest.status not in ("queued", "processing"):
        return latest
    prev_failed = (
        db.query(HomeworkGradingTask)
        .filter(
            HomeworkGradingTask.attempt_id == attempt_id,
            HomeworkGradingTask.status == "failed",
            HomeworkGradingTask.id < latest.id,
        )
        .order_by(HomeworkGradingTask.id.desc())
        .first()
    )
    return prev_failed or latest


def _best_candidate_for_attempt(db: Session, attempt_id: int) -> Optional[HomeworkScoreCandidate]:
    candidates = (
        db.query(HomeworkScoreCandidate)
        .filter(HomeworkScoreCandidate.attempt_id == attempt_id)
        .order_by(HomeworkScoreCandidate.updated_at.desc(), HomeworkScoreCandidate.id.desc())
        .all()
    )
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda item: (
            float(item.score or 0),
            1 if item.source == "teacher" else 0,
            item.updated_at or item.created_at,
        ),
    )


def _get_submission_summary(db: Session, homework_id: int, student_id: int) -> Optional[HomeworkSubmission]:
    return (
        db.query(HomeworkSubmission)
        .filter(
            HomeworkSubmission.homework_id == homework_id,
            HomeworkSubmission.student_id == student_id,
        )
        .first()
    )


def _attempt_allows_feedback_followup(
    db: Session,
    homework: Homework,
    submission: HomeworkSubmission,
    attempt: HomeworkAttempt,
) -> bool:
    """Whether the student may start a new attempt in feedback-followup mode using this attempt as prior."""
    if homework.max_submissions is not None:
        used = (
            db.query(func.count(HomeworkAttempt.id))
            .filter(HomeworkAttempt.homework_id == homework.id, HomeworkAttempt.student_id == attempt.student_id)
            .scalar()
            or 0
        )
        if int(used) >= int(homework.max_submissions):
            return False
    best = _best_candidate_for_attempt(db, attempt.id)
    if best is None:
        return False
    if best.comment and str(best.comment).strip():
        return True
    if best.source == "teacher":
        return True
    task = _latest_task_for_attempt(db, attempt.id)
    return bool(task and task.status == "success")


def _submission_appeal_status(db: Session, submission_id: Optional[int]) -> Optional[str]:
    if not submission_id:
        return None
    row = (
        db.query(HomeworkGradeAppeal)
        .filter(HomeworkGradeAppeal.submission_id == int(submission_id))
        .first()
    )
    return row.status if row else None


def _submission_appeal_row(db: Session, submission_id: Optional[int]) -> Optional[HomeworkGradeAppeal]:
    if not submission_id:
        return None
    return (
        db.query(HomeworkGradeAppeal)
        .filter(HomeworkGradeAppeal.submission_id == int(submission_id))
        .first()
    )


def _serialize_submission(db: Session, submission: HomeworkSubmission) -> HomeworkSubmissionResponse:
    refresh_submission_summary(db, submission)
    appeal_row = _submission_appeal_row(db, submission.id)
    latest_task = _latest_task_for_attempt(db, submission.latest_attempt_id)
    diag_task = _task_for_error_and_log(db, submission.latest_attempt_id, latest_task)
    latest_attempt = (
        db.query(HomeworkAttempt).filter(HomeworkAttempt.id == submission.latest_attempt_id).first()
        if submission.latest_attempt_id
        else None
    )
    hw = db.query(Homework).filter(Homework.id == submission.homework_id).first()
    allow_ff = (
        _attempt_allows_feedback_followup(db, hw, submission, latest_attempt)
        if hw and latest_attempt
        else False
    )
    eff_seq, eff_note = _effective_score_ui_payload(db, submission)
    return HomeworkSubmissionResponse(
        id=submission.id,
        homework_id=submission.homework_id,
        student_id=submission.student_id,
        subject_id=submission.subject_id,
        class_id=submission.class_id,
        content=submission.content,
        content_format=normalize_content_format(getattr(submission, "content_format", None)),
        attachment_name=submission.attachment_name,
        attachment_url=submission.attachment_url,
        used_llm_assist=bool(getattr(submission, "used_llm_assist", False)),
        submission_mode=getattr(latest_attempt, "submission_mode", None) if latest_attempt else None,
        prior_attempt_id=getattr(latest_attempt, "prior_attempt_id", None) if latest_attempt else None,
        allow_feedback_followup=allow_ff,
        submitted_at=submission.submitted_at,
        updated_at=submission.updated_at,
        student_name=submission.student.name if submission.student else None,
        student_no=submission.student.student_no if submission.student else None,
        review_score=submission.review_score,
        review_comment=submission.review_comment,
        latest_attempt_id=submission.latest_attempt_id,
        latest_task_status=submission.latest_task_status,
        latest_task_error=submission.latest_task_error,
        latest_task_error_code=diag_task.error_code if diag_task else None,
        latest_task_log=task_call_log(diag_task),
        appeal_status=appeal_row.status if appeal_row else None,
        appeal_reason_text=appeal_row.reason_text if appeal_row else None,
        appeal_teacher_response=appeal_row.teacher_response if appeal_row else None,
        effective_score_attempt_seq=eff_seq,
        effective_score_note_zh=eff_note,
    )


def _serialize_attempt(db: Session, attempt: HomeworkAttempt) -> HomeworkAttemptResponse:
    best_candidate = _best_candidate_for_attempt(db, attempt.id)
    task = _latest_task_for_attempt(db, attempt.id)
    diag_task = _task_for_error_and_log(db, attempt.id, task)
    hw = db.query(Homework).filter(Homework.id == attempt.homework_id).first()
    sub = (
        attempt.summary
        if getattr(attempt, "summary", None)
        else (
            db.query(HomeworkSubmission).filter(HomeworkSubmission.id == attempt.submission_summary_id).first()
            if attempt.submission_summary_id
            else None
        )
    )
    allow_ff = _attempt_allows_feedback_followup(db, hw, sub, attempt) if hw and sub else False
    return HomeworkAttemptResponse(
        id=attempt.id,
        homework_id=attempt.homework_id,
        student_id=attempt.student_id,
        subject_id=attempt.subject_id,
        class_id=attempt.class_id,
        submission_summary_id=attempt.submission_summary_id,
        content=attempt.content,
        content_format=normalize_content_format(getattr(attempt, "content_format", None)),
        attachment_name=attempt.attachment_name,
        attachment_url=attempt.attachment_url,
        is_late=bool(attempt.is_late),
        counts_toward_final_score=bool(attempt.counts_toward_final_score),
        used_llm_assist=bool(getattr(attempt, "used_llm_assist", False)),
        submission_mode=str(getattr(attempt, "submission_mode", None) or "full"),
        prior_attempt_id=getattr(attempt, "prior_attempt_id", None),
        submitted_at=attempt.submitted_at,
        updated_at=attempt.updated_at,
        review_score=best_candidate.score if best_candidate else None,
        review_comment=best_candidate.comment if best_candidate else None,
        task_status=task.status if task else None,
        task_error=diag_task.error_message if diag_task else None,
        task_error_code=diag_task.error_code if diag_task else None,
        task_log=task_call_log(diag_task),
        score_source=best_candidate.source if best_candidate else None,
        allow_feedback_followup=allow_ff,
    )


def _serialize_history(db: Session, submission: Optional[HomeworkSubmission]) -> HomeworkSubmissionHistoryResponse:
    if not submission:
        return HomeworkSubmissionHistoryResponse(summary=None, attempts=[])
    refresh_submission_summary(db, submission)
    attempts = (
        db.query(HomeworkAttempt)
        .filter(HomeworkAttempt.submission_summary_id == submission.id)
        .order_by(HomeworkAttempt.submitted_at.desc(), HomeworkAttempt.id.desc())
        .all()
    )
    return HomeworkSubmissionHistoryResponse(
        summary=_serialize_submission(db, submission),
        attempts=[_serialize_attempt(db, attempt) for attempt in attempts],
    )


def _serialize_submission_status(
    db: Session,
    enrollment: Optional[CourseEnrollment],
    submission: Optional[HomeworkSubmission],
    fallback_student: Optional[Student] = None,
) -> HomeworkSubmissionStatusResponse:
    student = enrollment.student if enrollment and enrollment.student else fallback_student
    class_obj = enrollment.class_obj if enrollment and enrollment.class_obj else (student.class_obj if student else None)
    if submission:
        refresh_submission_summary(db, submission)
    appeal_row = _submission_appeal_row(db, submission.id if submission else None)
    latest_attempt = submission.latest_attempt if submission else None
    latest_task = _latest_task_for_attempt(db, submission.latest_attempt_id) if submission else None
    diag_task = _task_for_error_and_log(db, submission.latest_attempt_id, latest_task) if submission else None
    eff_seq, eff_note = (
        _effective_score_ui_payload(db, submission)
        if submission
        else (None, "")
    )
    return HomeworkSubmissionStatusResponse(
        student_id=student.id if student else submission.student_id,
        student_name=student.name if student else None,
        student_no=student.student_no if student else None,
        class_name=class_obj.name if class_obj else None,
        submission_id=submission.id if submission else None,
        status="submitted" if submission else "pending",
        submitted_at=submission.submitted_at if submission else None,
        content=submission.content if submission else None,
        content_format=normalize_content_format(getattr(submission, "content_format", None)) if submission else "markdown",
        content_preview=preview_text(submission.content if submission else None),
        attachment_name=submission.attachment_name if submission else None,
        attachment_url=submission.attachment_url if submission else None,
        used_llm_assist=bool(submission.used_llm_assist) if submission else None,
        review_score=submission.review_score if submission else None,
        review_comment=submission.review_comment if submission else None,
        comment_preview=preview_text(submission.review_comment if submission else None, 120),
        latest_attempt_id=submission.latest_attempt_id if submission else None,
        latest_attempt_is_late=latest_attempt.is_late if latest_attempt else None,
        latest_task_status=submission.latest_task_status if submission else None,
        latest_task_error=submission.latest_task_error if submission else None,
        latest_task_error_code=diag_task.error_code if diag_task else None,
        latest_task_log=task_call_log(diag_task),
        attempt_count=len(submission.attempts) if submission else 0,
        appeal_status=appeal_row.status if appeal_row else None,
        appeal_reason_text=appeal_row.reason_text if appeal_row else None,
        appeal_teacher_response=appeal_row.teacher_response if appeal_row else None,
        effective_score_attempt_seq=eff_seq,
        effective_score_note_zh=eff_note,
    )


def _serialize_homework(
    homework: Homework,
    submission: Optional[HomeworkSubmission] = None,
    *,
    viewer: Optional[User] = None,
) -> HomeworkResponse:
    if submission:
        review_score = submission.review_score
        review_comment = submission.review_comment
        task_status = submission.latest_task_status
        task_error = submission.latest_task_error
        attempt_count = len(submission.attempts)
        latest_submission_is_late = submission.latest_attempt.is_late if submission.latest_attempt else None
        latest_used_llm_assist = bool(submission.used_llm_assist)
    else:
        review_score = None
        review_comment = None
        task_status = None
        task_error = None
        attempt_count = 0
        latest_submission_is_late = None
        latest_used_llm_assist = None

    cap = homework.max_submissions
    remaining: Optional[int] = None
    if cap is not None:
        remaining = max(0, int(cap) - int(attempt_count))

    student_view = bool(viewer and viewer.role == UserRole.STUDENT)
    rubric_out = homework.rubric_text
    rubric_staff_out = None if student_view else homework.rubric_staff_only
    reference_out = None if student_view else homework.reference_answer

    return HomeworkResponse(
        id=homework.id,
        title=homework.title,
        content=homework.content,
        content_format=normalize_content_format(getattr(homework, "content_format", None)),
        attachment_name=homework.attachment_name,
        attachment_url=homework.attachment_url,
        class_id=homework.class_id,
        subject_id=homework.subject_id,
        due_date=homework.due_date,
        max_score=homework.max_score,
        grade_precision=homework.grade_precision,
        auto_grading_enabled=homework.auto_grading_enabled,
        rubric_text=rubric_out,
        rubric_staff_only=rubric_staff_out,
        reference_answer=reference_out,
        response_language=homework.response_language,
        allow_late_submission=homework.allow_late_submission,
        late_submission_affects_score=homework.late_submission_affects_score,
        max_submissions=homework.max_submissions,
        created_by=homework.created_by,
        created_at=homework.created_at,
        updated_at=homework.updated_at,
        class_name=homework.class_obj.name if homework.class_obj else None,
        subject_name=homework.subject.name if homework.subject else None,
        creator_name=homework.creator.real_name if homework.creator else None,
        review_score=review_score,
        review_comment=review_comment,
        used_llm_assist=latest_used_llm_assist,
        task_status=task_status,
        task_error=task_error,
        attempt_count=attempt_count,
        submissions_remaining=remaining,
        latest_submission_is_late=latest_submission_is_late,
        grading_rule_hint=_grade_rule_hint(homework),
        llm_routing_spec=homework.llm_routing_spec,
        discussion_requires_context=homework.subject_id is None,
    )


def _serialize_homework_for_user(
    homework: Homework,
    current_user: User,
    submission: Optional[HomeworkSubmission] = None,
) -> HomeworkResponse:
    return _serialize_homework(homework, submission, viewer=current_user)


def _resolve_target_attempt(db: Session, submission: HomeworkSubmission, attempt_id: Optional[int]) -> HomeworkAttempt:
    if attempt_id is not None:
        attempt = (
            db.query(HomeworkAttempt)
            .filter(
                HomeworkAttempt.id == attempt_id,
                HomeworkAttempt.submission_summary_id == submission.id,
            )
            .first()
        )
    else:
        attempt = submission.latest_attempt
    if not attempt:
        raise HTTPException(status_code=404, detail="Homework attempt not found.")
    return attempt


@router.get("", response_model=HomeworkListResponse)
def get_homeworks(
    class_id: Optional[int] = None,
    subject_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    query = db.query(Homework)
    allowed_class_ids = get_accessible_class_ids(current_user, db)

    if subject_id:
        ensure_course_access_http(subject_id, current_user, db)
        query = query.filter(Homework.subject_id == subject_id)

    if current_user.role != UserRole.ADMIN:
        if subject_id is None and not allowed_class_ids:
            return HomeworkListResponse(total=0, data=[])
        if subject_id is None:
            query = query.filter(Homework.class_id.in_(allowed_class_ids))

    if class_id:
        if current_user.role != UserRole.ADMIN and subject_id is None and class_id not in allowed_class_ids:
            return HomeworkListResponse(total=0, data=[])
        query = query.filter(Homework.class_id == class_id)

    total = query.count()
    homeworks = query.order_by(desc(Homework.created_at)).offset((page - 1) * page_size).limit(page_size).all()

    submission_map: dict[int, HomeworkSubmission] = {}
    if current_user.role == UserRole.STUDENT and homeworks:
        class_ids = {item.class_id for item in homeworks}
        student = _match_student_for_user(db.query(Student).filter(Student.class_id.in_(class_ids)), current_user)
        if student:
            submission_rows = (
                db.query(HomeworkSubmission)
                .filter(
                    HomeworkSubmission.homework_id.in_([item.id for item in homeworks]),
                    HomeworkSubmission.student_id == student.id,
                )
                .all()
            )
            for row in submission_rows:
                refresh_submission_summary(db, row)
            submission_map = {row.homework_id: row for row in submission_rows}

    return HomeworkListResponse(
        total=total,
        data=[_serialize_homework_for_user(homework, current_user, submission_map.get(homework.id)) for homework in homeworks],
    )


@router.post("/batch-late-submission", response_model=dict)
def batch_update_late_submission_policy(
    payload: HomeworkBatchLateSubmissionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """批量更新作业的「允许迟交」「迟交是否影响评分」。仅处理当前用户有权限的作业。"""
    if not is_teacher(current_user):
        raise HTTPException(status_code=403, detail="Only teachers can update homework.")

    allowed_class_ids = get_accessible_class_ids(current_user, db)

    ids = list(dict.fromkeys(payload.homework_ids))
    rows = db.query(Homework).filter(Homework.id.in_(ids)).all()
    found = {h.id: h for h in rows}
    missing = [i for i in ids if i not in found]
    forbidden: list[int] = []
    updated = 0
    for hid in ids:
        hw = found.get(hid)
        if not hw:
            continue
        if hw.subject_id:
            try:
                ensure_course_access_http(hw.subject_id, current_user, db)
            except HTTPException:
                forbidden.append(hid)
                continue
            try:
                _ensure_homework_course_write_access(current_user, hw, db)
            except HTTPException:
                forbidden.append(hid)
                continue
        elif current_user.role != UserRole.ADMIN and hw.class_id not in allowed_class_ids:
            forbidden.append(hid)
            continue
        if payload.allow_late_submission is not None:
            hw.allow_late_submission = payload.allow_late_submission
        if payload.late_submission_affects_score is not None:
            hw.late_submission_affects_score = payload.late_submission_affects_score
        updated += 1

    db.commit()
    return {
        "updated": updated,
        "missing_ids": missing,
        "forbidden_ids": forbidden,
    }


@router.get(
    "/courses/{subject_id}/students/{student_id}/homeworks",
    response_model=StudentHomeworkListResponse,
)
def list_student_homeworks_for_course(
    subject_id: int,
    student_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _ensure_course_homework_status_access(subject_id, current_user, db)
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")

    enrolled = (
        db.query(CourseEnrollment)
        .filter(CourseEnrollment.subject_id == subject_id, CourseEnrollment.student_id == student_id)
        .first()
    )
    if not enrolled:
        raise HTTPException(status_code=403, detail="Student is not enrolled in this course.")

    homeworks = (
        db.query(Homework)
        .filter(Homework.subject_id == subject_id)
        .order_by(desc(Homework.created_at))
        .all()
    )
    rows: list[StudentHomeworkRowResponse] = []
    for hw in homeworks:
        sub = (
            db.query(HomeworkSubmission)
            .filter(HomeworkSubmission.homework_id == hw.id, HomeworkSubmission.student_id == student_id)
            .first()
        )
        appeal_row = _submission_appeal_row(db, sub.id if sub else None)
        if sub:
            refresh_submission_summary(db, sub)
        rows.append(
            StudentHomeworkRowResponse(
                homework_id=hw.id,
                title=hw.title,
                due_date=hw.due_date,
                submitted_at=sub.submitted_at if sub else None,
                review_score=sub.review_score if sub else None,
                attempt_count=len(sub.attempts) if sub else 0,
                latest_task_status=sub.latest_task_status if sub else None,
                submission_id=sub.id if sub else None,
                appeal_status=appeal_row.status if appeal_row else None,
                appeal_teacher_response=appeal_row.teacher_response if appeal_row else None,
            )
        )

    total = len(rows)
    offset = (page - 1) * page_size
    page_rows = rows[offset : offset + page_size]
    return StudentHomeworkListResponse(total=total, page=page, page_size=page_size, data=page_rows)


@router.get("/courses/{subject_id}/students")
def list_enrolled_students_for_course_teacher(
    subject_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _ensure_course_homework_status_access(subject_id, current_user, db)
    enrollments = get_enrolled_students(subject_id, db)
    return [
        {
            "student_id": e.student_id,
            "student_name": e.student.name if e.student else None,
            "student_no": e.student.student_no if e.student else None,
        }
        for e in enrollments
    ]


@router.get("/{homework_id}", response_model=HomeworkResponse)
def get_homework(
    homework_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    homework = _ensure_homework_access(_get_homework_or_404(homework_id, db), current_user, db)
    submission = None
    if current_user.role == UserRole.STUDENT:
        student = _match_student_for_user(db.query(Student).filter(Student.class_id == homework.class_id), current_user)
        if student:
            submission = _get_submission_summary(db, homework.id, student.id)
            if submission:
                refresh_submission_summary(db, submission)
    return _serialize_homework_for_user(homework, current_user, submission)


@router.post("", response_model=HomeworkResponse)
def create_homework(
    data: HomeworkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not is_teacher(current_user):
        raise HTTPException(status_code=403, detail="Only teachers can create homework.")

    allowed_class_ids = get_accessible_class_ids(current_user, db)

    if data.subject_id:
        course = ensure_course_access_http(data.subject_id, current_user, db)
        if not is_course_instructor(current_user, course):
            raise HTTPException(status_code=403, detail="Only the assigned course teacher can create homework.")
        if not _homework_subject_allows_class(db, course, data.class_id):
            raise HTTPException(status_code=400, detail="The selected course does not belong to this class.")
    elif current_user.role != UserRole.ADMIN and data.class_id not in allowed_class_ids:
        raise HTTPException(status_code=403, detail="You do not have access to this class.")

    class_obj = db.query(Class).filter(Class.id == data.class_id).first()
    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found.")

    homework = Homework(
        title=data.title,
        content=data.content,
        content_format=normalize_content_format(getattr(data, "content_format", None)),
        attachment_name=data.attachment_name,
        attachment_url=data.attachment_url,
        class_id=data.class_id,
        subject_id=data.subject_id,
        due_date=data.due_date,
        max_score=data.max_score,
        grade_precision=data.grade_precision,
        auto_grading_enabled=data.auto_grading_enabled,
        rubric_text=data.rubric_text,
        rubric_staff_only=data.rubric_staff_only,
        reference_answer=data.reference_answer,
        response_language=data.response_language,
        allow_late_submission=data.allow_late_submission,
        late_submission_affects_score=data.late_submission_affects_score,
        max_submissions=data.max_submissions,
        llm_routing_spec=data.llm_routing_spec,
        created_by=current_user.id,
    )
    db.add(homework)
    db.commit()
    db.refresh(homework)
    return _serialize_homework(homework, viewer=current_user)


@router.put("/{homework_id}", response_model=HomeworkResponse)
def update_homework(
    homework_id: int,
    data: HomeworkUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not is_teacher(current_user):
        raise HTTPException(status_code=403, detail="Only teachers can update homework.")

    homework = _ensure_homework_access(_get_homework_or_404(homework_id, db), current_user, db)
    _ensure_homework_course_write_access(current_user, homework, db)

    if data.subject_id is not None:
        course = ensure_course_access_http(data.subject_id, current_user, db)
        if not is_course_instructor(current_user, course):
            raise HTTPException(status_code=403, detail="Only the assigned course teacher can update homework.")
        if not _homework_subject_allows_class(db, course, homework.class_id):
            raise HTTPException(status_code=400, detail="The selected course does not belong to this class.")

    if data.title is not None:
        homework.title = data.title
    if data.content is not None:
        homework.content = data.content
    if data.content_format is not None:
        homework.content_format = normalize_content_format(data.content_format)
    if data.remove_attachment:
        previous_homework_attachment = homework.attachment_url
        homework.attachment_name = None
        homework.attachment_url = None
        delete_attachment_file_if_unreferenced(db, previous_homework_attachment)
    elif data.attachment_url is not None:
        previous_attachment_url = homework.attachment_url
        homework.attachment_name = data.attachment_name
        homework.attachment_url = data.attachment_url
        if previous_attachment_url and previous_attachment_url != data.attachment_url:
            delete_attachment_file_if_unreferenced(db, previous_attachment_url)
    if data.subject_id is not None:
        homework.subject_id = data.subject_id
    if data.due_date is not None:
        homework.due_date = data.due_date
    if data.max_score is not None:
        homework.max_score = data.max_score
    if data.grade_precision is not None:
        homework.grade_precision = data.grade_precision
    if data.auto_grading_enabled is not None:
        homework.auto_grading_enabled = data.auto_grading_enabled
    if data.rubric_text is not None:
        homework.rubric_text = data.rubric_text
    if data.rubric_staff_only is not None:
        homework.rubric_staff_only = data.rubric_staff_only
    if data.reference_answer is not None:
        homework.reference_answer = data.reference_answer
    if data.response_language is not None:
        homework.response_language = data.response_language
    if data.allow_late_submission is not None:
        homework.allow_late_submission = data.allow_late_submission
    if data.late_submission_affects_score is not None:
        homework.late_submission_affects_score = data.late_submission_affects_score

    if "llm_routing_spec" in data.model_dump(exclude_unset=True):
        homework.llm_routing_spec = data.llm_routing_spec

    update_payload = data.model_dump(exclude_unset=True)
    if "max_submissions" in update_payload:
        new_cap = update_payload["max_submissions"]
        if new_cap is not None:
            counts = [
                int(n or 0)
                for (n,) in db.query(func.count(HomeworkAttempt.id))
                .filter(HomeworkAttempt.homework_id == homework.id)
                .group_by(HomeworkAttempt.student_id)
                .all()
            ]
            max_per_student = max(counts) if counts else 0
            if int(new_cap) < max_per_student:
                raise HTTPException(
                    status_code=400,
                    detail=f"提交次数上限不能低于已有学生的最多提交次数（当前最大 {max_per_student} 次）。",
                )
        homework.max_submissions = new_cap

    db.commit()
    db.refresh(homework)
    return _serialize_homework(homework, viewer=current_user)


@router.delete("/{homework_id}")
def delete_homework(
    homework_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not is_teacher(current_user):
        raise HTTPException(status_code=403, detail="Only teachers can delete homework.")

    homework = _ensure_homework_access(_get_homework_or_404(homework_id, db), current_user, db)
    if homework.subject_id is not None:
        course = ensure_course_access_http(homework.subject_id, current_user, db)
        if not is_course_instructor(current_user, course):
            raise HTTPException(status_code=403, detail="Only the assigned course teacher can delete homework.")
    purge_homework_row(db, homework)
    db.commit()
    return {"message": "Homework deleted successfully."}


@router.get("/{homework_id}/submission/me", response_model=Optional[HomeworkSubmissionResponse])
def get_my_homework_submission(
    homework_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    homework = _ensure_homework_access(_get_homework_or_404(homework_id, db), current_user, db)
    student = _resolve_student_for_user(homework, current_user, db)
    submission = _get_submission_summary(db, homework.id, student.id)
    if not submission:
        return None
    return _serialize_submission(db, submission)


@router.get("/{homework_id}/submission/me/history", response_model=HomeworkSubmissionHistoryResponse)
def get_my_homework_submission_history(
    homework_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    homework = _ensure_homework_access(_get_homework_or_404(homework_id, db), current_user, db)
    student = _resolve_student_for_user(homework, current_user, db)
    submission = _get_submission_summary(db, homework.id, student.id)
    return _serialize_history(db, submission)


@router.post("/{homework_id}/submission", response_model=HomeworkSubmissionResponse)
def submit_homework(
    homework_id: int,
    data: HomeworkSubmissionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    homework = _ensure_homework_access(_get_homework_or_404(homework_id, db), current_user, db)
    student = _resolve_student_for_user(homework, current_user, db)
    submission = _get_submission_summary(db, homework.id, student.id)

    _ensure_homework_submission_open(homework, data, submission)

    if homework.max_submissions is not None:
        used = (
            db.query(func.count(HomeworkAttempt.id))
            .filter(HomeworkAttempt.homework_id == homework.id, HomeworkAttempt.student_id == student.id)
            .scalar()
            or 0
        )
        if int(used) >= int(homework.max_submissions):
            raise HTTPException(
                status_code=400,
                detail=f"已达到该作业允许的最大提交次数（{int(homework.max_submissions)} 次）。",
            )

    if submission is None:
        submission = HomeworkSubmission(
            homework_id=homework.id,
            student_id=student.id,
            subject_id=homework.subject_id,
            class_id=homework.class_id,
        )
        db.add(submission)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            homework = _get_homework_or_404(homework_id, db)
            homework = _ensure_homework_access(homework, current_user, db)
            student = _resolve_student_for_user(homework, current_user, db)
            submission = _get_submission_summary(db, homework.id, student.id)
            if submission is None:
                raise HTTPException(status_code=409, detail="Concurrent submission conflict; please retry.")

    next_content = data.content
    next_content_format = normalize_content_format(getattr(data, "content_format", None))
    next_attachment_name = submission.attachment_name or None
    next_attachment_url = submission.attachment_url or None

    prior_row: Optional[HomeworkAttempt] = None
    if data.submission_mode == "feedback_followup":
        if not data.prior_attempt_id:
            raise HTTPException(status_code=400, detail="按反馈补充提交需要指定 prior_attempt_id。")
        prior_row = (
            db.query(HomeworkAttempt)
            .filter(
                HomeworkAttempt.id == int(data.prior_attempt_id),
                HomeworkAttempt.homework_id == homework.id,
                HomeworkAttempt.student_id == student.id,
                HomeworkAttempt.submission_summary_id == submission.id,
            )
            .first()
        )
        if not prior_row:
            raise HTTPException(status_code=400, detail="指定的上一轮提交不存在或不属于当前作业汇总。")
        if not _attempt_allows_feedback_followup(db, homework, submission, prior_row):
            raise HTTPException(
                status_code=400,
                detail="当前尚不能使用「按反馈补充」：请等待上一轮自动评分完成，或确保已有教师/评语反馈后再试。",
            )
        if data.attachment_url is None and not data.remove_attachment:
            next_attachment_name = prior_row.attachment_name
            next_attachment_url = prior_row.attachment_url

    if data.remove_attachment and submission.attachment_url:
        next_attachment_name = None
        next_attachment_url = None

    if data.attachment_url is not None:
        next_attachment_name = data.attachment_name
        next_attachment_url = data.attachment_url

    if not (next_content or next_attachment_url):
        raise HTTPException(status_code=400, detail="Please provide submission content or an attachment.")

    submitted_at = datetime.now(timezone.utc)
    is_late = attempt_is_late(homework, submitted_at)
    counts_toward = attempt_counts_toward_final_score(homework, is_late)

    submission.content = next_content
    submission.content_format = next_content_format
    submission.attachment_name = next_attachment_name
    submission.attachment_url = next_attachment_url
    submission.used_llm_assist = bool(data.used_llm_assist)
    submission.submitted_at = submitted_at

    attempt = HomeworkAttempt(
        homework_id=homework.id,
        student_id=student.id,
        subject_id=homework.subject_id,
        class_id=homework.class_id,
        submission_summary_id=submission.id,
        content=next_content,
        content_format=next_content_format,
        attachment_name=next_attachment_name,
        attachment_url=next_attachment_url,
        is_late=is_late,
        counts_toward_final_score=counts_toward,
        used_llm_assist=bool(data.used_llm_assist),
        submission_mode=str(data.submission_mode or "full"),
        prior_attempt_id=int(data.prior_attempt_id) if data.prior_attempt_id is not None else None,
        submitted_at=submitted_at,
    )
    db.add(attempt)
    db.flush()

    submission.latest_attempt_id = attempt.id
    submission.latest_task_status = None
    submission.latest_task_error = None

    if homework.auto_grading_enabled:
        queue_grading_task(db, attempt, "new_submission", billed_user_id=None)

    refresh_submission_summary(db, submission)
    db.commit()
    db.refresh(submission)
    return _serialize_submission(db, submission)


@router.get("/{homework_id}/submissions", response_model=HomeworkSubmissionStatusListResponse)
def get_homework_submissions(
    homework_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not is_teacher(current_user):
        raise HTTPException(status_code=403, detail="Only teachers can view homework submissions.")

    homework = _ensure_homework_access(_get_homework_or_404(homework_id, db), current_user, db)
    _ensure_homework_submission_management_access(
        current_user,
        homework,
        db,
        detail="Only the course instructor can view homework submissions.",
    )
    submissions = (
        db.query(HomeworkSubmission)
        .filter(HomeworkSubmission.homework_id == homework.id)
        .order_by(HomeworkSubmission.submitted_at.desc())
        .all()
    )
    for submission in submissions:
        refresh_submission_summary(db, submission)
    submission_map = {submission.student_id: submission for submission in submissions}

    rows: list[HomeworkSubmissionStatusResponse] = []
    if homework.subject_id:
        enrollments = get_enrolled_students(homework.subject_id, db)
        for enrollment in enrollments:
            rows.append(_serialize_submission_status(db, enrollment, submission_map.get(enrollment.student_id)))
    else:
        students = db.query(Student).filter(Student.class_id == homework.class_id).order_by(Student.id.asc()).all()
        for student in students:
            rows.append(_serialize_submission_status(db, None, submission_map.get(student.id), student))

    rows.sort(
        key=lambda r: (
            0 if r.status == "submitted" else 1,
            -(r.submitted_at.timestamp() if r.submitted_at else 0),
            r.student_no or "",
            r.student_name or "",
            r.student_id,
        )
    )
    total = len(rows)
    offset = (page - 1) * page_size
    page_rows = rows[offset : offset + page_size]
    return HomeworkSubmissionStatusListResponse(
        total=total,
        page=page,
        page_size=page_size,
        data=page_rows,
    )


@router.get("/{homework_id}/submissions/{submission_id}/status", response_model=HomeworkSubmissionStatusResponse)
def get_homework_submission_status_single(
    homework_id: int,
    submission_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Teacher-only: returns one row shaped like `HomeworkSubmissionStatusResponse` for deep-links to the
    submission review page without paging through `GET /submissions`.
    """
    if not is_teacher(current_user):
        raise HTTPException(status_code=403, detail="Only teachers can view homework submissions.")

    homework = _ensure_homework_access(_get_homework_or_404(homework_id, db), current_user, db)
    _ensure_homework_submission_management_access(
        current_user,
        homework,
        db,
        detail="Only the course instructor can view homework submissions.",
    )
    submission = (
        db.query(HomeworkSubmission)
        .filter(
            HomeworkSubmission.id == submission_id,
            HomeworkSubmission.homework_id == homework.id,
        )
        .first()
    )
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found.")

    refresh_submission_summary(db, submission)

    enrollment = None
    if homework.subject_id:
        enrollment = (
            db.query(CourseEnrollment)
            .filter(
                CourseEnrollment.subject_id == homework.subject_id,
                CourseEnrollment.student_id == submission.student_id,
            )
            .first()
        )

    fallback_student = db.query(Student).filter(Student.id == submission.student_id).first()
    if not enrollment and not fallback_student:
        raise HTTPException(status_code=404, detail="Student record missing for submission.")

    return _serialize_submission_status(db, enrollment, submission, fallback_student)


@router.post("/{homework_id}/submissions/batch-regrade", response_model=HomeworkBatchRegradeResponse)
def batch_regrade_homework_submissions(
    homework_id: int,
    payload: HomeworkBatchRegradeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not is_teacher(current_user):
        raise HTTPException(status_code=403, detail="Only teachers can regrade homework submissions.")

    homework = _ensure_homework_access(_get_homework_or_404(homework_id, db), current_user, db)
    _ensure_homework_submission_management_access(
        current_user,
        homework,
        db,
        detail="Only the course instructor can regrade homework submissions.",
    )
    if not homework.auto_grading_enabled:
        raise HTTPException(status_code=400, detail="This homework does not have auto grading enabled.")

    if not payload.only_latest_attempt:
        raise HTTPException(status_code=400, detail="only_latest_attempt=false is not supported yet.")

    q = db.query(HomeworkSubmission).filter(HomeworkSubmission.homework_id == homework.id)
    if payload.submission_ids:
        q = q.filter(HomeworkSubmission.id.in_(payload.submission_ids))
    submissions = q.order_by(HomeworkSubmission.id.asc()).all()

    results: list[HomeworkBatchRegradeItemResult] = []
    queued = 0
    skipped = 0
    for sub in submissions:
        if not sub.latest_attempt_id:
            results.append(
                HomeworkBatchRegradeItemResult(submission_id=sub.id, status="skipped", reason="no_attempt")
            )
            skipped += 1
            continue
        attempt = (
            db.query(HomeworkAttempt)
            .filter(
                HomeworkAttempt.id == sub.latest_attempt_id,
                HomeworkAttempt.submission_summary_id == sub.id,
            )
            .first()
        )
        if not attempt:
            results.append(
                HomeworkBatchRegradeItemResult(submission_id=sub.id, status="skipped", reason="attempt_not_found")
            )
            skipped += 1
            continue
        queue_grading_task(db, attempt, "regrade", billed_user_id=current_user.id)
        refresh_submission_summary(db, sub)
        results.append(HomeworkBatchRegradeItemResult(submission_id=sub.id, status="queued", reason=None))
        queued += 1

    db.commit()
    return HomeworkBatchRegradeResponse(queued=queued, skipped=skipped, results=results)


@router.post(
    "/{homework_id}/submissions/{submission_id}/appeal",
    response_model=HomeworkGradeAppealResponse,
)
def create_grade_appeal(
    homework_id: int,
    submission_id: int,
    payload: HomeworkGradeAppealCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Only students can submit appeals.")

    homework = _ensure_homework_access(_get_homework_or_404(homework_id, db), current_user, db)
    student = _resolve_student_for_user(homework, current_user, db)
    submission = (
        db.query(HomeworkSubmission)
        .filter(
            HomeworkSubmission.id == submission_id,
            HomeworkSubmission.homework_id == homework.id,
            HomeworkSubmission.student_id == student.id,
        )
        .first()
    )
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found.")

    refresh_submission_summary(db, submission)
    if submission.review_score is None and not (submission.review_comment or "").strip():
        if submission.latest_task_status not in ("success", "failed"):
            raise HTTPException(
                status_code=400,
                detail="尚无评分结果，暂不可申诉。请等待批改完成后再试。",
            )

    existing = (
        db.query(HomeworkGradeAppeal).filter(HomeworkGradeAppeal.submission_id == submission.id).first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="该作业已提交过申诉，请等待教师处理。")

    appeal = HomeworkGradeAppeal(
        homework_id=homework.id,
        student_id=student.id,
        submission_id=submission.id,
        reason_text=payload.reason_text,
        status="pending",
    )
    try:
        db.add(appeal)
        db.flush()
        notify_teachers_grade_appeal(
            db,
            appeal=appeal,
            homework=homework,
            student_name=student.name,
            creator_user_id=current_user.id,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Appeal already exists for this submission.") from exc
    db.refresh(appeal)
    return appeal


@router.post("/{homework_id}/submissions/{submission_id}/appeal/acknowledge", response_model=dict)
def acknowledge_grade_appeal(
    homework_id: int,
    submission_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not is_teacher(current_user):
        raise HTTPException(status_code=403, detail="Only teachers can acknowledge appeals.")

    homework = _ensure_homework_access(_get_homework_or_404(homework_id, db), current_user, db)
    _ensure_homework_submission_management_access(
        current_user,
        homework,
        db,
        detail="Only the course instructor can acknowledge appeals.",
    )
    appeal = (
        db.query(HomeworkGradeAppeal)
        .filter(
            HomeworkGradeAppeal.submission_id == submission_id,
            HomeworkGradeAppeal.homework_id == homework.id,
        )
        .first()
    )
    if not appeal:
        raise HTTPException(status_code=404, detail="Appeal not found.")

    current_status_normalized = normalize_appeal_status(appeal.status)
    if current_status_normalized == "pending":
        updated_rows = db.execute(
            update(HomeworkGradeAppeal)
            .where(
                HomeworkGradeAppeal.id == appeal.id,
                HomeworkGradeAppeal.status == appeal.status,
            )
            .values(
                status="acknowledged",
                updated_at=datetime.now(timezone.utc),
            )
        ).rowcount
        if updated_rows != 1:
            db.rollback()
            fresh = (
                db.query(HomeworkGradeAppeal)
                .filter(
                    HomeworkGradeAppeal.submission_id == submission_id,
                    HomeworkGradeAppeal.homework_id == homework.id,
                )
                .first()
            )
            if not fresh:
                raise HTTPException(status_code=404, detail="Appeal not found.")
            return {"message": "宸叉爣璁颁负宸查槄銆?", "status": fresh.status}
        appeal.status = "acknowledged"
        mark_appeal_notifications_acknowledged(db, appeal.id)
    db.commit()
    return {"message": "已标记为已阅。", "status": appeal.status}


@router.put("/{homework_id}/submissions/{submission_id}/appeal", response_model=HomeworkGradeAppealResponse)
def respond_grade_appeal(
    homework_id: int,
    submission_id: int,
    payload: HomeworkGradeAppealTeacherUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not is_teacher(current_user):
        raise HTTPException(status_code=403, detail="Only teachers can handle appeals.")

    homework = _ensure_homework_access(_get_homework_or_404(homework_id, db), current_user, db)
    _ensure_homework_submission_management_access(
        current_user,
        homework,
        db,
        detail="Only the course instructor can handle appeals.",
    )
    appeal = (
        db.query(HomeworkGradeAppeal)
        .filter(
            HomeworkGradeAppeal.submission_id == submission_id,
            HomeworkGradeAppeal.homework_id == homework.id,
        )
        .first()
    )
    if not appeal:
        raise HTTPException(status_code=404, detail="Appeal not found.")

    next_status = (payload.status or "resolved").strip()
    if next_status not in ("pending", "acknowledged", "resolved", "rejected"):
        raise HTTPException(status_code=400, detail="Invalid appeal status.")

    next_status_normalized = normalize_appeal_status(next_status)
    current_status_normalized = normalize_appeal_status(appeal.status)
    current_teacher_response = (appeal.teacher_response or "").strip()
    next_teacher_response = payload.teacher_response.strip()
    allowed, reason = can_transition_homework_appeal_status(current_status_normalized, next_status_normalized)
    if not allowed and reason == "invalid_status":
        raise HTTPException(status_code=400, detail="Invalid appeal status.")
    if current_status_normalized == next_status_normalized and current_teacher_response == next_teacher_response:
        return appeal
    if not allowed and reason == "finalized":
        raise HTTPException(status_code=409, detail="This appeal has already been finalized and cannot be changed.")

    updated_rows = db.execute(
        update(HomeworkGradeAppeal)
        .where(
            HomeworkGradeAppeal.id == appeal.id,
            HomeworkGradeAppeal.status == appeal.status,
        )
        .values(
            teacher_response=next_teacher_response,
            status=next_status_normalized,
            updated_at=datetime.now(timezone.utc),
        )
    ).rowcount
    if updated_rows != 1:
        db.rollback()
        fresh = (
            db.query(HomeworkGradeAppeal)
            .filter(
                HomeworkGradeAppeal.submission_id == submission_id,
                HomeworkGradeAppeal.homework_id == homework.id,
            )
            .first()
        )
        if not fresh:
            raise HTTPException(status_code=404, detail="Appeal not found.")
        fresh_status_normalized = normalize_appeal_status(fresh.status)
        fresh_teacher_response = (fresh.teacher_response or "").strip()
        if fresh_status_normalized == next_status_normalized and fresh_teacher_response == next_teacher_response:
            return fresh
        fresh_allowed, fresh_reason = can_transition_homework_appeal_status(
            fresh_status_normalized,
            next_status_normalized,
        )
        if not fresh_allowed and fresh_reason == "invalid_status":
            raise HTTPException(status_code=400, detail="Invalid appeal status.")
        if not fresh_allowed and fresh_reason == "finalized":
            raise HTTPException(status_code=409, detail="This appeal has already been finalized and cannot be changed.")
        raise HTTPException(status_code=409, detail="This appeal changed during processing; please refresh and retry.")

    appeal.teacher_response = next_teacher_response
    appeal.status = next_status_normalized
    mark_appeal_notifications_handled(db, appeal.id, appeal.status)
    db.commit()
    db.refresh(appeal)
    return appeal


@router.get("/{homework_id}/submissions/{submission_id}/history", response_model=HomeworkSubmissionHistoryResponse)
def get_homework_submission_history(
    homework_id: int,
    submission_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not is_teacher(current_user):
        raise HTTPException(status_code=403, detail="Only teachers can view homework histories.")

    homework = _ensure_homework_access(_get_homework_or_404(homework_id, db), current_user, db)
    _ensure_homework_submission_management_access(
        current_user,
        homework,
        db,
        detail="Only the course instructor can view homework histories.",
    )
    submission = (
        db.query(HomeworkSubmission)
        .filter(
            HomeworkSubmission.id == submission_id,
            HomeworkSubmission.homework_id == homework.id,
        )
        .first()
    )
    if not submission:
        raise HTTPException(status_code=404, detail="Homework submission not found.")
    return _serialize_history(db, submission)


@router.put("/{homework_id}/submissions/{submission_id}/review", response_model=HomeworkSubmissionResponse)
def review_homework_submission(
    homework_id: int,
    submission_id: int,
    payload: HomeworkSubmissionReviewUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not is_teacher(current_user):
        raise HTTPException(status_code=403, detail="Only teachers can review homework submissions.")

    homework = _ensure_homework_access(_get_homework_or_404(homework_id, db), current_user, db)
    _ensure_homework_submission_management_access(
        current_user,
        homework,
        db,
        detail="Only the course instructor can review homework submissions.",
    )
    submission = (
        db.query(HomeworkSubmission)
        .filter(
            HomeworkSubmission.id == submission_id,
            HomeworkSubmission.homework_id == homework.id,
        )
        .first()
    )
    if not submission:
        raise HTTPException(status_code=404, detail="Homework submission not found.")

    if payload.review_score > homework.max_score:
        raise HTTPException(status_code=400, detail=f"Review score must be between 0 and {homework.max_score}.")

    attempt = _resolve_target_attempt(db, submission, payload.attempt_id)
    candidate = HomeworkScoreCandidate(
        attempt_id=attempt.id,
        homework_id=homework.id,
        student_id=submission.student_id,
        source="teacher",
        score=normalize_score_for_homework(homework, payload.review_score),
        comment=payload.review_comment,
        created_by=current_user.id,
        source_metadata={"submission_id": submission.id},
    )
    db.add(candidate)
    db.flush()
    refresh_submission_summary(db, submission)
    notify_student_homework_graded(
        db,
        homework_id=homework.id,
        student_id=submission.student_id,
        source_label="教师评分",
        created_by_user_id=current_user.id,
    )
    appeal_row = (
        db.query(HomeworkGradeAppeal)
        .filter(HomeworkGradeAppeal.submission_id == submission.id)
        .first()
    )
    if appeal_row and appeal_row.status in ("pending", "acknowledged"):
        appeal_row.status = "resolved"
        mark_appeal_notifications_resolved(db, appeal_row.id)
    db.commit()
    db.refresh(submission)
    return _serialize_submission(db, submission)


@router.post("/{homework_id}/submissions/{submission_id}/regrade", response_model=HomeworkSubmissionResponse)
def regrade_homework_submission(
    homework_id: int,
    submission_id: int,
    payload: HomeworkRegradeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not is_teacher(current_user):
        raise HTTPException(status_code=403, detail="Only teachers can regrade homework submissions.")

    homework = _ensure_homework_access(_get_homework_or_404(homework_id, db), current_user, db)
    _ensure_homework_submission_management_access(
        current_user,
        homework,
        db,
        detail="Only the course instructor can regrade homework submissions.",
    )
    if not homework.auto_grading_enabled:
        raise HTTPException(status_code=400, detail="This homework does not have auto grading enabled.")

    submission = (
        db.query(HomeworkSubmission)
        .filter(
            HomeworkSubmission.id == submission_id,
            HomeworkSubmission.homework_id == homework.id,
        )
        .first()
    )
    if not submission:
        raise HTTPException(status_code=404, detail="Homework submission not found.")

    attempt = _resolve_target_attempt(db, submission, payload.attempt_id)
    queue_grading_task(db, attempt, "regrade", billed_user_id=current_user.id)
    refresh_submission_summary(db, submission)
    db.commit()
    db.refresh(submission)
    return _serialize_submission(db, submission)


@router.post("/{homework_id}/submissions/download")
def download_homework_submissions(
    homework_id: int,
    payload: HomeworkSubmissionDownloadRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not is_teacher(current_user):
        raise HTTPException(status_code=403, detail="Only teachers can download homework submissions.")

    homework = _ensure_homework_access(_get_homework_or_404(homework_id, db), current_user, db)
    _ensure_homework_submission_management_access(
        current_user,
        homework,
        db,
        detail="Only the course instructor can download homework submissions.",
    )
    if not payload.submission_ids:
        raise HTTPException(status_code=400, detail="Please select at least one submission.")

    submissions = (
        db.query(HomeworkSubmission)
        .filter(
            HomeworkSubmission.homework_id == homework.id,
            HomeworkSubmission.id.in_(payload.submission_ids),
        )
        .order_by(HomeworkSubmission.submitted_at.asc())
        .all()
    )
    if not submissions:
        raise HTTPException(status_code=404, detail="No homework submissions found.")

    archive_buffer = io.BytesIO()
    added_files = 0
    used_names: set[str] = set()

    with zipfile.ZipFile(archive_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for submission in submissions:
            attempt = submission.latest_attempt
            attachment_url = attempt.attachment_url if attempt and attempt.attachment_url else submission.attachment_url
            attachment_name = attempt.attachment_name if attempt and attempt.attachment_name else submission.attachment_name
            file_path = get_attachment_file_path(attachment_url)
            if not file_path or not file_path.exists():
                continue

            original_name = Path(attachment_name or file_path.name).name
            student_account_id = (
                submission.student.student_no
                if submission.student and submission.student.student_no
                else str(submission.student_id)
            )
            safe_account_id = student_account_id.replace("/", "-").replace("\\", "-").strip() or str(submission.student_id)
            suffix = Path(original_name).suffix or file_path.suffix
            archive_name = f"{safe_account_id}{suffix}"
            counter = 1
            while archive_name in used_names:
                archive_name = f"{safe_account_id}-{counter}{suffix}"
                counter += 1

            archive.write(file_path, archive_name)
            used_names.add(archive_name)
            added_files += 1

    if not added_files:
        raise HTTPException(status_code=400, detail="The selected submissions do not contain downloadable attachments.")

    archive_buffer.seek(0)
    filename = f"{datetime.now().date().isoformat()}.zip"
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
    return StreamingResponse(archive_buffer, media_type="application/zip", headers=headers)
