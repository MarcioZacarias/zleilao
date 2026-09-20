"""RN-006/RN-007 — envio dos alertas pendentes.

Regras aplicadas, nesta ordem:
  1. Janela de silêncio (pessoal do usuário, ou a global) — pula o ciclo.
  2. Plano: `free` recebe um digest diário no horário configurado; `pro` recebe
     assim que o alerta nasce (near-real-time).
  3. Teto diário de alertas por usuário.
  4. Não-repetição: garantida no banco por `(user_id, item_id, reason)`.

Falha de infraestrutura (SMTP fora, WhatsApp mal configurado) **interrompe o
ciclo** em vez de marcar os alertas como enviados. Um alerta perdido é pior que
um alerta atrasado: o pregão acontece uma vez só.
"""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Alert, Item, PLAN_FREE, SavedFilter, Source, Subscription, User
from app.notify.email import EmailUnavailable, send_email
from app.notify.templates import alert_email, whatsapp_message
from app.notify.whatsapp import WhatsAppUnavailable, send_whatsapp
from app.settings_service import get_setting, get_setting_bool, get_setting_int
from app.timeutil import now_brt

logger = logging.getLogger("zleilao.dispatcher")


def parse_hhmm(value: str | None) -> time | None:
    if not value or ":" not in value:
        return None
    try:
        h, m = value.split(":", 1)
        return time(int(h), int(m))
    except (TypeError, ValueError):
        return None


def in_quiet_window(now: datetime, start: time | None, end: time | None) -> bool:
    """Janela que cruza a meia-noite é o caso normal (22:00–08:00)."""
    if not start or not end or start == end:
        return False
    current = now.time()
    if start < end:
        return start <= current < end
    return current >= start or current < end


async def _sent_today(db: AsyncSession, user_id: int, day_start: datetime) -> int:
    return await db.scalar(
        select(func.count(Alert.id)).where(
            Alert.user_id == user_id, Alert.status == "sent", Alert.sent_at >= day_start)
    ) or 0


async def run_dispatcher(db: AsyncSession) -> dict:
    now = now_brt()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    base_url = (await get_setting(db, "public_base_url", "")).rstrip("/") or "https://leilao.zconnect.ia.br"
    max_per_day = await get_setting_int(db, "max_alerts_per_user_day", 20)
    digest_hour = await get_setting_int(db, "free_digest_hour", 9)
    batch_limit = await get_setting_int(db, "dispatch_batch_size", 50)
    global_quiet = (parse_hhmm(await get_setting(db, "quiet_start", "")),
                    parse_hhmm(await get_setting(db, "quiet_end", "")))
    email_on = await get_setting_bool(db, "email_enabled", True)
    wa_on = await get_setting_bool(db, "whatsapp_enabled", False)

    stats = {"users": 0, "sent": 0, "skipped_quiet": 0, "skipped_limit": 0, "failed": 0, "stopped": None}
    if not email_on and not wa_on:
        stats["stopped"] = "nenhum canal habilitado"
        return stats

    pending = (await db.execute(
        select(Alert).where(Alert.status == "pending")
        .order_by(Alert.created_at).limit(batch_limit * 4)
    )).scalars().all()
    if not pending:
        return stats

    by_user: dict[int, list[Alert]] = {}
    for a in pending:
        by_user.setdefault(a.user_id, []).append(a)

    for user_id, alerts in by_user.items():
        user = await db.get(User, user_id)
        if not user or not user.is_active:
            for a in alerts:
                a.status, a.error = "skipped", "usuario inativo"
            continue

        quiet = (parse_hhmm(user.quiet_start) or global_quiet[0],
                 parse_hhmm(user.quiet_end) or global_quiet[1])
        if in_quiet_window(now, *quiet):
            stats["skipped_quiet"] += len(alerts)
            continue

        sub = await db.scalar(select(Subscription).where(Subscription.user_id == user_id))
        plan = sub.plan if sub and sub.status == "active" else PLAN_FREE
        if plan == PLAN_FREE:
            # Digest diário: só envia na hora marcada, e junta tudo que se acumulou.
            if now.hour != digest_hour:
                continue

        already = await _sent_today(db, user_id, day_start)
        room = max_per_day - already
        if room <= 0:
            stats["skipped_limit"] += len(alerts)
            continue
        alerts = alerts[:room]

        # Carrega itens e fontes de uma vez
        item_ids = [a.item_id for a in alerts]
        items = {i.id: i for i in (await db.execute(
            select(Item).where(Item.id.in_(item_ids)))).scalars().all()}
        sources = {s.id: s for s in (await db.execute(select(Source))).scalars().all()}
        entries, usable = [], []
        for a in alerts:
            item = items.get(a.item_id)
            if not item:
                a.status, a.error = "skipped", "item removido"
                continue
            entries.append({
                "item": item,
                "source_name": (sources.get(item.source_id).name if sources.get(item.source_id) else "fonte"),
                "reason": a.reason,
                "detail": a.detail,
            })
            usable.append(a)
        if not entries:
            continue

        stats["users"] += 1
        channels: list[str] = []
        if email_on and user.email_opt_in and user.email_verified_at:
            channels.append("email")
        if wa_on and user.whatsapp_opt_in and user.phone:
            channels.append("whatsapp")
        if not channels:
            for a in usable:
                a.status, a.error = "skipped", "usuario sem canal disponivel (e-mail nao verificado?)"
            continue

        delivered = False
        last_error = None
        for channel in channels:
            try:
                if channel == "email":
                    subject, html = alert_email(entries, base_url)
                    await send_email(db, user.email, subject, html)
                else:
                    tagline = await get_setting(db, "brand_tagline", "")
                    await send_whatsapp(db, user.phone, whatsapp_message(entries, base_url, tagline))
                for a in usable:
                    a.status, a.channel, a.sent_at, a.error = "sent", channel, now, None
                delivered = True
                stats["sent"] += len(usable)
                break
            except (EmailUnavailable, WhatsAppUnavailable) as exc:
                # Infraestrutura fora: não queima os alertas, tenta o próximo canal.
                last_error = f"{channel}: {exc}"
                logger.warning("canal %s indisponivel: %s", channel, exc)
                continue
            except Exception as exc:
                last_error = f"{channel}: {exc}"
                logger.exception("falha ao enviar por %s para %s", channel, user.email)
                continue

        if not delivered:
            for a in usable:
                a.error = (last_error or "falha desconhecida")[:1000]
            stats["failed"] += len(usable)
            stats["stopped"] = last_error
            await db.commit()
            # Se nenhum canal funcionou para um usuário, não adianta tentar os outros.
            logger.error("dispatcher interrompido: %s", last_error)
            return stats

    await db.commit()
    logger.info("dispatcher: %s", stats)
    return stats
