"""Unified, permission-filtered authored content feed."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.domains.courses.class_scope import get_accessible_class_ids
from apps.backend.courseeval_backend.api.schemas import (
    RecentPostAuthorResponse,
    RecentPostGroupResponse,
    RecentPostItemResponse,
    RecentPostsGroupedResponse,
    RecentPostsResponse,
)
from apps.backend.courseeval_backend.core.auth import get_current_active_user
from apps.backend.courseeval_backend.db.database import get_db
from apps.backend.courseeval_backend.db.models import (
    CourseDiscussionEntry,
    CourseMaterial,
    Homework,
    LearningNote,
    LearningNoteDiscussionEntry,
    Subject,
    User,
    UserRole,
)
from apps.backend.courseeval_backend.domains.courses.access import ensure_course_access_http
from apps.backend.courseeval_backend.domains.discussion_links import (
    LEARNING_NOTE_DISCUSSION_TARGET_ID_OFFSET,
    resolve_linked_target,
)
from apps.backend.courseeval_backend.domains.text_content_format import normalize_content_format

router = APIRouter(prefix="/api/recent-posts", tags=["最近发表"])

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 50
DEFAULT_GROUP_LIMIT = 3
MAX_GROUP_LIMIT = 10
RecentPostKind = Literal["all", "comment", "note", "material", "homework", "course"]
RecentPostConcreteKind = Literal["comment", "note", "material", "homework", "course"]
RECENT_POST_KIND_PATTERN = "^(all|comment|note|material|homework|course)$"
RECENT_POST_GROUP_ORDER: tuple[RecentPostConcreteKind, ...] = ("course", "homework", "material", "note", "comment")
RECENT_POST_GROUP_LABELS: dict[RecentPostConcreteKind, str] = {
    "course": "课程",
    "homework": "作业",
    "material": "资料",
    "note": "笔记",
    "comment": "讨论",
}

_MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MARKDOWN_MARKER_RE = re.compile(r"[*_`#>\-]+")


def _normalize_role(value: Any) -> str:
    return getattr(value, "value", value) or ""


def _serialize_author(author: User) -> RecentPostAuthorResponse:
    return RecentPostAuthorResponse(
        id=author.id,
        username=author.username,
        real_name=author.real_name,
        role=_normalize_role(author.role),
        avatar_url=author.avatar_url,
        class_id=author.class_id,
        class_name=author.class_obj.name if author.class_obj else None,
    )


def _preview_text(value: Optional[str], *, max_len: int = 160) -> str:
    text = str(value or "")
    text = _MARKDOWN_IMAGE_RE.sub(" ", text)
    text = _MARKDOWN_LINK_RE.sub(r"\1", text)
    text = _HTML_TAG_RE.sub(" ", text)
    text = _MARKDOWN_MARKER_RE.sub(" ", text)
    text = " ".join(text.split())
    if len(text) <= max_len:
        return text
    return f"{text[: max_len - 1]}..."


def _created_at(value: Optional[datetime]) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return datetime(1970, 1, 1, tzinfo=timezone.utc)


def _is_note_visible(note: LearningNote, viewer: User, db: Session) -> bool:
    if int(note.owner_user_id) == int(viewer.id):
        return True
    if note.visibility != "course":
        return False
    if note.subject_id is None:
        return True
    try:
        ensure_course_access_http(int(note.subject_id), viewer, db)
        return True
    except HTTPException:
        return False


def _is_material_visible(material: CourseMaterial, viewer: User, db: Session) -> bool:
    if material.subject_id:
        try:
            ensure_course_access_http(int(material.subject_id), viewer, db)
            return True
        except HTTPException:
            return False
    allowed_class_ids = get_accessible_class_ids(viewer, db)
    return viewer.role == UserRole.ADMIN or material.class_id in allowed_class_ids


def _is_homework_visible(homework: Homework, viewer: User, db: Session) -> bool:
    if homework.subject_id:
        try:
            ensure_course_access_http(int(homework.subject_id), viewer, db)
            return True
        except HTTPException:
            return False
    allowed_class_ids = get_accessible_class_ids(viewer, db)
    return viewer.role == UserRole.ADMIN or homework.class_id in allowed_class_ids


def _is_course_visible(course: Subject, viewer: User, db: Session) -> bool:
    try:
        ensure_course_access_http(int(course.id), viewer, db)
        return True
    except HTTPException:
        return False


def _course_discussion_visible(row: CourseDiscussionEntry, viewer: User, db: Session) -> bool:
    try:
        ensure_course_access_http(int(row.subject_id), viewer, db)
        return True
    except HTTPException:
        return False


def _target_payload(db: Session, viewer: User, *, target_type: str, target_id: int) -> Optional[dict[str, Any]]:
    return resolve_linked_target(
        db,
        viewer,
        target_type=target_type,
        target_id=target_id,
        require_visible=False,
    )


def _course_discussion_item(
    row: CourseDiscussionEntry,
    *,
    viewer: User,
    db: Session,
) -> Optional[RecentPostItemResponse]:
    if not _course_discussion_visible(row, viewer, db):
        return None
    target = _target_payload(db, viewer, target_type="discussion_entry", target_id=int(row.id))
    if target is None:
        return None
    subject_name = row.subject.name if row.subject else None
    return RecentPostItemResponse(
        id=f"course-discussion:{row.id}",
        kind="comment",
        source_type="course_discussion_entry",
        object_id=row.id,
        target_id=row.id,
        title=target.get("title") or "评论",
        body_preview=_preview_text(row.body),
        body_format=normalize_content_format(getattr(row, "body_format", None)),
        created_at=_created_at(row.created_at),
        subject_id=row.subject_id,
        subject_name=subject_name,
        class_id=row.class_id,
        class_name=row.class_obj.name if row.class_obj else None,
        context_title=target.get("secondary_text") or subject_name,
        target=target,
    )


def _note_discussion_item(
    row: LearningNoteDiscussionEntry,
    *,
    viewer: User,
    db: Session,
) -> Optional[RecentPostItemResponse]:
    if not row.note or not _is_note_visible(row.note, viewer, db):
        return None
    target_id = LEARNING_NOTE_DISCUSSION_TARGET_ID_OFFSET + int(row.id)
    target = _target_payload(db, viewer, target_type="discussion_entry", target_id=target_id)
    if target is None:
        return None
    note = row.note
    return RecentPostItemResponse(
        id=f"learning-note-discussion:{target_id}",
        kind="comment",
        source_type="learning_note_discussion_entry",
        object_id=row.id,
        target_id=target_id,
        title=target.get("title") or "笔记评论",
        body_preview=_preview_text(row.body),
        body_format=normalize_content_format(getattr(row, "body_format", None)),
        created_at=_created_at(row.created_at),
        subject_id=note.subject_id,
        subject_name=note.subject.name if note.subject else None,
        class_id=None,
        class_name=None,
        context_title=note.title,
        target=target,
    )


def _learning_note_item(note: LearningNote, *, viewer: User, db: Session) -> Optional[RecentPostItemResponse]:
    if not _is_note_visible(note, viewer, db):
        return None
    target = _target_payload(db, viewer, target_type="learning_note", target_id=int(note.id))
    if target is None:
        return None
    return RecentPostItemResponse(
        id=f"learning-note:{note.id}",
        kind="note",
        source_type="learning_note",
        object_id=note.id,
        target_id=note.id,
        title=note.title,
        body_preview=_preview_text(note.description),
        body_format="plain",
        created_at=_created_at(note.created_at),
        subject_id=note.subject_id,
        subject_name=note.subject.name if note.subject else None,
        class_id=None,
        class_name=None,
        context_title=target.get("secondary_text"),
        target=target,
    )


def _material_item(material: CourseMaterial, *, viewer: User, db: Session) -> Optional[RecentPostItemResponse]:
    if not _is_material_visible(material, viewer, db):
        return None
    target = _target_payload(db, viewer, target_type="material", target_id=int(material.id))
    if target is None:
        return None
    subject_name = material.subject.name if material.subject else None
    return RecentPostItemResponse(
        id=f"course-material:{material.id}",
        kind="material",
        source_type="course_material",
        object_id=material.id,
        target_id=material.id,
        title=material.title,
        body_preview=_preview_text(material.content),
        body_format=normalize_content_format(getattr(material, "content_format", None)),
        created_at=_created_at(material.created_at),
        subject_id=material.subject_id,
        subject_name=subject_name,
        class_id=material.class_id,
        class_name=material.class_obj.name if material.class_obj else None,
        context_title=target.get("secondary_text") or subject_name,
        target=target,
        has_attachment=bool(material.attachment_url or material.attachment_name),
    )


def _homework_item(homework: Homework, *, viewer: User, db: Session) -> Optional[RecentPostItemResponse]:
    if not _is_homework_visible(homework, viewer, db):
        return None
    target = _target_payload(db, viewer, target_type="homework", target_id=int(homework.id))
    if target is None:
        return None
    subject_name = homework.subject.name if homework.subject else None
    return RecentPostItemResponse(
        id=f"homework:{homework.id}",
        kind="homework",
        source_type="homework",
        object_id=homework.id,
        target_id=homework.id,
        title=homework.title,
        body_preview=_preview_text(homework.content),
        body_format=normalize_content_format(getattr(homework, "content_format", None)),
        created_at=_created_at(homework.created_at),
        subject_id=homework.subject_id,
        subject_name=subject_name,
        class_id=homework.class_id,
        class_name=homework.class_obj.name if homework.class_obj else None,
        context_title=target.get("secondary_text") or subject_name,
        target=target,
        has_attachment=bool(homework.attachment_url or homework.attachment_name),
    )


def _course_item(course: Subject, *, viewer: User, db: Session) -> Optional[RecentPostItemResponse]:
    if not _is_course_visible(course, viewer, db):
        return None
    target = _target_payload(db, viewer, target_type="course", target_id=int(course.id))
    if target is None:
        return None
    return RecentPostItemResponse(
        id=f"course:{course.id}",
        kind="course",
        source_type="course",
        object_id=course.id,
        target_id=course.id,
        title=course.name,
        body_preview=_preview_text(course.description),
        body_format="plain",
        created_at=_created_at(course.created_at),
        subject_id=course.id,
        subject_name=course.name,
        class_id=course.class_id,
        class_name=course.class_obj.name if course.class_obj else None,
        context_title=target.get("secondary_text"),
        target=target,
    )


def _collect_recent_posts(
    *,
    author: User,
    viewer: User,
    db: Session,
    kind: RecentPostKind,
    from_created_at: Optional[datetime],
    to_created_at: Optional[datetime],
) -> list[RecentPostItemResponse]:
    items: list[RecentPostItemResponse] = []

    def with_time_filter(query, column):
        if from_created_at is not None:
            query = query.filter(column >= from_created_at)
        if to_created_at is not None:
            query = query.filter(column <= to_created_at)
        return query

    if kind in ("all", "comment"):
        course_query = db.query(CourseDiscussionEntry).filter(
            CourseDiscussionEntry.author_user_id == author.id,
            or_(CourseDiscussionEntry.message_kind.is_(None), CourseDiscussionEntry.message_kind != "llm_assistant"),
        )
        course_query = with_time_filter(course_query, CourseDiscussionEntry.created_at)
        for row in course_query.order_by(desc(CourseDiscussionEntry.created_at), desc(CourseDiscussionEntry.id)).all():
            item = _course_discussion_item(row, viewer=viewer, db=db)
            if item is not None:
                items.append(item)

        note_discussion_query = db.query(LearningNoteDiscussionEntry).filter(
            LearningNoteDiscussionEntry.author_user_id == author.id,
            or_(
                LearningNoteDiscussionEntry.message_kind.is_(None),
                LearningNoteDiscussionEntry.message_kind != "llm_assistant",
            ),
        )
        note_discussion_query = with_time_filter(note_discussion_query, LearningNoteDiscussionEntry.created_at)
        for row in note_discussion_query.order_by(
            desc(LearningNoteDiscussionEntry.created_at),
            desc(LearningNoteDiscussionEntry.id),
        ).all():
            item = _note_discussion_item(row, viewer=viewer, db=db)
            if item is not None:
                items.append(item)

    if kind in ("all", "note"):
        note_query = db.query(LearningNote).filter(LearningNote.owner_user_id == author.id)
        note_query = with_time_filter(note_query, LearningNote.created_at)
        for note in note_query.order_by(desc(LearningNote.created_at), desc(LearningNote.id)).all():
            item = _learning_note_item(note, viewer=viewer, db=db)
            if item is not None:
                items.append(item)

    if kind in ("all", "material"):
        material_query = db.query(CourseMaterial).filter(CourseMaterial.created_by == author.id)
        material_query = with_time_filter(material_query, CourseMaterial.created_at)
        for material in material_query.order_by(desc(CourseMaterial.created_at), desc(CourseMaterial.id)).all():
            item = _material_item(material, viewer=viewer, db=db)
            if item is not None:
                items.append(item)

    if kind in ("all", "homework"):
        homework_query = db.query(Homework).filter(Homework.created_by == author.id)
        homework_query = with_time_filter(homework_query, Homework.created_at)
        for homework in homework_query.order_by(desc(Homework.created_at), desc(Homework.id)).all():
            item = _homework_item(homework, viewer=viewer, db=db)
            if item is not None:
                items.append(item)

    if kind in ("all", "course"):
        course_query = db.query(Subject).filter(Subject.teacher_id == author.id)
        course_query = with_time_filter(course_query, Subject.created_at)
        for course in course_query.order_by(desc(Subject.created_at), desc(Subject.id)).all():
            item = _course_item(course, viewer=viewer, db=db)
            if item is not None:
                items.append(item)

    items.sort(key=lambda item: (item.created_at, item.source_type, item.object_id), reverse=True)
    return items


def _get_author_or_404(user_id: int, db: Session) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return user


def _recent_posts_for_author(
    *,
    author: User,
    page: int,
    page_size: int,
    kind: RecentPostKind,
    from_created_at: Optional[datetime],
    to_created_at: Optional[datetime],
    db: Session,
    current_user: User,
) -> RecentPostsResponse:
    items = _collect_recent_posts(
        author=author,
        viewer=current_user,
        db=db,
        kind=kind,
        from_created_at=from_created_at,
        to_created_at=to_created_at,
    )
    start = (page - 1) * page_size
    return RecentPostsResponse(
        author=_serialize_author(author),
        page=page,
        page_size=page_size,
        total=len(items),
        data=items[start : start + page_size],
    )


def _recent_posts_grouped_for_author(
    *,
    author: User,
    group_limit: int,
    from_created_at: Optional[datetime],
    to_created_at: Optional[datetime],
    db: Session,
    current_user: User,
) -> RecentPostsGroupedResponse:
    groups: list[RecentPostGroupResponse] = []
    for kind in RECENT_POST_GROUP_ORDER:
        items = _collect_recent_posts(
            author=author,
            viewer=current_user,
            db=db,
            kind=kind,
            from_created_at=from_created_at,
            to_created_at=to_created_at,
        )
        if not items:
            continue
        groups.append(
            RecentPostGroupResponse(
                kind=kind,
                label=RECENT_POST_GROUP_LABELS[kind],
                total=len(items),
                latest_created_at=items[0].created_at,
                data=items[:group_limit],
            )
        )
    return RecentPostsGroupedResponse(
        author=_serialize_author(author),
        group_limit=group_limit,
        groups=groups,
    )


@router.get("/me/grouped", response_model=RecentPostsGroupedResponse)
def get_my_recent_posts_grouped(
    group_limit: int = Query(DEFAULT_GROUP_LIMIT, ge=1, le=MAX_GROUP_LIMIT),
    from_created_at: Optional[datetime] = Query(None),
    to_created_at: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return _recent_posts_grouped_for_author(
        author=current_user,
        group_limit=group_limit,
        from_created_at=from_created_at,
        to_created_at=to_created_at,
        db=db,
        current_user=current_user,
    )


@router.get("/me", response_model=RecentPostsResponse)
def get_my_recent_posts(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    kind: RecentPostKind = Query("all", pattern=RECENT_POST_KIND_PATTERN),
    from_created_at: Optional[datetime] = Query(None),
    to_created_at: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return _recent_posts_for_author(
        author=current_user,
        page=page,
        page_size=page_size,
        kind=kind,
        from_created_at=from_created_at,
        to_created_at=to_created_at,
        db=db,
        current_user=current_user,
    )


@router.get("/users/{user_id}/grouped", response_model=RecentPostsGroupedResponse)
def get_user_recent_posts_grouped(
    user_id: int,
    group_limit: int = Query(DEFAULT_GROUP_LIMIT, ge=1, le=MAX_GROUP_LIMIT),
    from_created_at: Optional[datetime] = Query(None),
    to_created_at: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    author = _get_author_or_404(user_id, db)
    return _recent_posts_grouped_for_author(
        author=author,
        group_limit=group_limit,
        from_created_at=from_created_at,
        to_created_at=to_created_at,
        db=db,
        current_user=current_user,
    )


@router.get("/users/{user_id}", response_model=RecentPostsResponse)
def get_user_recent_posts(
    user_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    kind: RecentPostKind = Query("all", pattern=RECENT_POST_KIND_PATTERN),
    from_created_at: Optional[datetime] = Query(None),
    to_created_at: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    author = _get_author_or_404(user_id, db)
    return _recent_posts_for_author(
        author=author,
        page=page,
        page_size=page_size,
        kind=kind,
        from_created_at=from_created_at,
        to_created_at=to_created_at,
        db=db,
        current_user=current_user,
    )
