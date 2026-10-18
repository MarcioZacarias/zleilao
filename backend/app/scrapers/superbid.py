"""Superbid (superbid.net) — a maior plataforma de leiloes do pais: ~6.900
carros e motos, ~950 caminhoes e onibus e ~1.800 maquinas abertos em
17/10/2026, judicial e extrajudicial, de dezenas de lojas (leiloeiros e
casas de leilao) que publicam no marketplace. O site (Next.js) fica atras de
um desafio Cloudflare que o httpx nao passa, mas o front le os dados de
microservicos sem desafio, sem cookie e sem token, com CORS aberto — e' por
eles que este coletor entra:

  GET https://offer-query.superbid.net/seo/offers/
      ?urlSeo=https://www.superbid.net/categorias/{cat}&searchType=opened
      &orderBy=endDate:asc&pageNumber=N&pageSize=M
      a mesma consulta que o SSR do site faz para a pagina da categoria. Cada
      oferta vem completa: preco e lances, datas, loja, leilao (com as pracas
      quando judicial), produto (template com marca/ano/km..., fotos,
      localizacao, processo). `searchType=opened` e' o que restringe a lotes
      abertos; filtrar por `statusId:1` devolve registros zumbis de 2021.
      `pageSize` ate 500 funciona (1,2 s); pagina alem do total responde 404.
  GET https://event-query.superbid.net/events/v2/?filter=modalityId:[1,4,5,7]
      agenda dos eventos (leiloes) com `eventPipeline.stages` (pracas).
      Opcional: a oferta ja' embute o pipeline quando o leilao tem pracas.
  GET https://offer-query.superbid.net/categories/
      contagem por tipo de produto e categoria (so' diagnostico).

Cobertura: `max_pages` vem do agente de coleta (2 por hora, 12 na varredura
profunda) por entrada de `categorias`. Com 100 por pagina seriam 200/hora e
1.200/dia por categoria, longe dos 6.865 carros e motos; por isso o default
e' 200 por pagina, a ordenacao e' `endDate:asc` (quem encerra antes aparece
primeiro, que e' o que o usuario precisa ver) e `categorias` aceita
subcategorias (`carros-motos/carros`, `carros-motos/motos`) e entradas com
`filter` (ex.: `auction.subMarketplaces.subMarketplaceId:3` = judicial),
fatiando o catalogo em consultas menores.

URL oficial (RN-001): `https://www.superbid.net/oferta/{slug}-{id}`, slug do
titulo (unidecode, minusculas, hifens); os cards do site apontam para
`exchange.superbid.net` com o mesmo caminho. Leilao: `/evento/{slug}-{id}`.

Dados pessoais (RN-009): `productCustomJson.vehicleOwner` (nome do dono),
`seller` pessoa fisica, `winnerBid.currentWinnerLogin`, telefones do
comitente e, em `product.judicial`, partes, depositario, advogados, juiz e
endereco NUNCA sao copiados — fica o numero e o tipo do processo, vara e
foro. Placa inteira, chassi e Renavam no texto sao mascarados. O leiloeiro
oficial (nome + matricula na junta) e' funcao publica e fica.

robots.txt: inacessivel (403 do desafio Cloudflare), tratado como `unknown`
pelo sistema; os microservicos nao tem robots.txt (404). Termos de uso (PDF,
v11 de 26/02/2026) vedam engenharia reversa da "Plataforma Financeira sbX"
(o meio de pagamento, nao o site) e nada dizem sobre coleta automatizada.
Verificado em 17/10/2026.
"""
from __future__ import annotations

import html
import json
import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential
from unidecode import unidecode

from app.scrapers.base import BaseScraper, ScrapedAuction, ScrapedItem, ScrapedSession

logger = logging.getLogger("zleilao.scraper.superbid")

OFFER_QUERY = "https://offer-query.superbid.net"
EVENT_QUERY = "https://event-query.superbid.net"
#: O SSR do site consulta os dois portais (2 = Superbid, 15 = Superbid Exchange).
PORTAL_IDS = "[2,15]"

# A SPA chama os microservicos por fetch() a partir de www.superbid.net:
# requisicao CORS de outro subdominio (same-site), com Origin.
API_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.superbid.net",
    "Referer": "https://www.superbid.net/",
    "Sec-Fetch-Site": "same-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
}

