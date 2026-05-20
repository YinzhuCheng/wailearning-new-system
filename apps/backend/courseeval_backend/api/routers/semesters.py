from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import List
from apps.backend.courseeval_backend.db.database import get_db
from apps.backend.courseeval_backend.db.models import Score, Subject, User, Semester
from apps.backend.courseeval_backend.api.schemas import SemesterCreate, SemesterResponse
from apps.backend.courseeval_backend.core.auth import get_current_active_user
from apps.backend.courseeval_backend.core.permissions import is_admin
from apps.backend.courseeval_backend.semester_utils import DEFAULT_SEMESTERS, normalize_semester_name

router = APIRouter(prefix="/api/semesters", tags=["学期管理"])
def init_default_semesters(db: Session):
    for sem_data in DEFAULT_SEMESTERS:
        existing = db.query(Semester).filter(Semester.name == sem_data["name"]).first()
        if not existing:
            semester = Semester(
                name=sem_data["name"],
                year=sem_data["year"],
                is_active=True
            )
            db.add(semester)
    
    try:
        db.commit()
    except IntegrityError:
        db.rollback()


def sync_semester_name_references(db: Session, old_name: str, new_name: str) -> None:
    if not old_name or old_name == new_name:
        return

    db.query(Subject).filter(Subject.semester == old_name).update(
        {Subject.semester: new_name},
        synchronize_session=False
    )
    db.query(Score).filter(Score.semester == old_name).update(
        {Score.semester: new_name},
        synchronize_session=False
    )

@router.get("", response_model=List[SemesterResponse])
def get_semesters(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    semesters = db.query(Semester).order_by(Semester.year.desc(), Semester.name.desc()).all()
    if not semesters:
        init_default_semesters(db)
        semesters = db.query(Semester).order_by(Semester.year.desc(), Semester.name.desc()).all()
    return semesters

@router.post("", response_model=SemesterResponse)
def create_semester(
    semester_data: SemesterCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    if not is_admin(current_user):
        raise HTTPException(status_code=403, detail="只有管理员可以创建学期")
    normalized_name = normalize_semester_name(semester_data.name)
    existing = db.query(Semester).filter(Semester.name == normalized_name).first()
    if existing:
        raise HTTPException(status_code=400, detail="学期名称已存在")
    
    semester = Semester(
        name=normalized_name,
        year=semester_data.year,
        is_active=True
    )
    db.add(semester)
    db.commit()
    db.refresh(semester)
    return semester

@router.put("/{semester_id}", response_model=SemesterResponse)
def update_semester(
    semester_id: int,
    semester_data: SemesterCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    if not is_admin(current_user):
        raise HTTPException(status_code=403, detail="只有管理员可以修改学期")
    semester = db.query(Semester).filter(Semester.id == semester_id).first()
    if not semester:
        raise HTTPException(status_code=404, detail="学期不存在")
    
    normalized_name = normalize_semester_name(semester_data.name)
    existing = db.query(Semester).filter(
        Semester.name == normalized_name,
        Semester.id != semester_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="学期名称已存在")
    
    old_name = semester.name
    semester.name = normalized_name
    semester.year = semester_data.year
    sync_semester_name_references(db, old_name, normalized_name)
    db.commit()
    db.refresh(semester)
    return semester

@router.delete("/{semester_id}")
def delete_semester(
    semester_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    if not is_admin(current_user):
        raise HTTPException(status_code=403, detail="只有管理员可以删除学期")
    semester = db.query(Semester).filter(Semester.id == semester_id).first()
    if not semester:
        raise HTTPException(status_code=404, detail="学期不存在")
    
    db.delete(semester)
    db.commit()
    return {"message": "学期删除成功"}

@router.post("/init")
def initialize_semesters(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    if not is_admin(current_user):
        raise HTTPException(status_code=403, detail="只有管理员可以初始化学期")
    init_default_semesters(db)
    semesters = db.query(Semester).order_by(Semester.year.desc(), Semester.name.desc()).all()
    return {
        "message": "初始化成功",
        "count": len(semesters),
        "semesters": semesters
    }
