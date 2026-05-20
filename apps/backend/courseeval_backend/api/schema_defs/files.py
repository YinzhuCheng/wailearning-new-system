from typing import Optional

from pydantic import BaseModel


class AttachmentUploadResponse(BaseModel):
    attachment_name: str
    attachment_url: str
    content_type: Optional[str] = None
    size: int