# `product.subCategory.category.description` (normalizado) -> slug do projeto.
# E' so' dica: o titulo decide a categoria.
CATEGORY_MAP = {
    "carros": "carros", "carros de detran": "carros",
    "motos": "motos",
    "caminhoes": "caminhoes", "impl. rod. e carrocerias": "caminhoes",
    "onibus": "onibus",
    "vans": "utilitarios",
    "maquinas pesadas": "maquinas-construcao", "equip. de pavimentacao": "maquinas-construcao",
    "equip. de mineracao": "maquinas-construcao",
    "maquinas agricolas": "maquinas-agricolas", "implementos agricolas": "maquinas-agricolas",
    "maquinas florestais": "maquinas-agricolas",
    "lanchas e barcos": "outros-veiculos",
}
# Subcategorias que contradizem a categoria-mae (um furgao esta' em "Carros").
SUBCATEGORY_MAP = {
    "utilitarios & furgoes": "utilitarios", "ambulancias": "utilitarios",
    "quadriciclos": "outros-veiculos", "reboque": "outros-veiculos",
}
PRODUCT_TYPE_MAP = {10: "veiculos", 11: "veiculos", 15: "maquinas-equipamentos"}
# Pecas, consorcios e ferramentas nao sao o bem inteiro: fora por default.
SKIP_CATEGORY_RE = re.compile(r"partes e pecas|consorcio|ferramentas|pecas e acessorios")
SUCATA_RE = re.compile(r"\bsucata")

# `statusId` da oferta (observado em 17/10/2026: 1 = aberta; 3 e 6 vieram em
# registros antigos, com `wantToKnowThePrice`/`closedToBids`). Os flags de
# `offerStatus` decidem antes do codigo.
STATUS_ID_MAP = {1: "open", 3: "closed", 6: "closed"}

#: `template.groups[].properties[].id` -> chave que o motor deterministico le.
TEMPLATE_MAP = {
    "marca": "marca", "modelo": "modelo",
    "anofabricacao": "ano_fabricacao", "anodefabricacao": "ano_fabricacao", "ano": "ano_fabricacao",
    "anomodelo": "ano_modelo",
    "quilometragem": "km", "km": "km", "kilometragem": "km", "hodometro": "km",
    "cor": "cor", "combustivel": "combustivel", "cambio": "cambio", "transmissao": "cambio",
    "quantidadedeportas": "portas", "valortabelafipe": "valor_fipe", "codigofipe": "codigo_fipe",
    "horimetro": "horimetro", "potencia": "potencia_cv", "tipo": "tipo_equipamento",
    "condicao": "condicao_fonte", "status": "condicao_fonte",
}
INT_KEYS = {"ano_fabricacao", "ano_modelo", "km", "portas", "horimetro", "potencia_cv"}
FUEL_MAP = {
    "gasolina": "gasolina", "alcool": "etanol", "etanol": "etanol", "flex": "flex",
    "gasolina/alcool": "flex", "alcool/gasolina": "flex", "gasolina/etanol": "flex",
    "diesel": "diesel", "gnv": "gnv", "eletrico": "eletrico", "hibrido": "hibrido",
}

# `product.judicial` traz partes, depositario, advogados, juiz e endereco
# (RN-009): so' estas chaves descrevem o processo sem identificar ninguem.
JUDICIAL_SAFE_KEYS = ("processNumber", "processYear", "processType", "nature", "foro", "district", "vara")

# O comitente so' entra quando e' instituicao. A fonte ja' diz: vendedor com
# cadastro de empresa tem `company[].fantasyName`; pessoa fisica vem com
# `company: [{}]`. Esta lista e' reserva para vendedor sem `company`: forma
# juridica, orgao publico ou ramo de atividade no nome. Palavras que tambem
# aparecem em nome de gente (luz, forca, ordem...) ficam de fora de proposito.
INSTITUTION_RE = re.compile(
    r"\b(ltda|s/a|s\.a\.?|sa|eireli|epp|cia|companhia|prefeitura|municipio|municipal|tribunal|"
    r"vara|juizado|juizo|comarca|forum|justica|banco|fundo|fundacao|instituto|associacao|"
    r"cooperativa|sindicato|governo|secretaria|detran|universidade|faculdade|hospital|hospitalar|"
    r"seguradora|seguros|locadora|transportes?|logistica|agroindustria|industria|industrial|"
    r"comercio|comercial|empreendimentos|construcao|construtora|construcoes|energia|engenharia|"
    r"servicos|distribuidora|mineracao|usina|agricola|agropecuaria|consorcio|administradora|"
    r"participacoes|holding|leiloes|concessionaria|autarquia|camara|departamento|ministerio|"
    r"procuradoria|defensoria|policia|correios|imobiliaria|incorporadora|telecomunicacoes|"
    r"tecnologia|equipamentos|rental)\b", re.I)
# "IMP." e "I/" na posicao da marca sao o prefixo de importado do Renavam.
NOT_A_BRAND = {"imp", "i", "imp."}
# Rotulos que antecedem nomes de partes na descricao: o trecho inteiro sai.
PARTY_RE = re.compile(
    r"\b(Exequentes?|Executad[oa]s?|Reclamantes?|Reclamad[oa]s?|Requerentes?|Requerid[oa]s?|"
    r"Embargantes?|Embargad[oa]s?|Agravantes?|Agravad[oa]s?|Apelantes?|Apelad[oa]s?|"
    r"Autor(?:a|es)?|R[ée]us?|Devedor(?:a|es)?|Credor(?:a|es)?|Deposit[aá]ri[oa]s?|Fiel deposit[aá]ri[oa]|"
    r"Partes?|Advogad[oa]s?|Ju[ií]z(?:a)?)\s*:\s*[^.;]+[.;]?", re.I)
