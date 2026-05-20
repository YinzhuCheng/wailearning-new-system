from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.core.auth import get_current_active_user
from apps.backend.courseeval_backend.domains.courses.access import ensure_course_access_http
from apps.backend.courseeval_backend.db.database import get_db
from apps.backend.courseeval_backend.db.models import Attendance, Class, CourseEnrollment, Score, Student, Subject, User
from apps.backend.courseeval_backend.api.schemas import ClassRanking, DashboardStats, ScoreResponse, StudentRanking
from apps.backend.courseeval_backend.domains.courses.class_scope import apply_class_id_filter, get_accessible_class_ids


router = APIRouter(prefix="/api/dashboard", tags=["仪表盘"])


def _apply_course_scope(subject_id: Optional[int], current_user: User, db: Session):
    selected_course = None
    if subject_id:
        selected_course = ensure_course_access_http(subject_id, current_user, db)
    return selected_course


def _course_scoped_score_query(db: Session, selected_course: Optional[Subject], class_ids: list[int]):
    if selected_course:
        return db.query(Score).filter(Score.subject_id == selected_course.id)
    return apply_class_id_filter(db.query(Score), Score.class_id, class_ids)


def _course_scoped_attendance_query(db: Session, selected_course: Optional[Subject], class_ids: list[int]):
    if selected_course:
        return db.query(Attendance).filter(Attendance.subject_id == selected_course.id)
    return apply_class_id_filter(db.query(Attendance), Attendance.class_id, class_ids)


