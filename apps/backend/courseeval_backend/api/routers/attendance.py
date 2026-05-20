from datetime import datetime, time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.core.auth import get_current_active_user
from apps.backend.courseeval_backend.domains.courses.access import (
    ensure_course_access_http,
    is_course_instructor,
    subject_linked_class_ids,
)
from apps.backend.courseeval_backend.db.database import get_db
from apps.backend.courseeval_backend.db.models import Attendance, Student, Subject, User, UserRole
from apps.backend.courseeval_backend.domains.courses.class_scope import apply_class_id_filter, get_accessible_class_ids
from apps.backend.courseeval_backend.api.schemas import AttendanceCreate, AttendanceListResponse, AttendanceResponse, AttendanceUpdate


router = APIRouter(prefix="/api/attendance", tags=["考勤管理"])


def _ensure_attendance_write_access(current_user: User):
    if current_user.role == UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Students cannot modify attendance.")


def _ensure_attendance_course_write_access(current_user: User, course: Subject):
    if not is_course_instructor(current_user, course):
        raise HTTPException(status_code=403, detail="Only the assigned course teacher can modify course attendance.")


def _attendance_subject_allows_class(db: Session, course: Subject, class_id: int) -> bool:
    linked = set(subject_linked_class_ids(db, course.id))
    if linked:
        return int(class_id) in linked
    if course.class_id:
        return int(course.class_id) == int(class_id)
    return True


def _parse_attendance_date(value) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception as exc:
            raise ValueError("Invalid date format.") from exc
    raise ValueError("Invalid date format.")


def _parse_attendance_query_boundary(value, *, end_of_day: bool = False) -> datetime:
    parsed = _parse_attendance_date(value)
    if isinstance(value, str) and "T" not in value and "t" not in value and " " not in value and "_" not in value:
        return datetime.combine(parsed.date(), time.max if end_of_day else time.min)
    return parsed


def _serialize_attendance(attendance: Attendance) -> AttendanceResponse:
    return AttendanceResponse(
        id=attendance.id,
        student_id=attendance.student_id,
        class_id=attendance.class_id,
        subject_id=attendance.subject_id,
        date=attendance.date,
        status=attendance.status,
        remark=attendance.remark,
        created_at=attendance.created_at,
        student_name=attendance.student.name if attendance.student else None,
        class_name=attendance.class_obj.name if attendance.class_obj else None,
        subject_name=attendance.subject.name if attendance.subject else None,
    )


def _upsert_attendance_row(
    db: Session,
    *,
    student_id: int,
    class_id: int,
    subject_id: Optional[int],
    attendance_date: datetime,
    status,
    remark: Optional[str],
) -> None:
    existing = db.query(Attendance).filter(
        Attendance.student_id == student_id,
        Attendance.date == attendance_date,
        Attendance.subject_id == subject_id,
    ).first()
    if existing:
        existing.status = status
        existing.remark = remark
        return

    db.add(
        Attendance(
            student_id=student_id,
            class_id=class_id,
            subject_id=subject_id,
            date=attendance_date,
            status=status,
            remark=remark,
        )
    )


def _has_subject_or_class_access(
    current_user: User,
    db: Session,
    *,
    class_id: Optional[int],
    subject_id: Optional[int],
    class_error_detail: str,
) -> set[int]:
    class_ids = set(get_accessible_class_ids(current_user, db))
    if current_user.role == UserRole.ADMIN:
        return class_ids
    if subject_id:
        ensure_course_access_http(subject_id, current_user, db)
        return class_ids
    if class_id not in class_ids:
        raise HTTPException(status_code=403, detail=class_error_detail)
    return class_ids


