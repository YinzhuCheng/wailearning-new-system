from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordBearer
from sqlalchemy.orm import Session
from apps.backend.courseeval_backend.core.config import settings
from apps.backend.courseeval_backend.db.database import get_db
from apps.backend.courseeval_backend.db.models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
# Optional Bearer for routes that accept anonymous requests but may inspect JWT when present (e.g. E2E dual gate).
_optional_http_bearer = HTTPBearer(auto_error=False)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def _user_from_jwt_token(token: str, db: Session) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_ver = payload.get("tv")
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    expected_ver = int(getattr(user, "token_version", 0) or 0)
    if token_ver is None:
        if expected_ver != 0:
            raise credentials_exception
    elif int(token_ver) != expected_ver:
        raise credentials_exception
    return user


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    return _user_from_jwt_token(token, db)


def get_current_user_optional(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(_optional_http_bearer)],
    db: Session = Depends(get_db),
) -> Optional[User]:
    if credentials is None or not credentials.credentials:
        return None
    try:
        return _user_from_jwt_token(credentials.credentials.strip(), db)
    except HTTPException:
        return None


def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user
