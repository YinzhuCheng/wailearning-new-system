"""Prompt construction helpers for LLM homework grading."""

from __future__ import annotations

from typing import Optional

from apps.backend.courseeval_backend.db.models import Homework, HomeworkAttempt
from apps.backend.courseeval_backend.domains.text_content_format import (
    body_text_for_grading_llm,
    normalize_content_format,
)
from apps.backend.courseeval_backend.markdown_llm import expand_markdown_images_for_llm

# Stable section markers for the scoring prompt (model + debugging)
SECTION_ASSIGNMENT = "[SECTION:INSTRUCTOR_ASSIGNMENT]"
SECTION_STUDENT_BODY = "[SECTION:STUDENT_TEXT_RESPONSE]"
SECTION_ATTACHMENT = "[SECTION:ATTACHMENT_CONTENT]"
SECTION_IMAGES = "[SECTION:STUDENT_IMAGES]"
SECTION_NOTES = "[SECTION:PIPELINE_NOTES]"
SECTION_PRIOR_SUBMISSION = "[SECTION:PRIOR_SUBMISSION_ROLLING]"


def llm_assist_assignment_addendum(attempt: HomeworkAttempt) -> str:
    if not bool(getattr(attempt, "used_llm_assist", False)):
        return ""
    return (
        "### 学生申报：使用大语言模型辅助作答\n"
        "该生在提交时**诚信申报**本次曾使用大语言模型辅助。请据此调整评分侧重：\n"
        "- **着重**考查作答思路、概念迁移、论证链条与问题拆解能力；透过表述**反推**其真实知识功底。\n"
        "- **弱化**对措辞润色、排版细节、枚举完整性等「表面完美度」的苛求；若核心结论或主干推理错误，仍应体现在 score 中。\n"
        "- 若与参考答案或思路字面高度相似但推理薄弱，应谨慎给高分。\n"
    )


def comment_format_system_suffix(system_prompt: str) -> str:
    base = (system_prompt or "").strip()
    if "Markdown" in base or "markdown" in base or "LaTeX" in base or "latex" in base:
        return base
    return (
        base
        + "\n\n除上述格式约束外，JSON 内的 `comment` 字符串可使用 Markdown（标题、列表、加粗等）；"
        "数学公式可使用 `$...$`（行内）或 `$$...$$`（独立行）LaTeX。"
    )


def expand_homework_field_for_llm(homework: Homework, field: Optional[str], *, field_role: str) -> str:
    raw = field or ""
    if field_role == "content" and normalize_content_format(getattr(homework, "content_format", None)) == "plain":
        raw = body_text_for_grading_llm(content=raw, content_format="plain")
    return expand_markdown_images_for_llm(raw)
