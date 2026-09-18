"""Campos dinamicos por categoria (RN-002), com heranca pela arvore.

Carros herda os campos de Veiculos. `effective_fields` devolve a lista
consolidada (pai primeiro); `validate_attributes` coage tipos e aplica a
regra "ausente = nao informado, nunca inferido".
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category, CategoryField
from unidecode import unidecode

NOT_INFORMED = "nao_informado"


async def category_chain(db: AsyncSession, category: Category) -> list[Category]:
    """[raiz, ..., categoria] seguindo o `path` materializado."""
    slugs = category.path.split("/")
    rows = (await db.execute(select(Category).where(Category.slug.in_(slugs)))).scalars().all()
    by_slug = {c.slug: c for c in rows}
    return [by_slug[s] for s in slugs if s in by_slug]


async def effective_fields(db: AsyncSession, category: Category) -> list[tuple[CategoryField, Category]]:
    chain = await category_chain(db, category)
    ids = [c.id for c in chain]
    rows = (await db.execute(
        select(CategoryField).where(CategoryField.category_id.in_(ids)).order_by(CategoryField.sort_order, CategoryField.id)
    )).scalars().all()
    by_cat = {c.id: c for c in chain}
    seen: set[str] = set()
    out: list[tuple[CategoryField, Category]] = []
    # pai primeiro; filho pode sobrescrever chave do pai
    for cat in chain:
        for f in rows:
            if f.category_id == cat.id and f.key not in seen:
                seen.add(f.key)
                out.append((f, by_cat[f.category_id]))
    return out


def _norm(v: Any) -> str:
    return unidecode(str(v)).strip().lower().replace("-", "_").replace(" ", "_")


def coerce_value(f: CategoryField, value: Any) -> tuple[Any, str | None]:
    """Devolve (valor_coagido, erro). Valor None/vazio -> (None, None)."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, None
    t = f.field_type
    try:
        if t == "int":
            if isinstance(value, bool):
                raise ValueError
            s = str(value).replace(".", "").replace(",", ".")
            n = int(float(s))
            return n, None
        if t == "decimal":
            if isinstance(value, (int, float, Decimal)):
                return float(Decimal(str(value))), None
            s = str(value).replace("R$", "").strip().replace(".", "").replace(",", ".")
            return float(Decimal(s)), None
        if t == "bool":
            if isinstance(value, bool):
                return value, None
            s = _norm(value)
            if s in ("true", "sim", "yes", "1", "pago"):
                return True, None
            if s in ("false", "nao", "no", "0"):
                return False, None
            raise ValueError
        if t == "enum":
            options = f.options or []
            s = _norm(value)
            for opt in options:
                if _norm(opt) == s:
                    return opt, None
            # tolerancia: valor contem a opcao ou vice-versa
            for opt in options:
                o = _norm(opt)
                if o != NOT_INFORMED and (o in s or s in o) and len(o) > 3:
                    return opt, None
            return None, f"valor '{value}' fora das opcoes de {f.key}"
        if t == "date":
            if isinstance(value, date):
                return value.isoformat(), None
            return str(value)[:10], None
        # string
        s = str(value).strip()
        return s[:500], None
    except (ValueError, InvalidOperation, TypeError):
        return None, f"valor '{value}' invalido para {f.key} ({t})"


def validate_attributes(fields: list[CategoryField], data: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Coage cada campo; campos desconhecidos sao descartados; obrigatorios
    ausentes viram erro (RN-003)."""
    clean: dict[str, Any] = {}
    errors: list[str] = []
    known = {f.key: f for f in fields}
    for key, f in known.items():
        raw = data.get(key)
        if isinstance(raw, str) and _norm(raw) in (NOT_INFORMED, "nao informado", "n/a", "null", "none", "-"):
            raw = None
        val, err = coerce_value(f, raw)
        if err:
            errors.append(err)
            val = None
        if val is None and f.field_type == "enum" and NOT_INFORMED in (f.options or []):
            val = NOT_INFORMED
        if val is None and f.required and f.field_type != "enum":
            errors.append(f"campo obrigatorio ausente: {key}")
        clean[key] = val
    return clean, errors


def json_schema_for(fields: list[CategoryField]) -> dict[str, Any]:
    """JSON Schema para a saida estruturada do LLM."""
    props: dict[str, Any] = {}
    for f in fields:
        if f.field_type == "int":
            typ: dict[str, Any] = {"type": ["integer", "null"]}
        elif f.field_type == "decimal":
            typ = {"type": ["number", "null"]}
        elif f.field_type == "bool":
            typ = {"type": ["boolean", "null"]}
        elif f.field_type == "enum":
            typ = {"type": ["string", "null"], "enum": list(f.options or []) + [None]}
        else:
            typ = {"type": ["string", "null"]}
        desc = f.label + (f" ({f.unit})" if f.unit else "")
        if f.description:
            desc += ". " + f.description
        typ["description"] = desc
        props[f.key] = typ
    return {
        "type": "object",
        "properties": props,
        "required": list(props.keys()),
        "additionalProperties": False,
    }
