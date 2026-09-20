"""Envio por WhatsApp via API do ZConnect RH (Baileys), mesmo caminho do Promo.

**Limite conhecido e deliberado.** O Promo usa essa API para postar em grupos
que o numero ja' administra. Aqui o envio seria 1:1 para assinantes, que e' um
uso diferente: disparo para nao-contatos por API nao oficial tem risco real de
banimento do numero. Por isso o canal nasce OPT-IN, desligado por padrao
(`whatsapp_enabled=false`), com teto proprio de envios por ciclo, e o e-mail e'
o canal principal. Para escala, o caminho e' a API oficial da Meta.

Toda chamada precisa de DOIS headers: Authorization e x-tenant. Sem o x-tenant
a API responde 404 "Tenant nao encontrado" e o envio falha em silencio dentro
do job — armadilha ja' documentada no SISTEMA.md do Promo.
"""
from __future__ import annotations

import logging
import re

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.settings_service import get_setting, get_setting_bool

logger = logging.getLogger("zleilao.notify.whatsapp")


class WhatsAppUnavailable(Exception):
    """Canal desligado ou mal configurado: o ciclo deve parar."""


def normalize_phone(raw: str | None) -> str | None:
    """'(11) 98765-4321' -> '5511987654321'. Devolve None se nao parecer valido."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("00"):
        digits = digits[2:]
    if not digits.startswith("55"):
        digits = "55" + digits
    # 55 + DDD(2) + numero(8 ou 9)
    if not (12 <= len(digits) <= 13):
        return None
    return digits


async def wa_config(db: AsyncSession) -> dict:
    return {
        "enabled": await get_setting_bool(db, "whatsapp_enabled", False),
        "api_url": (await get_setting(db, "whatsapp_api_url", "")).rstrip("/"),
        "token": await get_setting(db, "whatsapp_bearer_token", ""),
        "tenant": (await get_setting(db, "whatsapp_tenant", "")).strip(),
        "endpoint": (await get_setting(db, "whatsapp_send_endpoint", "/v1/send-text")).strip(),
    }


async def send_whatsapp(db: AsyncSession, phone: str, text: str) -> None:
    cfg = await wa_config(db)
    if not cfg["enabled"]:
        raise WhatsAppUnavailable("canal WhatsApp desligado em Configuracoes")
    missing = [k for k in ("api_url", "token", "tenant") if not cfg[k]]
    if missing:
        raise WhatsAppUnavailable(f"configuracao incompleta: {', '.join(missing)}")

    number = normalize_phone(phone)
    if not number:
        raise ValueError(f"telefone invalido: {phone!r}")

    url = f"{cfg['api_url']}{cfg['endpoint']}"
    headers = {"Authorization": f"Bearer {cfg['token']}", "x-tenant": cfg["tenant"]}
    payload = {"number": number, "text": text}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
    except httpx.RequestError as exc:
        raise WhatsAppUnavailable(f"nao foi possivel alcancar a API ({exc.__class__.__name__})") from exc

    if resp.status_code == 404:
        raise WhatsAppUnavailable("404 — confira o tenant (header x-tenant)")
    if resp.status_code in (401, 403):
        raise WhatsAppUnavailable(f"{resp.status_code} — token sem permissao para este tenant")
    if resp.status_code >= 500:
        raise WhatsAppUnavailable(f"API respondeu {resp.status_code}")
    if resp.status_code >= 400:
        raise ValueError(f"API respondeu {resp.status_code}: {resp.text[:200]}")
