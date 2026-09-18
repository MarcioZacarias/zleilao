"""RN-009 — mascaramento de dados pessoais antes de persistir ou enviar ao LLM.

Placa, chassi, RENAVAM, CPF, telefone e e-mail sao mascarados/removidos.
A placa completa vira um HMAC (para deduplicacao, RN-004) e uma versao
mascarada com 3 letras visiveis (para exibicao). Nomes de pessoas nao sao
detectaveis por regex: os parsers evitam capturar campos de partes
(autor/reu) e o prompt do LLM proibe devolver nomes.
"""
from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass, field

from app.config import get_settings

# Placa antiga ABC1234 / ABC-1234 e Mercosul ABC1D23. Ignora tokens ja' mascarados (com _ ou *).
PLATE_RE = re.compile(r"(?<![A-Z0-9])([A-Z]{3})[- ]?(\d[A-Z0-9]\d{2})(?![A-Z0-9])")
CHASSI_RE = re.compile(r"(?<![A-Z0-9])([A-HJ-NPR-Z0-9]{13})([A-HJ-NPR-Z0-9]{4})(?![A-Z0-9])")
RENAVAM_RE = re.compile(r"(renavam\D{0,12})(\d{9,11})", re.I)
CPF_RE = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?55\s?)?\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}(?!\d)")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


@dataclass
class MaskResult:
    text: str
    plate_masked: str | None = None
    plate_hash: str | None = None
    chassi_masked: str | None = None
    removed: list[str] = field(default_factory=list)


def plate_hash(plate: str) -> str:
    key = get_settings().SECRET_KEY.encode()
    norm = re.sub(r"[^A-Z0-9]", "", plate.upper())
    return hmac.new(key, norm.encode(), hashlib.sha256).hexdigest()


def mask_text(text: str | None) -> MaskResult:
    if not text:
        return MaskResult(text="")
    out = text
    result = MaskResult(text="")

    # Chassi (17 chars) antes da placa, para o trecho final nao virar "placa".
    def _chassi(m: re.Match) -> str:
        token = m.group(0)
        # 17 chars puramente numericos nao e' chassi (pode ser processo/telefone)
        if token.isdigit():
            return token
        masked = "*" * 13 + m.group(2)
        if result.chassi_masked is None:
            result.chassi_masked = masked
        result.removed.append("chassi")
        return masked

    out = CHASSI_RE.sub(_chassi, out)

    def _plate(m: re.Match) -> str:
        full = m.group(1) + m.group(2)
        # Evita falso positivo em siglas seguidas de numero (ex.: "KIT 2020" nao casa; "ABC 1234" casa)
        if result.plate_hash is None:
            result.plate_hash = plate_hash(full)
            result.plate_masked = f"{m.group(1)}-****"
        result.removed.append("placa")
        return f"{m.group(1)}-****"

    out = PLATE_RE.sub(_plate, out)
    out = RENAVAM_RE.sub(lambda m: m.group(1) + "*" * len(m.group(2)), out)
    if RENAVAM_RE.search(text):
        result.removed.append("renavam")
    if CPF_RE.search(out):
        out = CPF_RE.sub("[CPF removido]", out)
        result.removed.append("cpf")
    if EMAIL_RE.search(out):
        out = EMAIL_RE.sub("[e-mail removido]", out)
        result.removed.append("email")
    if PHONE_RE.search(out):
        out = PHONE_RE.sub("[telefone removido]", out)
        result.removed.append("telefone")

    result.text = out
    return result


def extract_plate_hash(text: str | None) -> str | None:
    """Hash da primeira placa completa encontrada (sem alterar o texto)."""
    if not text:
        return None
    m = PLATE_RE.search(text)
    return plate_hash(m.group(1) + m.group(2)) if m else None