@router.get("/stats", response_model=DashboardStats)
def get_dashboard_stats(
    semester: Optional[str] = None,
    subject_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    selected_course = _apply_course_scope(subject_id, current_user, db)
    class_ids = get_accessible_class_ids(current_user, db)
    if selected_course and selected_course.class_id:
        class_ids = [selected_course.class_id]

    # When a course is selected, "students" means enrolled learners for that subject — especially for
    # electives where the class roster can be larger than `course_enrollments`. Without subject scope,
    # keep the legacy class-wide Student count for admin-wide dashboards.
    if selected_course:
        total_students = (
            db.query(CourseEnrollment).filter(CourseEnrollment.subject_id == selected_course.id).count()
        )
    else:
        total_students_query = apply_class_id_filter(db.query(Student), Student.class_id, class_ids)
        total_students = total_students_query.count()
    total_classes = len(class_ids)

    score_query = _course_scoped_score_query(db, selected_course, class_ids)
    if semester:
        score_query = score_query.filter(Score.semester == semester)

    total_scores = score_query.count()
    avg_score = round(score_query.with_entities(func.avg(Score.score)).scalar() or 0, 2)

    attendance_query = _course_scoped_attendance_query(db, selected_course, class_ids)

    latest_attendance_date = attendance_query.with_entities(func.max(Attendance.date)).scalar()
    if latest_attendance_date:
        latest_attendance_query = attendance_query.filter(Attendance.date == latest_attendance_date)
        total_attendance = latest_attendance_query.count()
        present_attendance = latest_attendance_query.filter(Attendance.status == "present").count()
        attendance_rate = round((present_attendance / total_attendance) * 100, 2) if total_attendance else 0
    else:
        attendance_rate = 0

    recent_scores = score_query.order_by(Score.created_at.desc()).limit(10).all()
    recent_score_list = []
    for score in recent_scores:
        recent_score_list.append(
            ScoreResponse(
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
        )

    return DashboardStats(
        total_students=total_students,
        total_classes=total_classes,
        total_scores=total_scores,
        avg_score=avg_score,
        attendance_rate=attendance_rate,
        recent_scores=recent_score_list,
        class_rankings=[],
    )


@router.get("/rankings/classes", response_model=list[ClassRanking])
def get_class_rankings(
    semester: Optional[str] = None,
    exam_type: Optional[str] = None,
    subject_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    selected_course = _apply_course_scope(subject_id, current_user, db)
    class_ids = get_accessible_class_ids(current_user, db)
    if selected_course and selected_course.class_id:
        class_ids = [selected_course.class_id]

    query = db.query(
        Score.class_id,
        func.avg(Score.score).label("avg_score"),
    )
    if selected_course:
        query = query.filter(Score.subject_id == selected_course.id)
    else:
        query = apply_class_id_filter(query, Score.class_id, class_ids)

    if semester:
        query = query.filter(Score.semester == semester)
    if exam_type:
        query = query.filter(Score.exam_type == exam_type)

    results = query.group_by(Score.class_id).order_by(func.avg(Score.score).desc()).all()

    rankings = []
    for rank, (class_id, avg_score) in enumerate(results, 1):
        class_obj = db.query(Class).filter(Class.id == class_id).first()
        rankings.append(
            ClassRanking(
                class_id=class_id,
                class_name=class_obj.name if class_obj else "",
                avg_score=round(avg_score, 2) if avg_score else 0,
                rank=rank,
            )
        )

    return rankings


@router.get("/rankings/students", response_model=list[StudentRanking])
def get_student_rankings(
    class_id: Optional[int] = None,
    semester: Optional[str] = None,
    exam_type: Optional[str] = None,
    subject_id: Optional[int] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    selected_course = _apply_course_scope(subject_id, current_user, db)
    class_ids = get_accessible_class_ids(current_user, db)
    if selected_course and selected_course.class_id:
        class_ids = [selected_course.class_id]

    query = db.query(
        Score.student_id,
        func.avg(Score.score).label("avg_score"),
    )
    if selected_course:
        query = query.filter(Score.subject_id == selected_course.id)
    else:
        query = apply_class_id_filter(query, Score.class_id, class_ids)

    if class_id:
        if class_id not in class_ids:
            raise HTTPException(status_code=403, detail="You do not have access to this class.")
        query = query.filter(Score.class_id == class_id)
    if semester:
        query = query.filter(Score.semester == semester)
    if exam_type:
        query = query.filter(Score.exam_type == exam_type)

    results = query.group_by(Score.student_id).order_by(func.avg(Score.score).desc()).limit(limit).all()

    rankings = []
    for rank, (student_id, avg_score) in enumerate(results, 1):
        student = db.query(Student).filter(Student.id == student_id).first()
        class_obj = db.query(Class).filter(Class.id == student.class_id).first() if student else None
        rankings.append(
            StudentRanking(
                student_id=student_id,
                student_name=student.name if student else "",
                class_name=class_obj.name if class_obj else "",
                avg_score=round(avg_score, 2) if avg_score else 0,
                rank=rank,
            )
        )
    return rankings


@router.get("/rankings/subjects/{subject_id}")
def get_subject_rankings(
    subject_id: int,
    class_id: Optional[int] = None,
    semester: Optional[str] = None,
    exam_type: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    selected_course = _apply_course_scope(subject_id, current_user, db)
    class_ids = get_accessible_class_ids(current_user, db)
    if class_id:
        if class_id not in class_ids:
            raise HTTPException(status_code=403, detail="You do not have access to this class.")
        class_ids = [class_id]

    query = db.query(Score).filter(Score.subject_id == selected_course.id)
    if class_id:
        query = query.filter(Score.class_id == class_id)
    if semester:
        query = query.filter(Score.semester == semester)
    if exam_type:
        query = query.filter(Score.exam_type == exam_type)

    scores = query.order_by(Score.score.desc()).limit(limit).all()
    results = []
    for rank, score in enumerate(scores, 1):
        results.append(
            {
                "rank": rank,
                "student_id": score.student_id,
                "student_name": score.student.name if score.student else "",
                "score": score.score,
                "subject_name": score.subject.name if score.subject else "",
                "exam_type": score.exam_type,
                "semester": score.semester,
            }
        )
    return results


@router.get("/analysis/trends")
def get_score_trends(
    semester: Optional[str] = None,
    subject_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    selected_course = _apply_course_scope(subject_id, current_user, db)
    class_ids = get_accessible_class_ids(current_user, db)
    query = _course_scoped_score_query(db, selected_course, class_ids)
    if semester:
        query = query.filter(Score.semester == semester)

    scores = query.all()
    exam_types = {}
    for score in scores:
        exam_types.setdefault(score.exam_type, []).append(score.score)

    trends = {}
    for exam_type, score_list in exam_types.items():
        trends[exam_type] = {
            "avg": round(sum(score_list) / len(score_list), 2),
            "max": max(score_list),
            "min": min(score_list),
            "count": len(score_list),
        }
    return trends


@router.get("/analysis/subjects")
def get_subject_analysis(
    semester: Optional[str] = None,
    subject_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    selected_course = _apply_course_scope(subject_id, current_user, db)
    class_ids = get_accessible_class_ids(current_user, db)
    query = db.query(
        Score.subject_id,
        func.avg(Score.score).label("avg_score"),
        func.max(Score.score).label("max_score"),
        func.min(Score.score).label("min_score"),
        func.count(Score.id).label("count"),
    )
    if selected_course:
        query = query.filter(Score.subject_id == selected_course.id)
    else:
        query = apply_class_id_filter(query, Score.class_id, class_ids)

    if semester:
        query = query.filter(Score.semester == semester)

    results = query.group_by(Score.subject_id).all()
    analysis = []
    for current_subject_id, avg_score, max_score, min_score, count in results:
        subject = db.query(Subject).filter(Subject.id == current_subject_id).first()
        analysis.append(
            {
                "subject_id": current_subject_id,
                "subject_name": subject.name if subject else "",
                "avg_score": round(avg_score, 2) if avg_score else 0,
                "max_score": max_score,
                "min_score": min_score,
                "count": count,
            }
        )
    return analysis
