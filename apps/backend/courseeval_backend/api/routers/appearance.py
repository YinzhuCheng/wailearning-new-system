from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.api.schemas import (
    AppearancePresetResponse,
    AppearanceStyleConfig,
    MessageResponse,
    UserAppearanceStateResponse,
    UserAppearanceStyleCreate,
    UserAppearanceStyleResponse,
    UserAppearanceStyleUpdate,
)
from apps.backend.courseeval_backend.core.auth import get_current_active_user
from apps.backend.courseeval_backend.db.database import get_db
from apps.backend.courseeval_backend.db.models import SystemSetting, User, UserAppearanceStyle


router = APIRouter(prefix="/api/appearance", tags=["外观风格"])


OFFICIAL_PRESETS = [
    {
        "key": "professional-blue",
        "name": "Professional Blue",
        "description": "Calm operational blue with cyan accents, soft shadows, and balanced radius.",
        "config": {
            "primary": "blue",
            "accent": "cyan",
            "shadow": "soft",
            "transparency": "balanced",
            "radius": "balanced",
            "density": "comfortable",
            "font_family": "system",
            "font_scale": "medium",
        },
    },
    {
        "key": "fresh-green",
        "name": "Fresh Green",
        "description": "Green primary actions with blue accents, soft shadows, and softer corners.",
        "config": {
            "primary": "green",
            "accent": "blue",
            "shadow": "soft",
            "transparency": "balanced",
            "radius": "soft",
            "density": "comfortable",
            "font_family": "system",
            "font_scale": "medium",
        },
    },
    {
        "key": "warm-amber",
        "name": "Warm Amber",
        "description": "Amber action color, teal accents, medium shadow, and crisp surfaces.",
        "config": {
            "primary": "amber",
            "accent": "teal",
            "shadow": "medium",
            "transparency": "solid",
            "radius": "balanced",
            "density": "comfortable",
            "font_family": "system",
            "font_scale": "medium",
        },
    },
    {
        "key": "minimal-gray",
        "name": "Minimal Gray",
        "description": "Neutral gray theme with violet accents, lower shadows, and compact controls.",
        "config": {
            "primary": "gray",
            "accent": "violet",
            "shadow": "flat",
            "transparency": "solid",
            "radius": "subtle",
            "density": "compact",
            "font_family": "system",
            "font_scale": "medium",
        },
    },
    {
        "key": "academic-navy",
        "name": "Academic Navy",
        "description": "Navy primary palette with amber accents for a formal academic feel.",
        "config": {
            "primary": "navy",
            "accent": "amber",
            "shadow": "medium",
            "transparency": "balanced",
            "radius": "subtle",
            "density": "comfortable",
            "font_family": "system",
            "font_scale": "medium",
        },
    },
    {
        "key": "high-contrast",
        "name": "High Contrast",
        "description": "High contrast slate surfaces, red accents, solid backgrounds, and strong focus visibility.",
        "config": {
            "primary": "slate",
            "accent": "red",
            "shadow": "strong",
            "transparency": "solid",
            "radius": "subtle",
            "density": "comfortable",
            "font_family": "system",
            "font_scale": "medium",
        },
    },
]


def _preset_map() -> dict[str, dict]:
    return {item["key"]: item for item in OFFICIAL_PRESETS}


def _system_default_preset(db: Session) -> str:
    row = db.query(SystemSetting).filter(SystemSetting.setting_key == "appearance_default_preset").first()
    value = (row.setting_value if row else None) or "professional-blue"
    return value if value in _preset_map() else "professional-blue"


def _serialize_style(style: UserAppearanceStyle) -> UserAppearanceStyleResponse:
    raw_config = style.config or {}
    return UserAppearanceStyleResponse(
        id=style.id,
        user_id=style.user_id,
        name=style.name,
        source=style.source,
        preset_key=style.preset_key,
        config=AppearanceStyleConfig.model_validate(raw_config),
        is_selected=bool(style.is_selected),
        created_at=style.created_at,
        updated_at=style.updated_at,
    )


