from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator

ContentFormatLiteral = Literal["markdown", "plain"]


class NotificationBase(BaseModel):
    title: str
    content: Optional[str] = None
    content_format: ContentFormatLiteral = "markdown"
    attachment_name: Optional[str] = None
    attachment_url: Optional[str] = None
    priority: str = "normal"
    is_pinned: bool = False
    class_id: Optional[int] = None
    subject_id: Optional[int] = None
    target_student_id: Optional[int] = None
    related_homework_id: Optional[int] = None
    related_student_id: Optional[int] = None
    related_appeal_id: Optional[int] = None
    related_score_appeal_id: Optional[int] = None
    target_user_id: Optional[int] = None
    notification_kind: str = "general"

    @field_validator("content_format", mode="before")
    @classmethod
    def validate_notification_content_format(cls, value):
        from apps.backend.courseeval_backend.domains.text_content_format import normalize_content_format

        return normalize_content_format(value if isinstance(value, str) else None)


class NotificationCreate(NotificationBase):
    pass


class NotificationUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    content_format: Optional[ContentFormatLiteral] = None
    attachment_name: Optional[str] = None
    attachment_url: Optional[str] = None
    remove_attachment: bool = False
    priority: Optional[str] = None
    is_pinned: Optional[bool] = None
    class_id: Optional[int] = None
    subject_id: Optional[int] = None
    target_student_id: Optional[int] = None
    related_homework_id: Optional[int] = None
    related_student_id: Optional[int] = None
    related_appeal_id: Optional[int] = None
    related_score_appeal_id: Optional[int] = None
    target_user_id: Optional[int] = None
    notification_kind: Optional[str] = None

    @field_validator("content_format", mode="before")
    @classmethod
    def validate_notification_update_content_format(cls, value):
        if value is None:
            return None
        from apps.backend.courseeval_backend.domains.text_content_format import normalize_content_format

        return normalize_content_format(value if isinstance(value, str) else None)


class NotificationResponse(BaseModel):
    id: int
    title: str
    content: Optional[str] = None
    content_format: ContentFormatLiteral = "markdown"
    attachment_name: Optional[str] = None
    attachment_url: Optional[str] = None
    priority: str = "normal"
    is_pinned: bool = False
    class_id: Optional[int] = None
    subject_id: Optional[int] = None
    target_student_id: Optional[int] = None
    related_homework_id: Optional[int] = None
    related_student_id: Optional[int] = None
    related_appeal_id: Optional[int] = None
    related_score_appeal_id: Optional[int] = None
    appeal_status: Optional[str] = None
    target_user_id: Optional[int] = None
    notification_kind: str = "general"
    created_by: int
    created_at: datetime
    updated_at: datetime
    creator_name: Optional[str] = None
    class_name: Optional[str] = None
    subject_name: Optional[str] = None
    is_read: Optional[bool] = False

    model_config = ConfigDict(from_attributes=True)


class NotificationListResponse(BaseModel):
    total: int
    unread_count: int
    data: List[NotificationResponse]


class NotificationSyncStatus(BaseModel):
    """Lightweight snapshot for polling: size of visible inbox and change watermark."""

    total: int
    unread_count: int
    latest_updated_at: Optional[datetime] = None
