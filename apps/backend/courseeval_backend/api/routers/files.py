import logging
from pathlib import Path
from typing import Optional
from urllib.parse import unquote

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.attachments import (
    get_attachment_download_name,
    get_attachment_file_path,
    get_attachment_stored_name,
    save_attachment,
)
from apps.backend.courseeval_backend.core.auth import get_current_active_user
from apps.backend.courseeval_backend.domains.courses.access import ensure_course_access_http, get_student_profile_for_user
from apps.backend.courseeval_backend.db.database import get_db
from apps.backend.courseeval_backend.db.models import CourseMaterial, Homework, HomeworkAttempt, HomeworkSubmission, Notification, Subject, User, UserRole
from apps.backend.courseeval_backend.domains.courses.class_scope import get_accessible_class_ids
from apps.backend.courseeval_backend.api.schemas import AttachmentUploadResponse


router = APIRouter(prefix="/api/files", tags=["文件上传"])
_log = logging.getLogger(__name__)


@router.post("/upload", response_model=AttachmentUploadResponse)
async def upload_attachment(
    request: Request,
    file: UploadFile = File(...),
    _current_user: User = Depends(get_current_active_user),
):
    uploaded = await save_attachment(file, request)
    return AttachmentUploadResponse(**uploaded)


def _has_attachment_access(current_user: User, attachment_url: str, db: Session) -> bool:
    if current_user.avatar_url and attachment_url == current_user.avatar_url:
        return True

    allowed_class_ids = set(get_accessible_class_ids(current_user, db))
    current_student = get_student_profile_for_user(current_user, db) if current_user.role == UserRole.STUDENT else None

    def _has_subject_or_class_scope(subject_id: Optional[int], class_id: Optional[int]) -> bool:
        if current_user.role == UserRole.ADMIN:
            return True
        if subject_id:
            try:
                ensure_course_access_http(subject_id, current_user, db)
            except HTTPException:
                return False
            return True
        return class_id in allowed_class_ids

    homework = db.query(Homework).filter(Homework.attachment_url == attachment_url).first()
    if homework:
        return _has_subject_or_class_scope(homework.subject_id, homework.class_id)

    material = db.query(CourseMaterial).filter(CourseMaterial.attachment_url == attachment_url).first()
    if material:
        return _has_subject_or_class_scope(material.subject_id, material.class_id)

    notification = db.query(Notification).filter(Notification.attachment_url == attachment_url).first()
    if notification:
        return _has_subject_or_class_scope(notification.subject_id, notification.class_id)

    submission = db.query(HomeworkSubmission).filter(HomeworkSubmission.attachment_url == attachment_url).first()
    if submission:
        if current_user.role == UserRole.STUDENT:
            return current_student is not None and submission.student_id == current_student.id
        return _has_subject_or_class_scope(submission.subject_id, submission.class_id)

    attempt = db.query(HomeworkAttempt).filter(HomeworkAttempt.attachment_url == attachment_url).first()
    if attempt:
        if current_user.role == UserRole.STUDENT:
            return current_student is not None and attempt.student_id == current_student.id
        return _has_subject_or_class_scope(attempt.subject_id, attempt.class_id)

    subject_cover = db.query(Subject).filter(Subject.cover_image_url == attachment_url).first()
    if subject_cover:
        try:
            ensure_course_access_http(subject_cover.id, current_user, db)
        except HTTPException:
            return False
        return True

    return False