# Identificadores do veiculo que a fonte publica em claro no texto.
RENAVAM_RE = re.compile(r"(renavam)\s*:?\s*(?:n[ºo°]?\.?\s*)?[\d.\-]{9,}", re.I)
CHASSI_RE = re.compile(r"(chassi)\s*:?\s*(?:n[ºo°]?\.?\s*)?[A-HJ-NPR-Z0-9]{17}\b", re.I)
# Mercosul (ABC1D23) ou antiga com hifen (ABC-1234); sem hifen so' depois de
# "placa", porque "UNO 1000" e "GOL 1000" tem o mesmo formato.
PLATE_RE = re.compile(r"\b[A-Z]{3}\s?-?\s?\d[A-Z]\d{2}\b|\b[A-Z]{3}-\d{4}\b|(?<=placa)\s*:?\s*[A-Z]{3}\s?-?\s?\d{4}\b", re.I)
# "(Ref.: 26919)" / "(ID.: 51690)" no fim do titulo: referencia interna da loja.
REF_RE = re.compile(r"\s*\(\s*(?:Ref|ID)\.?\s*:?\s*([\w\-/]+)\s*\)\s*", re.I)
YEARS_RE = re.compile(r"\b((?:19|20)\d{2})\s*/\s*((?:19|20)\d{2})\b")

UF_BY_NAME = {
    "acre": "AC", "alagoas": "AL", "amapa": "AP", "amazonas": "AM", "bahia": "BA", "ceara": "CE",
    "distrito federal": "DF", "espirito santo": "ES", "goias": "GO", "maranhao": "MA",
    "mato grosso": "MT", "mato grosso do sul": "MS", "minas gerais": "MG", "para": "PA",
    "paraiba": "PB", "parana": "PR", "pernambuco": "PE", "piaui": "PI", "rio de janeiro": "RJ",
    "rio grande do norte": "RN", "rio grande do sul": "RS", "rondonia": "RO", "roraima": "RR",
    "santa catarina": "SC", "sao paulo": "SP", "sergipe": "SE", "tocantins": "TO",
}


def _retryable(exc: BaseException) -> bool:
    """404 e' "pagina alem do total", nao vale repetir; 429/5xx e rede valem."""
    if isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout)):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (429, 500, 502, 503, 504)


def slugify(text: str | None) -> str:
    """"FIAT STRADA, 2012/2012, (Ref.: 26919)" -> "fiat-strada-2012-2012-ref-26919",
    igual ao slug que o site poe na URL da oferta."""
    t = unidecode(text or "").lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


