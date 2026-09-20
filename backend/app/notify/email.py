"""Envio de e-mail por SMTP. Configuracao na tabela `settings`.

Sem SMTP configurado o envio falha de forma explicita (`EmailUnavailable`), e o
dispatcher para o ciclo em vez de marcar dezenas de alertas como enviados.
"""
from __future__ import annotations

import logging
import re
from email.message import EmailMessage

import aiosmtplib
from sqlalchemy.ext.asyncio import AsyncSession

from app.settings_service import get_setting, get_setting_bool, get_setting_int

logger = logging.getLogger("zleilao.notify.email")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")


class EmailUnavailable(Exception):
    """SMTP nao configurado ou inacessivel: o ciclo deve parar."""


def is_valid_email(address: str | None) -> bool:
    return bool(address and EMAIL_RE.match(address.strip()))


async def smtp_config(db: AsyncSession) -> dict:
    return {
        "host": (await get_setting(db, "smtp_host", "")).strip(),
        "port": await get_setting_int(db, "smtp_port", 587),
        "user": (await get_setting(db, "smtp_user", "")).strip(),
        "password": await get_setting(db, "smtp_password", ""),
        "from_email": (await get_setting(db, "smtp_from_email", "")).strip(),
        "from_name": (await get_setting(db, "smtp_from_name", "ZConnect Leilão")).strip(),
        "starttls": await get_setting_bool(db, "smtp_starttls", True),
        "ssl": await get_setting_bool(db, "smtp_ssl", False),
    }


async def send_email(db: AsyncSession, to: str, subject: str, html: str, text: str | None = None) -> None:
    cfg = await smtp_config(db)
    if not cfg["host"] or not cfg["from_email"]:
        raise EmailUnavailable("SMTP nao configurado (host e remetente sao obrigatorios)")
    if not is_valid_email(to):
        raise ValueError(f"endereco invalido: {to!r}")

    msg = EmailMessage()
    msg["From"] = f'{cfg["from_name"]} <{cfg["from_email"]}>' if cfg["from_name"] else cfg["from_email"]
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text or re.sub(r"<[^>]+>", " ", html))
    msg.add_alternative(html, subtype="html")

    try:
        await aiosmtplib.send(
            msg,
            hostname=cfg["host"],
            port=cfg["port"],
            username=cfg["user"] or None,
            password=cfg["password"] or None,
            start_tls=cfg["starttls"] and not cfg["ssl"],
            use_tls=cfg["ssl"],
            timeout=30,
        )
    except (aiosmtplib.SMTPAuthenticationError, aiosmtplib.SMTPConnectError,
            aiosmtplib.SMTPServerDisconnected, OSError) as exc:
        # Problema de infraestrutura: parar o ciclo, nao queimar os alertas.
        raise EmailUnavailable(f"{exc.__class__.__name__}: {exc}") from exc
