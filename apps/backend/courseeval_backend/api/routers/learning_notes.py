"""Learning notes owned by teachers or students.

Notes are intentionally separate from course materials because students may
create and freely edit their own copied outline, while course materials remain a
teacher-published course surface.
"""

from __future__ import annotations

import threading
from types import SimpleNamespace
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import asc, desc, or_
from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.core.auth import get_current_active_user
from apps.backend.courseeval_backend.db.database import SessionLocal, get_db
from apps.backend.courseeval_backend.db.models import (
    CourseMaterial,
    CourseMaterialChapter,
    CourseMaterialSection,
    LearningNote,
    LearningNoteChapter,
    LearningNoteDiscussionEntry,
    LearningNoteResource,
    Subject,
    User,
)
from apps.backend.courseeval_backend.domains.courses.access import ensure_course_access_http, get_accessible_course_ids
from apps.backend.courseeval_backend.domains.discussion_links import (
    LEARNING_NOTE_DISCUSSION_TARGET_ID_OFFSET,
    serialize_linked_targets_for_viewer,
    validate_visible_linked_targets,
)
from apps.backend.courseeval_backend.domains.text_content_format import body_text_for_grading_llm, normalize_content_format
from apps.backend.courseeval_backend.llm_discussion import (
    _call_discussion_with_routing,
    discussion_llm_user_is_quota_exempt,
    resolve_student_for_discussion_llm,
)
from apps.backend.courseeval_backend.llm_grading import ensure_course_llm_config
from apps.backend.courseeval_backend.domains.llm.discussion_ui import strip_llm_ui_prefix
from apps.backend.courseeval_backend.domains.llm.errors import NonRetryableLLMError
from apps.backend.courseeval_backend.api.schemas import (
    LearningNoteChapterCreate,
    LearningNoteChapterNode,
    LearningNoteChapterUpdate,
    LearningNoteCreate,
    LearningNoteDetailResponse,
    LearningNoteDiscussionCreate,
    LearningNoteDiscussionEntryResponse,
    LearningNoteDiscussionListResponse,
    LearningNoteListResponse,
    LearningNoteResourceCreate,
    LearningNoteResourceResponse,
    LearningNoteResourceUpdate,
    LearningNoteResponse,
    LearningNoteUpdate,
    LearningNoteVisibility,
)
from apps.backend.courseeval_backend.services.logging import LogService

router = APIRouter(prefix="/api/learning-notes", tags=["学习笔记"])

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
MAX_DISCUSSION_BODY_LEN = 8000


def _is_owner(note: LearningNote, user: User) -> bool:
    return int(note.owner_user_id) == int(user.id)


def _public_note_is_readable(note: LearningNote, user: User, db: Session) -> bool:
    if note.visibility != LearningNoteVisibility.COURSE.value:
        return False
    if note.subject_id is None:
        return True
    try:
        ensure_course_access_http(int(note.subject_id), user, db)
        return True
    except HTTPException:
        return False


def _ensure_note_read(note: LearningNote, user: User, db: Session) -> None:
    if _is_owner(note, user):
        return
    if _public_note_is_readable(note, user, db):
        return
    raise HTTPException(status_code=403, detail="You do not have access to this learning note.")


def _ensure_note_owner(note: LearningNote, user: User) -> None:
    if not _is_owner(note, user):
        raise HTTPException(status_code=403, detail="Only the note owner can change this learning note.")