def _owned_style_or_404(style_id: int, current_user: User, db: Session) -> UserAppearanceStyle:
    style = (
        db.query(UserAppearanceStyle)
        .filter(UserAppearanceStyle.id == style_id, UserAppearanceStyle.user_id == current_user.id)
        .first()
    )
    if not style:
        raise HTTPException(status_code=404, detail="Appearance style not found.")
    return style


def _clear_selected_styles(current_user: User, db: Session) -> None:
    (
        db.query(UserAppearanceStyle)
        .filter(UserAppearanceStyle.user_id == current_user.id, UserAppearanceStyle.is_selected.is_(True))
        .update({UserAppearanceStyle.is_selected: False}, synchronize_session=False)
    )


@router.get("/presets", response_model=List[AppearancePresetResponse])
def list_appearance_presets():
    return OFFICIAL_PRESETS


@router.get("/me", response_model=UserAppearanceStateResponse)
def get_my_appearance(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    styles = (
        db.query(UserAppearanceStyle)
        .filter(UserAppearanceStyle.user_id == current_user.id)
        .order_by(UserAppearanceStyle.is_selected.desc(), UserAppearanceStyle.updated_at.desc(), UserAppearanceStyle.id.desc())
        .all()
    )
    selected = next((style for style in styles if style.is_selected), None)
    return UserAppearanceStateResponse(
        system_default_preset=_system_default_preset(db),
        selected_style=_serialize_style(selected) if selected else None,
        saved_styles=[_serialize_style(style) for style in styles],
    )


@router.post("/me/styles", response_model=UserAppearanceStyleResponse)
def create_my_appearance_style(
    payload: UserAppearanceStyleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if payload.source == "preset" and payload.preset_key and payload.preset_key not in _preset_map():
        raise HTTPException(status_code=400, detail="Unknown official preset.")

    if payload.select_after_save:
        _clear_selected_styles(current_user, db)

    style = UserAppearanceStyle(
        user_id=current_user.id,
        name=payload.name,
        source=payload.source,
        preset_key=payload.preset_key,
        config=payload.config.model_dump(),
        is_selected=payload.select_after_save,
    )
    db.add(style)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A style with this name already exists.") from exc
    db.refresh(style)
    return _serialize_style(style)


@router.put("/me/styles/{style_id}", response_model=UserAppearanceStyleResponse)
def update_my_appearance_style(
    style_id: int,
    payload: UserAppearanceStyleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    style = _owned_style_or_404(style_id, current_user, db)
    if payload.name is not None:
        style.name = payload.name
    if payload.source is not None:
        style.source = payload.source
    if payload.preset_key is not None:
        if payload.preset_key and payload.preset_key not in _preset_map():
            raise HTTPException(status_code=400, detail="Unknown official preset.")
        style.preset_key = payload.preset_key
    if payload.config is not None:
        style.config = payload.config.model_dump()
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A style with this name already exists.") from exc
    db.refresh(style)
    return _serialize_style(style)


@router.post("/me/styles/{style_id}/select", response_model=UserAppearanceStateResponse)
def select_my_appearance_style(
    style_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    style = _owned_style_or_404(style_id, current_user, db)
    _clear_selected_styles(current_user, db)
    style.is_selected = True
    db.commit()
    return get_my_appearance(db=db, current_user=current_user)


@router.post("/me/use-system", response_model=UserAppearanceStateResponse)
def use_system_appearance(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _clear_selected_styles(current_user, db)
    db.commit()
    return get_my_appearance(db=db, current_user=current_user)


@router.delete("/me/styles/{style_id}", response_model=MessageResponse)
def delete_my_appearance_style(
    style_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    style = _owned_style_or_404(style_id, current_user, db)
    db.delete(style)
    db.commit()
    return {"message": "Appearance style deleted."}
