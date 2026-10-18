"""Sodré Santoro (sodresantoro.com.br; patios em Guarulhos/SP, Curitiba/PR,
Monte Mor/SP e Ribeirao Preto/SP) — um dos maiores leiloeiros de veiculos do
pais: ~500-650 lotes abertos de carros, motos, utilitarios leves e caminhoes,
quase tudo extrajudicial (Allianz, Banco Pan, Suhai...) e ~11% judicial
(varas criminais e civeis de SP/PR). Sem navegador.

O site e' uma SPA (Nuxt) que consulta um Elasticsearch pelo proprio dominio:

  GET  /lotes            capa da busca. So' serve para o bot manager (Azion)
                         devolver os cookies `az_asm`/`az_botm` (24 h); sem
                         eles o POST abaixo da 403. A capa so' responde 200
                         com cabecalhos completos de Chrome (client hints
                         `sec-ch-ua*`, `Sec-Fetch-*`), que o
                         `BaseScraper.headers()` ja' manda.
  POST /api/search-lots  corpo = a consulta que a propria SPA manda por
                         padrao (lotes de leilao aberto ou online, sem lotes
                         de teste; `SEARCH_FILTER`), com `from`/`size` para
                         paginar. Resposta {results, total, page, perPage}.
                         Precisa de `Origin`/`Referer` do site e
                         `Sec-Fetch-Site: same-origin` (`XHR`), com os
                         cookies da sessao (ficam no `self.client`).

Cada resultado e' o card completo: marca, modelo, anos, km, combustivel,
cambio, cor, placa ja' mascarada ("final 3"), opcionais, sinistro, origem,
categoria, lances, datas das pracas, fotos, comitente e, nos judiciais, vara
e processo. Nao ha' detalhe a buscar: `fetch_details` e' ignorado.

URL oficial do lote (RN-001): `/leilao/{auction_id}/lote/{lot_id}`; do
leilao, `/leilao/{auction_id}`. Complemento disponivel e nao usado:
`GET https://prd-api.sodresantoro.com.br/api/v1/auctions?status=aberto`
(leiloes com datas e pracas) — tudo que traz ja' vem no card.

Dados pessoais (RN-009): `lot_judicial_executor`, `lot_judicial_executed`,
`lot_judicial_defendant` e `lot_judicial_judge` sao partes/juiz do processo
e `bid_user_nickname` e' o apelido de quem deu o lance: nenhum entra em
lugar nenhum, nem no `raw_payload` (`search_terms` tambem sai, porque os
repete). A `lot_description` dos judiciais traz placa, RENAVAM e chassi em
claro e o nome e o endereco do depositario ("sob o deposito da executada
Fulana, na Rua..."); a de comitente "outros" (pessoa fisica) traz nome e
telefone de contato e o endereco da casa. Os trechos que citam partes ou
contato sao descartados inteiros, endereco sai quando o comitente nao e'
institucional, e o que sobra passa pelo `mask_text`. O endereco do patio
(`lot_location_address`) segue a mesma regra.

`lot_rate_information` e `lot_note` chegam com mojibake (UTF-8 lido como
Latin-1 em algum ponto da indexacao): `fix_mojibake` desfaz.

robots.txt permite tudo. Termos de uso: conteudo "para uso estritamente
pessoal", proibido uso comercial sem consentimento; nada sobre robos (mesmo
texto-padrao de outras fontes ja' cadastradas). Verificado em 17/10/2026.
"""
from __future__ import annotations

import json
import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from unidecode import unidecode

from app.engine.masking import mask_text
from app.scrapers.base import BaseScraper, ScrapedAuction, ScrapedItem, ScrapedSession

logger = logging.getLogger("zleilao.scraper.sodresantoro")

#: Filtro padrao da busca do site, copiado do chunk `elastic` da SPA em
#: 17/10/2026: lotes de leiloes online, ou abertos menos os status 5 e 7, ou
#: encerrados so' no status 6 do segmento 1 (veiculos); nunca lote de teste.
#: `indices`, `from` e `size` entram por `search_body`.
SEARCH_VERIFIED_AT = "2026-10-17"
SEARCH_FILTER: list[dict[str, Any]] = [
    {"bool": {"should": [
        {"bool": {"must": [{"term": {"auction_status": "online"}}]}},
        {"bool": {"must": [{"term": {"auction_status": "aberto"}}],
                  "must_not": [{"terms": {"lot_status_id": [5, 7]}}]}},
        {"bool": {"must": [{"term": {"auction_status": "encerrado"}}, {"terms": {"lot_status_id": [6]}}]}},
    ], "minimum_should_match": 1}},
    {"bool": {"should": [
        {"bool": {"must_not": {"term": {"lot_status_id": 6}}}},
        {"bool": {"must": [{"term": {"lot_status_id": 6}}, {"term": {"segment_id": 1}}]}},
    ], "minimum_should_match": 1}},
    {"bool": {"should": [{"bool": {"must_not": [{"term": {"lot_test": True}}]}}], "minimum_should_match": 1}},
]
SEARCH_SORT = [{"lot_status_id_order": {"order": "asc"}}]
DEFAULT_INDICES = ["veiculos", "judiciais-veiculos"]