@router.get("", response_model=AttendanceListResponse)
def get_attendances(
    class_id: Optional[int] = None,
    student_id: Optional[int] = None,
    student_name: Optional[str] = None,
    subject_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(1000, ge=1, le=10000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    class_ids = set(get_accessible_class_ids(current_user, db))
    if subject_id:
        ensure_course_access_http(subject_id, current_user, db)
        query = db.query(Attendance).filter(Attendance.subject_id == subject_id)
    else:
        query = apply_class_id_filter(db.query(Attendance), Attendance.class_id, list(class_ids))

    if class_id:
        if subject_id is None and class_id not in class_ids:
            raise HTTPException(status_code=403, detail="You do not have access to this class.")
        query = query.filter(Attendance.class_id == class_id)
    if student_id:
        query = query.filter(Attendance.student_id == student_id)
    if student_name:
        query = query.join(Student, Attendance.student_id == Student.id).filter(Student.name.contains(student_name))
    if start_date:
        try:
            start_dt = _parse_attendance_query_boundary(start_date, end_of_day=False)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format.")
        query = query.filter(Attendance.date >= start_dt)
    if end_date:
        try:
            end_dt = _parse_attendance_query_boundary(end_date, end_of_day=True)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format.")
        query = query.filter(Attendance.date <= end_dt)
    if status:
        query = query.filter(Attendance.status == status)

    total = query.count()
    attendances = query.order_by(Attendance.date.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return AttendanceListResponse(total=total, data=[_serialize_attendance(attendance) for attendance in attendances])


@router.post("", response_model=AttendanceResponse)
def create_attendance(
    attendance_data: AttendanceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _ensure_attendance_write_access(current_user)
    _has_subject_or_class_access(
        current_user,
        db,
        class_id=attendance_data.class_id,
        subject_id=attendance_data.subject_id,
        class_error_detail="You do not have access to this class.",
    )

    student = db.query(Student).filter(Student.id == attendance_data.student_id).first()
    if not student or student.class_id != attendance_data.class_id:
        raise HTTPException(status_code=400, detail="Student not found in the selected class.")

    if attendance_data.subject_id:
        course = ensure_course_access_http(attendance_data.subject_id, current_user, db)
        _ensure_attendance_course_write_access(current_user, course)
        if not _attendance_subject_allows_class(db, course, attendance_data.class_id):
            raise HTTPException(status_code=400, detail="The selected course does not belong to this class.")

    try:
        attendance_date = _parse_attendance_date(attendance_data.date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format.")

    existing = db.query(Attendance).filter(
        Attendance.student_id == attendance_data.student_id,
        Attendance.date == attendance_date,
        Attendance.subject_id == attendance_data.subject_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Attendance already exists for this date and course.")

    attendance = Attendance(
        student_id=attendance_data.student_id,
        class_id=attendance_data.class_id,
        subject_id=attendance_data.subject_id,
        date=attendance_date,
        status=attendance_data.status,
        remark=attendance_data.remark,
    )
    db.add(attendance)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Attendance already exists for this date and course.")
    db.refresh(attendance)
    return _serialize_attendance(attendance)


@router.put("/{attendance_id}", response_model=AttendanceResponse)
def update_attendance(
    attendance_id: int,
    attendance_data: AttendanceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _ensure_attendance_write_access(current_user)
    attendance = db.query(Attendance).filter(Attendance.id == attendance_id).first()
    if not attendance:
        raise HTTPException(status_code=404, detail="Attendance not found.")

    _has_subject_or_class_access(
        current_user,
        db,
        class_id=attendance.class_id,
        subject_id=attendance.subject_id,
        class_error_detail="You do not have access to this attendance record.",
    )
    if attendance.subject_id:
        course = ensure_course_access_http(attendance.subject_id, current_user, db)
        _ensure_attendance_course_write_access(current_user, course)

    if attendance_data.status is not None:
        attendance.status = attendance_data.status
    if attendance_data.remark is not None:
        attendance.remark = attendance_data.remark

    db.commit()
    db.refresh(attendance)
    return _serialize_attendance(attendance)


@router.delete("/{attendance_id}")
def delete_attendance(
    attendance_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _ensure_attendance_write_access(current_user)
    attendance = db.query(Attendance).filter(Attendance.id == attendance_id).first()
    if not attendance:
        raise HTTPException(status_code=404, detail="Attendance not found.")

    _has_subject_or_class_access(
        current_user,
        db,
        class_id=attendance.class_id,
        subject_id=attendance.subject_id,
        class_error_detail="You do not have access to this attendance record.",
    )
    if attendance.subject_id:
        course = ensure_course_access_http(attendance.subject_id, current_user, db)
        _ensure_attendance_course_write_access(current_user, course)

    db.delete(attendance)
    db.commit()
    return {"message": "Attendance deleted successfully."}


@router.get("/statistics/class/{class_id}")
def get_class_attendance_stats(
    class_id: int,
    subject_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _has_subject_or_class_access(
        current_user,
        db,
        class_id=class_id,
        subject_id=subject_id,
        class_error_detail="You do not have access to this class.",
    )

    query = db.query(Attendance).filter(Attendance.class_id == class_id)
    if subject_id:
        query = query.filter(Attendance.subject_id == subject_id)
    if start_date:
        try:
            start_dt = _parse_attendance_query_boundary(start_date, end_of_day=False)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format.")
        query = query.filter(Attendance.date >= start_dt)
    if end_date:
        try:
            end_dt = _parse_attendance_query_boundary(end_date, end_of_day=True)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format.")
        query = query.filter(Attendance.date <= end_dt)

    attendances = query.all()
    stats = {"total": len(attendances), "present": 0, "absent": 0, "late": 0, "leave": 0}
    for attendance in attendances:
        stats[attendance.status] = stats.get(attendance.status, 0) + 1
    stats["attendance_rate"] = round((stats["present"] / stats["total"]) * 100, 2) if stats["total"] else 0
    return stats


@router.post("/batch")
async def create_attendances_batch(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _ensure_attendance_write_access(current_user)
    import json

    body = await request.body()
    body_str = body.decode("utf-8").replace("\x00", "").replace("\ufeff", "")
    try:
        data = json.loads(body_str)
        attendances_list = data.get("attendances", []) if isinstance(data, dict) else data
    except Exception as exc:
        return {"success": 0, "failed": 1, "errors": [f"JSON parse error: {exc}"]}

    if not attendances_list:
        return {"success": 0, "failed": 0, "errors": ["No valid attendance data found."]}

    results = []
    errors = []
    normalized_rows = []

    for index, attendance_data in enumerate(attendances_list, 1):
        if not isinstance(attendance_data, dict):
            errors.append(f"Row {index}: invalid record format.")
            continue

        class_id = attendance_data.get("class_id")
        student_no = attendance_data.get("student_no")
        if not student_no:
            errors.append(f"Row {index}: missing student number.")
            continue

        subject_id = attendance_data.get("subject_id")
        try:
            _has_subject_or_class_access(
                current_user,
                db,
                class_id=class_id,
                subject_id=subject_id,
                class_error_detail="You do not have access to this class.",
            )
        except HTTPException:
            errors.append(f"Row {index}: no access to the selected class.")
            continue

        student = db.query(Student).filter(Student.student_no == student_no, Student.class_id == class_id).first()
        if not student:
            errors.append(f"Row {index}: student not found in the selected class.")
            continue

        if subject_id:
            course = db.query(Subject).filter(Subject.id == subject_id).first()
            if not course:
                errors.append(f"Row {index}: course not found.")
                continue
            if not is_course_instructor(current_user, course):
                errors.append(f"Row {index}: only the assigned course teacher can modify course attendance.")
                continue
            if not _attendance_subject_allows_class(db, course, class_id):
                errors.append(f"Row {index}: selected course does not belong to this class.")
                continue

        status = attendance_data.get("status", "present")
        if status not in ["present", "absent", "late", "leave"]:
            errors.append(f"Row {index}: invalid attendance status.")
            continue

        attendance_date = attendance_data.get("date")
        if not attendance_date:
            errors.append(f"Row {index}: missing date.")
            continue
        try:
            attendance_date = _parse_attendance_date(attendance_date)
        except ValueError:
            errors.append(f"Row {index}: invalid date format.")
            continue

        remark = attendance_data.get("remark", "")
        normalized_rows.append(
            {
                "student_id": student.id,
                "class_id": class_id,
                "subject_id": subject_id,
                "attendance_date": attendance_date,
                "status": status,
                "remark": remark,
            }
        )
        _upsert_attendance_row(
            db,
            student_id=student.id,
            class_id=class_id,
            subject_id=subject_id,
            attendance_date=attendance_date,
            status=status,
            remark=remark,
        )
        results.append(f"{student.name} {attendance_date.strftime('%Y-%m-%d')}")

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        for row in normalized_rows:
            _upsert_attendance_row(db, **row)
        db.commit()
    except Exception as exc:
        db.rollback()
        errors.append(f"Database error: {exc}")

    return {"success": len(results), "failed": len(errors), "errors": errors}


@router.post("/class-batch")
async def create_class_attendance_batch(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _ensure_attendance_write_access(current_user)
    import json

    body = await request.body()
    body_str = body.decode("utf-8").replace("\x00", "").replace("\ufeff", "")

    try:
        data = json.loads(body_str)
    except Exception as exc:
        return {"success": 0, "failed": 1, "errors": [f"JSON parse error: {exc}"]}

    class_id = data.get("class_id")
    subject_id = data.get("subject_id")
    attendance_date = data.get("date")
    status = data.get("status", "present")
    remark = data.get("remark", "")

    if not class_id or not attendance_date:
        return {"success": 0, "failed": 1, "errors": ["Missing class_id or date."]}

    if subject_id:
        try:
            course = ensure_course_access_http(subject_id, current_user, db)
        except HTTPException:
            return {"success": 0, "failed": 1, "errors": ["No access to the selected course."]}
        _ensure_attendance_course_write_access(current_user, course)
        if not _attendance_subject_allows_class(db, course, class_id):
            return {"success": 0, "failed": 1, "errors": ["Course does not belong to the selected class."]}
    else:
        class_ids = set(get_accessible_class_ids(current_user, db))
        if class_id not in class_ids:
            return {"success": 0, "failed": 1, "errors": ["No access to the selected class."]}

    try:
        attendance_date = _parse_attendance_date(attendance_date)
    except ValueError:
        return {"success": 0, "failed": 1, "errors": ["Invalid date format."]}

    students = db.query(Student).filter(Student.class_id == class_id).all()
    if not students:
        return {"success": 0, "failed": 1, "errors": ["No students found in this class."]}

    results = []
    normalized_rows = []
    for student in students:
        normalized_rows.append(
            {
                "student_id": student.id,
                "class_id": class_id,
                "subject_id": subject_id,
                "attendance_date": attendance_date,
                "status": status,
                "remark": remark,
            }
        )
        _upsert_attendance_row(
            db,
            student_id=student.id,
            class_id=class_id,
            subject_id=subject_id,
            attendance_date=attendance_date,
            status=status,
            remark=remark,
        )
        results.append(student.name)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        for row in normalized_rows:
            _upsert_attendance_row(db, **row)
        db.commit()
    return {"success": len(results), "failed": 0, "errors": [], "message": f"Updated attendance for {len(results)} students."}


@router.get("/statistics/student/{student_id}")
def get_student_attendance_stats(
    student_id: int,
    subject_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")

    _has_subject_or_class_access(
        current_user,
        db,
        class_id=student.class_id,
        subject_id=subject_id,
        class_error_detail="You do not have access to this student.",
    )

    query = db.query(Attendance).filter(Attendance.student_id == student_id)
    if subject_id:
        query = query.filter(Attendance.subject_id == subject_id)
    if start_date:
        try:
            start_dt = _parse_attendance_query_boundary(start_date, end_of_day=False)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format.")
        query = query.filter(Attendance.date >= start_dt)
    if end_date:
        try:
            end_dt = _parse_attendance_query_boundary(end_date, end_of_day=True)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format.")
        query = query.filter(Attendance.date <= end_dt)

    attendances = query.all()
    stats = {"total": len(attendances), "present": 0, "absent": 0, "late": 0, "leave": 0}
    for attendance in attendances:
        stats[attendance.status] = stats.get(attendance.status, 0) + 1
    stats["attendance_rate"] = round((stats["present"] / stats["total"]) * 100, 2) if stats["total"] else 0
    return stats
