from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AppearanceStyleConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    primary: str = "blue"
    accent: str = "cyan"
    shadow: str = "soft"
    transparency: str = "balanced"
    radius: str = "balanced"
    density: str = "comfortable"
    font_family: Literal["system", "song", "hei", "kai", "mono"] = "system"
    font_scale: Literal["small", "medium", "large"] = "medium"


class AppearancePresetResponse(BaseModel):
    key: str
    name: str
    description: str
    config: AppearanceStyleConfig


class UserAppearanceStyleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    source: Literal["preset", "custom"] = "custom"
    preset_key: Optional[str] = Field(default=None, max_length=80)
    config: AppearanceStyleConfig
    select_after_save: bool = True

    @field_validator("name")
    @classmethod
    def strip_style_name(cls, value: str) -> str:
        stripped = (value or "").strip()
        if not stripped:
            raise ValueError("Style name cannot be empty.")
        return stripped


class UserAppearanceStyleUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    source: Optional[Literal["preset", "custom"]] = None
    preset_key: Optional[str] = Field(default=None, max_length=80)
    config: Optional[AppearanceStyleConfig] = None

    @field_validator("name")
    @classmethod
    def strip_optional_style_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        stripped = (value or "").strip()
        if not stripped:
            raise ValueError("Style name cannot be empty.")
        return stripped


class UserAppearanceStyleResponse(BaseModel):
    id: int
    user_id: int
    name: str
    source: str
    preset_key: Optional[str] = None
    config: AppearanceStyleConfig
    is_selected: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserAppearanceStateResponse(BaseModel):
    system_default_preset: str = "professional-blue"
    selected_style: Optional[UserAppearanceStyleResponse] = None
    saved_styles: List[UserAppearanceStyleResponse] = Field(default_factory=list)
