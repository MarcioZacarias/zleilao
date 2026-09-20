"""Medicao de audiencia por fonte (F5): aberturas de ficha e cliques de saida.

Por que agregado e nao evento: o relatorio de parceria responde "quantas
pessoas abriram os seus lotes e quantas foram ao seu site", e isso e uma taxa.
Uma linha por fonte por dia responde a pergunta e cabe no servidor; um evento
por visita cresceria sem limite para produzir o mesmo numero.

`views` conta **abertura de ficha**, nao visitante unico — nao ha identificacao
do visitante e nao vamos criar uma so para inflar um relatorio. O rotulo na
tela diz "aberturas", nao "visitantes".
"""
from __future__ import annotations

import logging
import re

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SourceDailyStat
from app.timeutil import now_brt

logger = logging.getLogger("zleilao.metrics")

#: User-agents que nao sao gente. Sem esse filtro o relatorio de parceria
#: contaria o proprio robot de busca como interesse no lote do parceiro.
BOT_RE = re.compile(
    r"bot|crawler|spider|crawl|slurp|bingpreview|facebookexternalhit|whatsapp|"
    r"telegram|headless|python-requests|httpx|curl|wget|axios|scrapy|monitor|"
    r"uptime|pingdom|lighthouse|gtmetrix",
    re.IGNORECASE,
)


def is_bot(user_agent: str | None) -> bool:
    """True quando o acesso nao deve contar como audiencia."""
    if not user_agent or len(user_agent) < 10:
        return True  # cliente sem UA e robo mal-educado, nao visitante
    return bool(BOT_RE.search(user_agent))


async def bump(db: AsyncSession, source_id: int | None, field: str, user_agent: str | None = None) -> None:
    """Soma 1 no contador do dia. Nunca derruba a requisicao do visitante.

    A metrica e subordinada a navegacao: se o UPSERT falhar, o usuario ainda
    precisa ver a ficha e ser redirecionado para o leiloeiro.
    """
    if not source_id or field not in ("views", "clicks"):
        return
    if is_bot(user_agent):
        return
    try:
        stmt = pg_insert(SourceDailyStat).values(
            source_id=source_id, day=now_brt().date(), views=int(field == "views"), clicks=int(field == "clicks")
        )
        col = getattr(SourceDailyStat, field)
        await db.execute(stmt.on_conflict_do_update(
            constraint="uq_source_daily_stats",
            set_={field: col + 1},
        ))
    except Exception as exc:  # pragma: no cover - metrica nunca quebra a tela
        logger.warning("falha ao contabilizar %s da fonte %s: %s", field, source_id, exc)
