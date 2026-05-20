from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import func

from apps.backend.courseeval_backend.db.database import get_db
from apps.backend.courseeval_backend.db.models import Class, Notification, OperationLog, Student, User, UserRole
from apps.backend.courseeval_backend.attachments import delete_attachment_file_if_unreferenced, save_attachment
from apps.backend.courseeval_backend.api.schemas import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    MessageResponse,
    ProfileSelfUpdate,
    Token,
    UserCreate,
    UserResponse,
)
from apps.backend.courseeval_backend.core.auth import verify_password, get_password_hash, create_access_token, get_current_active_user
from apps.backend.courseeval_backend.core.config import settings
from apps.backend.courseeval_backend.domains.courses.access import prepare_student_course_context
from apps.backend.courseeval_backend.domains.roster.identity import ensure_student_class_id
from apps.backend.courseeval_backend.domains.roster.reconciliation import sync_student_roster_from_user_accounts
from apps.backend.courseeval_backend.services.logging import LogService

router = APIRouter(prefix="/api/auth", tags=["认证"])


def _client_ip(request: Optional[Request]) -> Optional[str]:
    if request is None or request.client is None:
        return None
    return request.client.host


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db), request: Request = None):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        LogService.log_login(
            db=db,
            user_id=None,
            username=form_data.username,
            ip_address=_client_ip(request),
            user_agent=str(request.headers.get("user-agent")) if request else None,
            success=False
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    user_id = user.id
    username = user.username
    is_student_with_class = user.role == UserRole.STUDENT.value and bool(user.class_id)

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={
            "sub": username,
            "tv": int(getattr(user, "token_version", 0) or 0),
        },
        expires_delta=access_token_expires,
    )

    LogService.log_login(
        db=db,
        user_id=user_id,
        username=username,
        ip_address=_client_ip(request),
        user_agent=str(request.headers.get("user-agent")) if request else None,
        success=True
    )

    if is_student_with_class:
        user = db.query(User).filter(User.id == user_id).first()
        if user is not None:
            prepare_student_course_context(user, db)
            db.commit()

    return {"access_token": access_token, "token_type": "bearer"}


def _forgot_password_ip_over_budget(db: Session, ip: Optional[str]) -> bool:
    lim = int(getattr(settings, "FORGOT_PASSWORD_MAX_REQUESTS_PER_IP_PER_HOUR", 40) or 0)
    if lim <= 0 or not ip:
        return False
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    n = (
        db.query(func.count(OperationLog.id))
        .filter(
            OperationLog.action == "forgot_password_request",
            OperationLog.ip_address == ip,
            OperationLog.created_at >= since,
        )
        .scalar()
        or 0
    )
    return int(n) >= lim


def _forgot_password_user_on_cooldown(db: Session, user: User) -> bool:
    cooldown = int(getattr(settings, "FORGOT_PASSWORD_USERNAME_COOLDOWN_SECONDS", 0) or 0)
    if cooldown <= 0:
        return False
    title = f"忘记密码：{user.username}"
    last = (
        db.query(Notification)
        .filter(
            Notification.notification_kind == "password_reset_request",
            Notification.title == title,
        )
        .order_by(Notification.id.desc())
        .first()
    )
    if not last or not last.created_at:
        return False
    prev = last.created_at
    if prev.tzinfo is None:
        prev = prev.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - prev
    return delta.total_seconds() < float(cooldown)


def _admin_reset_link_path(user_id: int) -> str:
    return f"/users?open_reset_password_user_id={int(user_id)}"


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_db),
    request: Request = None,
):
    """Non-admin login-page flow: notify administrators to reset the account password."""
    raw = (payload.username or "").strip()
    if not raw:
        return {"message": "若账号存在且需要重置密码，已向管理员发送提醒。"}

    ip = _client_ip(request)
    if _forgot_password_ip_over_budget(db, ip):
        LogService.log(
            db=db,
            action="forgot_password_request",
            target_type="auth",
            user_id=None,
            username=raw,
            target_id=None,
            target_name=None,
            details="Forgot-password skipped: IP hourly budget exceeded.",
            ip_address=ip,
            user_agent=str(request.headers.get("user-agent")) if request else None,
            result="rate_limited",
        )
        return {"message": "若账号存在且需要重置密码，已向管理员发送提醒。"}

    user = db.query(User).filter(User.username == raw).first()
    if not user or (user.role or "").strip() == UserRole.ADMIN.value:
        return {"message": "若账号存在且需要重置密码，已向管理员发送提醒。"}

    if _forgot_password_user_on_cooldown(db, user):
        LogService.log(
            db=db,
            action="forgot_password_request",
            target_type="auth",
            user_id=None,
            username=raw,
            target_id=user.id,
            target_name=user.username,
            details="Forgot-password skipped: per-username cooldown.",
            ip_address=ip,
            user_agent=str(request.headers.get("user-agent")) if request else None,
            result="cooldown",
        )
        return {"message": "若账号存在且需要重置密码，已向管理员发送提醒。"}

    system_actor = (
        db.query(User).filter(User.role == UserRole.ADMIN.value).order_by(User.id.asc()).first()
    )
    if not system_actor:
        return {"message": "若账号存在且需要重置密码，已向管理员发送提醒。"}

    base = (settings.FRONTEND_ADMIN_BASE_URL or "").strip().rstrip("/")
    link_href = f"{base}{_admin_reset_link_path(user.id)}" if base else _admin_reset_link_path(user.id)
    safe_name = escape(user.real_name or user.username or "")
    safe_user = escape(user.username or "")
    safe_href = escape(link_href)
    content = (
        f"<p>用户「{safe_name}」（用户名 <code>{safe_user}</code>）在登录页发起了<strong>忘记密码</strong>请求，"
        f"请通过安全渠道告知其新密码。</p>"
        f'<p><a href="{safe_href}">打开用户管理并执行密码重置</a></p>'
    )
    note = Notification(
        title=f"忘记密码：{user.username}",
        content=content,
        priority="important",
        is_pinned=False,
        class_id=None,
        subject_id=None,
        target_student_id=None,
        related_homework_id=None,
        related_student_id=None,
        related_appeal_id=None,
        target_user_id=None,
        notification_kind="password_reset_request",
        created_by=system_actor.id,
    )
    db.add(note)
    db.commit()

    LogService.log(
        db=db,
        action="forgot_password_request",
        target_type="auth",
        user_id=None,
        username=raw,
        target_id=user.id,
        target_name=user.username,
        details="Forgot-password notification created for administrators.",
        ip_address=_client_ip(request),
        user_agent=str(request.headers.get("user-agent")) if request else None,
        result="success",
    )
    return {"message": "若账号存在且需要重置密码，已向管理员发送提醒。"}


