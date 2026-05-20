from __future__ import annotations

from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse
from uuid import uuid4

from fastapi import HTTPException, Request, UploadFile
from sqlalchemy import or_
from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.attachment_compliance import assert_attachment_format_compliant
from apps.backend.courseeval_backend.core.config import settings

REPO_ROOT = Path(__file__).resolve().parents[3]
UPLOADS_DIR = Path(settings.UPLOADS_DIR).expanduser() if settings.UPLOADS_DIR else REPO_ROOT / "uploads"
ATTACHMENTS_DIR = UPLOADS_DIR / "attachments"
MAX_ATTACHMENT_SIZE = 20 * 1024 * 1024
COURSE_COVER_MAX_BYTES = 10 * 1024 * 1024
COURSE_COVER_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"}
COURSE_COVER_IMAGE_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/bmp",
    "image/svg+xml",
}
BLOCKED_ATTACHMENT_EXTENSIONS = {
    ".apk",
    ".app",
    ".bat",
    ".cmd",
    ".com",
    ".exe",
    ".msi",
    ".ps1",
    ".scr",
}
BLOCKED_ATTACHMENT_CONTENT_TYPES = {
    "application/x-msdownload",
    "application/x-msdos-program",
    "application/vnd.microsoft.portable-executable",
}
ATTACHMENT_URL_PREFIXES = (
    "/api/files/download/",
    "/uploads/attachments/",
    "/api/uploads/attachments/",
    "uploads/attachments/",
)


def get_attachment_directories() -> list[Path]:
    return [ATTACHMENTS_DIR]


def ensure_upload_directories() -> None:
    for attachments_dir in get_attachment_directories()[:1]:
        attachments_dir.mkdir(parents=True, exist_ok=True)


def validate_attachment_upload(file: UploadFile) -> str:
    filename = (file.filename or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="Please select a file to upload.")

    extension = Path(filename).suffix.lower()
    if extension in BLOCKED_ATTACHMENT_EXTENSIONS or file.content_type in BLOCKED_ATTACHMENT_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Executable files are not allowed.")

    return extension


def _looks_like_executable_payload(content: bytes) -> bool:
    head = bytes(content[:512]).lstrip()
    lower_head = head.lower()
    return (
        head.startswith(b"MZ")
        or head.startswith(b"\x7fELF")
        or lower_head.startswith(b"#!/bin/")
        or lower_head.startswith(b"#! /bin/")
        or b"<script language=\"jscript\"" in lower_head
    )


async def save_attachment(
    file: UploadFile,
    request: Request,
    *,
    preloaded: bytes | None = None,
) -> dict[str, object]:
    ensure_upload_directories()
    extension = validate_attachment_upload(file)
    content = preloaded if preloaded is not None else await file.read()
    size = len(content)
    if size == 0:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if size > MAX_ATTACHMENT_SIZE:
        raise HTTPException(status_code=400, detail="Attachment size must be 20 MB or smaller.")
    if _looks_like_executable_payload(content):
        raise HTTPException(status_code=400, detail="Executable file content is not allowed.")

    upload_filename = (file.filename or "").strip()
    assert_attachment_format_compliant(filename=upload_filename, extension=extension, content=content)

    stored_name = f"{uuid4().hex}{extension}"
    target_path = ATTACHMENTS_DIR / stored_name
    target_path.write_bytes(content)

    return {
        "attachment_name": file.filename,
        "attachment_url": str(request.url_for("download_attachment_by_name", stored_name=stored_name)),
        "content_type": file.content_type,
        "size": size,
    }


async def save_course_cover_image(file: UploadFile, request: Request) -> dict[str, object]:
    """Course cover: common raster/SVG formats, max 10 MiB."""
    ensure_upload_directories()
    filename = (file.filename or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="Please select an image file to upload.")
    extension = Path(filename).suffix.lower()
    if extension not in COURSE_COVER_IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported image format. Use JPG, PNG, GIF, WebP, BMP, or SVG.",
        )
    ct = (file.content_type or "").strip().lower()
    if ct and ct not in COURSE_COVER_IMAGE_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="File must be a common image type (e.g. image/jpeg, image/png).")

    content = await file.read()
    size = len(content)
    if size == 0:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if size > COURSE_COVER_MAX_BYTES:
        raise HTTPException(status_code=400, detail="Course cover image must be 10 MB or smaller.")

    stored_name = f"{uuid4().hex}{extension}"
    target_path = ATTACHMENTS_DIR / stored_name
    target_path.write_bytes(content)

    return {
        "attachment_name": file.filename,
        "attachment_url": str(request.url_for("download_attachment_by_name", stored_name=stored_name)),
        "content_type": file.content_type,
        "size": size,
    }


