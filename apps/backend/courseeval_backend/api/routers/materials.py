from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import desc, asc
from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.core.auth import get_current_active_user
from apps.backend.courseeval_backend.attachments import delete_attachment_file_if_unreferenced
from apps.backend.courseeval_backend.domains.courses.access import (
    ensure_course_access_http,
    is_course_instructor,
    subject_linked_class_ids,
)
from apps.backend.courseeval_backend.domains.text_content_format import normalize_content_format
from apps.backend.courseeval_backend.db.database import get_db
from apps.backend.courseeval_backend.db.models import Class, CourseMaterial, CourseMaterialChapter, CourseMaterialSection, User, UserRole
from apps.backend.courseeval_backend.domains.courses.class_scope import get_accessible_class_ids
from apps.backend.courseeval_backend.api.schemas import (
    CourseMaterialCreate,
    CourseMaterialListResponse,
    CourseMaterialPlacement,
    CourseMaterialResponse,
    CourseMaterialUpdate,
)
from apps.backend.courseeval_backend.services.logging import LogService

router = APIRouter(prefix="/api/materials", tags=["课程资料"])


def can_publish_materials(user: User) -> bool:
    return user.role in [UserRole.ADMIN, UserRole.CLASS_TEACHER, UserRole.TEACHER]


def _get_uncategorized_chapter(db: Session, subject_id: int) -> CourseMaterialChapter:
    unc = (
        db.query(CourseMaterialChapter)
        .filter(
            CourseMaterialChapter.subject_id == subject_id,
            CourseMaterialChapter.is_uncategorized.is_(True),
        )
        .first()
    )
    if not unc:
        unc = CourseMaterialChapter(
            subject_id=subject_id,
            parent_id=None,
            title="未分类",
            sort_order=0,
            is_uncategorized=True,
        )
        db.add(unc)
        db.flush()
    return unc


def _get_default_material_chapter(db: Session, subject_id: int) -> CourseMaterialChapter:
    structured = (
        db.query(CourseMaterialChapter)
        .filter(
            CourseMaterialChapter.subject_id == subject_id,
            CourseMaterialChapter.is_uncategorized.is_(False),
        )
        .order_by(CourseMaterialChapter.sort_order.asc(), CourseMaterialChapter.id.asc())
        .first()
    )
    if structured:
        return structured
    return _get_uncategorized_chapter(db, subject_id)


def _chapter_match_score(chapter: CourseMaterialChapter, title: str, content: str) -> int:
    chapter_title = (chapter.title or "").strip().lower()
    haystack = f"{title} {content}".lower()
    if not chapter_title or not haystack:
        return 0

    score = 0
    if chapter_title in haystack:
        score += max(len(chapter_title), 4) * 10

    normalized = chapter_title.replace("：", " ").replace(":", " ").replace("-", " ")
    for token in normalized.split():
        if len(token) >= 2 and token in haystack:
            score += len(token) * 6

    for marker in ("第一", "第二", "第三", "第四", "第五", "第六", "1.1", "1.2", "2.1", "2.2", "3.1", "3.2"):
        if marker in chapter_title and marker in haystack:
            score += 24

    return score


def _infer_chapter_ids_for_material(db: Session, subject_id: int, title: str | None, content: str | None) -> list[int]:
    chapters = (
        db.query(CourseMaterialChapter)
        .filter(
            CourseMaterialChapter.subject_id == subject_id,
            CourseMaterialChapter.is_uncategorized.is_(False),
        )
        .order_by(CourseMaterialChapter.sort_order.asc(), CourseMaterialChapter.id.asc())
        .all()
    )
    if not chapters:
        return [_get_uncategorized_chapter(db, subject_id).id]

    title_text = (title or "").strip()
    content_text = (content or "").strip()
    scored = [(chapter.id, _chapter_match_score(chapter, title_text, content_text)) for chapter in chapters]
    best_id, best_score = max(scored, key=lambda item: item[1], default=(chapters[0].id, 0))
    if best_score > 0:
        return [best_id]
    return [chapters[0].id]


def _validate_chapter_ids_exist(db: Session, subject_id: int, chapter_ids: Optional[List[int]]) -> None:
    default_chapter = _get_default_material_chapter(db, subject_id)
    ids = list(chapter_ids) if chapter_ids else []
    if not ids:
        ids = [default_chapter.id]
    seen = set()
    ordered_unique: List[int] = []
    for cid in ids:
        if cid in seen:
            continue
        seen.add(cid)
        ordered_unique.append(cid)
    for cid in ordered_unique:
        ch = db.query(CourseMaterialChapter).filter(CourseMaterialChapter.id == cid).first()
        if not ch or int(ch.subject_id) != int(subject_id):
            raise HTTPException(status_code=400, detail="Invalid chapter for this course.")


