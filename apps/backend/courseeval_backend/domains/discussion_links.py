from __future__ import annotations

import json
from typing import Any, Literal, Optional

from fastapi import HTTPException
from sqlalchemy import case, desc, or_
from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.db.models import (
    Class,
    CourseDiscussionEntry,
    CourseMaterial,
    CourseMaterialChapter,
    CourseMaterialSection,
    Homework,
    LearningNote,
    LearningNoteDiscussionEntry,
    Subject,
    User,
    UserRole,
)
from apps.backend.courseeval_backend.domains.courses.access import (
    ensure_course_access_http,
    get_accessible_course_ids,
    get_accessible_courses_query,
)

DiscussionLinkTargetType = Literal["homework", "material", "learning_note", "course", "discussion_entry"]

LINKABLE_TARGET_TYPES: tuple[str, ...] = ("homework", "material", "learning_note", "course", "discussion_entry")
MAX_LINKED_TARGETS = 12
DEFAULT_SEARCH_LIMIT = 12
MAX_SEARCH_LIMIT = 30
LEARNING_NOTE_DISCUSSION_TARGET_ID_OFFSET = 1_000_000_000


def target_label(target_type: str) -> str:
    labels = {
        "homework": "\u4f5c\u4e1a",
        "material": "\u8d44\u6599",
        "learning_note": "\u7b14\u8bb0",
        "course": "\u8bfe\u7a0b",
        "discussion_entry": "\u8bc4\u8bba",
    }
    if target_type in labels:
        return labels[target_type]
    return {
        "homework": "作业",
        "material": "资料",
        "learning_note": "笔记",
    }.get(target_type, target_type)


def _normalize_target_type(value: Any) -> DiscussionLinkTargetType:
    normalized = str(value or "").strip().lower()
    if normalized not in LINKABLE_TARGET_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported linked target type: {value!r}.")
    return normalized  # type: ignore[return-value]


def _normalize_target_id(value: Any) -> int:
    try:
        target_id = int(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="linked target id must be a positive integer.") from None
    if target_id < 1:
        raise HTTPException(status_code=400, detail="linked target id must be a positive integer.")
    return target_id


def _coerce_raw_targets(raw_targets: Any) -> list[dict[str, Any]]:
    if raw_targets in (None, "", []):
        return []
    if isinstance(raw_targets, str):
        try:
            parsed = json.loads(raw_targets)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    if isinstance(raw_targets, list):
        return raw_targets
    return []


def normalize_linked_targets_payload(raw_targets: Any) -> list[dict[str, int | str]]:
    normalized: list[dict[str, int | str]] = []
    seen: set[tuple[str, int]] = set()
    for item in _coerce_raw_targets(raw_targets):
        if hasattr(item, "model_dump"):
            item = item.model_dump()
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="linked_targets items must be objects.")
        current_type = _normalize_target_type(item.get("target_type"))
        current_id = _normalize_target_id(item.get("target_id"))
        key = (current_type, current_id)
        if key in seen:
            continue
        seen.add(key)
        normalized.append({"target_type": current_type, "target_id": current_id})
    if len(normalized) > MAX_LINKED_TARGETS:
        raise HTTPException(status_code=400, detail=f"linked_targets cannot exceed {MAX_LINKED_TARGETS} items.")
    return normalized


def _note_is_visible(note: LearningNote, current_user: User, db: Session) -> bool:
    if int(note.owner_user_id) == int(current_user.id):
        return True
    if note.visibility != "course":
        return False
    if note.subject_id is None:
        return True
    try:
        ensure_course_access_http(int(note.subject_id), current_user, db)
        return True
    except HTTPException:
        return False


def _material_chapter_hint(material_id: int, db: Session) -> Optional[str]:
    row = (
        db.query(CourseMaterialChapter.title)
        .join(CourseMaterialSection, CourseMaterialSection.chapter_id == CourseMaterialChapter.id)
        .filter(CourseMaterialSection.material_id == material_id)
        .order_by(CourseMaterialSection.sort_order.asc(), CourseMaterialSection.id.asc())
        .first()
    )
    return str(row[0]).strip() if row and row[0] else None


