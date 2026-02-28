"""
app/routes/auth_routes.py — Login endpoint.
POST /api/auth/login  →  { access_token, token_type }
"""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from ..config import config
from ..auth import create_access_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

class LoginRequest(BaseModel):
    username: str
    password: str

@router.post("/login")
def login(body: LoginRequest):
    if body.username != config.APP_USERNAME:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not verify_password(body.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token({"sub": body.username})
    return {"access_token": token, "token_type": "bearer"}