class SuperbidScraper(BaseScraper):
    display_name = "Superbid"
    default_config = {
        "categorias": ["carros-motos", "caminhoes-onibus", "maquinas-pesadas-agricolas"],
        "page_size": 200,
        "max_pages": 2,
        "order_by": "endDate:asc",
        "include_parts": False,
        "fetch_events": False,
        "events_pages": 2,
        "fetch_details": False,
    }

    @property
    def default_base_url(self) -> str:
        return "https://www.superbid.net"

    def _flag(self, key: str, default: bool) -> bool:
        return str(self.cfg(key, default)).lower() in ("1", "true", "yes")

    # ── rotas ────────────────────────────────────────────────────────

    def offer_url(self, title: str | None, offer_id: Any) -> str:
        slug = slugify(title)
        return f"{self.base_url}/oferta/{slug}-{offer_id}" if slug else f"{self.base_url}/oferta/{offer_id}"

    def event_url(self, desc: str | None, event_id: Any) -> str:
        slug = slugify(desc)
        return f"{self.base_url}/evento/{slug}-{event_id}" if slug else f"{self.base_url}/evento/{event_id}"

    def category_entries(self) -> list[dict[str, str]]:
        """`categorias` aceita "carros-motos", "carros-motos/motos", uma URL
        completa ou {"url": ..., "filter": ..., "order_by": ...}."""
        out: list[dict[str, str]] = []
        for entry in self.cfg("categorias") or self.default_config["categorias"]:
            if entry is None:
                continue
            if isinstance(entry, dict):
                url, flt, order = entry.get("url") or entry.get("urlSeo") or "", entry.get("filter") or "", entry.get("order_by") or ""
            else:
                url, flt, order = str(entry), "", ""
            url = url.strip()
            if not url:
                continue
            if not url.startswith("http"):
                url = f"{self.base_url}/categorias/{url.strip('/')}"
            label = url.split("/categorias/", 1)[-1] if "/categorias/" in url else url
            if flt:
                label += f" [{flt}]"
            out.append({"url": url, "filter": flt, "order_by": order or str(self.cfg("order_by", "endDate:asc")), "label": label})
        return out

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=30),
           retry=retry_if_exception(_retryable), reraise=True)
    async def offers_page(self, entry: dict[str, str], page: int, page_size: int) -> Any:
        params = {
            "locale": "pt_BR", "portalId": PORTAL_IDS, "requestOrigin": "marketplace",
            "timeZoneId": "America/Sao_Paulo",
            "preOrderBy": "orderByFirstOpenedOffersAndSecondHasPhoto",
            "filter": entry.get("filter") or "", "orderBy": entry.get("order_by") or "endDate:asc",
            "pageNumber": page, "pageSize": page_size, "searchType": "opened", "urlSeo": entry["url"],
        }
        return await self.fetch_json(f"{OFFER_QUERY}/seo/offers/", params=params, headers=API_HEADERS)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=30),
           retry=retry_if_exception(_retryable), reraise=True)
    async def events_page(self, page: int, page_size: int = 50) -> Any:
        params = {
            "portalId": PORTAL_IDS, "locale": "pt_BR", "timeZoneId": "America/Sao_Paulo",
            "filter": "modalityId:[1,4,5,7]", "pageNumber": page, "pageSize": page_size, "byPage": "marketPlacePage",
        }
        return await self.fetch_json(f"{EVENT_QUERY}/events/v2/", params=params, headers=API_HEADERS)

    # ── coleta ───────────────────────────────────────────────────────

    async def scrape(self) -> list[ScrapedItem]:
        events: dict[str, dict[str, Any]] = {}
        if self._flag("fetch_events", False):
            events = await self.load_events()
        items: list[ScrapedItem] = []
        for entry in self.category_entries():
            items.extend(await self.scrape_category(entry, events))
        return items

    async def load_events(self) -> dict[str, dict[str, Any]]:
        """Agenda indexada por id de evento (e por id de cada praca, que e' o
        `auction.id` que a oferta carrega)."""
        events: dict[str, dict[str, Any]] = {}
        pages = int(self.cfg("events_pages", 2) or 0)
        for page in range(1, pages + 1):
            try:
                await self.delay()
                data = await self.events_page(page)
            except Exception as exc:
                self.stats.errors += 1
                logger.warning("[Superbid] agenda pagina %d falhou: %s", page, exc)
                break
            self.stats.pages += 1
            got = self.events_from_json(data)
            events.update(got)
            rows = data.get("events") if isinstance(data, dict) else None
            if not rows or len(rows) < 50:
                break
        logger.info("[Superbid] %d eventos na agenda", len({e.get("id") for e in events.values()}))
        return events

    async def scrape_category(self, entry: dict[str, str], events: dict[str, dict[str, Any]]) -> list[ScrapedItem]:
        items: list[ScrapedItem] = []
        label = entry["label"]
        page_size = max(1, int(self.cfg("page_size", 200) or 200))
        max_pages = int(self.cfg("max_pages", 2) or 1)
        page, seen, total = 1, 0, None
        while page <= max_pages:
            try:
                await self.delay()
                data = await self.offers_page(entry, page, page_size)
            except Exception as exc:
                self.stats.errors += 1
                self.stats.mark_partial(f"{label}: pagina {page} falhou: {exc}")
                break
            self.stats.pages += 1
            offers = data.get("offers") if isinstance(data, dict) else None
            if not isinstance(offers, list):
                self.stats.errors += 1
                self.stats.mark_partial(f"{label}: pagina {page} com resposta inesperada")
                break
            if isinstance(data.get("total"), int):
                total = data["total"]
            got = self.parse_offers(offers, events)
            items.extend(got)
            seen += len(offers)
            logger.debug("[Superbid] %s pagina %d: %d ofertas, %d aproveitadas", label, page, len(offers), len(got))
            if not offers or len(offers) < page_size or (total is not None and seen >= total):
                break
            if page == max_pages:
                self.stats.mark_partial(f"{label}: parou em {max_pages} paginas ({seen} de {total} ofertas)")
            page += 1
        logger.info("[Superbid] %s: %d ofertas lidas de %s, %d itens", label, seen, total, len(items))
        return items

    # ── agenda ───────────────────────────────────────────────────────

    @staticmethod
    def events_from_json(data: Any) -> dict[str, dict[str, Any]]:
        rows = data.get("events") if isinstance(data, dict) else data
        out: dict[str, dict[str, Any]] = {}
        for e in rows or []:
            if not isinstance(e, dict) or e.get("id") is None:
                continue
            out[str(e["id"])] = e
            pipeline = e.get("eventPipeline") if isinstance(e.get("eventPipeline"), dict) else {}
            for stage in pipeline.get("stages") or []:
                if isinstance(stage, dict) and stage.get("eventId") is not None:
                    out.setdefault(str(stage["eventId"]), e)
        return out

    # ── ofertas ──────────────────────────────────────────────────────

    def parse_offers(self, offers: list[dict[str, Any]], events: dict[str, dict[str, Any]] | None = None) -> list[ScrapedItem]:
        out: list[ScrapedItem] = []
        for offer in offers or []:
            try:
                item = self._map_offer(offer, events or {})
                if item:
                    out.append(item)
            except Exception as exc:
                self.stats.errors += 1
                logger.debug("[Superbid] oferta ignorada: %s", exc)
        return out

    def _map_offer(self, o: dict[str, Any], events: dict[str, dict[str, Any]]) -> Optional[ScrapedItem]:
        oid = o.get("id")
        product = o.get("product") if isinstance(o.get("product"), dict) else {}
        raw_title = self.clean_text(product.get("shortDesc"))
        if not oid or not raw_title:
            return None
        ref = REF_RE.search(raw_title)
        title = self.mask_identifiers(self.clean_text(REF_RE.sub(" ", raw_title)).strip(" ,;-"))
        hint, sucata = self.category_hint(product)
        if hint is None:
            if not self._flag("include_parts", False):
                return None
            ptype = product.get("productType") if isinstance(product.get("productType"), dict) else {}
            hint = PRODUCT_TYPE_MAP.get(self._int(ptype.get("id")) or 0) or "diversos"

        auction = o.get("auction") if isinstance(o.get("auction"), dict) else {}
        event = events.get(str(auction.get("id"))) if auction.get("id") is not None else None
        store = o.get("store") if isinstance(o.get("store"), dict) else {}
        detail = o.get("offerDetail") if isinstance(o.get("offerDetail"), dict) else {}
        bids = self._int(o.get("totalBids")) or 0
        initial = self._num(detail.get("initialBidValue")) or self._num(detail.get("currentMinBid")) or self._num(o.get("price"))
        current = self._num(detail.get("currentMaxBid"))
        if bids > 0 and current:
            price, price_kind = current, "lance_atual"
        else:
            price, price_kind = initial, "lance_inicial"

        committer = self.institutional_name(o.get("seller"), store)
        judicial = self.safe_judicial(product.get("judicial"))
        submkts = self.sub_marketplaces(auction, event)
        is_judicial = bool(
            "judicial" in submkts or judicial.get("processNumber")
            or auction.get("judicialPraca") or auction.get("judicialControlNumber")
        )
        pipeline = auction.get("eventPipeline") if isinstance(auction.get("eventPipeline"), dict) else None
        if not pipeline and event and isinstance(event.get("eventPipeline"), dict):
            pipeline = event["eventPipeline"]
        sessions = self._sessions(auction, o, pipeline, initial)
        price_second = sessions[1].min_bid if len(sessions) > 1 and sessions[1].kind == "2a_praca" else None

        city, state, location_text = self.location(product.get("location"))
        images = self._images(product)
        custom = self.safe_custom(product.get("productCustomJson"))
        status_hint = self.status_hint(o)
        modality_desc = self.clean_text(auction.get("modalityDesc")) or None
        auction_desc = self.clean_text(auction.get("desc")) or None
        increment = o.get("currentBidIncrement") if isinstance(o.get("currentBidIncrement"), dict) else {}
        commercial = o.get("commercialCondition") if isinstance(o.get("commercialCondition"), dict) else {}
        quantity = self._int(o.get("quantityInLot")) or 1
        # Sem `product.judicial.vara`, o nome do leilao costuma ser a propria vara
        vara = judicial.get("vara")
        if not vara and is_judicial and auction_desc and re.search(r"\bvara\b", unidecode(auction_desc).lower()):
            vara = auction_desc

        raw: dict[str, Any] = self.template_attrs(product.get("template"))
        raw.update({
            "lance_inicial": str(initial) if initial else None,
            "lance_atual": str(current) if bids > 0 and current else None,
            "incremento": str(self._num(increment.get("currentBidIncrement")) or "") or None,
            "n_lances": bids,
            "n_licitantes": self._int(o.get("totalBidders")),
            "visitas": self._int(o.get("visits")),
            "fotos": self._int(product.get("photoCount")),
            "quantidade": quantity if quantity > 1 else None,
            "loja": self.clean_text(store.get("name")) or None,
            "leiloeiro": self.clean_text(auction.get("auctioneer")) or None,
            "matricula_leiloeiro": self.clean_text(auction.get("registry")) or None,
            "comitente": committer,
            "sub_marketplace": ", ".join(submkts) if submkts else None,
            "modalidade": modality_desc,
            "praca": (self.clean_text(auction.get("judicialPracaDescription")) or None) if is_judicial else None,
            "processo": judicial.get("processNumber"),
            "processo_tipo": judicial.get("processType"),
            "vara": vara,
            "foro": judicial.get("foro"),
            "restricoes": self.reject_unknown(self.clean_text(custom.get("vehicleRestrictions"))) or None,
            "debitos_veiculo": str(self._num(custom.get("vehicleDebts")) or "") or None,
            "codigo_fipe": raw.get("codigo_fipe") or self.clean_text(custom.get("vehicleFipeCode")) or None,
            "comissao_pct": self._num(commercial.get("auctioneerCommissionPercent")),
            "categoria_fonte": self.source_category(product),
            "sucata": True if sucata else None,
            "origem": "judicial" if is_judicial else ("particular" if o.get("seller") and not committer else None),
            "ref_fonte": ref.group(1) if ref else None,
            "oferta_tipo_id": self._int(o.get("offerTypeId")),
        })
        raw = {k: v for k, v in raw.items() if v not in (None, "", [], {})}

        desc_parts = [title + "."]
        offer_desc = o.get("offerDescription") if isinstance(o.get("offerDescription"), dict) else {}
        text = self.description_text(product.get("detailedDescription") or offer_desc.get("offerDescription"))
        if text and unidecode(text).lower().startswith(unidecode(raw_title).lower()):
            text = self.clean_text(text[len(raw_title):]).lstrip(" .,;-:")  # a fonte repete o titulo no inicio
        if text and unidecode(text).lower() != unidecode(title).lower():
            desc_parts.append(text)
        if committer:
            desc_parts.append(f"Comitente: {committer}.")
        if raw.get("loja"):
            desc_parts.append(f"Loja: {raw['loja']}.")
        if auction_desc:
            desc_parts.append(f"Leilão: {auction_desc}.")
        if modality_desc:
            desc_parts.append(f"Modalidade: {modality_desc}.")
        if is_judicial and raw.get("praca"):
            desc_parts.append(f"Praça: {raw['praca']}.")
        if raw.get("processo"):
            desc_parts.append(f"Processo: {raw['processo']}.")
        if sucata:
            desc_parts.append("Lote de sucata.")

        auction_obj = ScrapedAuction(
            external_id=str(auction.get("id") or f"lot-{oid}"),
            title=auction_desc or raw.get("loja") or f"Leilão {auction.get('id') or oid}",
            # O leiloeiro oficial (pessoa com matricula na junta) responde pelo
            # leilao; a loja (casa de leilao) fica em `raw.loja`.
            auctioneer_name=raw.get("leiloeiro") or raw.get("loja"),
            auctioneer_registration=raw.get("matricula_leiloeiro"),
            committer_name=committer,
            modality="online",  # a plataforma e' online mesmo quando ha' pregoeiro (`crier`)
            auction_type="judicial" if is_judicial else "extrajudicial",
            official_url=self.event_url(auction_desc, auction["id"]) if auction.get("id") else None,
            sessions=sessions,
        )
        return ScrapedItem(
            external_id=str(oid),
            title=title,
            official_url=self.offer_url(raw_title, oid),
            price=price,
            price_kind=price_kind,
            price_second=price_second,
            lot_number=str(o["lotNumber"]) if o.get("lotNumber") not in (None, "") else None,
            city=city,
            state=state,
            location_text=location_text,
            image_url=images[0] if images else None,
            images=images[:12],
            description=" ".join(desc_parts)[:4000],
            raw_attributes=raw,
            category_hint=hint,
            status_hint=status_hint,
            auction=auction_obj,
            raw_payload=json.dumps(self._compact(o, committer), ensure_ascii=False),
        )

    # ── pedacos da oferta ────────────────────────────────────────────

    @staticmethod
    def source_category(product: dict[str, Any]) -> Optional[str]:
        sub = product.get("subCategory") if isinstance(product.get("subCategory"), dict) else {}
        cat = sub.get("category") if isinstance(sub.get("category"), dict) else {}
        parts = [BaseScraper.clean_text(cat.get("description")), BaseScraper.clean_text(sub.get("description"))]
        return " / ".join(p for p in parts if p) or None

    @classmethod
    def category_hint(cls, product: dict[str, Any]) -> tuple[Optional[str], bool]:
        """(slug, e' sucata). Slug None = peca/consorcio, que nao e' um bem."""
        sub = product.get("subCategory") if isinstance(product.get("subCategory"), dict) else {}
        cat = sub.get("category") if isinstance(sub.get("category"), dict) else {}
        cat_n = unidecode(str(cat.get("description") or "")).lower().strip()
        sub_n = unidecode(str(sub.get("description") or "")).lower().strip()
        if SKIP_CATEGORY_RE.search(cat_n) or SKIP_CATEGORY_RE.search(sub_n):
            return None, False
        sucata = bool(SUCATA_RE.search(sub_n) or SUCATA_RE.search(cat_n))
        if sucata and cat_n in ("carros", "motos", "caminhoes", "onibus", "vans", "impl. rod. e carrocerias"):
            return "outros-veiculos", True
        hint = SUBCATEGORY_MAP.get(sub_n) or CATEGORY_MAP.get(cat_n)
        if not hint:
            ptype = product.get("productType") if isinstance(product.get("productType"), dict) else {}
            hint = PRODUCT_TYPE_MAP.get(cls._int(ptype.get("id")) or 0)
        return hint, sucata

    @staticmethod
    def sub_marketplaces(auction: dict[str, Any], event: dict[str, Any] | None) -> list[str]:
        rows = auction.get("subMarketplaces") or (event or {}).get("subMarketplaces") or []
        out: list[str] = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            d = BaseScraper.clean_text(r.get("subMarketplaceDesc") or r.get("desc")).lower()
            if d and d not in out:
                out.append(d)
        return out

    @classmethod
    def institutional_name(cls, seller: Any, store: dict[str, Any] | None = None) -> Optional[str]:
        """Nome do comitente so' quando e' instituicao (RN-009): cadastro de
        empresa (`company[].fantasyName`), `courtId` (varas e tribunais), o
        nome da loja dentro do nome do vendedor (revendedor que vende na
        propria loja) ou, sem `company`, o vocabulario de `INSTITUTION_RE`."""
        if not isinstance(seller, dict):
            return None
        name = cls.clean_text(seller.get("name"))
        if not name:
            return None
        norm = unidecode(name).lower()
        if seller.get("courtId"):
            return name
        company = seller.get("company") if isinstance(seller.get("company"), list) else []
        if any(isinstance(c, dict) and cls.clean_text(c.get("fantasyName")) for c in company):
            return name
        store_name = unidecode(cls.clean_text((store or {}).get("name"))).lower()
        if store_name and len(store_name) >= 4 and store_name in norm:
            return name
        if not company and (INSTITUTION_RE.search(norm) or "&" in name):
            return name
        return None

    @staticmethod
    def safe_judicial(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        out = {}
        for k in JUDICIAL_SAFE_KEYS:
            v = BaseScraper.clean_text(value.get(k)) if value.get(k) is not None else ""
            if v:
                out[k] = v
        return out

    @staticmethod
    def safe_custom(value: Any) -> dict[str, Any]:
        """`productCustomJson` e' uma string JSON com `vehicleOwner` (nome do
        dono): esse campo nao sai daqui em hipotese alguma."""
        data: Any = value
        if isinstance(value, str):
            try:
                data = json.loads(value) if value.strip() else {}
            except ValueError:
                return {}
        if not isinstance(data, dict):
            return {}
        return {k: v for k, v in data.items() if k != "vehicleOwner" and v not in (None, "")}

    @classmethod
    def template_attrs(cls, template: Any) -> dict[str, Any]:
        """`template.groups[].properties[]` -> chaves do motor. Placa, numero
        de motor, CEP de origem e o checklist de avarias da carroceria ficam
        de fora: ou identificam o bem/dono, ou nao cabem na ficha."""
        out: dict[str, Any] = {}
        groups = template.get("groups") if isinstance(template, dict) else None
        for g in groups or []:
            for p in (g.get("properties") or []) if isinstance(g, dict) else []:
                if not isinstance(p, dict):
                    continue
                key = TEMPLATE_MAP.get(unidecode(str(p.get("id") or "")).lower())
                value = cls.clean_text(str(p.get("value"))) if p.get("value") not in (None, "") else ""
                if not key or not value or key in out:
                    continue
                if key == "ano_fabricacao":
                    m = YEARS_RE.search(value)  # "ano" pode vir "2012/2013"
                    if m:
                        out["ano_fabricacao"] = int(m.group(1))
                        out.setdefault("ano_modelo", int(m.group(2)))
                        continue
                if key in INT_KEYS:
                    n = cls._int(value)
                    if n and n > 0:
                        out[key] = n
                    continue
                if key == "combustivel":
                    fuel = FUEL_MAP.get(unidecode(value).lower().replace(" ", ""))
                    out[key] = fuel or unidecode(value).lower()
                    continue
                if key == "valor_fipe":
                    n = cls._num(value) or cls.parse_brl(value)
                    if n:
                        out[key] = str(n)
                    continue
                if key in ("marca", "modelo", "cor"):
                    v = cls.reject_unknown(value)
                    if v and not (key == "marca" and unidecode(v).lower().strip(" ./") in NOT_A_BRAND):
                        out[key] = v.title()
                    continue
                out[key] = value[:120]
        return out

    def location(self, loc: Any) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """`location.city` vem "Jaguapita - PR" (as vezes so' a cidade) e
        `state` por extenso."""
        if not isinstance(loc, dict):
            return None, None, None
        text = self.clean_text(loc.get("city"))
        city, uf = self.parse_city_state(text) if text else (None, None)
        if not uf:
            uf = UF_BY_NAME.get(unidecode(self.clean_text(loc.get("state"))).lower())
        city = self.reject_unknown(city)
        return city, uf, text or None

    def _images(self, product: dict[str, Any]) -> list[str]:
        out: list[str] = []
        for g in product.get("galleryJson") or []:
            if not isinstance(g, dict) or (g.get("type") and g.get("type") != "photo"):
                continue
            u = self.reject_placeholder(g.get("link") or g.get("thumbnailUrl"))
            if u and u not in out:
                out.append(u)
        thumb = self.reject_placeholder(product.get("thumbnailUrl"))
        if not out and thumb:
            out.append(thumb)
        return out

    @staticmethod
    def status_hint(o: dict[str, Any]) -> str:
        st = o.get("offerStatus") if isinstance(o.get("offerStatus"), dict) else {}
        if st.get("removed"):
            return "withdrawn"
        if st.get("sold"):
            return "sold"
        if st.get("closed") or st.get("closedToBids"):
            return "closed"
        if st.get("giveYourBid") or st.get("available") or st.get("makeYourProposal"):
            return "open"
        try:
            return STATUS_ID_MAP.get(int(o.get("statusId")), "open")
        except (TypeError, ValueError):
            return "open"

    def _sessions(self, auction: dict[str, Any], o: dict[str, Any], pipeline: dict[str, Any] | None,
                  initial: Optional[Decimal]) -> list[ScrapedSession]:
        stages = [s for s in ((pipeline or {}).get("stages") or []) if isinstance(s, dict)]
        if len(stages) >= 2:
            # Duas pracas; o sistema modela 1a e 2a, entao uma terceira etapa
            # (rara) fica de fora em vez de sobrescrever a segunda.
            return [
                ScrapedSession(kind="1a_praca" if i == 0 else "2a_praca",
                               starts_at=self.parse_datetime_br(s.get("beginDate")),
                               ends_at=self.parse_datetime_br(s.get("endDate")),
                               min_bid=self._num(s.get("initialBidValue")))
                for i, s in enumerate(stages[:2])
            ]
        kind = {1: "1a_praca", 2: "2a_praca"}.get(self._int(auction.get("judicialPraca")) or 0, "unica")
        return [ScrapedSession(
            kind=kind,
            starts_at=self.parse_datetime_br(auction.get("beginDate")),
            ends_at=self.parse_datetime_br(o.get("endDate") or auction.get("endDate")),
            min_bid=initial,
        )]

    @classmethod
    def description_text(cls, src: Any) -> Optional[str]:
        """HTML da descricao -> texto limpo, sem partes do processo nem
        identificadores em claro (RN-009), ate 3.000 caracteres."""
        if not src or not isinstance(src, str):
            return None
        t = re.sub(r"<(?:br|/p|/li|/div|/h\d|/tr)\s*/?>", " . ", src, flags=re.I)
        t = html.unescape(re.sub(r"<[^>]+>", " ", t))
        t = cls.clean_text(t)
        t = re.sub(r"(?:\s*\.\s*){2,}", ". ", t)
        t = re.sub(r"\s+([,.;:!?)])", r"\1", t).strip(" .")
        if not t:
            return None
        t = cls.clean_text(PARTY_RE.sub("", t))
        t = cls.mask_identifiers(t)
        return t[:3000] or None

    @staticmethod
    def mask_identifiers(text: str) -> str:
        t = RENAVAM_RE.sub(r"\1 (omitido)", text)
        t = CHASSI_RE.sub(r"\1 (omitido)", t)
        return PLATE_RE.sub(lambda m: re.sub(r"[A-Za-z0-9]", "*", m.group(0)), t)

    def _compact(self, o: dict[str, Any], committer: Optional[str]) -> dict[str, Any]:
        """A oferta tem ~40 chaves, textos de 5 KB e dados pessoais. Para
        `raw_items` fica o que identifica o lote, sem nada de pessoa."""
        drop = {"offerDescription", "stores", "installmentPaymentTerms", "systemMetric", "isFavorite",
                "isShopping", "shoppingOfferType", "winnerBid", "seller", "manager", "groupOffer",
                "currentTimestamp", "indexationDate"}
        out = {k: v for k, v in o.items() if k not in drop}
        seller = o.get("seller") if isinstance(o.get("seller"), dict) else {}
        out["seller"] = {"id": seller.get("id"), "name": committer} if committer else ({"pessoa_fisica": True} if seller else None)
        product = dict(o.get("product") or {}) if isinstance(o.get("product"), dict) else {}
        product.pop("detailedDescription", None)
        product["productCustomJson"] = self.safe_custom(product.get("productCustomJson"))
        product["judicial"] = self.safe_judicial(product.get("judicial"))
        for key in ("productType", "subCategory"):
            product[key] = self._strip_translation(product.get(key))
        out["product"] = product
        auction = dict(o.get("auction") or {}) if isinstance(o.get("auction"), dict) else {}
        auction.pop("internalParameters", None)
        auction.pop("address", None)
        out["auction"] = auction
        return out

    @classmethod
    def _strip_translation(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {k: cls._strip_translation(v) for k, v in value.items() if k != "translation"}
        if isinstance(value, list):
            return [cls._strip_translation(v) for v in value]
        return value

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _num(value: Any) -> Optional[Decimal]:
        """Numeros da API sao float/int (8958.3); string vem com ponto decimal."""
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
            return int(str(value).strip().split(".")[0].replace(",", ""))
        except ValueError:
            return None
