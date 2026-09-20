"""Leilo (leilo.com.br) — SPA que embute o estado inicial em
`window.__INITIAL_STATE__`, com `elastic.lotes` (36 lotes por consulta) e
`leiloesSite.leiloes` (agenda). Dados ja' estruturados: marca, modelo, ano,
km, laudo cautelar, comitente, retomada, valor de mercado.

A paginacao e' feita por API client-side sem endpoint publico documentado,
entao a cobertura vem de consultar a pagina geral + uma pagina filtrada por
leilao ativo (`/leilao?leilao.nome=...`), 36 lotes por consulta.

URL oficial do lote: `/leilao?lote=<uuid>`. robots.txt permite tudo.
Verificado em 18/09/2026.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import quote_plus

from app.engine.deterministic import clean_model
from app.scrapers.base import BaseScraper, ScrapedAuction, ScrapedItem, ScrapedSession
from app.timeutil import BRT

logger = logging.getLogger("zleilao.scraper.leilo")

RETOMADA_MAP = {
    "frota": "frota", "financeira": "financeira", "banco": "financeira", "seguradora": "seguradora",
    "locadora": "locadora", "judicial": "judicial", "particular": "particular",
}
# Situacoes vistas no campo `situacao` do Leilo (18/09/2026)
SITUACAO_MAP = {
    "repasse": "open", "aberto": "open", "emandamento": "open", "em andamento": "open",
    "condicional": "open",        # lance condicional aguardando o comitente: lote ainda em disputa
    "condicionalnegada": "open",  # comitente recusou o lance: o lote volta a ser ofertado
    "agpagamento": "sold", "pago": "sold", "vendido": "sold", "arrematado": "sold",
    "naoarrematado": "closed",    # nao vendido nesta sessao; volta como "Repasse" se for reofertado
    "cancelado": "withdrawn", "retirado": "withdrawn", "suspenso": "withdrawn",
    "encerrado": "closed", "finalizado": "closed", "executado": "closed",
}

TIPO_MAP = {
    "leves": "carros", "carros": "carros", "pesados": "caminhoes", "motos": "motos",
    "utilitarios": "utilitarios", "utilitários": "utilitarios", "agro": "maquinas-equipamentos",
    "maquinas": "maquinas-equipamentos", "máquinas": "maquinas-equipamentos", "sucata": "outros-veiculos",
}


def parse_initial_state(html: str) -> dict[str, Any]:
    m = re.search(r"__INITIAL_STATE__\s*=\s*", html)
    if not m:
        raise ValueError("__INITIAL_STATE__ nao encontrado")
    start = m.end()
    depth = 0
    i = start
    in_str = False
    esc = False
    while i < len(html):
        c = html[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    break
        i += 1
    return json.loads(html[start:i + 1])


def iso_to_brt_naive(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(BRT).replace(tzinfo=None)


class LeiloScraper(BaseScraper):
    display_name = "Leilo"
    default_config = {
        "path": "/leilao",
        "per_auction": True,
        "max_auctions": 60,
        "include_executed": False,
        "fetch_details": False,
    }

    @property
    def default_base_url(self) -> str:
        return "https://www.leilo.com.br"

    async def scrape(self) -> list[ScrapedItem]:
        html = await self.fetch(self.abs_url(self.cfg("path", "/leilao")))
        self.stats.pages += 1
        state = parse_initial_state(html)
        items = self.items_from_state(state)
        total = (state.get("elastic") or {}).get("totalRegistros")
        logger.info("[Leilo] pagina geral: %d lotes (total informado: %s)", len(items), total)

        if str(self.cfg("per_auction", True)).lower() in ("1", "true", "yes"):
            auctions = (state.get("leiloesSite") or {}).get("leiloes") or []
            include_exec = str(self.cfg("include_executed", False)).lower() in ("1", "true", "yes")
            count = 0
            for a in auctions:
                if count >= int(self.cfg("max_auctions", 60)):
                    break
                situacao = (a.get("situacao") or "").lower()
                if not include_exec and situacao in ("executado", "encerrado", "finalizado"):
                    continue
                nome = a.get("nome")
                if not nome:
                    continue
                url = f"{self.base_url}/leilao?leilao.nome={quote_plus(nome)}"
                try:
                    await self.delay()
                    sub = parse_initial_state(await self.fetch(url))
                    self.stats.pages += 1
                    got = self.items_from_state(sub)
                    items.extend(got)
                    count += 1
                    logger.debug("[Leilo] %s: %d lotes", nome, len(got))
                except Exception as exc:
                    self.stats.errors += 1
                    logger.warning("[Leilo] falha em %s: %s", nome, exc)
            if count >= int(self.cfg("max_auctions", 60)):
                self.stats.mark_partial("limite de leiloes por ciclo atingido")

        # A paginacao do Leilo e' client-side: cada consulta devolve 36 lotes.
        # So' e' completa se o total informado couber no que foi visto.
        if isinstance(total, int) and len(items) < total:
            self.stats.mark_partial(f"{len(items)} de {total} lotes (paginacao client-side)")
        return items

    @staticmethod
    def _clean_model(raw: str | None) -> Optional[str]:
        """O modelo vem da base Infocar com o sufixo de portas — "Gol (2P/4P)".
        Isso atrapalha busca e deduplicacao, e nao descreve o bem."""
        if not raw:
            return None
        cleaned = clean_model(raw)
        return cleaned.title() if cleaned else None

    # ── mapeamento ───────────────────────────────────────────────────

    def items_from_state(self, state: dict[str, Any]) -> list[ScrapedItem]:
        out: list[ScrapedItem] = []
        for lot in (state.get("elastic") or {}).get("lotes") or []:
            try:
                item = self._map_lot(lot)
                if item:
                    out.append(item)
            except Exception as exc:
                self.stats.errors += 1
                logger.debug("[Leilo] lote ignorado: %s", exc)
        return out

    def _map_lot(self, lot: dict[str, Any]) -> Optional[ScrapedItem]:
        lot_id = lot.get("id")
        title = self.clean_text(lot.get("nome"))
        if not lot_id or not title:
            return None
        veic = lot.get("veiculo") or {}
        valor = lot.get("valor") or {}
        leilao = lot.get("leilao") or {}
        loc = lot.get("localizacao") or {}
        comitente = lot.get("comitente") or {}

        retomada = (veic.get("retomada") or "").lower()
        origem = next((v for k, v in RETOMADA_MAP.items() if k in retomada), None)
        laudo_raw = (lot.get("laudoCautelarResultado") or "").lower()
        laudo = "reprovado" if "reprov" in laudo_raw else ("aprovado" if "aprov" in laudo_raw else None)
        tipo = (lot.get("tipo") or "").lower()
        category_hint = TIPO_MAP.get(tipo) or (tipo or None)

        photos = [u for u in (lot.get("fotosUrls") or []) if isinstance(u, str)]
        situacao = lot.get("situacao") or ""
        status_hint = SITUACAO_MAP.get(situacao.lower().replace(" ", "")) or self.status_from_text(situacao) or "open"

        raw: dict[str, Any] = {
            "lel_id": lot.get("lelId"),
            "marca": (veic.get("infocarMarca") or "").title() or None,
            "modelo": self._clean_model(veic.get("infocarModelo")),
            "ano_modelo": veic.get("anoModelo"),
            "ano_fabricacao": veic.get("anoFabricacao"),
            "km": veic.get("km"),
            "origem": origem,
            "laudo_cautelar": laudo,
            "observacoes": self.clean_text(lot.get("laudoCautelarObservacao"))[:300] or None,
            "valor_mercado": veic.get("valorMercado"),
            "comissao_pct": valor.get("comissaoPorcentagem"),
            "total_despesas": valor.get("totalDespesas"),
            "lance_atual": ((valor.get("lance") or {}).get("valor")),
            "comitente": comitente.get("nome"),
            "tipo": lot.get("tipo"),
            "situacao": situacao,
            "permite_financiamento": lot.get("permiteFinanciamento"),
        }
        raw = {k: v for k, v in raw.items() if v not in (None, "", [])}

        desc_parts = [title]
        if laudo:
            desc_parts.append(f"Laudo cautelar: {laudo}.")
        if raw.get("observacoes"):
            desc_parts.append(f"Avarias apontadas: {raw['observacoes']}.")
        if veic.get("retomada"):
            desc_parts.append(f"Retomada: {veic['retomada']}.")
        if comitente.get("nome"):
            desc_parts.append(f"Comitente: {comitente['nome']}.")
        if valor.get("comissaoPorcentagem"):
            desc_parts.append(f"Comissão do leiloeiro: {valor['comissaoPorcentagem']}%.")
        if situacao:
            desc_parts.append(f"Situação: {situacao}.")

        sessions: list[ScrapedSession] = []
        p1 = iso_to_brt_naive(leilao.get("dataPrimeiraPraca"))
        p2 = iso_to_brt_naive(leilao.get("dataSegundaPraca"))
        if p1 or p2:
            if p1:
                sessions.append(ScrapedSession(kind="1a_praca", starts_at=p1))
            if p2:
                sessions.append(ScrapedSession(kind="2a_praca", starts_at=p2))
        else:
            kind = "repasse" if "repasse" in situacao.lower() else ("condicional" if "condicional" in situacao.lower() else "unica")
            sessions.append(ScrapedSession(
                kind=kind, starts_at=iso_to_brt_naive(leilao.get("data")),
                ends_at=iso_to_brt_naive(lot.get("dataFim")),
                min_bid=self.parse_brl(valor.get("minimo")),
            ))

        auction = ScrapedAuction(
            external_id=str(leilao.get("id") or f"lot-{lot_id}"),
            title=leilao.get("nome"),
            committer_name=comitente.get("nome"),
            modality=(leilao.get("modalidade") or "").lower() or None,
            auction_type="extrajudicial",
            official_url=f"{self.base_url}/leilao?leilao.nome={quote_plus(leilao.get('nome') or '')}" if leilao.get("nome") else None,
            sessions=sessions,
        )
        return ScrapedItem(
            external_id=str(lot_id),
            title=title,
            official_url=f"{self.base_url}/leilao?lote={lot_id}",
            price=self.parse_brl(valor.get("minimo")),
            price_kind="lance_inicial",
            lot_number=str(lot.get("numero")) if lot.get("numero") is not None else None,
            city=self.reject_unknown((loc.get("cidade") or "").title() or None),
            state=self.reject_unknown((loc.get("estado") or "").upper()[:2] or None),
            location_text=self.reject_unknown(loc.get("nome")),
            image_url=photos[0] if photos else None,
            images=photos[:12],
            description=" ".join(desc_parts),
            raw_attributes=raw,
            category_hint=category_hint,
            status_hint=status_hint,
            auction=auction,
            raw_payload=json.dumps(lot, ensure_ascii=False),
        )
