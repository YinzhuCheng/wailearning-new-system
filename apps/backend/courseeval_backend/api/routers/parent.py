import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Deque, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.core.auth import get_current_active_user
from apps.backend.courseeval_backend.domains.courses.access import get_accessible_class_ids_from_courses
from apps.backend.courseeval_backend.db.database import get_db
from apps.backend.courseeval_backend.db.models import Attendance, Class, CourseEnrollment, Homework, Notification, Score, Student, User, UserRole

router = APIRouter(prefix="/api/parent", tags=["家长端口"])

# In-memory limiter: limits scraping by code + client IP (best-effort; resets on process restart).
_PARENT_RATE_WINDOW_S = 60.0
_PARENT_RATE_MAX = 30
_parent_hits: dict[str, Deque[float]] = defaultdict(deque)

def _check_parent_unauthenticated_rate_limit(request: Request, parent_code: str) -> None:
    ip = request.client.host if request.client else "unknown"
    key = f"{ip}:{(parent_code or '')[:32]}"
    now = time.monotonic()
    q = _parent_hits[key]
    while q and (now - q[0]) > _PARENT_RATE_WINDOW_S:
        q.popleft()
    if len(q) >= _PARENT_RATE_MAX:
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试。")
    q.append(now)


def generate_parent_code():
    """生成8位家长码"""
    return secrets.token_hex(4).upper()


def _now_naive() -> datetime:
    return datetime.now()


def _parent_code_expired(exp: Optional[datetime]) -> bool:
    if not exp:
        return False
    if exp.tzinfo is not None:
        return exp < datetime.now(timezone.utc)
    return exp < _now_naive()


def _get_parent_bound_student_or_404(parent_code: str, db: Session) -> Student:
    student = db.query(Student).filter(Student.parent_code == parent_code).first()
    if not student:
        raise HTTPException(status_code=404, detail="家长码无效")
    if _parent_code_expired(student.parent_code_expires):
        raise HTTPException(status_code=403, detail="家长码已过期")
    return student


def _ensure_teacher_can_manage_student(student: Student, current_user: User, db: Session) -> None:
    if current_user.role == UserRole.ADMIN:
        return
    if current_user.role == UserRole.CLASS_TEACHER:
        if current_user.class_id and int(student.class_id) == int(current_user.class_id):
            return
        raise HTTPException(status_code=403, detail="You do not have permission to manage this student.")

    accessible_class_ids = get_accessible_class_ids_from_courses(current_user, db)
    if student.class_id not in accessible_class_ids:
        raise HTTPException(status_code=403, detail="You do not have permission to manage this student.")


def _student_enrolled_subject_ids(student_id: int, db: Session) -> set[int]:
    return {
        int(row[0])
        for row in db.query(CourseEnrollment.subject_id)
        .filter(CourseEnrollment.student_id == student_id)
        .all()
    }


def _apply_parent_subject_scope(query, subject_column, student: Student, db: Session):
    enrolled_subject_ids = _student_enrolled_subject_ids(int(student.id), db)
    if enrolled_subject_ids:
        return query.filter(or_(subject_column.is_(None), subject_column.in_(enrolled_subject_ids)))
    return query.filter(subject_column.is_(None))


