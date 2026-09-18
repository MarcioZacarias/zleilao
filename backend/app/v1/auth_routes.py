from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token, get_current_user, hash_password, verify_password
from app.database import get_db
from app.models import User

router = APIRouter()


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_name: str | None = None
    user_email: str
    role: str = "admin"


class MeResponse(BaseModel):
    id: int
    email: str
    name: str | None
    role: str
    is_active: bool


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/auth/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="E-mail ou senha incorretos")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Usuário desativado")
    token = create_access_token(data={"sub": user.email})
    return TokenResponse(access_token=token, user_name=user.name, user_email=user.email, role=user.role)


@router.get("/auth/me", response_model=MeResponse)
async def me(user: User = Depends(get_current_user)):
    return MeResponse(id=user.id, email=user.email, name=user.name, role=user.role, is_active=user.is_active)


@router.post("/auth/change-password")
async def change_password(body: ChangePasswordRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Senha atual incorreta")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="A nova senha precisa ter ao menos 8 caracteres")
    user.hashed_password = hash_password(body.new_password)
    await db.commit()
    return {"status": "ok"}
