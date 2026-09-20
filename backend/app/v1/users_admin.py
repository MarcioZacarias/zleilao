"""Admin: contas, planos e alertas enviados.

Na F2 a ativacao do plano pago e' MANUAL (`provider="manual"`): a estrutura
esta' pronta para um gateway, mas cobranca automatica exige credenciais que
ainda nao existem. Isso permite vender antes de integrar pagamento.
"""
from __future__ import annotations

import logging
import math
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_admin
from app.database import get_db
from app.engine.search import describe_criteria, normalize_criteria
from app.models import Alert, Item, PLAN_FREE, PLAN_PRO, SavedFilter, Subscription, User
from app.timeutil import now_brt
from app.v1.serializers import SerializerContext

logger = logging.getLogger("zleilao.users_admin")
users_router = APIRouter()
alerts_router = APIRouter()


class PlanUpdate(BaseModel):
    plan: str = Field(pattern="^(free|pro)$")
    months: int = Field(default=1, ge=0, le=36)
    note: Optional[str] = None


class UserUpdate(BaseModel):
    is_active: Optional[bool] = None
    role: Optional[str] = Field(default=None, pattern="^(user|admin)$")
    email_verified: Optional[bool] = None


async def _user_out(db: AsyncSession, u: User) -> dict:
    sub = await db.scalar(select(Subscription).where(Subscription.user_id == u.id))
    filters = await db.scalar(select(func.count(SavedFilter.id)).where(SavedFilter.user_id == u.id)) or 0
    alerts_sent = await db.scalar(select(func.count(Alert.id)).where(
        Alert.user_id == u.id, Alert.status == "sent")) or 0
    return {
        "id": u.id, "email": u.email, "name": u.name, "role": u.role, "is_active": u.is_active,
        "phone": u.phone, "email_opt_in": u.email_opt_in, "whatsapp_opt_in": u.whatsapp_opt_in,
        "email_verified": u.email_verified_at is not None,
        "created_at": u.created_at, "last_login_at": u.last_login_at,
        "plan": sub.plan if sub else PLAN_FREE,
        "plan_status": sub.status if sub else "active",
        "plan_expires_at": sub.current_period_end if sub else None,
        "plan_note": sub.note if sub else None,
        "filters": filters, "alerts_sent": alerts_sent,
    }