# `lot_status` (texto, unidecode minusculo) -> status nosso. Em 17/10/2026 a
# busca padrao so' devolvia "andamento" (id 1); os demais rotulos sao os que
# o vocabulario do site sugere e, fora do mapa, o texto e o status do leilao
# decidem.
LOT_STATUS_MAP = {
    "andamento": "open", "em andamento": "open", "aberto": "open", "condicional": "open",
    "venda direta": "open", "repasse": "open",
    "aguardando": "soon", "em breve": "soon", "agendado": "soon",
    "vendido": "sold", "arrematado": "sold",
    "nao vendido": "closed", "encerrado": "closed", "finalizado": "closed",
    "retirado": "withdrawn", "cancelado": "withdrawn", "suspenso": "withdrawn",
}
AUCTION_STATUS_MAP = {"aberto": "open", "online": "open", "encerrado": "closed"}

# `lot_category` da fonte -> dica de categoria. "utilitarios leves" mistura
# picape e furgao; o HINT_MAP do classificador ja' trata "utilitarios-leves"
# (carros, e o titulo decide o resto). "van leve" e' van mesmo.
CATEGORY_MAP = {
    "carros": "carros", "motos": "motos",
    "utilitarios leves": "utilitarios-leves", "van leve": "utilitarios", "vans": "utilitarios",
    "caminhoes": "caminhoes", "utilitarios pesados": "caminhoes", "onibus": "onibus",
    "maquinas": "maquinas-equipamentos", "tratores": "maquinas-equipamentos",
}
FUEL_MAP = {
    "flex": "flex", "gasolina/alcool": "flex", "alcool/gasolina": "flex",
    "gasolina": "gasolina", "diesel": "diesel", "hibrido": "hibrido",
    "alcool": "etanol", "etanol": "etanol", "gnv": "gnv", "eletrico": "eletrico",
}
GEAR_MAP = {"automatico": "automatico", "automatica": "automatico", "automatizado": "automatizado",
            "cvt": "cvt", "manual": "manual"}
# `lot_sinister` -> `condicao` no vocabulario do deterministic.py. A ordem
# importa: "sucata desmanche" tem que render sucata antes de qualquer monta.
SINISTER_MAP = [
    ("sucata", "sucata"), ("grande monta", "sinistro_grande_monta"), ("media monta", "sinistro_media_monta"),
    ("pequena monta", "sinistro_recuperavel"), ("sem sinistro", "normal"),
]
ORIGIN_MAP = {
    "seguro": "seguradora", "seguradora": "seguradora", "judicial": "judicial", "frota": "frota",
    "financeira": "financeira", "banco": "financeira", "locadora": "locadora", "particular": "particular",
}
# Origem pelo comitente quando `lot_origin` vem vazio (92% dos cards em
# 17/10/2026). Seguradoras antes das financeiras: "Bradesco Seguros" nao e'
# "Banco Bradesco". Comitente fora dos padroes fica sem origem (RN-002).
ORIGIN_BY_CLIENT = [
    (r"segur|allianz|suhai|mapfre|\bporto\b|tokio|\bhdi\b|liberty|sompo|\bazul\b", "seguradora"),
    (r"^banco\b|\bpan\b|financ|santander|ita[uú]|\bbv\b|safra|\bomni\b|daycoval|cons[oó]rcio|bradesco", "financeira"),
    (r"localiza|movida|unidas|locadora|\brent\b", "locadora"),
    (r"\bfrota\b", "frota"),
]

# Trecho que cita uma parte do processo ou o depositario sai inteiro da
# descricao: e' onde a fonte escreve nome e endereco de pessoa (RN-009).
PARTY_RE = re.compile(
    r"\b(?:executad[oa]s?|exequentes?|deposit[aá]ri[oa]s?|fiel\s+deposit\w*|r[ée]us?|acusad[oa]s?|"
    r"indiciad[oa]s?|investigad[oa]s?|devedor(?:a|es|as)?|credor(?:a|es|as)?|reclamantes?|"
    r"reclamad[oa]s?|requerentes?|requerid[oa]s?|embargantes?|embargad[oa]s?|autor(?:a|es)?\s+d[ao]|"
    r"em\s+poder\s+d[oa])\b", re.I)
