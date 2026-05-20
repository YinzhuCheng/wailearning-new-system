"""Attachment format compliance for generic uploads (homework, materials, notifications).

Aligned with domains.llm.attachments extraction rules: allow-list extensions; archives must
contain at least one allowed inner file (non-empty compliance).
"""

from __future__ import annotations

import io
import os
import tempfile
import zipfile
from pathlib import PurePosixPath

# Mirrors domains/llm/attachments.py — single-file types we accept for upload compliance.
ALLOWED_ATTACHMENT_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".txt",
        ".docx",
        ".doc",
        ".xlsx",
        ".xls",
        ".ipynb",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".bmp",
        ".zip",
        ".rar",
    }
    | {
        ext
        for ext in (
            ".c",
            ".cc",
            ".cpp",
            ".csv",
            ".go",
            ".h",
            ".hpp",
            ".html",
            ".java",
            ".js",
            ".json",
            ".jsx",
            ".md",
            ".py",
            ".rb",
            ".rs",
            ".sql",
            ".tex",
            ".ts",
            ".tsx",
            ".vue",
            ".xml",
            ".yaml",
            ".yml",
        )
    }
)

ARCHIVE_EXTENSIONS = frozenset({".zip", ".rar"})


def _safe_zip_member_name(name: str) -> str | None:
    normalized = PurePosixPath((name or "").replace("\\", "/"))
    parts = [p for p in normalized.parts if p not in ("", ".", "..")]
    if not parts:
        return None
    return "/".join(parts)


def _inner_suffix_allowed(suf: str) -> bool:
    return bool(suf) and suf in ALLOWED_ATTACHMENT_EXTENSIONS and suf not in ARCHIVE_EXTENSIONS


def _zip_has_allowed_inner(content: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                inner = _safe_zip_member_name(info.filename or "")
                if not inner:
                    continue
                suf = PurePosixPath(inner).suffix.lower()
                if _inner_suffix_allowed(suf):
                    return True
    except zipfile.BadZipFile:
        return False
    return False


def _rar_has_allowed_inner(content: bytes) -> bool:
    from apps.backend.courseeval_backend.domains.llm.attachments import _rar_extractor_tool_path

    if not _rar_extractor_tool_path():
        return True

    import rarfile

    tmp_path: str | None = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=".rar")
        os.write(fd, content)
        os.close(fd)
        with rarfile.RarFile(tmp_path) as archive:
            if archive.needs_password():
                from fastapi import HTTPException

                raise HTTPException(status_code=400, detail="加密的 RAR 压缩包不允许上传。")
            for info in archive.infolist():
                if info.isdir():
                    continue
                if getattr(info, "needs_password", lambda: False)():
                    from fastapi import HTTPException

                    raise HTTPException(status_code=400, detail="RAR 内含加密条目，不允许上传。")
                inner = _safe_zip_member_name(info.filename or "")
                if not inner:
                    continue
                suf = PurePosixPath(inner).suffix.lower()
                if _inner_suffix_allowed(suf):
                    return True
    except rarfile.BadRarFile as exc:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=400,
            detail="RAR 压缩包损坏或格式不合法。请更换文件后重试。",
        ) from exc
    except rarfile.NotRarFile as exc:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=400,
            detail="不是有效的 RAR 文件。请更换文件后重试。",
        ) from exc
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    return False


def assert_attachment_format_compliant(*, filename: str, extension: str, content: bytes) -> None:
    from fastapi import HTTPException

    ext = (extension or "").lower()
    if ext not in ALLOWED_ATTACHMENT_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                "附件格式不在允许列表内。支持 Office（.doc/.docx/.xls/.xlsx）、PDF、TXT、"
                "常见图片、Jupyter（.ipynb）、以及 .zip/.rar；"
                "压缩包内需至少包含一个上述类型的文件。"
            ),
        )

    if ext == ".zip":
        if not _zip_has_allowed_inner(content):
            raise HTTPException(
                status_code=400,
                detail="压缩包内未找到允许的文档类型，或压缩包已损坏。请更换文件后重试。",
            )
        return

    if ext == ".rar":
        if not _rar_has_allowed_inner(content):
            raise HTTPException(
                status_code=400,
                detail="压缩包内未找到允许的文档类型。请更换文件后重试。",
            )
        return

    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}:
        from PIL import Image, ImageFile, UnidentifiedImageError

        prev = ImageFile.LOAD_TRUNCATED_IMAGES
        ImageFile.LOAD_TRUNCATED_IMAGES = True
        try:
            im = Image.open(io.BytesIO(content))
            im.load()
        except (UnidentifiedImageError, OSError) as exc:
            raise HTTPException(
                status_code=400,
                detail="图片文件无法通过校验（可能已损坏或实际格式与扩展名不符）。请更换文件后重试。",
            ) from exc
        finally:
            ImageFile.LOAD_TRUNCATED_IMAGES = prev
        return

    if ext == ".pdf":
        import fitz

        try:
            doc = fitz.open(stream=content, filetype="pdf")
            doc.close()
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail="PDF 无法通过校验（可能已损坏）。请更换文件后重试。",
            ) from exc
        return

    if ext == ".docx":
        from docx import Document

        try:
            Document(io.BytesIO(content))
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail="Word（.docx）无法通过校验（可能已损坏）。请更换文件后重试。",
            ) from exc
        return

    if ext == ".doc":
        import olefile

        if not olefile.isOleFile(io.BytesIO(content)):
            raise HTTPException(
                status_code=400,
                detail="Word（.doc）无法通过校验（可能已损坏）。请更换文件后重试。",
            )
        return

    if ext == ".xlsx":
        import openpyxl

        try:
            openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True).close()
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail="Excel（.xlsx）无法通过校验（可能已损坏）。请更换文件后重试。",
            ) from exc
        return

    if ext == ".xls":
        import xlrd

        try:
            xlrd.open_workbook(file_contents=content)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail="Excel（.xls）无法通过校验（可能已损坏）。请更换文件后重试。",
            ) from exc
        return

    if ext == ".ipynb":
        import json

        try:
            data = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            try:
                data = json.loads(content.decode("utf-8-sig"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise HTTPException(
                    status_code=400,
                    detail="Jupyter（.ipynb）不是有效的 JSON。请更换文件后重试。",
                ) from exc
        if not isinstance(data, dict) or ("nbformat" not in data and "cells" not in data):
            raise HTTPException(
                status_code=400,
                detail="Jupyter（.ipynb）结构不符合笔记本格式。请更换文件后重试。",
            )
        return

    try:
        content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail="文本类附件须为 UTF-8 编码。请另存为 UTF-8 后重试，或改用 zip 打包。",
        ) from exc