@router.post("/register", response_model=UserResponse)
def register(user_data: UserCreate, db: Session = Depends(get_db)):
    if not settings.ALLOW_PUBLIC_REGISTRATION:
        raise HTTPException(status_code=403, detail="Public registration is disabled.")

    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already registered")

    normalized_role = (user_data.role or "").strip()
    if normalized_role not in {UserRole.STUDENT.value}:
        raise HTTPException(status_code=403, detail="Public registration can only create student accounts.")
    if user_data.student_id is not None:
        raise HTTPException(status_code=403, detail="Public registration cannot bind an existing student profile.")
    target_class_id = ensure_student_class_id(db, user_data.class_id)

    if getattr(settings, "PUBLIC_REGISTRATION_VALIDATE_CLASS_EXISTS", True):
        klass = db.query(Class).filter(Class.id == target_class_id).first()
        if not klass:
            raise HTTPException(status_code=400, detail="Invalid class_id: class does not exist.")

    existing_student = (
        db.query(Student)
        .filter(Student.student_no == user_data.username, Student.class_id == target_class_id)
        .first()
    )
    if existing_student and db.query(User).filter(User.student_id == existing_student.id).first():
        raise HTTPException(status_code=400, detail="Student profile is already bound to an account.")

    hashed_password = get_password_hash(user_data.password)
    user = User(
        username=user_data.username,
        hashed_password=hashed_password,
        real_name=user_data.real_name,
        role=UserRole.STUDENT.value,
        class_id=target_class_id,
        student_id=existing_student.id if existing_student else None,
    )
    db.add(user)
    db.flush()
    if user.role == UserRole.STUDENT.value:
        sync_student_roster_from_user_accounts(db, [user.id])
    db.commit()
    db.refresh(user)
    return user

@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_active_user)):
    return current_user


@router.patch("/me", response_model=UserResponse)
def update_my_profile(
    payload: ProfileSelfUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    data = payload.model_dump(exclude_unset=True)
    if "real_name" in data:
        current_user.real_name = data["real_name"]
    if "discussion_page_size" in data:
        current_user.discussion_page_size = data["discussion_page_size"]
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return current_user


ALLOWED_AVATAR_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_AVATAR_BYTES = 2 * 1024 * 1024


@router.post("/me/avatar", response_model=UserResponse)
async def upload_my_avatar(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    filename = (file.filename or "").strip()
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_AVATAR_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Avatar must be a JPEG, PNG, GIF, or WebP image.",
        )

    content = await file.read()
    if len(content) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=400, detail="Avatar image must be 2 MB or smaller.")

    uploaded = await save_attachment(file, request, preloaded=content)
    size = int(uploaded.get("size") or 0)
    assert size <= MAX_AVATAR_BYTES

    previous = current_user.avatar_url
    current_user.avatar_url = str(uploaded["attachment_url"])
    db.add(current_user)
    db.commit()
    db.refresh(current_user)

    if previous and previous != current_user.avatar_url:
        delete_attachment_file_if_unreferenced(db, previous)

    return current_user


@router.delete("/me/avatar", response_model=UserResponse)
def remove_my_avatar(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    previous = current_user.avatar_url
    if not previous:
        return current_user

    current_user.avatar_url = None
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    delete_attachment_file_if_unreferenced(db, previous)
    return current_user


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None
):
    if not verify_password(payload.current_password, current_user.hashed_password):
        LogService.log(
            db=db,
            action="change_password",
            target_type="auth",
            user_id=current_user.id,
            username=current_user.username,
            target_id=current_user.id,
            target_name=current_user.username,
            details="Current password verification failed.",
            ip_address=_client_ip(request),
            user_agent=str(request.headers.get("user-agent")) if request else None,
            result="failed",
        )
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    current_user.hashed_password = get_password_hash(payload.new_password)
    current_user.token_version = int(getattr(current_user, "token_version", 0) or 0) + 1
    db.add(current_user)
    db.commit()

    LogService.log(
        db=db,
        action="change_password",
        target_type="auth",
        user_id=current_user.id,
        username=current_user.username,
        target_id=current_user.id,
        target_name=current_user.username,
        details="User changed their own password.",
        ip_address=_client_ip(request),
        user_agent=str(request.headers.get("user-agent")) if request else None,
        result="success"
    )

    return {"message": "Password updated successfully"}