def _serialize_material(db: Session, material: CourseMaterial) -> CourseMaterialResponse:
    placements: List[CourseMaterialPlacement] = []
    rows = (
        db.query(CourseMaterialSection, CourseMaterialChapter)
        .join(CourseMaterialChapter, CourseMaterialSection.chapter_id == CourseMaterialChapter.id)
        .filter(CourseMaterialSection.material_id == material.id)
        .order_by(CourseMaterialSection.sort_order.asc(), CourseMaterialSection.id.asc())
        .all()
    )
    for sec, ch in rows:
        placements.append(
            CourseMaterialPlacement(
                section_id=sec.id,
                chapter_id=ch.id,
                chapter_title=ch.title,
                sort_order=sec.sort_order,
            )
        )
    chapter_ids = [p.chapter_id for p in placements]
    return CourseMaterialResponse(
        id=material.id,
        title=material.title,
        content=material.content,
        content_format=normalize_content_format(getattr(material, "content_format", None)),
        attachment_name=material.attachment_name,
        attachment_url=material.attachment_url,
        class_id=material.class_id,
        subject_id=material.subject_id,
        chapter_ids=chapter_ids,
        created_by=material.created_by,
        created_at=material.created_at,
        updated_at=material.updated_at,
        class_name=material.class_obj.name if material.class_obj else None,
        subject_name=material.subject.name if material.subject else None,
        creator_name=material.creator.real_name if material.creator else None,
        placements=placements,
        discussion_requires_context=material.subject_id is None,
    )


def _apply_material_placements(
    db: Session,
    *,
    material_id: int,
    subject_id: int,
    chapter_ids: Optional[List[int]],
) -> None:
    default_chapter = _get_default_material_chapter(db, subject_id)
    ids = list(chapter_ids) if chapter_ids else []
    if not ids:
        ids = [default_chapter.id]

    seen = set()
    ordered_unique: List[int] = []
    for cid in ids:
        if cid in seen:
            continue
        seen.add(cid)
        ordered_unique.append(cid)

    for cid in ordered_unique:
        ch = db.query(CourseMaterialChapter).filter(CourseMaterialChapter.id == cid).first()
        if not ch or int(ch.subject_id) != int(subject_id):
            raise HTTPException(status_code=400, detail="Invalid chapter for this course.")

    db.query(CourseMaterialSection).filter(CourseMaterialSection.material_id == material_id).delete(
        synchronize_session=False
    )
    for idx, cid in enumerate(ordered_unique):
        db.add(
            CourseMaterialSection(
                material_id=material_id,
                chapter_id=cid,
                sort_order=idx,
            )
        )


