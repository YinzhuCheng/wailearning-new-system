from typing import List

from sqlalchemy import select

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.core.auth import get_current_active_user
from apps.backend.courseeval_backend.domains.courses.class_scope import get_accessible_class_ids
from apps.backend.courseeval_backend.db.database import get_db
from apps.backend.courseeval_backend.db.models import Class, Student, Subject, SubjectClassLink, User, UserRole
from apps.backend.courseeval_backend.api.schemas import ClassCreate, ClassResponse, ClassUpdate


router = APIRouter(prefix="/api/classes", tags=["班级管理"])


@router.get("", response_model=List[ClassResponse])
def get_classes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    class_ids = get_accessible_class_ids(current_user, db)
    if not class_ids:
        return []

    classes = db.query(Class).filter(Class.id.in_(class_ids)).all()

    result = []
    for class_obj in classes:
        student_count = db.query(Student).filter(Student.class_id == class_obj.id).count()
        result.append(
            ClassResponse(
                id=class_obj.id,
                name=class_obj.name,
                grade=class_obj.grade,
                created_at=class_obj.created_at,
                student_count=student_count,
            )
        )
    return result


@router.post("", response_model=ClassResponse)
def create_class(
    class_data: ClassCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only administrators can create classes.")

    new_class = Class(name=class_data.name, grade=class_data.grade)
    db.add(new_class)
    db.commit()
    db.refresh(new_class)
    return ClassResponse(
        id=new_class.id,
        name=new_class.name,
        grade=new_class.grade,
        created_at=new_class.created_at,
        student_count=0,
    )


@router.get("/{class_id}", response_model=ClassResponse)
def get_class(
    class_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    class_ids = get_accessible_class_ids(current_user, db)
    if class_id not in class_ids:
        raise HTTPException(status_code=403, detail="You do not have access to this class.")

    class_obj = db.query(Class).filter(Class.id == class_id).first()
    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found.")

    student_count = db.query(Student).filter(Student.class_id == class_id).count()
    return ClassResponse(
        id=class_obj.id,
        name=class_obj.name,
        grade=class_obj.grade,
        created_at=class_obj.created_at,
        student_count=student_count,
    )


@router.put("/{class_id}", response_model=ClassResponse)
def update_class(
    class_id: int,
    class_data: ClassUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only administrators can update classes.")

    class_obj = db.query(Class).filter(Class.id == class_id).first()
    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found.")

    if class_data.name is not None:
        class_obj.name = class_data.name
    if class_data.grade is not None:
        class_obj.grade = class_data.grade

    db.commit()
    db.refresh(class_obj)

    student_count = db.query(Student).filter(Student.class_id == class_id).count()
    return ClassResponse(
        id=class_obj.id,
        name=class_obj.name,
        grade=class_obj.grade,
        created_at=class_obj.created_at,
        student_count=student_count,
    )


@router.delete("/{class_id}")
def delete_class(
    class_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only administrators can delete classes.")

    class_obj = db.query(Class).filter(Class.id == class_id).first()
    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found.")

    students = db.query(Student).filter(Student.class_id == class_id).count()
    if students > 0:
        raise HTTPException(status_code=400, detail="This class still contains students and cannot be deleted.")

    linked_subject_ids = (
        select(SubjectClassLink.subject_id)
        .filter(SubjectClassLink.class_id == class_id)
    )
    courses = (
        db.query(Subject)
        .filter((Subject.class_id == class_id) | (Subject.id.in_(linked_subject_ids)))
        .count()
    )
    if courses > 0:
        raise HTTPException(
            status_code=400,
            detail="This class still has courses assigned and cannot be deleted.",
        )

    db.delete(class_obj)
    db.commit()
    return {"message": "Class deleted successfully."}