@users_router.get("")
async def list_users(
    q: Optional[str] = None,
    plan: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    stmt = select(User)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(User.email.ilike(like), User.name.ilike(like), User.phone.ilike(like)))
    if plan:
        stmt = stmt.join(Subscription, Subscription.user_id == User.id).where(Subscription.plan == plan)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (await db.execute(
        stmt.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return {
        "users": [await _user_out(db, u) for u in rows],
        "meta": {"page": page, "page_size": page_size, "total": total, "pages": max(1, math.ceil(total / page_size))},
    }


@users_router.get("/summary")
async def users_summary(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_admin)):
    total = await db.scalar(select(func.count(User.id))) or 0
    verified = await db.scalar(select(func.count(User.id)).where(User.email_verified_at.isnot(None))) or 0
    by_plan = dict((await db.execute(
        select(Subscription.plan, func.count()).where(Subscription.status == "active").group_by(Subscription.plan)
    )).all())
    filters = await db.scalar(select(func.count(SavedFilter.id)).where(SavedFilter.is_active.is_(True))) or 0
    day_start = now_brt().replace(hour=0, minute=0, second=0, microsecond=0)
    sent_today = await db.scalar(select(func.count(Alert.id)).where(
        Alert.status == "sent", Alert.sent_at >= day_start)) or 0
    pending = await db.scalar(select(func.count(Alert.id)).where(Alert.status == "pending")) or 0
    failed = await db.scalar(select(func.count(Alert.id)).where(Alert.status == "failed")) or 0
    return {
        "users_total": total, "users_verified": verified, "by_plan": by_plan,
        "active_filters": filters, "alerts_sent_today": sent_today,
        "alerts_pending": pending, "alerts_failed": failed,
    }


@users_router.patch("/{user_id}")
async def update_user(user_id: int, body: UserUpdate, db: AsyncSession = Depends(get_db),
                      admin: User = Depends(get_current_admin)):
    u = await db.get(User, user_id)
    if not u:
        raise HTTPException(404, "Usuário não encontrado")
    data = body.model_dump(exclude_unset=True)
    if u.id == admin.id and data.get("role") == "user":
        raise HTTPException(400, "Você não pode remover o próprio acesso de administrador")
    if u.id == admin.id and data.get("is_active") is False:
        raise HTTPException(400, "Você não pode desativar a própria conta")
    if "is_active" in data:
        u.is_active = data["is_active"]
    if "role" in data:
        u.role = data["role"]
    if "email_verified" in data:
        u.email_verified_at = now_brt() if data["email_verified"] else None
    await db.commit()
    return await _user_out(db, u)


@users_router.put("/{user_id}/plan")
async def set_plan(user_id: int, body: PlanUpdate, db: AsyncSession = Depends(get_db),
                   admin: User = Depends(get_current_admin)):
    u = await db.get(User, user_id)
    if not u:
        raise HTTPException(404, "Usuário não encontrado")
    sub = await db.scalar(select(Subscription).where(Subscription.user_id == user_id))
    if not sub:
        sub = Subscription(user_id=user_id)
        db.add(sub)
    sub.plan = body.plan
    sub.status = "active"
    sub.provider = "manual"
    sub.activated_by = admin.email
    sub.note = body.note
    # `months=0` no plano pago = acesso sem vencimento (cortesia, parceiro).
    sub.current_period_end = (now_brt() + timedelta(days=30 * body.months)) if (body.plan == PLAN_PRO and body.months) else None
    await db.commit()
    logger.info("plano de %s alterado para %s por %s", u.email, body.plan, admin.email)
    return await _user_out(db, u)


@users_router.get("/{user_id}/filters")
async def user_filters(user_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_admin)):
    rows = (await db.execute(select(SavedFilter).where(SavedFilter.user_id == user_id))).scalars().all()
    # `description` vem pronta, igual em /me/filters: o admin não deveria ter
    # que remontar o resumo do critério no cliente.
    return [{"id": f.id, "name": f.name, "criteria": f.criteria, "channels": f.channels,
             "is_active": f.is_active, "matches_count": f.matches_count,
             "last_matched_at": f.last_matched_at, "created_at": f.created_at,
             "description": describe_criteria(normalize_criteria(f.criteria))} for f in rows]


# ── alertas (admin) ────────────────────────────────────────────────────

@alerts_router.get("")
async def list_alerts(
    status: Optional[str] = None,
    reason: Optional[str] = None,
    user_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    stmt = select(Alert)
    if status:
        stmt = stmt.where(Alert.status.in_(status.split(",")))
    if reason:
        stmt = stmt.where(Alert.reason.in_(reason.split(",")))
    if user_id:
        stmt = stmt.where(Alert.user_id == user_id)
    rows = (await db.execute(stmt.order_by(Alert.created_at.desc()).limit(limit))).scalars().all()
    users = {u.id: u for u in (await db.execute(
        select(User).where(User.id.in_([a.user_id for a in rows])))).scalars().all()} if rows else {}
    items = {i.id: i for i in (await db.execute(
        select(Item).where(Item.id.in_([a.item_id for a in rows])).options(selectinload(Item.auction)))).scalars().all()} if rows else {}
    ctx = await SerializerContext(db).load(list(items.values()))
    return [{
        "id": a.id, "reason": a.reason, "status": a.status, "channel": a.channel,
        "detail": a.detail, "error": a.error, "created_at": a.created_at, "sent_at": a.sent_at,
        "user": {"id": a.user_id, "email": users[a.user_id].email, "name": users[a.user_id].name} if a.user_id in users else None,
        "item": ctx.card(items[a.item_id]) if a.item_id in items else None,
    } for a in rows]


@alerts_router.post("/{alert_id}/retry")
async def retry_alert(alert_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_admin)):
    a = await db.get(Alert, alert_id)
    if not a:
        raise HTTPException(404, "Alerta não encontrado")
    if a.status == "sent":
        raise HTTPException(400, "Este alerta já foi enviado")
    a.status, a.error = "pending", None
    await db.commit()
    return {"status": "ok", "id": a.id}