def _load_note(note_id: int, db: Session) -> LearningNote:
    note = db.query(LearningNote).filter(LearningNote.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Learning note not found.")
    return note


def _validate_visibility_and_course(
    *,
    visibility: str,
    subject_id: Optional[int],
    user: User,
    db: Session,
) -> Optional[Subject]:
    course = None
    if subject_id is not None:
        course = ensure_course_access_http(int(subject_id), user, db)
    return course


def _serialize_note(note: LearningNote) -> LearningNoteResponse:
    return LearningNoteResponse(
        id=note.id,
        title=note.title,
        description=note.description,
        owner_user_id=note.owner_user_id,
        owner_real_name=note.owner.real_name if note.owner else None,
        owner_username=note.owner.username if note.owner else None,
        owner_role=note.owner.role if note.owner else None,
        subject_id=note.subject_id,
        subject_name=note.subject.name if note.subject else None,
        visibility=note.visibility,
        source_subject_id=note.source_subject_id,
        source_subject_name=note.source_subject.name if note.source_subject else None,
        copied_materials=bool(note.copied_materials),
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


def _serialize_resource(resource: LearningNoteResource) -> LearningNoteResourceResponse:
    return LearningNoteResourceResponse(
        id=resource.id,
        note_id=resource.note_id,
        chapter_id=resource.chapter_id,
        title=resource.title,
        content=resource.content,
        content_format=normalize_content_format(resource.content_format),
        attachment_name=resource.attachment_name,
        attachment_url=resource.attachment_url,
        source_material_id=resource.source_material_id,
        sort_order=resource.sort_order,
        created_at=resource.created_at,
        updated_at=resource.updated_at,
    )


def _build_note_tree(note_id: int, db: Session) -> tuple[list[LearningNoteChapterNode], list[LearningNoteResourceResponse]]:
    chapters = (
        db.query(LearningNoteChapter)
        .filter(LearningNoteChapter.note_id == note_id)
        .order_by(LearningNoteChapter.sort_order.asc(), LearningNoteChapter.id.asc())
        .all()
    )
    resources = (
        db.query(LearningNoteResource)
        .filter(LearningNoteResource.note_id == note_id)
        .order_by(LearningNoteResource.sort_order.asc(), LearningNoteResource.id.asc())
        .all()
    )
    resources_by_chapter: dict[Optional[int], list[LearningNoteResourceResponse]] = {}
    for resource in resources:
        resources_by_chapter.setdefault(resource.chapter_id, []).append(_serialize_resource(resource))

    by_parent: dict[Optional[int], list[LearningNoteChapter]] = {}
    for chapter in chapters:
        by_parent.setdefault(chapter.parent_id, []).append(chapter)

    def build(parent_id: Optional[int]) -> list[LearningNoteChapterNode]:
        nodes: list[LearningNoteChapterNode] = []
        for chapter in by_parent.get(parent_id, []):
            nodes.append(
                LearningNoteChapterNode(
                    id=chapter.id,
                    note_id=chapter.note_id,
                    parent_id=chapter.parent_id,
                    title=chapter.title,
                    sort_order=chapter.sort_order,
                    source_chapter_id=chapter.source_chapter_id,
                    resources=resources_by_chapter.get(chapter.id, []),
                    children=build(chapter.id),
                )
            )
        return nodes

    return build(None), resources_by_chapter.get(None, [])


def _serialize_note_detail(note: LearningNote, db: Session) -> LearningNoteDetailResponse:
    chapters, loose_resources = _build_note_tree(note.id, db)
    base = _serialize_note(note).model_dump()
    return LearningNoteDetailResponse(**base, chapters=chapters, loose_resources=loose_resources)


def _copy_course_outline(
    *,
    note: LearningNote,
    subject_id: int,
    copy_materials: bool,
    db: Session,
) -> None:
    course = db.query(Subject).filter(Subject.id == subject_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Source course not found.")

    source_chapters = (
        db.query(CourseMaterialChapter)
        .filter(CourseMaterialChapter.subject_id == subject_id)
        .order_by(CourseMaterialChapter.sort_order.asc(), CourseMaterialChapter.id.asc())
        .all()
    )
    chapter_id_map: dict[int, int] = {}
    pending = list(source_chapters)
    while pending:
        progressed = False
        for source in pending[:]:
            if source.parent_id is not None and source.parent_id not in chapter_id_map:
                continue
            copied = LearningNoteChapter(
                note_id=note.id,
                parent_id=chapter_id_map.get(source.parent_id),
                title=source.title,
                sort_order=source.sort_order,
                source_chapter_id=source.id,
            )
            db.add(copied)
            db.flush()
            chapter_id_map[source.id] = copied.id
            pending.remove(source)
            progressed = True
        if not progressed:
            raise HTTPException(status_code=400, detail="Source course chapter tree is not copyable.")

    if not copy_materials:
        return

    rows = (
        db.query(CourseMaterialSection, CourseMaterial)
        .join(CourseMaterial, CourseMaterial.id == CourseMaterialSection.material_id)
        .join(CourseMaterialChapter, CourseMaterialChapter.id == CourseMaterialSection.chapter_id)
        .filter(CourseMaterial.subject_id == subject_id)
        .order_by(CourseMaterialSection.sort_order.asc(), CourseMaterialSection.id.asc())
        .all()
    )
    for section, material in rows:
        target_chapter_id = chapter_id_map.get(section.chapter_id)
        copied_resource = LearningNoteResource(
            note_id=note.id,
            chapter_id=target_chapter_id,
            title=material.title,
            content=material.content,
            content_format=normalize_content_format(material.content_format),
            attachment_name=material.attachment_name,
            attachment_url=material.attachment_url,
            source_material_id=material.id,
            sort_order=section.sort_order,
        )
        db.add(copied_resource)


@router.get("", response_model=LearningNoteListResponse)
def list_learning_notes(
    scope: str = Query("mine", pattern="^(mine|public)$"),
    subject_id: Optional[int] = Query(None, ge=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    query = db.query(LearningNote)
    if scope == "mine":
        query = query.filter(LearningNote.owner_user_id == current_user.id)
    else:
        query = query.filter(LearningNote.visibility == LearningNoteVisibility.COURSE.value)
        if subject_id is not None:
            ensure_course_access_http(subject_id, current_user, db)
            query = query.filter(LearningNote.subject_id == subject_id)
        else:
            # Bound public notes stay course-scoped; unbound public notes are visible to every authenticated user.
            readable_course_ids = get_accessible_course_ids(current_user, db)
            if readable_course_ids:
                query = query.filter(
                    or_(
                        LearningNote.subject_id.is_(None),
                        LearningNote.subject_id.in_(readable_course_ids),
                    )
                )
            else:
                query = query.filter(LearningNote.subject_id.is_(None))

    total = query.count()
    rows = (
        query.order_by(desc(LearningNote.updated_at), desc(LearningNote.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return LearningNoteListResponse(total=total, data=[_serialize_note(row) for row in rows])


@router.post("", response_model=LearningNoteDetailResponse)
def create_learning_note(
    payload: LearningNoteCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    copy_source = payload.copy_from_subject_id
    subject_id = payload.subject_id or copy_source
    _validate_visibility_and_course(
        visibility=payload.visibility.value,
        subject_id=subject_id,
        user=current_user,
        db=db,
    )
    if copy_source is not None:
        ensure_course_access_http(copy_source, current_user, db)

    note = LearningNote(
        title=payload.title,
        description=payload.description,
        owner_user_id=current_user.id,
        subject_id=subject_id,
        visibility=payload.visibility.value,
        source_subject_id=copy_source,
        copied_materials=bool(payload.copy_materials),
    )
    db.add(note)
    db.flush()
    if payload.copy_chapters and copy_source is not None:
        _copy_course_outline(note=note, subject_id=copy_source, copy_materials=payload.copy_materials, db=db)

    db.commit()
    db.refresh(note)
    LogService.log_create(
        db,
        user_id=current_user.id,
        username=current_user.username,
        target_type="learning_note",
        target_id=note.id,
        target_name=note.title,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return _serialize_note_detail(note, db)


@router.get("/{note_id}", response_model=LearningNoteDetailResponse)
def get_learning_note(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    note = _load_note(note_id, db)
    _ensure_note_read(note, current_user, db)
    return _serialize_note_detail(note, db)


@router.put("/{note_id}", response_model=LearningNoteDetailResponse)
def update_learning_note(
    note_id: int,
    payload: LearningNoteUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    note = _load_note(note_id, db)
    _ensure_note_owner(note, current_user)
    next_visibility = payload.visibility.value if payload.visibility is not None else note.visibility
    next_subject_id = payload.subject_id if "subject_id" in payload.model_fields_set else note.subject_id
    _validate_visibility_and_course(
        visibility=next_visibility,
        subject_id=next_subject_id,
        user=current_user,
        db=db,
    )
    if payload.title is not None:
        note.title = payload.title
    if payload.description is not None:
        note.description = payload.description
    if "subject_id" in payload.model_fields_set:
        note.subject_id = payload.subject_id
    if payload.visibility is not None:
        note.visibility = payload.visibility.value
    db.commit()
    db.refresh(note)
    LogService.log_update(
        db,
        user_id=current_user.id,
        username=current_user.username,
        target_type="learning_note",
        target_id=note.id,
        target_name=note.title,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return _serialize_note_detail(note, db)


@router.delete("/{note_id}", status_code=204)
def delete_learning_note(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    note = _load_note(note_id, db)
    _ensure_note_owner(note, current_user)
    db.delete(note)
    db.commit()
    return None


def _ensure_chapter_owner(note_id: int, chapter_id: Optional[int], db: Session) -> Optional[LearningNoteChapter]:
    if chapter_id is None:
        return None
    chapter = db.query(LearningNoteChapter).filter(LearningNoteChapter.id == chapter_id).first()
    if not chapter or int(chapter.note_id) != int(note_id):
        raise HTTPException(status_code=400, detail="Invalid note chapter.")
    return chapter


@router.post("/{note_id}/chapters", response_model=LearningNoteChapterNode)
def create_learning_note_chapter(
    note_id: int,
    payload: LearningNoteChapterCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    note = _load_note(note_id, db)
    _ensure_note_owner(note, current_user)
    parent = _ensure_chapter_owner(note_id, payload.parent_id, db)
    sort_order = payload.sort_order
    if sort_order is None:
        sort_order = (
            db.query(LearningNoteChapter)
            .filter(LearningNoteChapter.note_id == note_id, LearningNoteChapter.parent_id == payload.parent_id)
            .count()
        )
    chapter = LearningNoteChapter(
        note_id=note_id,
        parent_id=parent.id if parent else None,
        title=payload.title.strip(),
        sort_order=int(sort_order),
    )
    db.add(chapter)
    db.commit()
    db.refresh(chapter)
    return LearningNoteChapterNode(
        id=chapter.id,
        note_id=chapter.note_id,
        parent_id=chapter.parent_id,
        title=chapter.title,
        sort_order=chapter.sort_order,
        source_chapter_id=chapter.source_chapter_id,
        resources=[],
        children=[],
    )


@router.put("/{note_id}/chapters/{chapter_id}", response_model=LearningNoteDetailResponse)
def update_learning_note_chapter(
    note_id: int,
    chapter_id: int,
    payload: LearningNoteChapterUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    note = _load_note(note_id, db)
    _ensure_note_owner(note, current_user)
    chapter = _ensure_chapter_owner(note_id, chapter_id, db)
    if payload.title is not None:
        chapter.title = payload.title.strip()
    if "parent_id" in payload.model_fields_set:
        parent = _ensure_chapter_owner(note_id, payload.parent_id, db)
        if parent and parent.id == chapter.id:
            raise HTTPException(status_code=400, detail="Chapter cannot be its own parent.")
        chapter.parent_id = parent.id if parent else None
    if payload.sort_order is not None:
        chapter.sort_order = int(payload.sort_order)
    db.commit()
    db.refresh(note)
    return _serialize_note_detail(note, db)


@router.delete("/{note_id}/chapters/{chapter_id}", response_model=LearningNoteDetailResponse)
def delete_learning_note_chapter(
    note_id: int,
    chapter_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    note = _load_note(note_id, db)
    _ensure_note_owner(note, current_user)
    chapter = _ensure_chapter_owner(note_id, chapter_id, db)
    for child in db.query(LearningNoteChapter).filter(LearningNoteChapter.parent_id == chapter.id).all():
        child.parent_id = chapter.parent_id
    for resource in db.query(LearningNoteResource).filter(LearningNoteResource.chapter_id == chapter.id).all():
        resource.chapter_id = None
    db.delete(chapter)
    db.commit()
    db.refresh(note)
    return _serialize_note_detail(note, db)


@router.post("/{note_id}/resources", response_model=LearningNoteDetailResponse)
def create_learning_note_resource(
    note_id: int,
    payload: LearningNoteResourceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    note = _load_note(note_id, db)
    _ensure_note_owner(note, current_user)
    chapter = _ensure_chapter_owner(note_id, payload.chapter_id, db)
    sort_order = payload.sort_order
    if sort_order is None:
        sort_order = (
            db.query(LearningNoteResource)
            .filter(LearningNoteResource.note_id == note_id, LearningNoteResource.chapter_id == payload.chapter_id)
            .count()
        )
    resource = LearningNoteResource(
        note_id=note_id,
        chapter_id=chapter.id if chapter else None,
        title=payload.title.strip(),
        content=payload.content,
        content_format=normalize_content_format(payload.content_format),
        attachment_name=payload.attachment_name,
        attachment_url=payload.attachment_url,
        sort_order=int(sort_order),
    )
    db.add(resource)
    db.commit()
    db.refresh(note)
    return _serialize_note_detail(note, db)


@router.put("/{note_id}/resources/{resource_id}", response_model=LearningNoteDetailResponse)
def update_learning_note_resource(
    note_id: int,
    resource_id: int,
    payload: LearningNoteResourceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    note = _load_note(note_id, db)
    _ensure_note_owner(note, current_user)
    resource = (
        db.query(LearningNoteResource)
        .filter(LearningNoteResource.id == resource_id, LearningNoteResource.note_id == note_id)
        .first()
    )
    if not resource:
        raise HTTPException(status_code=404, detail="Learning note resource not found.")
    if "chapter_id" in payload.model_fields_set:
        chapter = _ensure_chapter_owner(note_id, payload.chapter_id, db)
        resource.chapter_id = chapter.id if chapter else None
    if payload.title is not None:
        resource.title = payload.title.strip()
    if payload.content is not None:
        resource.content = payload.content
    if payload.content_format is not None:
        resource.content_format = normalize_content_format(payload.content_format)
    if "attachment_name" in payload.model_fields_set:
        resource.attachment_name = payload.attachment_name
    if "attachment_url" in payload.model_fields_set:
        resource.attachment_url = payload.attachment_url
    if payload.sort_order is not None:
        resource.sort_order = int(payload.sort_order)
    db.commit()
    db.refresh(note)
    return _serialize_note_detail(note, db)


@router.delete("/{note_id}/resources/{resource_id}", response_model=LearningNoteDetailResponse)
def delete_learning_note_resource(
    note_id: int,
    resource_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    note = _load_note(note_id, db)
    _ensure_note_owner(note, current_user)
    resource = (
        db.query(LearningNoteResource)
        .filter(LearningNoteResource.id == resource_id, LearningNoteResource.note_id == note_id)
        .first()
    )
    if not resource:
        raise HTTPException(status_code=404, detail="Learning note resource not found.")
    db.delete(resource)
    db.commit()
    db.refresh(note)
    return _serialize_note_detail(note, db)


def _serialize_note_discussion(
    row: LearningNoteDiscussionEntry,
    author: User,
    *,
    db: Session,
    current_user: User,
) -> LearningNoteDiscussionEntryResponse:
    return LearningNoteDiscussionEntryResponse(
        id=row.id,
        note_id=row.note_id,
        author_user_id=row.author_user_id,
        author_student_id=author.student_id,
        author_real_name=author.real_name,
        author_username=author.username,
        author_role=author.role,
        author_avatar_url=author.avatar_url,
        body=row.body,
        body_format=normalize_content_format(row.body_format),
        linked_targets=serialize_linked_targets_for_viewer(db, current_user, getattr(row, "linked_targets", None)),
        message_kind=row.message_kind,
        llm_invocation=bool(row.llm_invocation),
        created_at=row.created_at,
    )


@router.get("/{note_id}/discussion", response_model=LearningNoteDiscussionListResponse)
def list_learning_note_discussion(
    note_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    note = _load_note(note_id, db)
    _ensure_note_read(note, current_user, db)
    q = (
        db.query(LearningNoteDiscussionEntry, User)
        .join(User, User.id == LearningNoteDiscussionEntry.author_user_id)
        .filter(LearningNoteDiscussionEntry.note_id == note_id)
    )
    total = q.count()
    rows: Tuple[LearningNoteDiscussionEntry, User] = (
        q.order_by(asc(LearningNoteDiscussionEntry.created_at), asc(LearningNoteDiscussionEntry.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return LearningNoteDiscussionListResponse(
        page=page,
        page_size=page_size,
        total=total,
        data=[_serialize_note_discussion(row, author, db=db, current_user=current_user) for row, author in rows],
    )


@router.get("/discussion-entries/{entry_target_id}/locator")
def locate_learning_note_discussion_entry(
    entry_target_id: int,
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    entry_id = entry_target_id
    if entry_id > LEARNING_NOTE_DISCUSSION_TARGET_ID_OFFSET:
        entry_id -= LEARNING_NOTE_DISCUSSION_TARGET_ID_OFFSET
    row = db.query(LearningNoteDiscussionEntry).filter(LearningNoteDiscussionEntry.id == entry_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Discussion entry not found.")
    note = _load_note(row.note_id, db)
    _ensure_note_read(note, current_user, db)
    before_count = (
        db.query(LearningNoteDiscussionEntry)
        .filter(
            LearningNoteDiscussionEntry.note_id == row.note_id,
            (
                (LearningNoteDiscussionEntry.created_at < row.created_at)
                | ((LearningNoteDiscussionEntry.created_at == row.created_at) & (LearningNoteDiscussionEntry.id <= row.id))
            ),
        )
        .count()
    )
    page = max(1, ((before_count - 1) // page_size) + 1)
    return {
        "discussion_family": "learning_note",
        "entry_id": row.id,
        "target_id": LEARNING_NOTE_DISCUSSION_TARGET_ID_OFFSET + int(row.id),
        "note_id": row.note_id,
        "page": page,
        "page_size": page_size,
    }


@router.post("/{note_id}/discussion", response_model=LearningNoteDiscussionEntryResponse)
def create_learning_note_discussion(
    note_id: int,
    payload: LearningNoteDiscussionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    note = _load_note(note_id, db)
    _ensure_note_read(note, current_user, db)
    body = (payload.body or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="body cannot be empty.")
    if len(body) > MAX_DISCUSSION_BODY_LEN:
        raise HTTPException(status_code=400, detail=f"body exceeds {MAX_DISCUSSION_BODY_LEN} characters.")
    linked_targets = validate_visible_linked_targets(db, current_user, payload.linked_targets)

    entry = LearningNoteDiscussionEntry(
        note_id=note.id,
        author_user_id=current_user.id,
        body=body,
        body_format=payload.body_format,
        linked_targets=linked_targets,
        message_kind="human",
        llm_invocation=bool(payload.invoke_llm),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    if payload.invoke_llm:
        threading.Thread(target=_run_learning_note_llm_reply, args=(entry.id,), daemon=True).start()

    return _serialize_note_discussion(entry, current_user, db=db, current_user=current_user)


def _note_context_text(db: Session, note: LearningNote) -> str:
    chapters, loose = _build_note_tree(note.id, db)
    lines = [
        f"【笔记标题】\n{note.title}",
        f"【笔记说明】\n{note.description or '无'}",
    ]

    def walk(nodes: list[LearningNoteChapterNode], depth: int = 0) -> None:
        for node in nodes:
            prefix = "  " * depth
            lines.append(f"{prefix}- {node.title}")
            for resource in node.resources:
                body = resource.content or ""
                if normalize_content_format(resource.content_format) == "plain":
                    body = body_text_for_grading_llm(content=body, content_format="plain")
                lines.append(f"{prefix}  * {resource.title}: {body[:1200]}")
            walk(node.children, depth + 1)

    walk(chapters)
    for resource in loose:
        body = resource.content or ""
        if normalize_content_format(resource.content_format) == "plain":
            body = body_text_for_grading_llm(content=body, content_format="plain")
        lines.append(f"- {resource.title}: {body[:1200]}")
    return "\n".join(lines)


def _note_thread_text(db: Session, note_id: int) -> str:
    rows = (
        db.query(LearningNoteDiscussionEntry, User)
        .join(User, User.id == LearningNoteDiscussionEntry.author_user_id)
        .filter(LearningNoteDiscussionEntry.note_id == note_id)
        .order_by(LearningNoteDiscussionEntry.created_at.asc(), LearningNoteDiscussionEntry.id.asc())
        .limit(200)
        .all()
    )
    if not rows:
        return "（暂无讨论）"
    lines = []
    for row, author in rows:
        who = author.real_name or author.username
        role = "（智能助教）" if row.message_kind == "llm_assistant" else ""
        lines.append(f"- {who}{role}: {row.body}")
    return "\n".join(lines)


def _run_learning_note_llm_reply(entry_id: int) -> None:
    db = SessionLocal()
    try:
        entry = db.query(LearningNoteDiscussionEntry).filter(LearningNoteDiscussionEntry.id == entry_id).first()
        if not entry:
            return
        note = db.query(LearningNote).filter(LearningNote.id == entry.note_id).first()
        user = db.query(User).filter(User.id == entry.author_user_id).first()
        sys_user = db.query(User).filter(User.username == "__system_llm_assistant__").first()
        if not note or not user or not sys_user:
            return

        def add_assistant(text: str) -> None:
            db.add(
                LearningNoteDiscussionEntry(
                    note_id=note.id,
                    author_user_id=sys_user.id,
                    body=text,
                    body_format="markdown",
                    linked_targets=[],
                    message_kind="llm_assistant",
                    llm_invocation=False,
                )
            )
            db.commit()

        if note.subject_id is None:
            add_assistant("【智能助教】这条学习笔记尚未关联课程。请先给笔记选择课程范围，再调用课程 LLM 配置参与讨论。")
            return

        course = db.query(Subject).filter(Subject.id == note.subject_id).first()
        if not course:
            add_assistant("【智能助教】笔记关联的课程不存在，暂时无法调用课程 LLM。")
            return

        config = ensure_course_llm_config(db, int(note.subject_id), user_id=user.id)
        if not config.is_enabled or (not (config.groups or []) and not (config.endpoints or [])):
            add_assistant("【智能助教】当前课程尚未启用可用的 LLM 配置。")
            return

        quota_exempt = discussion_llm_user_is_quota_exempt(user)
        if not quota_exempt:
            class_id = course.class_id or user.class_id
            if class_id is None:
                add_assistant("【智能助教】无法确定该笔记的班级范围，暂时不能为学生账号计费调用。")
                return
            try:
                resolve_student_for_discussion_llm(db, user, class_id=int(class_id))
            except ValueError:
                add_assistant("【智能助教】当前学生账号没有匹配的花名册记录，暂时不能调用。")
                return

        user_visible = strip_llm_ui_prefix(entry.body) or entry.body
        system = (
            "你是学习笔记讨论区里的智能助教。只根据笔记内容、课程范围和讨论历史回答，"
            "帮助学生或教师整理知识、提出复习建议、解释章节资料。不要编造不存在的课程事实。"
        )
        user_block = (
            f"【学习笔记上下文】\n{_note_context_text(db, note)}\n\n"
            f"【讨论历史】\n{_note_thread_text(db, note.id)}\n\n"
            f"【当前问题】\n{user_visible}"
        )
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user_block}]
        max_out = int(config.max_output_tokens) if config.max_output_tokens else None
        dummy_job = SimpleNamespace(id=entry.id)
        try:
            result = _call_discussion_with_routing(
                db=db,
                config=config,
                messages=messages,
                max_output_tokens=max_out,
                job=dummy_job,
            )
        except NonRetryableLLMError as exc:
            add_assistant(f"【智能助教】暂时无法回复：{exc}")
            return
        except Exception as exc:
            add_assistant(f"【智能助教】调用异常：{exc}")
            return
        add_assistant(result["text"])
    finally:
        db.close()