@router.get("", response_model=CourseMaterialListResponse)
def get_materials(
    class_id: Optional[int] = None,
    subject_id: Optional[int] = None,
    chapter_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    query = db.query(CourseMaterial)
    allowed_class_ids = get_accessible_class_ids(current_user, db)

    if subject_id:
        ensure_course_access_http(subject_id, current_user, db)
        query = query.filter(CourseMaterial.subject_id == subject_id)

    if current_user.role != UserRole.ADMIN:
        if subject_id is None and not allowed_class_ids:
            return CourseMaterialListResponse(total=0, data=[])
        if subject_id is None:
            query = query.filter(CourseMaterial.class_id.in_(allowed_class_ids))

    if class_id:
        if current_user.role != UserRole.ADMIN and subject_id is None and class_id not in allowed_class_ids:
            return CourseMaterialListResponse(total=0, data=[])
        query = query.filter(CourseMaterial.class_id == class_id)

    if chapter_id is not None:
        ch = db.query(CourseMaterialChapter).filter(CourseMaterialChapter.id == chapter_id).first()
        if not ch:
            return CourseMaterialListResponse(total=0, data=[])
        if subject_id and int(ch.subject_id) != int(subject_id):
            return CourseMaterialListResponse(total=0, data=[])
        query = query.join(
            CourseMaterialSection,
            CourseMaterialSection.material_id == CourseMaterial.id,
        ).filter(
            CourseMaterialSection.chapter_id == chapter_id,
            CourseMaterial.subject_id == ch.subject_id,
        )

    total = query.count()
    if chapter_id is None:
        materials = (
            query.order_by(desc(CourseMaterial.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
    else:
        materials = (
            query.order_by(asc(CourseMaterialSection.sort_order), desc(CourseMaterial.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
    return CourseMaterialListResponse(total=total, data=[_serialize_material(db, item) for item in materials])


@router.get("/{material_id}", response_model=CourseMaterialResponse)
def get_material(
    material_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    material = db.query(CourseMaterial).filter(CourseMaterial.id == material_id).first()
    if not material:
        raise HTTPException(status_code=404, detail="Material not found.")

    if material.subject_id:
        ensure_course_access_http(material.subject_id, current_user, db)
    else:
        allowed_class_ids = get_accessible_class_ids(current_user, db)
        if current_user.role != UserRole.ADMIN and material.class_id not in allowed_class_ids:
            raise HTTPException(status_code=403, detail="You do not have access to this material.")

    return _serialize_material(db, material)


@router.post("", response_model=CourseMaterialResponse)
def create_material(
    data: CourseMaterialCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not can_publish_materials(current_user):
        raise HTTPException(status_code=403, detail="Only teachers can publish materials.")

    class_obj = db.query(Class).filter(Class.id == data.class_id).first()
    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found.")

    effective_chapter_ids = list(data.chapter_ids) if data.chapter_ids else None

    if data.subject_id:
        course = ensure_course_access_http(data.subject_id, current_user, db)
        if not is_course_instructor(current_user, course):
            raise HTTPException(status_code=403, detail="Only the assigned course teacher can publish materials.")
        linked = set(subject_linked_class_ids(db, course.id))
        if linked:
            if data.class_id not in linked:
                raise HTTPException(status_code=400, detail="课程资料的所属班级必须是该必修课已绑定的行政班之一。")
        elif course.class_id and course.class_id != data.class_id:
            raise HTTPException(status_code=400, detail="The selected course does not belong to this class.")

        if not effective_chapter_ids:
            effective_chapter_ids = _infer_chapter_ids_for_material(db, data.subject_id, data.title, data.content)

        _validate_chapter_ids_exist(db, data.subject_id, effective_chapter_ids)
    else:
        if current_user.role != UserRole.ADMIN:
            allowed_class_ids = get_accessible_class_ids(current_user, db)
            if data.class_id not in allowed_class_ids:
                raise HTTPException(status_code=403, detail="You do not have access to this class.")

    material = CourseMaterial(
        title=data.title,
        content=data.content,
        content_format=normalize_content_format(getattr(data, "content_format", None)),
        attachment_name=data.attachment_name,
        attachment_url=data.attachment_url,
        class_id=data.class_id,
        subject_id=data.subject_id,
        created_by=current_user.id,
    )
    db.add(material)
    db.flush()

    if data.subject_id:
        _apply_material_placements(
            db,
            material_id=material.id,
            subject_id=data.subject_id,
            chapter_ids=effective_chapter_ids,
        )

    db.commit()
    db.refresh(material)

    LogService.log_create(
        db,
        user_id=current_user.id,
        username=current_user.username,
        target_type="课程资料",
        target_id=material.id,
        target_name=material.title,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return _serialize_material(db, material)


@router.put("/{material_id}", response_model=CourseMaterialResponse)
def update_material(
    material_id: int,
    data: CourseMaterialUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not can_publish_materials(current_user):
        raise HTTPException(status_code=403, detail="Only teachers can update materials.")

    material = db.query(CourseMaterial).filter(CourseMaterial.id == material_id).first()
    if not material:
        raise HTTPException(status_code=404, detail="Material not found.")

    if material.subject_id:
        ensure_course_access_http(material.subject_id, current_user, db)
    else:
        allowed_class_ids = get_accessible_class_ids(current_user, db)
        if current_user.role != UserRole.ADMIN and material.class_id not in allowed_class_ids:
            raise HTTPException(status_code=403, detail="You do not have access to this material.")

    if current_user.role != UserRole.ADMIN and material.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="You can only edit your own materials.")

    old_attachment_url = material.attachment_url

    if data.title is not None:
        material.title = data.title
    if data.content is not None:
        material.content = data.content
    if data.content_format is not None:
        material.content_format = normalize_content_format(data.content_format)
    if data.remove_attachment:
        material.attachment_name = None
        material.attachment_url = None
    elif data.attachment_url is not None:
        material.attachment_name = data.attachment_name
        material.attachment_url = data.attachment_url

    if material.subject_id and data.chapter_ids is not None:
        _validate_chapter_ids_exist(db, material.subject_id, data.chapter_ids)
        _apply_material_placements(
            db,
            material_id=material.id,
            subject_id=material.subject_id,
            chapter_ids=data.chapter_ids,
        )

    db.commit()
    db.refresh(material)

    if data.remove_attachment or (
        data.attachment_url is not None and old_attachment_url and old_attachment_url != material.attachment_url
    ):
        delete_attachment_file_if_unreferenced(db, old_attachment_url)

    LogService.log_update(
        db,
        user_id=current_user.id,
        username=current_user.username,
        target_type="课程资料",
        target_id=material.id,
        target_name=material.title,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return _serialize_material(db, material)


@router.delete("/{material_id}")
def delete_material(
    material_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not can_publish_materials(current_user):
        raise HTTPException(status_code=403, detail="Only teachers can delete materials.")

    material = db.query(CourseMaterial).filter(CourseMaterial.id == material_id).first()
    if not material:
        raise HTTPException(status_code=404, detail="Material not found.")

    if current_user.role != UserRole.ADMIN and material.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="You can only delete your own materials.")

    title = material.title
    attachment_url = material.attachment_url
    db.delete(material)
    db.flush()
    delete_attachment_file_if_unreferenced(db, attachment_url)
    db.commit()

    LogService.log_delete(
        db,
        user_id=current_user.id,
        username=current_user.username,
        target_type="课程资料",
        target_id=material_id,
        target_name=title,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return {"message": "Material deleted successfully."}
