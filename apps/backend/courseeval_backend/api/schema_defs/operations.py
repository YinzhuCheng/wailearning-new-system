from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class OperationLogResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    username: Optional[str] = None
    action: str
    target_type: str
    target_id: Optional[int] = None
    target_name: Optional[str] = None
    details: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    result: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OperationLogListResponse(BaseModel):
    total: int
    data: List[OperationLogResponse]


class SystemSettingResponse(BaseModel):
    id: int
    setting_key: str
    setting_value: Optional[str]
    description: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SystemSettingUpdate(BaseModel):
    setting_value: str


class SystemSettingsResponse(BaseModel):
    system_name: str
    login_background: str
    system_logo: str
    system_intro: str
    copyright: str
    use_bing_background: bool
    appearance_default_preset: str = "professional-blue"