# Contato para visita ("agendar com o Sr. Fulano no fone ...") e' pessoa.
# A fonte escreve "whattsapp"; telefone com 4 ou 5 digitos no prefixo.
CONTACT_RE = re.compile(
    r"\b(?:sr|sra|srta|dr|dra|senhor|senhora)\.?\s+[^\W\d_]|\b(?:sr|sra|srta|dr|dra)\.?\s*$|"
    r"\b(?:fone|telefone|what+s\w*|zap|celular|contato)\b|"
    r"\(?\d{2}\)?[-\s.]?\d{4,5}[-.\s]\d{4}\b", re.I)
# Logradouro: so' e' descartado quando o comitente nao e' institucional
# (pode ser a casa de quem vende). "R$" nao e' "R ".
ADDRESS_RE = re.compile(
    r"\b(?:rua|r\s+(?=[^\W\d_])|av\.|avenida|al\.|alameda|travessa|estrada|rodovia|rod\.|s[ií]tio|ch[aá]cara)\b", re.I)
# Segmentos: " - " (a fonte separa itens assim) ou fim de frase seguido de
# maiuscula, digito ou "(i)" — menos depois de "Sr.", "Dr.", "Rod.", "Av.",
# que nao fecham frase ("Sr. Fulano" tem que ficar junto para o CONTACT_RE
# descarta-lo). O separador e' capturado para ser reposto.
SEGMENT_SPLIT_RE = re.compile(
    r"(\s+-\s+|(?<![Ss]r\.)(?<![Ss]ra\.)(?<![Dd]r\.)(?<![Dd]ra\.)(?<![Rr]od\.)(?<![Aa]v\.)"
    r"(?<=[.;])\s+(?=\(?[A-ZÀ-Ü0-9(]))")
AVALIACAO_RE = re.compile(r"avalia[cç][aã]o:?\s*R\$\s*([\d.]+,\d{2})", re.I)
COMISSAO_RE = re.compile(r"comiss[aã]o:?\s*([\d.,]+)\s*%", re.I)
TAXA_RE = re.compile(r"([A-Za-zÀ-ü/ ]+?):\s*(?:R\$\s*)?(\d{1,3}(?:\.\d{3})*,\d{2})\b")
# Placa em claro (antiga ou Mercosul): nunca entra como atributo
CLEAR_PLATE_RE = re.compile(r"[A-Za-z]{3}-?\s?\d[A-Za-z0-9]\d{2}")
# "curitiba i" -> o algarismo romano e' o numero do patio, nao parte da cidade
PATIO_SUFFIX_RE = re.compile(r"\s+(?:i{1,3}|iv|v|vi{1,3})$")
LOCATION_RE = re.compile(r"^(.+?)\s*/\s*([a-z]{2})$")
ADDRESS_CITY_RE = re.compile(r"([^,\-/#]+?)\s*[/#]\s*([a-z]{2})\s*$")
# Ultimo "de <cidade>/<uf>" do nome da vara: "5a vara criminal de ribeirao preto/sp"
COURT_CITY_RE = re.compile(r"\bde\s+((?:(?!\bde\s)[^/,-])+?)\s*/\s*([a-z]{2})\s*$")
SMALL_WORDS = {"de", "da", "do", "das", "dos", "e", "em", "a", "o", "as", "os", "no", "na", "nos", "nas",
               "ao", "aos", "para", "por", "com", "sem"}
ROMAN_RE = re.compile(r"^(?:i{1,3}|iv|v|vi{1,3}|ix|x)$")
# Siglas de versao/motor que a fonte escreve em minusculas ("xre 300 abs")
ACRONYMS = {
    "abs", "es", "esd", "esdi", "ex", "exl", "lx", "ls", "lt", "ltz", "xl", "xls", "xlt", "xei", "gli", "glx",
    "gls", "cd", "cs", "ce", "td", "tdi", "tsi", "tfsi", "gti", "gts", "mpi", "hdi", "amg", "rs", "sr", "srv",
    "srx", "xre", "cbr", "cb", "cg", "pcx", "nxr", "xr", "xt", "xtz", "mt", "at", "cvt", "dx", "sw", "aut",
    "mec", "hev", "phev", "ev", "awd", "4wd", "cvt", "dct", "tb", "tgv", "vhc", "vhce", "mi", "ie", "gl",
    "se", "sel", "sle", "slx", "xs", "xsi", "xli", "xrs", "xlr", "xd", "xr", "yes",
}

