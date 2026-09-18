"""Configuracao operacional na tabela `system_settings` (padrao Promo).

Adicionar uma chave nova = uma linha em DEFAULTS + restart. O seed insere as
chaves que faltam a cada boot e sincroniza os labels. A tela de Configuracoes
do admin renderiza os grupos automaticamente.
"""
import logging
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SystemSetting

logger = logging.getLogger("zleilao.settings")

_cache: dict[str, tuple[str, float]] = {}
CACHE_TTL = 60  # segundos

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

DEFAULT_DISCLAIMER = (
    "O ZConnect Leilão é um agregador: não realiza leilões, não recebe lances nem "
    "intermedeia transações. As informações são coletadas dos sites dos leiloeiros "
    "oficiais e podem estar desatualizadas — confira sempre a data da última coleta e "
    "as condições de venda na fonte oficial antes de participar."
)

DEFAULTS = [
    # ── LLM (normalizacao) ─────────────────────────────────────────────
    {"key": "llm_enabled", "value": "true", "label": "Usar LLM na normalizacao (false = so' regras deterministicas)", "group": "llm", "is_secret": False},
    {"key": "llm_provider", "value": "anthropic", "label": "Provedor (anthropic)", "group": "llm", "is_secret": False},
    {"key": "llm_api_key", "value": "", "label": "API Key", "group": "llm", "is_secret": True},
    {"key": "llm_model", "value": "claude-haiku-4-5", "label": "Modelo (ex.: claude-haiku-4-5 para baixo custo, claude-sonnet-5 para mais precisao)", "group": "llm", "is_secret": False},
    {"key": "llm_max_items_per_cycle", "value": "40", "label": "Max itens extraidos por ciclo", "group": "llm", "is_secret": False},
    {"key": "llm_max_input_chars", "value": "6000", "label": "Max caracteres de descricao enviados", "group": "llm", "is_secret": False},
    # ── Pipeline ───────────────────────────────────────────────────────
    {"key": "scrape_tick_minutes", "value": "10", "label": "Intervalo de verificacao de fontes (min)", "group": "pipeline", "is_secret": False},
    {"key": "normalize_interval_minutes", "value": "5", "label": "Intervalo do job de normalizacao (min)", "group": "pipeline", "is_secret": False},
    {"key": "lifecycle_interval_minutes", "value": "30", "label": "Intervalo do job de ciclo de vida (min)", "group": "pipeline", "is_secret": False},
    {"key": "dedup_interval_minutes", "value": "60", "label": "Intervalo do job de deduplicacao (min)", "group": "pipeline", "is_secret": False},
    {"key": "extraction_max_attempts", "value": "2", "label": "RN-003: tentativas antes da fila de revisao", "group": "pipeline", "is_secret": False},
    {"key": "lifecycle_misses_threshold", "value": "3", "label": "RN-005: coletas sem reencontrar -> possivelmente retirado", "group": "pipeline", "is_secret": False},
    {"key": "auction_soon_days", "value": "2", "label": "RN-005: dias para marcar 'pregao proximo'", "group": "pipeline", "is_secret": False},
    {"key": "closed_grace_hours", "value": "6", "label": "Horas apos a ultima sessao para marcar encerrado", "group": "pipeline", "is_secret": False},
    {"key": "raw_retention_days", "value": "30", "label": "Retencao de payload bruto (dias)", "group": "pipeline", "is_secret": False},
    {"key": "closed_retention_days", "value": "90", "label": "Retencao de itens encerrados (dias, 0 = nunca apagar)", "group": "pipeline", "is_secret": False},
    {"key": "dedup_enabled", "value": "true", "label": "RN-004: deduplicacao ligada", "group": "pipeline", "is_secret": False},
    {"key": "dedup_threshold", "value": "0.85", "label": "RN-004: similaridade minima (0-1)", "group": "pipeline", "is_secret": False},
    # ── Saude da coleta (RN-008) ───────────────────────────────────────
    {"key": "incident_variation_pct", "value": "60", "label": "RN-008: variacao % vs media que gera incidente", "group": "health", "is_secret": False},
    {"key": "incident_min_history", "value": "3", "label": "RN-008: coletas boas antes de avaliar variacao", "group": "health", "is_secret": False},
    {"key": "suspend_on_incident", "value": "true", "label": "RN-008: suspender publicacao da fonte no incidente", "group": "health", "is_secret": False},
    # ── Scraping ───────────────────────────────────────────────────────
    {"key": "scraper_user_agent", "value": DEFAULT_UA, "label": "User-Agent", "group": "scraping", "is_secret": False},
    {"key": "request_delay_min", "value": "1.0", "label": "Atraso minimo entre requisicoes (s)", "group": "scraping", "is_secret": False},
    {"key": "request_delay_max", "value": "3.0", "label": "Atraso maximo entre requisicoes (s)", "group": "scraping", "is_secret": False},
    {"key": "respect_robots", "value": "true", "label": "RN-009: respeitar robots.txt", "group": "scraping", "is_secret": False},
    {"key": "fetch_details_default", "value": "true", "label": "Buscar pagina de detalhe do lote (descricao completa)", "group": "scraping", "is_secret": False},
    {"key": "max_details_per_run", "value": "60", "label": "Max paginas de detalhe por coleta por fonte", "group": "scraping", "is_secret": False},
    # ── Portal ─────────────────────────────────────────────────────────
    {"key": "portal_items_per_page", "value": "24", "label": "Itens por pagina na vitrine", "group": "portal", "is_secret": False},
    {"key": "portal_disclaimer", "value": DEFAULT_DISCLAIMER, "label": "Disclaimer exibido nas fichas", "group": "portal", "is_secret": False},
    # ── Branding ───────────────────────────────────────────────────────
    {"key": "brand_site_title", "value": "ZConnect Leilão", "label": "Titulo do site", "group": "branding", "is_secret": False},
    {"key": "brand_tagline", "value": "Todos os leilões de veículos do Brasil em um só radar", "label": "Slogan", "group": "branding", "is_secret": False},
]