def _serialize_target_payload(
    *,
    target_type: str,
    target_id: int,
    title: str,
    subject_id: Optional[int],
    subject_name: Optional[str],
    class_id: Optional[int],
    class_name: Optional[str],
    secondary_text: Optional[str],
    available: bool,
    meta: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    payload = {
        "target_type": target_type,
        "target_id": target_id,
        "target_label": target_label(target_type),
        "title": title,
        "subject_id": subject_id,
        "subject_name": subject_name,
        "class_id": class_id,
        "class_name": class_name,
        "secondary_text": secondary_text,
        "available": available,
    }
    if meta:
        payload["meta"] = meta
    return payload


def _short_excerpt(value: Optional[str], *, max_len: int = 72) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_len:
        return text or "\u7a7a\u8bc4\u8bba"
    return f"{text[: max_len - 1]}\u2026"


def _author_label(author: Optional[User]) -> str:
    if not author:
        return "\u672a\u77e5\u7528\u6237"
    return author.real_name or author.username or f"\u7528\u6237 {author.id}"


def _resolve_homework_target(
    db: Session,
    current_user: User,
    target_id: int,
    *,
    require_visible: bool,
) -> Optional[dict[str, Any]]:
    homework = db.query(Homework).filter(Homework.id == target_id).first()
    if not homework or homework.subject_id is None:
        if require_visible:
            raise HTTPException(status_code=404, detail="Linked homework not found.")
        return None
    try:
        ensure_course_access_http(int(homework.subject_id), current_user, db)
    except HTTPException:
        if require_visible:
            raise HTTPException(status_code=403, detail="You do not have access to this linked homework.") from None
        return None
    secondary = homework.subject.name if homework.subject else homework.class_obj.name if homework.class_obj else "课程作业"
    return _serialize_target_payload(
        target_type="homework",
        target_id=homework.id,
        title=homework.title,
        subject_id=homework.subject_id,
        subject_name=homework.subject.name if homework.subject else None,
        class_id=homework.class_id,
        class_name=homework.class_obj.name if homework.class_obj else None,
        secondary_text=secondary,
        available=True,
    )


def _resolve_material_target(
    db: Session,
    current_user: User,
    target_id: int,
    *,
    require_visible: bool,
) -> Optional[dict[str, Any]]:
    material = db.query(CourseMaterial).filter(CourseMaterial.id == target_id).first()
    if not material or material.subject_id is None:
        if require_visible:
            raise HTTPException(status_code=404, detail="Linked material not found.")
        return None
    try:
        ensure_course_access_http(int(material.subject_id), current_user, db)
    except HTTPException:
        if require_visible:
            raise HTTPException(status_code=403, detail="You do not have access to this linked material.") from None
        return None
    chapter_hint = _material_chapter_hint(material.id, db)
    secondary = material.subject.name if material.subject else material.class_obj.name if material.class_obj else "课程资料"
    if chapter_hint:
        secondary = f"{secondary} · {chapter_hint}"
    return _serialize_target_payload(
        target_type="material",
        target_id=material.id,
        title=material.title,
        subject_id=material.subject_id,
        subject_name=material.subject.name if material.subject else None,
        class_id=material.class_id,
        class_name=material.class_obj.name if material.class_obj else None,
        secondary_text=secondary,
        available=True,
    )


def _resolve_learning_note_target(
    db: Session,
    current_user: User,
    target_id: int,
    *,
    require_visible: bool,
) -> Optional[dict[str, Any]]:
    note = db.query(LearningNote).filter(LearningNote.id == target_id).first()
    if not note:
        if require_visible:
            raise HTTPException(status_code=404, detail="Linked learning note not found.")
        return None
    if not _note_is_visible(note, current_user, db):
        if require_visible:
            raise HTTPException(status_code=403, detail="You do not have access to this linked learning note.") from None
        return None
    if note.subject_id is None:
        secondary = "全员公开笔记" if note.visibility == "course" else "仅创建者可见"
    else:
        secondary = note.subject.name if note.subject else "同课程公开笔记"
    return _serialize_target_payload(
        target_type="learning_note",
        target_id=note.id,
        title=note.title,
        subject_id=note.subject_id,
        subject_name=note.subject.name if note.subject else None,
        class_id=None,
        class_name=None,
        secondary_text=secondary,
        available=True,
    )


def _resolve_course_target(
    db: Session,
    current_user: User,
    target_id: int,
    *,
    require_visible: bool,
) -> Optional[dict[str, Any]]:
    try:
        course = ensure_course_access_http(target_id, current_user, db)
    except HTTPException:
        if require_visible:
            raise HTTPException(status_code=403, detail="You do not have access to this linked course.") from None
        return None
    class_name = course.class_obj.name if course.class_obj else None
    secondary_parts = []
    if class_name:
        secondary_parts.append(class_name)
    if course.course_type:
        secondary_parts.append(str(course.course_type))
    if course.teacher:
        secondary_parts.append(_author_label(course.teacher))
    return _serialize_target_payload(
        target_type="course",
        target_id=course.id,
        title=course.name,
        subject_id=course.id,
        subject_name=course.name,
        class_id=course.class_id,
        class_name=class_name,
        secondary_text=" · ".join(secondary_parts) if secondary_parts else "\u53ef\u89c1\u8bfe\u7a0b",
        available=True,
    )


def _resolve_course_discussion_entry_target(
    db: Session,
    current_user: User,
    target_id: int,
    *,
    require_visible: bool,
) -> Optional[dict[str, Any]]:
    row = db.query(CourseDiscussionEntry).filter(CourseDiscussionEntry.id == target_id).first()
    if not row:
        if require_visible:
            raise HTTPException(status_code=404, detail="Linked discussion entry not found.")
        return None
    try:
        ensure_course_access_http(int(row.subject_id), current_user, db)
    except HTTPException:
        if require_visible:
            raise HTTPException(status_code=403, detail="You do not have access to this linked discussion entry.") from None
        return None
    author = row.author
    title = f"{_author_label(author)}: {_short_excerpt(row.body)}"
    subject_name = row.subject.name if row.subject else "\u8bfe\u7a0b"
    secondary = f"{subject_name} · {target_label(row.target_type)}\u8ba8\u8bba"
    return _serialize_target_payload(
        target_type="discussion_entry",
        target_id=row.id,
        title=title,
        subject_id=row.subject_id,
        subject_name=row.subject.name if row.subject else None,
        class_id=row.class_id,
        class_name=row.class_obj.name if row.class_obj else None,
        secondary_text=secondary,
        available=True,
        meta={
            "discussion_family": "course",
            "thread_target_type": row.target_type,
            "thread_target_id": row.target_id,
            "entry_id": row.id,
        },
    )


def _resolve_learning_note_discussion_entry_target(
    db: Session,
    current_user: User,
    target_id: int,
    *,
    require_visible: bool,
) -> Optional[dict[str, Any]]:
    row = db.query(LearningNoteDiscussionEntry).filter(LearningNoteDiscussionEntry.id == target_id).first()
    if not row or not row.note:
        if require_visible:
            raise HTTPException(status_code=404, detail="Linked discussion entry not found.")
        return None
    if not _note_is_visible(row.note, current_user, db):
        if require_visible:
            raise HTTPException(status_code=403, detail="You do not have access to this linked discussion entry.") from None
        return None
    note = row.note
    author = row.author
    title = f"{_author_label(author)}: {_short_excerpt(row.body)}"
    secondary = f"{note.title} · \u7b14\u8bb0\u8ba8\u8bba"
    return _serialize_target_payload(
        target_type="discussion_entry",
        target_id=LEARNING_NOTE_DISCUSSION_TARGET_ID_OFFSET + int(row.id),
        title=title,
        subject_id=note.subject_id,
        subject_name=note.subject.name if note.subject else None,
        class_id=None,
        class_name=None,
        secondary_text=secondary,
        available=True,
        meta={
            "discussion_family": "learning_note",
            "note_id": note.id,
            "entry_id": row.id,
        },
    )


def _resolve_discussion_entry_target(
    db: Session,
    current_user: User,
    target_id: int,
    *,
    require_visible: bool,
) -> Optional[dict[str, Any]]:
    if target_id > LEARNING_NOTE_DISCUSSION_TARGET_ID_OFFSET:
        return _resolve_learning_note_discussion_entry_target(
            db,
            current_user,
            target_id - LEARNING_NOTE_DISCUSSION_TARGET_ID_OFFSET,
            require_visible=require_visible,
        )
    return _resolve_course_discussion_entry_target(db, current_user, target_id, require_visible=require_visible)


def resolve_linked_target(
    db: Session,
    current_user: User,
    *,
    target_type: str,
    target_id: int,
    require_visible: bool,
) -> Optional[dict[str, Any]]:
    normalized_type = _normalize_target_type(target_type)
    normalized_id = _normalize_target_id(target_id)
    if normalized_type == "homework":
        return _resolve_homework_target(db, current_user, normalized_id, require_visible=require_visible)
    if normalized_type == "material":
        return _resolve_material_target(db, current_user, normalized_id, require_visible=require_visible)
    if normalized_type == "learning_note":
        return _resolve_learning_note_target(db, current_user, normalized_id, require_visible=require_visible)
    if normalized_type == "course":
        return _resolve_course_target(db, current_user, normalized_id, require_visible=require_visible)
    return _resolve_discussion_entry_target(db, current_user, normalized_id, require_visible=require_visible)


def validate_visible_linked_targets(db: Session, current_user: User, raw_targets: Any) -> list[dict[str, int | str]]:
    normalized = normalize_linked_targets_payload(raw_targets)
    for item in normalized:
        resolve_linked_target(
            db,
            current_user,
            target_type=str(item["target_type"]),
            target_id=int(item["target_id"]),
            require_visible=True,
        )
    return normalized


def serialize_linked_targets_for_viewer(db: Session, current_user: User, raw_targets: Any) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in normalize_linked_targets_payload(raw_targets):
        payload = resolve_linked_target(
            db,
            current_user,
            target_type=str(item["target_type"]),
            target_id=int(item["target_id"]),
            require_visible=False,
        )
        if payload is None:
            results.append(
                _serialize_target_payload(
                    target_type=str(item["target_type"]),
                    target_id=int(item["target_id"]),
                    title="目标不可用",
                    subject_id=None,
                    subject_name=None,
                    class_id=None,
                    class_name=None,
                    secondary_text="你当前无法访问该内容，或该内容已被删除。",
                    available=False,
                )
            )
            continue
        results.append(payload)
    return results


def _visible_note_query(db: Session, current_user: User):
    query = db.query(LearningNote)
    if current_user.role == UserRole.ADMIN:
        return query.filter(or_(LearningNote.owner_user_id == current_user.id, LearningNote.visibility == "course"))

    accessible_course_ids = get_accessible_course_ids(current_user, db)
    public_filter = [LearningNote.visibility == "course", LearningNote.subject_id.is_(None)]
    if accessible_course_ids:
        public_filter.append(LearningNote.subject_id.in_(accessible_course_ids))
    return query.filter(
        or_(
            LearningNote.owner_user_id == current_user.id,
            or_(*public_filter),
        )
    )


def search_link_targets(
    db: Session,
    current_user: User,
    *,
    target_type: str,
    query_text: Optional[str] = None,
    preferred_subject_id: Optional[int] = None,
    limit: int = DEFAULT_SEARCH_LIMIT,
) -> list[dict[str, Any]]:
    normalized_type = _normalize_target_type(target_type)
    q = (query_text or "").strip()
    safe_limit = max(1, min(MAX_SEARCH_LIMIT, int(limit)))

    if normalized_type == "course":
        query = get_accessible_courses_query(current_user, db)
        if q:
            query = query.filter(Subject.name.ilike(f"%{q}%"))
        if preferred_subject_id is not None:
            query = query.order_by(case((Subject.id == preferred_subject_id, 0), else_=1), desc(Subject.created_at))
        else:
            query = query.order_by(desc(Subject.created_at))
        return [
            _serialize_target_payload(
                target_type="course",
                target_id=row.id,
                title=row.name,
                subject_id=row.id,
                subject_name=row.name,
                class_id=row.class_id,
                class_name=row.class_obj.name if row.class_obj else None,
                secondary_text=row.class_obj.name if row.class_obj else (row.course_type or "\u53ef\u89c1\u8bfe\u7a0b"),
                available=True,
            )
            for row in query.limit(safe_limit).all()
        ]

    if normalized_type == "discussion_entry":
        results: list[dict[str, Any]] = []
        accessible_course_ids = get_accessible_course_ids(current_user, db)
        if accessible_course_ids:
            course_query = (
                db.query(CourseDiscussionEntry)
                .filter(CourseDiscussionEntry.subject_id.in_(accessible_course_ids))
                .order_by(
                    case((CourseDiscussionEntry.subject_id == preferred_subject_id, 0), else_=1)
                    if preferred_subject_id is not None
                    else desc(CourseDiscussionEntry.created_at),
                    desc(CourseDiscussionEntry.created_at),
                    desc(CourseDiscussionEntry.id),
                )
            )
            if q:
                course_query = course_query.filter(CourseDiscussionEntry.body.ilike(f"%{q}%"))
            for row in course_query.limit(safe_limit).all():
                payload = _resolve_course_discussion_entry_target(db, current_user, row.id, require_visible=False)
                if payload is not None:
                    results.append(payload)

        remaining = safe_limit - len(results)
        if remaining > 0:
            visible_note_ids = [row.id for row in _visible_note_query(db, current_user).all()]
            if visible_note_ids:
                note_query = (
                    db.query(LearningNoteDiscussionEntry)
                    .filter(LearningNoteDiscussionEntry.note_id.in_(visible_note_ids))
                    .order_by(desc(LearningNoteDiscussionEntry.created_at), desc(LearningNoteDiscussionEntry.id))
                )
                if q:
                    note_query = note_query.filter(LearningNoteDiscussionEntry.body.ilike(f"%{q}%"))
                for row in note_query.limit(remaining).all():
                    payload = _resolve_learning_note_discussion_entry_target(db, current_user, row.id, require_visible=False)
                    if payload is not None:
                        results.append(payload)
        return results[:safe_limit]

    if normalized_type == "homework":
        query = db.query(Homework).filter(Homework.subject_id.is_not(None))
        if current_user.role != UserRole.ADMIN:
            accessible_course_ids = get_accessible_course_ids(current_user, db)
            if not accessible_course_ids:
                return []
            query = query.filter(Homework.subject_id.in_(accessible_course_ids))
        if q:
            query = query.filter(Homework.title.ilike(f"%{q}%"))
        if preferred_subject_id is not None:
            query = query.order_by(case((Homework.subject_id == preferred_subject_id, 0), else_=1), desc(Homework.created_at))
        else:
            query = query.order_by(desc(Homework.created_at))
        return [
            _serialize_target_payload(
                target_type="homework",
                target_id=row.id,
                title=row.title,
                subject_id=row.subject_id,
                subject_name=row.subject.name if row.subject else None,
                class_id=row.class_id,
                class_name=row.class_obj.name if row.class_obj else None,
                secondary_text=row.subject.name if row.subject else row.class_obj.name if row.class_obj else "课程作业",
                available=True,
            )
            for row in query.limit(safe_limit).all()
        ]

    if normalized_type == "material":
        query = db.query(CourseMaterial).filter(CourseMaterial.subject_id.is_not(None))
        if current_user.role != UserRole.ADMIN:
            accessible_course_ids = get_accessible_course_ids(current_user, db)
            if not accessible_course_ids:
                return []
            query = query.filter(CourseMaterial.subject_id.in_(accessible_course_ids))
        if q:
            query = query.filter(CourseMaterial.title.ilike(f"%{q}%"))
        if preferred_subject_id is not None:
            query = query.order_by(
                case((CourseMaterial.subject_id == preferred_subject_id, 0), else_=1),
                desc(CourseMaterial.created_at),
            )
        else:
            query = query.order_by(desc(CourseMaterial.created_at))
        results: list[dict[str, Any]] = []
        for row in query.limit(safe_limit).all():
            chapter_hint = _material_chapter_hint(row.id, db)
            secondary = row.subject.name if row.subject else row.class_obj.name if row.class_obj else "课程资料"
            if chapter_hint:
                secondary = f"{secondary} · {chapter_hint}"
            results.append(
                _serialize_target_payload(
                    target_type="material",
                    target_id=row.id,
                    title=row.title,
                    subject_id=row.subject_id,
                    subject_name=row.subject.name if row.subject else None,
                    class_id=row.class_id,
                    class_name=row.class_obj.name if row.class_obj else None,
                    secondary_text=secondary,
                    available=True,
                )
            )
        return results

    query = _visible_note_query(db, current_user)
    if q:
        query = query.filter(LearningNote.title.ilike(f"%{q}%"))
    if preferred_subject_id is not None:
        query = query.order_by(case((LearningNote.subject_id == preferred_subject_id, 0), else_=1), desc(LearningNote.updated_at))
    else:
        query = query.order_by(desc(LearningNote.updated_at))
    results = []
    for row in query.limit(safe_limit).all():
        if row.subject_id is None:
            secondary = "全员公开笔记" if row.visibility == "course" else "仅创建者可见"
        else:
            secondary = row.subject.name if row.subject else "同课程公开笔记"
        results.append(
            _serialize_target_payload(
                target_type="learning_note",
                target_id=row.id,
                title=row.title,
                subject_id=row.subject_id,
                subject_name=row.subject.name if row.subject else None,
                class_id=None,
                class_name=None,
                secondary_text=secondary,
                available=True,
            )
        )
    return results