#: Chaves do card que nunca sao gravadas, nem no payload bruto (RN-009).
PRIVATE_KEYS = ("lot_judicial_executor", "lot_judicial_executed", "lot_judicial_defendant",
                "lot_judicial_judge", "bid_user_nickname", "search_terms")
#: Boilerplate de visitacao repetido em todo card (~300 bytes cada)
NOISE_KEYS = ("lot_note",)


def fix_mojibake(text: str | None) -> Optional[str]:
    """"ComissÃ£o" -> "Comissão". So' mexe quando ha' marca de UTF-8 lido como
    Latin-1; texto sao passa intacto."""
    if not text:
        return None
    if "Ã" not in text and "Â" not in text:
        return text
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


class SodreSantoroScraper(BaseScraper):
    display_name = "Sodré Santoro"
    default_config = {
        "path": "/lotes",
        "api_path": "/api/search-lots",
        "indices": DEFAULT_INDICES,
        "page_size": 100,
        "max_pages": 8,
        "fetch_details": False,
    }

    @property
    def default_base_url(self) -> str:
        return "https://www.sodresantoro.com.br"

    # ── busca ────────────────────────────────────────────────────────

    def search_body(self, offset: int, size: int) -> dict[str, Any]:
        indices = self.cfg("indices") or DEFAULT_INDICES
        if isinstance(indices, str):
            indices = [s.strip() for s in indices.split(",") if s.strip()]
        return {
            "indices": list(indices),
            "from": int(offset),
            "size": int(size),
            "sort": SEARCH_SORT,
            "query": {"bool": {"filter": SEARCH_FILTER}},
        }

    async def search(self, offset: int, size: int) -> Any:
        """A SPA chama a API por fetch() de dentro de /lotes: Origin e Referer
        do proprio site. Os cookies do bot manager vem da capa e o
        `self.client` os reaproveita."""
        headers = {
            "Content-Type": "application/json",
            "Origin": self.base_url,
            "Referer": self.abs_url(self.cfg("path", "/lotes")),
        }
        url = self.abs_url(self.cfg("api_path", "/api/search-lots"))
        return await self.post_json(url, json=self.search_body(offset, size), headers=headers)

    async def scrape(self) -> list[ScrapedItem]:
        capa = self.abs_url(self.cfg("path", "/lotes"))
        try:
            await self.fetch(capa)
        except Exception as exc:
            # Sem a capa nao vem cookie e o POST tende a dar 403; ainda assim
            # tenta, porque o bloqueio e' do bot manager e pode nao estar ativo.
            self.stats.errors += 1
            self.stats.notes.append(f"capa {capa} falhou: {str(exc)[:120]}")
            logger.warning("[Sodre] capa nao carregou (%s); tenta a busca mesmo assim", exc)

        items: list[ScrapedItem] = []
        size = max(1, int(self.cfg("page_size", 100)))
        max_pages = int(self.cfg("max_pages", 8))
        offset, page, total = 0, 1, None
        while page <= max_pages:
            try:
                await self.delay()
                data = await self.search(offset, size)
            except Exception as exc:
                self.stats.errors += 1
                self.stats.mark_partial(f"pagina {page} da busca falhou: {str(exc)[:120]}")
                break
            self.stats.pages += 1
            results = data.get("results") if isinstance(data, dict) else None
            if not isinstance(results, list):
                self.stats.errors += 1
                self.stats.mark_partial(f"pagina {page}: resposta inesperada da busca")
                break
            if isinstance(data.get("total"), int):
                total = data["total"]
            got = self.parse_results(results)
            items.extend(got)
            logger.debug("[Sodre] pagina %d: %d lotes (total informado: %s)", page, len(got), total)
            offset += len(results)
            if not results or (total is not None and offset >= total):
                break
            if page == max_pages:
                self.stats.mark_partial(f"parou em {max_pages} paginas: {offset} de {total or '?'} lotes")
            page += 1
        return items

    # ── mapeamento ───────────────────────────────────────────────────

    def parse_results(self, results: list[dict[str, Any]]) -> list[ScrapedItem]:
        out: list[ScrapedItem] = []
        for lot in results:
            try:
                item = self._map_lot(lot) if isinstance(lot, dict) else None
                if item:
                    out.append(item)
            except Exception as exc:
                self.stats.errors += 1
                logger.debug("[Sodre] lote ignorado: %s", exc)
        return out

    def _map_lot(self, lot: dict[str, Any]) -> Optional[ScrapedItem]:
        lot_id = lot.get("lot_id")
        auction_id = lot.get("auction_id")
        if not lot_id or not auction_id:
            return None
        judicial = bool(lot.get("lot_is_judicial"))
        scrap = bool(lot.get("lot_is_scrap"))

        brand = self.model_case(lot.get("lot_brand"))
        model = self.model_case(lot.get("lot_model"))
        fab, mod = self._int(lot.get("lot_year_manufacture")), self._int(lot.get("lot_year_model"))
        title = self.build_title(brand, model, fab, mod, lot.get("lot_title"), scrap)
        if not title:
            return None

        inicial = self._num(lot.get("bid_initial"))
        atual = self._num(lot.get("bid_actual"))
        has_bid = bool(lot.get("bid_has_bid"))
        if has_bid and atual:
            price, price_kind = atual, "lance_atual"
        else:
            # `bid_initial` 0,00 e' "sem lance minimo publicado", nao preco zero
            price, price_kind = inicial, "lance_inicial"

        client = self.nice_name(self.reject_unknown(self.clean_text(lot.get("client_name"))))
        court = self.nice_name(lot.get("lot_judicial_court")) if judicial else None
        # A vara que remeteu o bem e' mais especifica que o `client_name`, que
        # a fonte abrevia ("vara do juizado esp. civ da com de ...")
        committer = court or client
        # Judicial ou comitente "outros" (pessoa fisica): endereco e' dado pessoal
        strict = judicial or not client

        origem_fonte = unidecode(str(lot.get("lot_origin") or "")).lower().strip() or None
        if judicial:
            origem = "judicial"
        else:
            origem = ORIGIN_MAP.get(origem_fonte or "") or self.origin_from_client(client)

        sinister = self.clean_text(lot.get("lot_sinister")).lower() or None
        condicao = "sucata" if scrap else self.condition_from_sinister(sinister)

        fuel_src = unidecode(self.clean_text(lot.get("lot_fuel"))).lower() or None
        fuel = FUEL_MAP.get(fuel_src or "")
        gear_src = unidecode(self.clean_text(lot.get("lot_transmission"))).lower() or None
        plate = self.clean_text(lot.get("lot_plate")) or None
        if plate and CLEAR_PLATE_RE.search(plate):
            plate = None  # so' a placa que a fonte ja' mascarou ("final 3")

        city, state, location_text = self.resolve_location(lot, strict, court or client)

        rate = fix_mojibake(lot.get("lot_rate_information"))
        comissao, taxas = self.parse_rate(rate)
        description, avaliacao = self.scrub_description(lot.get("lot_description"), strict=strict)
        desconto = self._num(lot.get("tj_praca_discount"))

        raw: dict[str, Any] = {
            "marca": brand,
            "modelo": model,
            "ano_fabricacao": fab,
            "ano_modelo": mod,
            "km": self._int(lot.get("lot_km")) or None,  # 0 e' "nao informado"
            "combustivel": fuel,
            "combustivel_fonte": fuel_src if fuel_src and not fuel and self.reject_unknown(fuel_src) else None,
            "cambio": GEAR_MAP.get(gear_src or "") or (self.reject_unknown(gear_src) if gear_src else None),
            "cor": (self.reject_unknown(self.clean_text(lot.get("lot_color"))) or "").title() or None,
            "placa_mascarada": plate,
            "opcionais": [str(o) for o in (lot.get("lot_optionals") or []) if o] or None,
            "condicao": condicao,
            "sinistro_fonte": sinister,
            "sucata": True if scrap else None,
            "origem": origem,
            "origem_fonte": origem_fonte if origem_fonte and ORIGIN_MAP.get(origem_fonte) != origem else None,
            "categoria_fonte": self.clean_text(lot.get("lot_category")) or None,
            "patio": None if self._unknown_location(lot.get("lot_location")) else self.nice_name(lot.get("lot_location")),
            "comitente": committer,
            "comissao_pct": comissao,
            "taxas": taxas or None,
            "processo": (self.clean_text(lot.get("lot_judicial_process")) or None) if judicial else None,
            "vara": court,
            "acao_judicial": (self.clean_text(lot.get("lot_judicial_action"))[:150] or None) if judicial else None,
            "valor_avaliacao": avaliacao,
            "lance_inicial": str(inicial) if inicial else None,
            "lance_atual": str(atual) if has_bid and atual else None,
            "desconto_2a_praca_pct": str(desconto) if desconto else None,
            "permite_financiamento": bool(lot["lot_status_financeable"]) if "lot_status_financeable" in lot else None,
            "status_fonte": self.clean_text(lot.get("lot_status")) or None,
            "praca": self.clean_text(lot.get("lot_praca_label")) or None,
        }
        raw = {k: v for k, v in raw.items() if v not in (None, "", [], {})}

        desc_parts = [description] if description else [title + "."]
        if sinister:
            desc_parts.append(f"Sinistro: {sinister}.")
        if committer:
            desc_parts.append(f"Comitente: {committer}.")
        if raw.get("praca"):
            desc_parts.append(f"{raw['praca']}.")
        if comissao is not None:
            desc_parts.append(f"Comissão do leiloeiro: {comissao:g}%.")
        if raw.get("permite_financiamento"):
            desc_parts.append("Financiável.")
        if raw.get("status_fonte"):
            desc_parts.append(f"Situação: {raw['status_fonte']}.")

        status_src = unidecode(str(lot.get("lot_status") or "")).lower().strip()
        auction_status = unidecode(str(lot.get("auction_status") or "")).lower().strip()
        status_hint = (LOT_STATUS_MAP.get(status_src) or self.status_from_text(status_src)
                       or AUCTION_STATUS_MAP.get(auction_status) or "open")

        images = [u for u in (lot.get("lot_pictures") or []) if isinstance(u, str) and u.startswith("http")]
        category_hint = "sucatas" if scrap else self.category_hint(lot.get("lot_category"))

        auction = ScrapedAuction(
            external_id=str(auction_id),
            title=self.nice_name(lot.get("auction_name")) or f"Leilão {auction_id}",
            auctioneer_name=self.nice_name(lot.get("auctioneer_name")) or self.display_name,
            committer_name=committer,
            auction_type="judicial" if judicial else "extrajudicial",
            official_url=f"{self.base_url}/leilao/{auction_id}",
            sessions=self.sessions(lot, inicial),
        )
        return ScrapedItem(
            external_id=str(lot_id),
            title=title,
            official_url=f"{self.base_url}/leilao/{auction_id}/lote/{lot_id}",
            price=price,
            price_kind=price_kind,
            price_second=self._num(lot.get("tj_praca_value")),
            lot_number=str(lot.get("lot_number")).strip() if lot.get("lot_number") not in (None, "") else None,
            city=city,
            state=state,
            location_text=location_text,
            image_url=images[0] if images else None,
            images=images[:12],
            description=" ".join(desc_parts)[:4000],
            raw_attributes=raw,
            category_hint=category_hint,
            status_hint=status_hint,
            auction=auction,
            raw_payload=json.dumps(self._compact(lot, description, strict), ensure_ascii=False),
        )

    # ── sessoes ──────────────────────────────────────────────────────

    def sessions(self, lot: dict[str, Any], inicial: Optional[Decimal]) -> list[ScrapedSession]:
        """Judicial tem duas pracas: `auction_date_init` e `auction_date_2`
        sao as datas das duas, mas qual e' qual depende da praca corrente
        (na 2a, `date_2` e' a 1a, ja' passada). A ordem cronologica resolve.
        `lot_date_end` e' o fechamento do lote na praca corrente. Extrajudicial
        e' sessao unica que fecha em `lot_date_end`."""
        d_init = self.parse_datetime_br(lot.get("auction_date_init"))
        d_2 = self.parse_datetime_br(lot.get("auction_date_2"))
        lot_end = self.parse_datetime_br(lot.get("lot_date_end"))
        praca = str(lot.get("lot_praca_status") or "").strip()
        label = unidecode(str(lot.get("lot_praca_label") or "")).lower()
        if not praca and label:
            praca = "2" if label.startswith("2") else "1"
        if not d_2 and not praca:
            return [ScrapedSession(kind="unica", starts_at=d_init, ends_at=lot_end, min_bid=inicial)]
        dates = sorted(d for d in (d_init, d_2) if d)
        first = dates[0] if dates else None
        second = dates[1] if len(dates) > 1 else None
        s1 = ScrapedSession(kind="1a_praca", starts_at=first)
        s2 = ScrapedSession(kind="2a_praca", starts_at=second, min_bid=self._num(lot.get("tj_praca_value")))
        active = s2 if praca == "2" else s1
        active.ends_at = lot_end
        active.min_bid = inicial or active.min_bid
        return [s1, s2]

    # ── localizacao ──────────────────────────────────────────────────

    @staticmethod
    def _unknown_location(text: Any) -> bool:
        t = unidecode(str(text or "")).lower().strip()
        return not t or t.startswith("outros")

    def resolve_location(self, lot: dict[str, Any], strict: bool,
                         committer: Optional[str]) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """Cidade/UF do bem: o endereco do patio quando a fonte o da' e o
        comitente e' institucional; senao o nome do patio ("curitiba i/pr");
        no judicial sem patio, a comarca da vara (o bem fica sob a custodia
        dela, como no Montenegro)."""
        city = state = location_text = None
        address = self.clean_text(lot.get("lot_location_address")) or None
        if address and not strict:
            city, state = self.city_state_from_address(address)
            location_text = self.nice_name(address)
        if not city:
            c2, s2 = self.city_state_from_location(lot.get("lot_location"))
            city, state = city or c2, state or s2
            if location_text is None and c2:
                location_text = self.nice_name(lot.get("lot_location"))
        if not city and lot.get("lot_is_judicial"):
            c3, s3 = self.city_state_from_court(committer)
            city, state = c3, s3 or state
        return city, state, location_text

    @classmethod
    def city_state_from_location(cls, text: str | None) -> tuple[Optional[str], Optional[str]]:
        t = cls.clean_text(text).lower()
        if cls._unknown_location(t):
            return None, None
        m = LOCATION_RE.match(t)
        if not m:
            return None, None
        city = cls.reject_unknown(cls.nice_name(PATIO_SUFFIX_RE.sub("", m.group(1)).strip()))
        return city, (m.group(2).upper() if city else None)

    @classmethod
    def city_state_from_address(cls, text: str | None) -> tuple[Optional[str], Optional[str]]:
        t = cls.clean_text(text).lower()
        m = ADDRESS_CITY_RE.search(t)
        if not m:
            return None, None
        city = cls.reject_unknown(cls.nice_name(m.group(1).strip()))
        return city, (m.group(2).upper() if city else None)

    @classmethod
    def city_state_from_court(cls, text: str | None) -> tuple[Optional[str], Optional[str]]:
        t = cls.clean_text(text).lower()
        m = COURT_CITY_RE.search(t)
        if not m:
            return None, None
        city = cls.reject_unknown(cls.nice_name(m.group(1).strip()))
        return city, (m.group(2).upper() if city else None)

    # ── texto ────────────────────────────────────────────────────────

    @classmethod
    def scrub_description(cls, text: str | None, strict: bool = False) -> tuple[Optional[str], Optional[str]]:
        """Descricao sem os trechos que citam partes do processo ou contato
        de pessoa (e, com `strict`, sem logradouro), e sem placa, RENAVAM e
        chassi em claro (RN-009). Devolve tambem o valor da avaliacao
        judicial, quando o texto o traz."""
        t = cls.clean_text(text)
        if not t:
            return None, None
        parts = SEGMENT_SPLIT_RE.split(t)
        kept: list[str] = []
        for i in range(0, len(parts), 2):
            seg = parts[i]
            if not seg.strip():
                continue
            if PARTY_RE.search(seg) or CONTACT_RE.search(seg) or (strict and ADDRESS_RE.search(seg)):
                continue
            kept.append((parts[i - 1] if i and kept else "") + seg)
        t = cls.clean_text("".join(kept))
        if not t:
            return None, None
        m = AVALIACAO_RE.search(t)
        avaliacao = cls.parse_brl(m.group(1)) if m else None
        return mask_text(t).text[:3000] or None, (str(avaliacao) if avaliacao else None)

    @staticmethod
    def parse_rate(text: str | None) -> tuple[Optional[float], dict[str, str]]:
        """"Comissão: 5.00% do valor do lance, Depósito de Bens: R$ 2.350,00,
        Outros Débitos: 153,00, Sedex: Valores na condição de venda" ->
        (5.0, {"Depósito de Bens": "2350.00", "Outros Débitos": "153.00"})."""
        if not text:
            return None, {}
        pct = None
        m = COMISSAO_RE.search(text)
        if m:
            try:
                pct = float(m.group(1).replace(",", "."))
            except ValueError:
                pct = None
        taxas: dict[str, str] = {}
        for m in TAXA_RE.finditer(text):
            label = BaseScraper.clean_text(m.group(1))
            if not label or unidecode(label).lower().startswith("comiss"):
                continue
            valor = BaseScraper.parse_brl(m.group(2))
            if valor:
                taxas[label] = str(valor)
        return pct, taxas

    @classmethod
    def nice_name(cls, text: str | None) -> Optional[str]:
        """A fonte indexa tudo em minusculas ("1ª vara criminal da comarca de
        ribeirão preto/sp", "allianz seguros s.a"): capitaliza as palavras,
        mantem preposicoes e sobe a UF e siglas entre parenteses."""
        t = cls.clean_text(text).lower()
        if not t:
            return None

        def word(m: re.Match) -> str:
            w = m.group(0)
            prev = t[m.start() - 1] if m.start() else ""
            # `prev` vazio no inicio da string: "" esta' em qualquer string
            if prev and prev in "/(" and len(w) <= 3:
                return w.upper()
            if w in SMALL_WORDS and m.start():
                return w
            return w[0].upper() + w[1:]

        out = re.sub(r"[^\W\d_]+", word, t)
        return re.sub(r"\bS\.a\b", "S.A", out)

    @staticmethod
    def model_case(text: str | None) -> Optional[str]:
        """"cg 160 fan esdi" -> "CG 160 Fan ESDI"; "r540 a6x4" -> "R540 A6X4";
        "belina ii l" -> "Belina II L". So' legibilidade: marca e modelo sao
        normalizados pelo motor deterministico depois. Sobe o que tem digito,
        sigla curta sem vogal, algarismo romano e as siglas de versao mais
        comuns; o resto capitaliza (hifen inclusive: "mercedes-benz")."""
        t = BaseScraper.clean_text(text).lower()
        if not t:
            return None
        out = []
        for tok in t.split(" "):
            if (re.search(r"\d", tok) or (len(tok) <= 4 and not re.search(r"[aeiouy]", tok))
                    or ROMAN_RE.match(tok) or tok in ACRONYMS):
                out.append(tok.upper())
            else:
                out.append("-".join(p[:1].upper() + p[1:] for p in tok.split("-")))
        return " ".join(out)

    @classmethod
    def build_title(cls, brand: Optional[str], model: Optional[str], fab: Optional[int], mod: Optional[int],
                    lot_title: str | None, scrap: bool) -> str:
        base = " ".join(x for x in (brand, model) if x)
        if not base:
            base = cls.model_case(cls.clean_text(lot_title).replace(" - ", " ")) or ""
        if not base:
            return ""
        years = f"{fab}/{mod}" if fab and mod else str(fab or mod or "")
        title = f"{base} {years}".strip()
        # "Sucata" no titulo: a categoria e a condicao vem do titulo (sucata
        # de CG 125 nao e' uma moto a venda)
        return f"Sucata {title}" if scrap else title

    # ── vocabulario ──────────────────────────────────────────────────

    @staticmethod
    def condition_from_sinister(text: str | None) -> Optional[str]:
        t = unidecode(text or "").lower()
        if not t:
            return None
        return next((v for k, v in SINISTER_MAP if k in t), None)

    @staticmethod
    def origin_from_client(client: str | None) -> Optional[str]:
        t = unidecode(client or "").lower()
        if not t:
            return None
        return next((v for pat, v in ORIGIN_BY_CLIENT if re.search(pat, t)), None)

    @staticmethod
    def category_hint(text: str | None) -> Optional[str]:
        t = unidecode(str(text or "")).lower().strip()
        if not t:
            return None
        return CATEGORY_MAP.get(t) or t.replace(" ", "-")

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _compact(lot: dict[str, Any], description: Optional[str], strict: bool) -> dict[str, Any]:
        """Card sem as chaves de pessoas e sem o boilerplate; a descricao vai
        ja' limpa, porque o payload bruto tambem e' persistido (RN-009). Com
        `strict` (judicial ou comitente "outros") o endereco do bem sai."""
        out = {k: v for k, v in lot.items() if k not in PRIVATE_KEYS and k not in NOISE_KEYS}
        out["lot_description"] = description
        if strict:
            out.pop("lot_location_address", None)
        if out.get("lot_rate_information"):
            out["lot_rate_information"] = fix_mojibake(out["lot_rate_information"])
        return out

    @staticmethod
    def _num(value: Any) -> Optional[Decimal]:
        """"91285.20" (ponto decimal) -> Decimal; zero e vazio viram None."""
        if value in (None, "", False):
            return None
        try:
            d = Decimal(str(value).strip().replace(",", "."))
        except (InvalidOperation, ValueError):
            return None
        return d.quantize(Decimal("0.01")) if d > 0 else None

    @staticmethod
    def _int(value: Any) -> Optional[int]:
        if value in (None, ""):
            return None
        try:
            return int(str(value).strip().split(".")[0])
        except ValueError:
            return None
