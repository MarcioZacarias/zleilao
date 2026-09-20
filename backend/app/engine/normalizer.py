"""Normalizacao (RN-002/RN-003/RN-009).

Ordem: classificar categoria -> mascarar PII -> extracao deterministica ->
LLM (opcional, saida JSON validada por schema) -> validacao por categoria ->
promocao de colunas. Falha 2x => fila de revisao (status `review`).

Cache por hash do conteudo evita pagar LLM duas vezes pelo mesmo texto.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.category_fields import effective_fields, json_schema_for, validate_attributes
from app.engine.classifier import classify
from app.engine.deterministic import DET_VERSION, extract_vehicle_fields
from app.engine.geo import coords_for
from app.engine.masking import mask_text
from app.models import Category, ExtractionCache, Item, Source
from app.settings_service import get_setting, get_setting_bool, get_setting_int

logger = logging.getLogger("zleilao.normalizer")

PROMPT_VERSION = "p1"

# Campos em que o julgamento do texto completo (LLM) vale mais que a regex do titulo.
LLM_PRIORITY_KEYS = {
    "condicao", "situacao_documento", "origem", "observacoes", "opcionais", "restricoes",
    "debitos", "laudo_cautelar", "cor", "combustivel", "cambio", "versao", "ipva_pago",
    "eixos", "carroceria", "tracao", "cilindradas",
}

SYSTEM_PROMPT = """Você extrai campos estruturados de anúncios de lotes de leilão no Brasil.
Regras:
- Responda SOMENTE com o JSON pedido. Campo não informado no texto = null. Nunca invente nem infira.
- Ignore texto jurídico padrão (condições gerais de venda, avisos genéricos sobre "sinistros já ocorridos", comissões) — ele não descreve ESTE veículo. Use apenas o que o anúncio afirma sobre o bem específico.
- "condicao": use sinistro/sucata apenas quando o anúncio afirmar isso sobre o bem. Use "normal" quando o texto indicar retomada de financeira, frota ou locadora sem menção a dano, ou laudo aprovado. Caso contrário, "nao_informado".
- Nunca devolva nomes de pessoas, CPF, telefone, e-mail, placa completa, chassi completo ou RENAVAM.
- Números: km sem pontos; anos com 4 dígitos; valores em reais como número.
- "observacoes": até 300 caracteres com avarias e pontos relevantes do bem, sem texto jurídico."""


class LLMUnavailable(Exception):
    """Sinaliza que o ciclo deve parar (sem chave, rate limit, rede)."""


def content_hash(*parts: str | None) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update((p or "").encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


async def _llm_extract(db: AsyncSession, schema: dict[str, Any], title: str, description: str,
                       raw: dict[str, Any], category: Category, hint: str | None) -> tuple[dict[str, Any], str]:
    """Chama o modelo com saida estruturada. Devolve (json, modelo)."""
    api_key = await get_setting(db, "llm_api_key", "")
    model = await get_setting(db, "llm_model", "claude-haiku-4-5")
    max_chars = await get_setting_int(db, "llm_max_input_chars", 6000)
    if not api_key:
        raise LLMUnavailable("llm_api_key nao configurada")

    import anthropic

    client = anthropic.AsyncAnthropic(api_key=api_key, max_retries=2, timeout=60.0)
    raw_txt = json.dumps({k: v for k, v in raw.items() if not str(k).startswith("_")}, ensure_ascii=False, default=str)
    user = (
        f"Categoria: {category.name}" + (f" — {hint}" if hint else "") + "\n"
        f"Título: {title}\n"
        f"Dados estruturados da fonte (confiáveis): {raw_txt}\n"
        f"Descrição:\n{description[:max_chars]}"
    )
    try:
        resp = await client.messages.create(
            model=model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
    except anthropic.AuthenticationError as exc:
        raise LLMUnavailable(f"chave invalida: {exc}") from exc
    except anthropic.RateLimitError as exc:
        raise LLMUnavailable(f"rate limit: {exc}") from exc
    except anthropic.APIConnectionError as exc:
        raise LLMUnavailable(f"sem conexao: {exc}") from exc
    # Outros APIStatusError (400 etc.) propagam e contam como tentativa falha.
    if resp.stop_reason == "refusal":
        raise ValueError("modelo recusou a extracao")
    txt = next((b.text for b in resp.content if b.type == "text"), None)
    if not txt:
        raise ValueError("resposta sem texto")
    return json.loads(txt), model


async def normalize_item(db: AsyncSession, item: Item, source: Source, categories: list[Category]) -> str:
    """Normaliza um item. Devolve o extraction_status final."""
    llm_enabled = await get_setting_bool(db, "llm_enabled", True)
    if llm_enabled and not await get_setting(db, "llm_api_key", ""):
        # Sem chave: segue so' com regras. Nao interrompe o ciclo — uma instalacao
        # nova precisa publicar mesmo antes de alguem configurar o LLM.
        llm_enabled = False
    max_attempts = await get_setting_int(db, "extraction_max_attempts", 2)
    attrs = dict(item.attributes or {})
    raw = dict(attrs.get("_raw") or {})

    # 1. Categoria
    if not item.category_id:
        cat = classify(item.title, attrs.get("_category_hint"), categories)
        if cat:
            item.category_id = cat.id
    category = next((c for c in categories if c.id == item.category_id), None)
    if category is None:
        item.extraction_status = "skipped"
        item.extraction_error = "sem categoria"
        return item.extraction_status

    # 1b. Geolocalizacao pelo municipio (busca por raio).
    # Roda ANTES de qualquer saida por erro: a cidade vem da COLETA, nao da
    # extracao. Um lote sem marca identificada continua tendo endereco, e
    # sumir da busca por raio por causa disso seria perder dado bom.
    if item.city and item.state and (item.lat is None or item.lng is None):
        coords = coords_for(item.city, item.state)
        if coords:
            item.lat, item.lng = coords

    # 2. Mascaramento (idempotente: texto ja' mascarado nao casa de novo)
    masked_desc = mask_text(item.description)
    masked_title = mask_text(item.title)
    item.description = masked_desc.text or None
    item.title = masked_title.text or item.title
    plate_h = masked_desc.plate_hash or masked_title.plate_hash
    if plate_h:
        item.plate_hash = plate_h
    if masked_desc.plate_masked or masked_title.plate_masked:
        raw.setdefault("placa_mascarada", masked_desc.plate_masked or masked_title.plate_masked)
    if masked_desc.chassi_masked:
        raw.setdefault("chassi_mascarado", masked_desc.chassi_masked)

    # 3. Campos da categoria + deterministico
    fields = [f for f, _ in await effective_fields(db, category)]
    is_vehicle = category.path.split("/")[0] == "veiculos"
    short = (item.description or "")[:400]
    det = extract_vehicle_fields(item.title, short, raw) if is_vehicle else dict(raw)

    # 4. LLM (com cache)
    version = f"{PROMPT_VERSION}+{DET_VERSION}"
    merged = dict(det)
    used_model = None
    if llm_enabled and fields:
        schema = json_schema_for(fields)
        chash = content_hash(item.title, item.description, json.dumps(raw, sort_keys=True, default=str), str(category.id))
        cached = await db.scalar(select(ExtractionCache).where(
            ExtractionCache.content_hash == chash, ExtractionCache.category_id == category.id,
            ExtractionCache.extraction_version == version,
        ))
        try:
            if cached:
                llm_out = dict(cached.result)
                used_model = "cache"
            else:
                llm_out, used_model = await _llm_extract(db, schema, item.title, item.description or "", raw, category, category.llm_hint)
                db.add(ExtractionCache(content_hash=chash, category_id=category.id, extraction_version=version, result=llm_out))
            for k, v in llm_out.items():
                if v is None:
                    continue
                if k in LLM_PRIORITY_KEYS or merged.get(k) in (None, ""):
                    merged[k] = v
        except LLMUnavailable:
            raise
        except Exception as exc:  # 400, JSON invalido, recusa...
            item.extraction_attempts += 1
            item.extraction_error = f"llm: {str(exc)[:300]}"
            if item.extraction_attempts >= max_attempts:
                item.extraction_status = "review"
                item.status = "review"
            else:
                item.extraction_status = "failed"
            logger.warning("LLM falhou no item %s (%d/%d): %s", item.id, item.extraction_attempts, max_attempts, exc)
            return item.extraction_status

    # 5. Validacao por categoria (RN-002/RN-003)
    clean, errors = validate_attributes(fields, merged)
    if errors and any(e.startswith("campo obrigatorio") for e in errors):
        item.extraction_attempts += 1
        item.extraction_error = "; ".join(errors)[:500]
        if item.extraction_attempts >= max_attempts:
            item.extraction_status = "review"
            item.status = "review"
        else:
            item.extraction_status = "failed"
        return item.extraction_status

    # 6. Persistencia + promocao de colunas
    clean["_raw"] = raw
    if attrs.get("_category_hint"):
        clean["_category_hint"] = attrs["_category_hint"]
    item.attributes = clean
    # A extracao concluida SUBSTITUI as colunas promovidas, inclusive com None.
    # Preservar o valor anterior faria uma correcao de regra nunca limpar um
    # dado errado ja gravado (ex.: modelo "(Lote 21)" sobreviveria a reextracao).
    def _cut(key: str, n: int) -> str | None:
        val = clean.get(key)
        return str(val)[:n] if val not in (None, "") else None

    item.brand = _cut("marca", 60)
    item.model = _cut("modelo", 120)
    item.year_model = clean.get("ano_modelo")
    item.year_fab = clean.get("ano_fabricacao")
    item.km = clean.get("km")
    item.condition = _cut("condicao", 30) or "nao_informado"
    item.extraction_status = "done"
    item.extraction_error = None
    item.extraction_version = version + (f"+{used_model}" if used_model else "")
    item.extraction_model = used_model
    if item.status == "review":
        item.status = "collected"
    await refresh_search_vector(db, item)
    return item.extraction_status


async def refresh_search_vector(db: AsyncSession, item: Item) -> None:
    parts = " ".join(filter(None, [
        item.title, item.brand, item.model, str(item.year_model or ""), item.city, item.state,
        (item.description or "")[:2000],
    ]))
    item.search_tsv = func.to_tsvector("portuguese", parts)