@router.get("/verify/{parent_code}")
def verify_parent_code(
    parent_code: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """验证家长码是否有效"""
    _check_parent_unauthenticated_rate_limit(request, parent_code)
    try:
        student = _get_parent_bound_student_or_404(parent_code, db)
    except HTTPException as exc:
        return {"valid": False, "message": exc.detail}

    class_obj = db.query(Class).filter(Class.id == student.class_id).first()

    return {
        "valid": True,
        "message": "验证成功",
        "student_name": student.name,
        "class_name": class_obj.name if class_obj else None
    }


@router.get("/student/{parent_code}")
def get_student_by_parent_code(
    parent_code: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """通过家长码获取学生信息"""
    _check_parent_unauthenticated_rate_limit(request, parent_code)
    student = _get_parent_bound_student_or_404(parent_code, db)

    class_obj = db.query(Class).filter(Class.id == student.class_id).first()

    return {
        "student_id": student.id,
        "student_name": student.name,
        "student_no": student.student_no,
        "class_id": student.class_id,
        "class_name": class_obj.name if class_obj else None,
        "gender": student.gender.value if student.gender else None,
    }


@router.get("/scores/{parent_code}")
def get_student_scores_by_parent_code(
    parent_code: str,
    request: Request,
    semester: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """通过家长码获取学生成绩"""
    _check_parent_unauthenticated_rate_limit(request, parent_code)
    student = _get_parent_bound_student_or_404(parent_code, db)

    query = db.query(Score).filter(Score.student_id == student.id)

    if semester:
        query = query.filter(Score.semester == semester)

    total = query.count()
    scores = query.order_by(desc(Score.exam_date)).offset((page-1)*page_size).limit(page_size).all()

    return {
        "total": total,
        "student_name": student.name,
        "scores": [
            {
                "id": s.id,
                "subject_name": s.subject.name if s.subject else None,
                "score": s.score,
                "exam_type": s.exam_type,
                "exam_date": s.exam_date,
                "semester": s.semester
            }
            for s in scores
        ]
    }


@router.get("/notifications/{parent_code}")
def get_class_notifications_by_parent_code(
    parent_code: str,
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """通过家长码获取班级通知"""
    _check_parent_unauthenticated_rate_limit(request, parent_code)
    student = _get_parent_bound_student_or_404(parent_code, db)

    query = db.query(Notification).filter(
        or_(
            Notification.class_id.is_(None),
            Notification.class_id == student.class_id,
        ),
        or_(Notification.target_student_id.is_(None), Notification.target_student_id == student.id),
    )
    query = _apply_parent_subject_scope(query, Notification.subject_id, student, db)

    total = query.count()
    notifications = query.order_by(
        desc(Notification.is_pinned),
        desc(Notification.created_at)
    ).offset((page-1)*page_size).limit(page_size).all()

    return {
        "total": total,
        "notifications": [
            {
                "id": n.id,
                "title": n.title,
                "content": n.content,
                "priority": n.priority,
                "is_pinned": n.is_pinned,
                "created_at": n.created_at,
                "creator_name": n.creator.real_name if n.creator else None
            }
            for n in notifications
        ]
    }


@router.get("/homework/{parent_code}")
def get_class_homework_by_parent_code(
    parent_code: str,
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """通过家长码获取班级作业"""
    _check_parent_unauthenticated_rate_limit(request, parent_code)
    student = _get_parent_bound_student_or_404(parent_code, db)

    query = db.query(Homework).filter(Homework.class_id == student.class_id)
    query = _apply_parent_subject_scope(query, Homework.subject_id, student, db)

    total = query.count()
    homeworks = query.order_by(desc(Homework.created_at)).offset((page-1)*page_size).limit(page_size).all()

    return {
        "total": total,
        "homeworks": [
            {
                "id": h.id,
                "title": h.title,
                "content": h.content,
                "subject_name": h.subject.name if h.subject else None,
                "due_date": h.due_date,
                "created_at": h.created_at,
                "creator_name": h.creator.real_name if h.creator else None
            }
            for h in homeworks
        ]
    }


@router.get("/stats/{parent_code}")
def get_student_stats_by_parent_code(
    parent_code: str,
    request: Request,
    semester: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """通过家长码获取学生统计数据"""
    _check_parent_unauthenticated_rate_limit(request, parent_code)
    student = _get_parent_bound_student_or_404(parent_code, db)

    score_query = db.query(Score).filter(Score.student_id == student.id)
    if semester:
        score_query = score_query.filter(Score.semester == semester)

    scores = score_query.all()
    total_exams = len(scores)
    avg_score = round(sum(s.score for s in scores if s.score) / len([s for s in scores if s.score]), 2) if scores else 0

    attendances = db.query(Attendance).filter(Attendance.student_id == student.id).all()
    total_days = len(attendances)
    present_days = len([a for a in attendances if a.status == 'present'])
    attendance_rate = round(present_days / total_days * 100, 2) if total_days > 0 else 100

    return {
        "student_name": student.name,
        "class_name": student.class_obj.name if student.class_obj else None,
        "semester": semester or "全部",
        "total_exams": total_exams,
        "average_score": avg_score,
        "total_attendance_days": total_days,
        "attendance_rate": attendance_rate
    }


@router.post("/students/{student_id}/generate-code")
def generate_student_parent_code(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """生成/重置学生家长码（需要教师权限）"""
    if current_user.role not in (UserRole.ADMIN, UserRole.CLASS_TEACHER, UserRole.TEACHER):
        raise HTTPException(status_code=403, detail="只有教师可以操作")

    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")

    _ensure_teacher_can_manage_student(student, current_user, db)

    parent_code = generate_parent_code()

    student.parent_code = parent_code
    student.parent_code_expires = _now_naive() + timedelta(days=365)

    db.commit()

    return {
        "student_id": student.id,
        "student_name": student.name,
        "parent_code": parent_code,
        "expires_at": student.parent_code_expires
    }


@router.post("/students/batch-generate-codes")
def batch_generate_student_parent_codes(
    student_ids: List[int],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """批量生成学生家长码（需要教师权限）"""
    if current_user.role not in (UserRole.ADMIN, UserRole.CLASS_TEACHER, UserRole.TEACHER):
        raise HTTPException(status_code=403, detail="只有教师可以操作")

    results = []
    seen_student_ids: set[int] = set()

    for student_id in student_ids:
        if student_id in seen_student_ids:
            continue
        seen_student_ids.add(student_id)

        student = db.query(Student).filter(Student.id == student_id).first()
        if not student:
            continue

        try:
            _ensure_teacher_can_manage_student(student, current_user, db)
        except HTTPException:
            continue

        parent_code = generate_parent_code()
        student.parent_code = parent_code
        student.parent_code_expires = _now_naive() + timedelta(days=365)

        results.append({
            "student_id": student.id,
            "student_name": student.name,
            "parent_code": parent_code
        })

    db.commit()

    return {
        "generated_count": len(results),
        "students": results
    }


@router.delete("/students/{student_id}/revoke-code")
def revoke_student_parent_code(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """撤销学生家长码（需要教师权限）"""
    if current_user.role not in (UserRole.ADMIN, UserRole.CLASS_TEACHER, UserRole.TEACHER):
        raise HTTPException(status_code=403, detail="只有教师可以操作")

    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")

    _ensure_teacher_can_manage_student(student, current_user, db)

    student.parent_code = None
    student.parent_code_expires = None

    db.commit()

    return {"message": "家长码已撤销"}
