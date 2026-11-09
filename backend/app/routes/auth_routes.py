"""
app/routes/auth_routes.py — Login endpoint.
POST /api/auth/login  →  { access_token, token_type }
"""
import time

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from ..config import config
from ..auth import create_access_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Brute-force guard: after MAX_FAILURES wrong passwords from one IP, refuse
# logins from that IP for LOCKOUT_S. In-memory is enough for one API process.
MAX_FAILURES = 5
LOCKOUT_S = 300
_failures: dict[str, tuple[int, float]] = {}  # ip -> (count, last_failure_epoch)


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginRequest, request: Request):
    ip = request.client.host if request.client else "unknown"
    count, last = _failures.get(ip, (0, 0.0))
    if count >= MAX_FAILURES and time.time() - last < LOCKOUT_S:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed logins. Try again in a few minutes.",
        )

    if body.username != config.APP_USERNAME or not verify_password(body.password):
        if len(_failures) > 1000:  # keep the table bounded
            _failures.clear()
        if time.time() - last >= LOCKOUT_S:
            count = 0  # old failures expire
        _failures[ip] = (count + 1, time.time())
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    _failures.pop(ip, None)
    token = create_access_token({"sub": body.username})
    return {"access_token": token, "token_type": "bearer"}
