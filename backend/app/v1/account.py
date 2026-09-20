"""Conta do usuario final: cadastro, verificacao de e-mail, senha, filtros
salvos e historico de alertas.

Separado de `auth_routes` (admin) porque as regras sao outras: cadastro
publico, verificacao obrigatoria antes de alertar e limite de filtros por
plano (RN-007).
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import create_access_token, get_current_user, hash_password, verify_password
from app.database import get_db
from app.engine.search import describe_criteria, normalize_criteria
from app.models import (
    Alert, AuthToken, Item, PLAN_FREE, PLAN_PRO, SavedFilter, Source, Subscription, User,
)
from app.notify.email import EmailUnavailable, is_valid_email, send_email
from app.notify.templates import reset_email, verify_email
from app.notify.whatsapp import normalize_phone
from app.settings_service import get_setting, get_setting_bool, get_setting_int
from app.timeutil import now_brt
from app.v1.serializers import SerializerContext

logger = logging.getLogger("zleilao.account")
router = APIRouter()


# ── schemas ────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    phone: Optional[str] = None


class ForgotRequest(BaseModel):
    email: EmailStr


class ResetRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=200)


class ProfileUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=100)
    phone: Optional[str] = None
    email_opt_in: Optional[bool] = None
    whatsapp_opt_in: Optional[bool] = None
    quiet_start: Optional[str] = None
    quiet_end: Optional[str] = None


class FilterInput(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    criteria: dict[str, Any] = Field(default_factory=dict)
    channels: list[str] = Field(default_factory=lambda: ["email"])
    is_active: bool = True


# ── helpers ────────────────────────────────────────────────────────────

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def _issue_token(db: AsyncSession, user: User, kind: str) -> str:
    ttl = await get_setting_int(db, "token_ttl_hours", 48)
    token = secrets.token_urlsafe(32)
    db.add(AuthToken(user_id=user.id, kind=kind, token_hash=_token_hash(token),
                     expires_at=now_brt() + timedelta(hours=ttl)))
    return token


async def _consume_token(db: AsyncSession, token: str, kind: str) -> User:
    row = await db.scalar(select(AuthToken).where(
        AuthToken.token_hash == _token_hash(token), AuthToken.kind == kind))
    if not row or row.used_at or row.expires_at < now_brt():
        raise HTTPException(400, "Link inválido ou expirado. Peça um novo.")
    row.used_at = now_brt()
    user = await db.get(User, row.user_id)
    if not user:
        raise HTTPException(400, "Conta não encontrada")
    return user


async def _plan_of(db: AsyncSession, user_id: int) -> str:
    sub = await db.scalar(select(Subscription).where(Subscription.user_id == user_id))
    return sub.plan if sub and sub.status == "active" else PLAN_FREE


async def _max_filters(db: AsyncSession, plan: str) -> int:
    key = "pro_max_filters" if plan == PLAN_PRO else "free_max_filters"
    return await get_setting_int(db, key, 30 if plan == PLAN_PRO else 3)


def _filter_out(sf: SavedFilter) -> dict:
    return {
        "id": sf.id, "name": sf.name, "criteria": sf.criteria or {}, "channels": sf.channels or [],
        "is_active": sf.is_active, "last_matched_at": sf.last_matched_at,
        "matches_count": sf.matches_count, "created_at": sf.created_at,
        "description": describe_criteria(normalize_criteria(sf.criteria)),
    }


async def get_current_account(user: User = Depends(get_current_user)) -> User:
    return user


# ── cadastro e verificação ─────────────────────────────────────────────

@router.post("/auth/register", status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    if not await get_setting_bool(db, "signup_enabled", True):
        raise HTTPException(403, "Cadastro temporariamente fechado")
    email = body.email.lower().strip()
    if await db.scalar(select(User).where(User.email == email)):
        # Não confirma nem nega a existência da conta para quem não está logado.
        raise HTTPException(409, "Não foi possível criar a conta com esse e-mail")

    phone = normalize_phone(body.phone) if body.phone else None
    if body.phone and not phone:
        raise HTTPException(400, "Telefone inválido. Use DDD + número.")

    user = User(email=email, hashed_password=hash_password(body.password), name=body.name.strip(),
                role="user", phone=phone, email_opt_in=True, whatsapp_opt_in=False)
    db.add(user)
    await db.flush()
    db.add(Subscription(user_id=user.id, plan=PLAN_FREE, status="active", provider="manual"))

    require_verify = await get_setting_bool(db, "require_email_verification", True)
    sent = False
    if require_verify:
        token = await _issue_token(db, user, "verify_email")
        base = (await get_setting(db, "public_base_url", "")).rstrip("/")
        subject, html = verify_email(f"{base}/verificar-email?token={token}", base)
        try:
            await send_email(db, user.email, subject, html)
            sent = True
        except EmailUnavailable as exc:
            # A conta é criada mesmo assim; o usuário pode pedir o reenvio depois.
            logger.warning("cadastro sem e-mail de verificacao (SMTP): %s", exc)
    else:
        user.email_verified_at = now_brt()

    await db.commit()
    return {
        "status": "ok",
        "verification_required": require_verify,
        "verification_sent": sent,
        "detail": ("Enviamos um e-mail de confirmação." if sent else
                   "Conta criada. O e-mail de confirmação não pôde ser enviado agora — peça o reenvio."),
    }


@router.post("/auth/verify-email")
async def verify_email_token(token: str, db: AsyncSession = Depends(get_db)):
    user = await _consume_token(db, token, "verify_email")
    user.email_verified_at = user.email_verified_at or now_brt()
    await db.commit()
    return {"status": "ok", "email": user.email}


@router.post("/auth/resend-verification")
async def resend_verification(body: ForgotRequest, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.email == body.email.lower().strip()))
    if user and not user.email_verified_at:
        token = await _issue_token(db, user, "verify_email")
        base = (await get_setting(db, "public_base_url", "")).rstrip("/")
        subject, html = verify_email(f"{base}/verificar-email?token={token}", base)
        try:
            await send_email(db, user.email, subject, html)
        except EmailUnavailable as exc:
            # Responder 503 aqui e 200 nos demais casos revelaria, pelo próprio
            # código de status, que a conta existe e está sem verificar. A falha
            # de SMTP vai só para o log; a resposta continua igual para todos.
            logger.warning("reenvio de verificacao sem SMTP para %s: %s", user.email, exc)
        await db.commit()
    # Resposta igual exista ou não a conta, para não vazar quem tem cadastro.
    return {"status": "ok", "detail": "Se houver uma conta com esse e-mail, enviamos o link."}


@router.post("/auth/forgot-password")
async def forgot_password(body: ForgotRequest, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.email == body.email.lower().strip()))
    if user and user.is_active:
        token = await _issue_token(db, user, "reset_password")
        base = (await get_setting(db, "public_base_url", "")).rstrip("/")
        subject, html = reset_email(f"{base}/redefinir-senha?token={token}", base)
        try:
            await send_email(db, user.email, subject, html)
        except EmailUnavailable as exc:
            logger.warning("reset sem e-mail (SMTP): %s", exc)
        await db.commit()
    return {"status": "ok", "detail": "Se houver uma conta com esse e-mail, enviamos o link."}


@router.post("/auth/reset-password")
async def reset_password(body: ResetRequest, db: AsyncSession = Depends(get_db)):
    user = await _consume_token(db, body.token, "reset_password")
    user.hashed_password = hash_password(body.new_password)
    # Quem provou controlar a caixa de e-mail também verificou o endereço.
    user.email_verified_at = user.email_verified_at or now_brt()
    await db.commit()
    token = create_access_token(data={"sub": user.email})
    return {"status": "ok", "access_token": token, "token_type": "bearer",
            "user_email": user.email, "user_name": user.name, "role": user.role}


# ── perfil ─────────────────────────────────────────────────────────────

@router.get("/me")
async def me(user: User = Depends(get_current_account), db: AsyncSession = Depends(get_db)):
    plan = await _plan_of(db, user.id)
    sub = await db.scalar(select(Subscription).where(Subscription.user_id == user.id))
    used = await db.scalar(select(func.count(SavedFilter.id)).where(SavedFilter.user_id == user.id)) or 0
    return {
        "id": user.id, "email": user.email, "name": user.name, "role": user.role,
        "phone": user.phone, "email_opt_in": user.email_opt_in, "whatsapp_opt_in": user.whatsapp_opt_in,
        "email_verified": user.email_verified_at is not None,
        "quiet_start": user.quiet_start, "quiet_end": user.quiet_end,
        "plan": plan,
        "plan_status": sub.status if sub else "active",
        "plan_expires_at": sub.current_period_end if sub else None,
        "filters_used": used,
        "filters_limit": await _max_filters(db, plan),
        "whatsapp_channel_available": await get_setting_bool(db, "whatsapp_enabled", False),
        "realtime_alerts": plan == PLAN_PRO,
    }


@router.patch("/me")
async def update_me(body: ProfileUpdate, user: User = Depends(get_current_account), db: AsyncSession = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    if "phone" in data:
        if data["phone"]:
            phone = normalize_phone(data["phone"])
            if not phone:
                raise HTTPException(400, "Telefone inválido. Use DDD + número.")
            user.phone = phone
        else:
            user.phone = None
            user.whatsapp_opt_in = False
    if data.get("whatsapp_opt_in") and not user.phone:
        raise HTTPException(400, "Cadastre um telefone antes de ativar o WhatsApp")
    for field in ("name", "email_opt_in", "whatsapp_opt_in", "quiet_start", "quiet_end"):
        if field in data:
            setattr(user, field, data[field])
    await db.commit()
    return await me(user, db)


class ChangePassword(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)


@router.post("/me/change-password")
async def change_password(body: ChangePassword, user: User = Depends(get_current_account), db: AsyncSession = Depends(get_db)):
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(400, "Senha atual incorreta")
    user.hashed_password = hash_password(body.new_password)
    await db.commit()
    return {"status": "ok"}


# ── filtros salvos ─────────────────────────────────────────────────────

@router.get("/me/filters")
async def list_filters(user: User = Depends(get_current_account), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(SavedFilter).where(SavedFilter.user_id == user.id).order_by(SavedFilter.created_at.desc())
    )).scalars().all()
    plan = await _plan_of(db, user.id)
    return {"filters": [_filter_out(f) for f in rows], "limit": await _max_filters(db, plan), "plan": plan}


@router.post("/me/filters", status_code=201)
async def create_filter(body: FilterInput, user: User = Depends(get_current_account), db: AsyncSession = Depends(get_db)):
    plan = await _plan_of(db, user.id)
    limit = await _max_filters(db, plan)
    used = await db.scalar(select(func.count(SavedFilter.id)).where(SavedFilter.user_id == user.id)) or 0
    if used >= limit:
        raise HTTPException(
            403, f"Seu plano permite {limit} filtro(s) salvo(s). Remova um ou mude de plano para criar mais.")

    criteria = normalize_criteria(body.criteria)
    channels = [c for c in body.channels if c in ("email", "whatsapp")] or ["email"]
    if "whatsapp" in channels and not await get_setting_bool(db, "whatsapp_enabled", False):
        channels = [c for c in channels if c != "whatsapp"] or ["email"]
    sf = SavedFilter(
        user_id=user.id, name=(body.name or describe_criteria(criteria))[:120],
        criteria=criteria, channels=channels, is_active=body.is_active,
        # Nasce já avaliado: sem isso o usuário recebe de imediato tudo que foi
        # publicado na janela de lookback, o que parece spam.
        last_checked_at=now_brt(),
    )
    db.add(sf)
    await db.commit()
    await db.refresh(sf)
    return _filter_out(sf)


@router.put("/me/filters/{filter_id}")
async def update_filter(filter_id: int, body: FilterInput, user: User = Depends(get_current_account), db: AsyncSession = Depends(get_db)):
    sf = await db.scalar(select(SavedFilter).where(SavedFilter.id == filter_id, SavedFilter.user_id == user.id))
    if not sf:
        raise HTTPException(404, "Filtro não encontrado")
    sf.criteria = normalize_criteria(body.criteria)
    sf.name = (body.name or describe_criteria(sf.criteria))[:120]
    channels = [c for c in body.channels if c in ("email", "whatsapp")] or ["email"]
    if "whatsapp" in channels and not await get_setting_bool(db, "whatsapp_enabled", False):
        channels = [c for c in channels if c != "whatsapp"] or ["email"]
    sf.channels = channels
    sf.is_active = body.is_active
    await db.commit()
    await db.refresh(sf)
    return _filter_out(sf)


@router.delete("/me/filters/{filter_id}")
async def delete_filter(filter_id: int, user: User = Depends(get_current_account), db: AsyncSession = Depends(get_db)):
    sf = await db.scalar(select(SavedFilter).where(SavedFilter.id == filter_id, SavedFilter.user_id == user.id))
    if not sf:
        raise HTTPException(404, "Filtro não encontrado")
    await db.delete(sf)
    await db.commit()
    return {"status": "ok"}


@router.get("/me/filters/{filter_id}/preview")
async def preview_filter(filter_id: int, limit: int = 6, user: User = Depends(get_current_account), db: AsyncSession = Depends(get_db)):
    """Mostra o que o filtro pegaria hoje — o usuário confere antes de esperar o alerta."""
    from app.engine.search import apply_filters, base_query, category_path_for

    sf = await db.scalar(select(SavedFilter).where(SavedFilter.id == filter_id, SavedFilter.user_id == user.id))
    if not sf:
        raise HTTPException(404, "Filtro não encontrado")
    criteria = normalize_criteria(sf.criteria)
    cat = await category_path_for(db, criteria.get("category"))
    stmt = apply_filters(base_query(), criteria, category_path=cat)
    total = await db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    items = (await db.execute(
        stmt.order_by(Item.published_at.desc().nulls_last()).limit(min(limit, 24)).options(selectinload(Item.auction))
    )).scalars().unique().all()
    ctx = await SerializerContext(db).load(items)
    return {"total": total, "items": [ctx.card(i) for i in items]}


# ── alertas recebidos ──────────────────────────────────────────────────

@router.get("/me/alerts")
async def my_alerts(limit: int = 50, user: User = Depends(get_current_account), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(Alert).where(Alert.user_id == user.id).order_by(Alert.created_at.desc()).limit(min(limit, 200))
    )).scalars().all()
    items = {i.id: i for i in (await db.execute(
        select(Item).where(Item.id.in_([a.item_id for a in rows])).options(selectinload(Item.auction)))).scalars().all()} if rows else {}
    ctx = await SerializerContext(db).load(list(items.values()))
    out = []
    for a in rows:
        item = items.get(a.item_id)
        out.append({
            "id": a.id, "reason": a.reason, "status": a.status, "channel": a.channel,
            "detail": a.detail, "created_at": a.created_at, "sent_at": a.sent_at,
            "saved_filter_id": a.saved_filter_id,
            "item": ctx.card(item) if item else None,
        })
    return out