def delete_attachment_file(attachment_url: Optional[str]) -> None:
    target_path = get_attachment_file_path(attachment_url)
    if not target_path:
        return
    if target_path.exists():
        target_path.unlink()


def attachment_is_referenced(db: Session, attachment_url: Optional[str]) -> bool:
    if not attachment_url:
        return False

    from apps.backend.courseeval_backend.db.models import CourseMaterial, Homework, HomeworkAttempt, HomeworkSubmission, Notification, Subject, User

    if db.query(User).filter(User.avatar_url == attachment_url).first():
        return True

    if db.query(Subject).filter(Subject.cover_image_url == attachment_url).first():
        return True

    references = [
        db.query(Homework).filter(Homework.attachment_url == attachment_url).first(),
        db.query(HomeworkSubmission).filter(HomeworkSubmission.attachment_url == attachment_url).first(),
        db.query(HomeworkAttempt).filter(HomeworkAttempt.attachment_url == attachment_url).first(),
        db.query(Notification).filter(Notification.attachment_url == attachment_url).first(),
        db.query(CourseMaterial).filter(CourseMaterial.attachment_url == attachment_url).first(),
    ]
    if any(item is not None for item in references):
        return True

    needle = (attachment_url or "").replace("\\", "/")
    stored = get_attachment_stored_name(attachment_url)
    if needle:
        if (
            db.query(Homework)
            .filter(
                or_(
                    Homework.content.contains(needle),
                    Homework.reference_answer.contains(needle),
                    Homework.rubric_text.contains(needle),
                    Homework.rubric_staff_only.contains(needle),
                )
            )
            .first()
        ):
            return True
        if db.query(CourseMaterial).filter(CourseMaterial.content.contains(needle)).first():
            return True
    if stored and len(stored) >= 8:
        if (
            db.query(Homework)
            .filter(
                or_(
                    Homework.content.contains(stored),
                    Homework.reference_answer.contains(stored),
                    Homework.rubric_text.contains(stored),
                    Homework.rubric_staff_only.contains(stored),
                )
            )
            .first()
        ):
            return True
        if db.query(CourseMaterial).filter(CourseMaterial.content.contains(stored)).first():
            return True
    return False


def delete_attachment_file_if_unreferenced(db: Session, attachment_url: Optional[str]) -> None:
    if not attachment_url:
        return
    if attachment_is_referenced(db, attachment_url):
        return
    delete_attachment_file(attachment_url)


def get_attachment_file_path(attachment_url: Optional[str]) -> Optional[Path]:
    stored_name = get_attachment_stored_name(attachment_url)
    if not stored_name:
        return None

    directories = get_attachment_directories()
    for attachments_dir in directories:
        candidate = attachments_dir / stored_name
        if candidate.exists():
            return candidate

    return directories[0] / stored_name if directories else None


def get_attachment_stored_name(attachment_url: Optional[str]) -> Optional[str]:
    if not attachment_url:
        return None

    parsed_url = urlparse(attachment_url)
    attachment_path = unquote(parsed_url.path or attachment_url).replace("\\", "/")

    for prefix in ATTACHMENT_URL_PREFIXES:
        if prefix in attachment_path:
            suffix = attachment_path.split(prefix, 1)[1]
            stored_name = Path(suffix).name
            if stored_name:
                return stored_name

    fallback_name = Path(attachment_path).name
    if fallback_name and fallback_name not in {"", ".", "..", "attachments"}:
        return fallback_name

    return None


def get_attachment_download_name(attachment_url: Optional[str], attachment_name: Optional[str]) -> str:
    normalized_name = Path((attachment_name or "").strip()).name
    if normalized_name:
        return normalized_name

    target_path = get_attachment_file_path(attachment_url)
    if target_path:
        return target_path.name

    return "attachment"