def _attachment_urls_with_exact_stored_basename(db: Session, stored_basename: str) -> list[str]:
    """All DB attachment_url values whose parsed stored file name exactly matches (no full-table scan)."""
    if not stored_basename or Path(stored_basename).name in {"", ".", "..", "attachments"}:
        return []
    urls: list[str] = []
    suffixes = (
        f"/{stored_basename}",
        f"\\{stored_basename}",
        stored_basename,
    )
    for model in (HomeworkSubmission, HomeworkAttempt, Homework, CourseMaterial, Notification):
        if not hasattr(model, "attachment_url"):
            continue
        conditions = [model.attachment_url.endswith(s) for s in suffixes]
        q = db.query(model.attachment_url).filter(model.attachment_url.isnot(None), or_(*conditions))
        for (u,) in q.all():
            if u and get_attachment_stored_name(str(u)) == stored_basename:
                urls.append(str(u))
    user_rows = (
        db.query(User.avatar_url)
        .filter(User.avatar_url.isnot(None), or_(*[User.avatar_url.endswith(s) for s in suffixes]))
        .all()
    )
    for (u,) in user_rows:
        if u and get_attachment_stored_name(str(u)) == stored_basename:
            urls.append(str(u))
    sub_rows = (
        db.query(Subject.cover_image_url)
        .filter(Subject.cover_image_url.isnot(None), or_(*[Subject.cover_image_url.endswith(s) for s in suffixes]))
        .all()
    )
    for (u,) in sub_rows:
        if u and get_attachment_stored_name(str(u)) == stored_basename:
            urls.append(str(u))
    return urls


@router.get("/download/{stored_name:path}", name="download_attachment_by_name")
def download_attachment_by_stored_name(
    stored_name: str,
    attachment_url: Optional[str] = Query(
        None,
        description="Canonical attachment URL when multiple DB rows share the same stored file name (disambiguates basename collisions).",
    ),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Serves a file from storage by the stored file name; access matches DB-referenced attachment URLs."""
    safe_name = unquote(stored_name).strip().replace("\\", "/")
    if not safe_name or Path(safe_name).name in {"", ".", "..", "attachments"}:
        raise HTTPException(status_code=404, detail="Attachment file not found on server.")
    target_base = Path(safe_name).name
    candidates = _attachment_urls_with_exact_stored_basename(db, target_base)
    if not candidates:
        raise HTTPException(status_code=404, detail="Attachment file not found on server.")
    allowed = [u for u in candidates if _has_attachment_access(current_user, u, db)]
    if not allowed:
        raise HTTPException(status_code=403, detail="You do not have access to this attachment.")

    url_to_path: dict[str, Path] = {}
    for u in allowed:
        p = get_attachment_file_path(u)
        if not p or not p.exists():
            raise HTTPException(status_code=404, detail="Attachment file not found on server.")
        try:
            url_to_path[u] = p.resolve()
        except OSError:
            url_to_path[u] = p

    unique_disk_paths = {str(path) for path in url_to_path.values()}
    chosen_url: Optional[str] = None

    if attachment_url is not None:
        au = unquote(attachment_url).strip()
        if au not in url_to_path:
            raise HTTPException(
                status_code=403,
                detail="You do not have access to this attachment reference.",
            )
        chosen_url = au
    elif len(unique_disk_paths) == 1:
        chosen_url = sorted(allowed)[0]
    else:
        _log.warning(
            "attachment basename collision: user=%s basename=%s allowed_urls=%s",
            getattr(current_user, "id", None),
            target_base,
            len(allowed),
        )
        raise HTTPException(
            status_code=400,
            detail="Multiple attachment references share this file name. Open the file from the application or pass the full attachment_url query parameter.",
        )

    file_path = url_to_path[chosen_url]
    return FileResponse(
        path=file_path,
        filename=get_attachment_download_name(chosen_url, None),
        media_type="application/octet-stream",
    )


@router.get("/download")
def download_attachment(
    attachment_url: str,
    attachment_name: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    if not _has_attachment_access(current_user, attachment_url, db):
        raise HTTPException(status_code=403, detail="You do not have access to this attachment.")

    file_path = get_attachment_file_path(attachment_url)
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="Attachment file not found on server.")

    return FileResponse(
        path=file_path,
        filename=get_attachment_download_name(attachment_url, attachment_name),
        media_type="application/octet-stream",
    )
