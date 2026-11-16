"""
app/auth.py — JWT creation, verification, and FastAPI dependency.
"""
import logging
import re
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from .config import config

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24


class HideTokenInLogs(logging.Filter):
    """The app sends its login JWT as /ws/market?token=..., and uvicorn logs that
    path; without this anyone who can read the logs could reuse the token."""
    _token = re.compile(r"token=[^&\s\"]+")

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(self._token.sub("token=***", a) if isinstance(a, str) else a
                                for a in record.args)
        return True

def verify_password(plain: str) -> bool:
    """Constant-time comparison to prevent timing attacks."""
    return secrets.compare_digest(plain, config.APP_PASSWORD)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, config.JWT_SECRET, algorithm=ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, config.JWT_SECRET, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

bearer_scheme = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> str:
    """Dependency: validates Bearer token and returns the username."""
    payload = decode_token(credentials.credentials)
    username: str = payload.get("sub")
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    return username