async def seed_defaults(db: AsyncSession):
    for d in DEFAULTS:
        existing = await db.scalar(select(SystemSetting).where(SystemSetting.key == d["key"]))
        if not existing:
            db.add(SystemSetting(**d))
        elif existing.label != d["label"]:
            existing.label = d["label"]
    await db.commit()
    logger.info("System settings seeded")


async def get_setting(db: AsyncSession, key: str, default: str = "") -> str:
    now = time.time()
    if key in _cache:
        val, ts = _cache[key]
        if now - ts < CACHE_TTL:
            return val
    row = await db.scalar(select(SystemSetting.value).where(SystemSetting.key == key))
    value = row if row is not None else default
    _cache[key] = (value, now)
    return value


async def get_setting_int(db: AsyncSession, key: str, default: int = 0) -> int:
    val = await get_setting(db, key, str(default))
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


async def get_setting_float(db: AsyncSession, key: str, default: float = 0.0) -> float:
    val = await get_setting(db, key, str(default))
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


async def get_setting_bool(db: AsyncSession, key: str, default: bool = False) -> bool:
    val = (await get_setting(db, key, "true" if default else "false")).strip().lower()
    return val in ("1", "true", "yes", "sim", "on")


async def get_all_settings(db: AsyncSession) -> list[dict]:
    result = await db.execute(select(SystemSetting).order_by(SystemSetting.group, SystemSetting.key))
    return [
        {
            "key": s.key,
            "value": s.value if not s.is_secret else ("*" * 8 if s.value else ""),
            "raw_value": s.value,
            "label": s.label,
            "group": s.group,
            "is_secret": s.is_secret,
        }
        for s in result.scalars().all()
    ]


async def update_settings(db: AsyncSession, updates: dict[str, str]):
    for key, value in updates.items():
        row = await db.scalar(select(SystemSetting).where(SystemSetting.key == key))
        if row:
            row.value = value
            _cache.pop(key, None)
        else:
            logger.warning("Setting '%s' nao existe, ignorando", key)
    await db.commit()
    logger.info("Updated %d settings", len(updates))


def invalidate_cache():
    _cache.clear()
