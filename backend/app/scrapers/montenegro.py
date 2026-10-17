"""Montenegro Leilões (montenegroleiloes.com.br, Fortaleza/CE) — leiloeiros
oficiais com pregoes judiciais de veiculos (TJCE, TRT 7ª Regiao), prefeituras
do interior do Ceara e um ou outro particular. O site e' uma SPA (Inertia/Vue)
que le os dados de uma API JSON publica no proprio dominio:

  GET /api-publica/stale/dados-home-lotes/veicular/categorias/veiculos?page=N
      lotes de veiculos, 12 por pagina, `[]` quando acaba. Cada lote ja' vem
      com o pregao embutido (`leilao`: titulo, data, comitente, tipo), o
      status, as imagens e a flag `vistoria_veicular.sucata`.
  GET /api-publica/stale/dados-home/veicular/categorias/veiculos?page=1
      agenda dos pregoes que tem veiculos (1 requisicao; `lotes_count` conta
      todas as categorias do pregao, nao so' veiculos).
  GET /leiloes/{id_leilao}/lotes/{id}
      pagina do lote: o estado inicial esta' em `#app[data-page]` (JSON
      escapado), com `props.loteInit.vistoria_veicular` (marca, modelo, anos,
      km, cor, combustivel, placa ja' mascarada) e a `descricao` HTML (vara,
      processo, localizacao, despesas que se somam ao arremate).

Sem categoria (`/api-publica/stale/dados-home-lotes`) a API traz tambem
imoveis e bens diversos. Limite informado: 120 requisicoes/min. Imagens e
documentos em `/midia/{id_arquivo}`.

Dados pessoais (RN-009): placa e chassi ja' chegam mascarados pela fonte; o
historico de lances do detalhe traz o apelido dos licitantes e NAO e' copiado
(fica so' a contagem). Comitentes sao orgaos (varas, tribunais, prefeituras);
"Particular (N)" e' um placeholder da fonte para pessoa fisica e vira origem
`particular`, sem nome. Rotulos de partes do processo na descricao
(exequente, executado...) sao suprimidos.

Cloudflare na frente do site (17/10/2026): o httpx com o contexto TLS padrao
leva 403 "Sorry, you have been blocked" em todas as rotas (menos robots.txt)
enquanto urllib, curl e o proprio httpx com ClientHello diferente passam —
a Cloudflare pontua o cliente pela impressao digital TLS e pela coerencia
dos cabecalhos (User-Agent de Chrome sem `sec-ch-ua`/`sec-fetch-*` e' sinal
de bot). Por isso este coletor abre o proprio AsyncClient com TLS 1.3 e
manda os cabecalhos que o Chrome manda, le a API com a mesma politica de
retry do `fetch` e passa pela home antes da API (fluxo da SPA, cookie
`__cf_bm`). Atrasos conservadores entre requisicoes importam aqui.

robots.txt: so' `/cadastro/` proibido. Termos de uso (PDF) sem clausula
sobre coleta automatizada. Verificado em 17/10/2026.
"""
from __future__ import annotations

import html
import json
import logging
import re
import ssl
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

import certifi
import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from unidecode import unidecode

from app.scrapers.base import BaseScraper, ScrapedAuction, ScrapedItem, ScrapedSession

logger = logging.getLogger("zleilao.scraper.montenegro")

# `status_lote.identificador` (constantes do bundle da SPA, 17/10/2026). O
# identificador vem antes do texto porque "Nao Vendido" contem "vendido".
STATUS_MAP = {
    "ABERTO": "open", "EM_PREGAO": "open", "DOULHE_UMA": "open", "DOULHE_DUAS": "open",
    "CONDICIONAL": "open", "CONDICIONAL_REABERTA": "open",
    "DIVULGACAO": "soon",
    "VENDIDO": "sold",
    "NAO_VENDIDO": "closed", "ENCERRADO": "closed",
    "RETIRADO": "withdrawn", "CANCELADO": "withdrawn", "SUSPENSO": "withdrawn",
}

# `vistoria_veicular.tipo_bem` (subcategorias vistas na home) -> slug. E' so'
# dica: o titulo decide a categoria.
TIPO_BEM_MAP = {
    "moto": "motos", "motocicleta": "motos", "motoneta": "motos", "ciclomotor": "motos",
    "carro": "carros", "automovel": "carros",
    "caminhonete": "utilitarios", "camioneta": "utilitarios", "utilitario": "utilitarios", "van": "utilitarios",
    "caminhao": "caminhoes", "reboque": "caminhoes", "semirreboque": "caminhoes", "semi-reboque": "caminhoes",
    "onibus": "onibus", "onibus-e-microonibus": "onibus", "microonibus": "onibus", "micro-onibus": "onibus",
    "trator": "maquinas-equipamentos", "maquina": "maquinas-equipamentos",
}

FUEL_MAP = {
    "gasolina": "gasolina", "alcool": "etanol", "etanol": "etanol", "flex": "flex",
    "gasolina/alcool": "flex", "gas/alc": "flex", "alcool/gasolina": "flex",
    "diesel": "diesel", "gnv": "gnv", "eletrico": "eletrico", "hibrido": "hibrido",
}

# Judicial quando o comitente e' um orgao do Judiciario. Prefeituras e
# autarquias sao leiloes administrativos, que o projeto trata como
# extrajudiciais (o enum e' judicial | extrajudicial).
JUDICIAL_RE = re.compile(
    r"\b(VARA|TRIBUNAL|TRT|TRF|TJ[A-Z]{0,2}|COMARCA|JUSTI[CÇ]A|JU[IÍ]ZO|JUIZADO)\b", re.I)
# "COMARCA DE FORTALEZA-CE", "PREFEITURA MUNICIPAL DE IPUEIRAS/CE"
COMMITTER_PLACE_RE = re.compile(
    r"(?:COMARCA|MUNIC[IÍ]PIO|PREFEITURA(?:\s+MUNICIPAL)?|C[AÂ]MARA\s+MUNICIPAL)\s+DE\s+"
    r"([A-ZÀ-Ü][A-ZÀ-Üa-zà-ü'\. ]+?)\s*[-/]\s*([A-Z]{2})\b")
# "TRIBUNAL REGIONAL DO TRABALHO DA 7ª REGIÃO (CE)": so' a UF
COMMITTER_STATE_RE = re.compile(r"\(([A-Z]{2})\)\s*$")
# Sem ponto nem virgula na classe: "Esplanada do Castelão. Fortaleza/CE" tem
# que render so' "Fortaleza".
CITY_STATE_RE = re.compile(r"([A-Za-zÀ-ÿ' ]{3,}?)\s*/\s*([A-Z]{2})\b")
CNJ_RE = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")
PROCESSO_RE = re.compile(r"Processo:?\s*(?:n[ºo°]?\.?\s*)?:?\s*([\d][\d\.\-]{12,30})", re.I)
# Rotulos que antecedem nomes de partes: o trecho inteiro sai (RN-009).
PARTY_RE = re.compile(
    r"\b(Exequentes?|Executad[oa]s?|Reclamantes?|Reclamad[oa]s?|Requerentes?|Requerid[oa]s?|"
    r"Embargantes?|Embargad[oa]s?|Agravantes?|Agravad[oa]s?|Apelantes?|Apelad[oa]s?|"
    r"Autor(?:a|es)?|R[ée]us?|Devedor(?:a|es)?|Credor(?:a|es)?|Partes?)\s*:\s*[^.;]+[.;]?", re.I)
DATA_PAGE_RE = re.compile(r'<div[^>]+id="app"[^>]+data-page="([^"]*)"', re.S)
# A fonte as vezes repete o modelo no titulo: "FIAT UNO WAY 1 0 FIAT UNO WAY 1 0 2011/2012"
REPEAT_RE = re.compile(r"^(.{4,}?)\s+\1(?=\s|$)")

PAGE_SIZE = 12  # lotes por pagina da API em 17/10/2026
ONLINE_LOCALIDADE_ID = "7"  # `localidade` {id: 7, nome: "ONLINE"} no detalhe (17/10/2026)

# Cabecalhos que o Chrome 124 manda junto do User-Agent do `BaseScraper`.
CHROME_HEADERS = {
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-User": "?1",
}
# A SPA chama a API por fetch() a partir da pagina: requisicao CORS same-origin.
API_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
}


class MontenegroScraper(BaseScraper):
    display_name = "Montenegro Leilões"
    default_config = {
        "tipo": "veicular",
        "categoria": "veiculos",
        "max_pages": 20,
        "fetch_auctions": True,
        "fetch_details": True,
        "max_details_per_run": 60,
    }

    @property
    def default_base_url(self) -> str:
        return "https://montenegroleiloes.com.br"

    # ── cliente ──────────────────────────────────────────────────────

    def headers(self) -> dict[str, str]:
        h = super().headers()
        if not self.config.get("headers"):
            h.update(CHROME_HEADERS)
        return h

    async def __aenter__(self):
        verify: Any = str(self.cfg("verify_ssl", True)).lower() not in ("0", "false", "no")
        if verify:
            # So' TLS 1.3 muda o ClientHello em relacao ao padrao do httpx
            # (que a Cloudflare bloqueia); o site aceita 1.3 (17/10/2026).
            ctx = ssl.create_default_context(cafile=certifi.where())
            ctx.minimum_version = ssl.TLSVersion.TLSv1_3
            verify = ctx
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(40.0),
            headers=self.headers(),
            follow_redirects=True,
            verify=verify,
        )
        return self

    # ── rotas ────────────────────────────────────────────────────────

    def _api_path(self, recurso: str) -> str:
        """`categoria` vazia na config pede o catalogo inteiro (imoveis e bens
        diversos inclusive); ausente, vale o default de veiculos."""
        tipo = str(self.cfg("tipo", "veicular") or "veicular").strip("/")
        categoria = str(self.cfg("categoria", "veiculos") or "").strip("/")
        if not categoria:
            return f"/api-publica/stale/{recurso}"
        return f"/api-publica/stale/{recurso}/{tipo}/categorias/{categoria}"

    def lot_url(self, auction_id: Any, lot_id: Any) -> str:
        return f"{self.base_url}/leiloes/{auction_id}/lotes/{lot_id}"

    def media_url(self, file_id: str) -> str:
        return f"{self.base_url}/midia/{file_id}"

    # ── coleta ───────────────────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.ReadTimeout)),
        reraise=True,
    )
    async def api_json(self, path: str, page: int) -> Any:
        """`fetch_json` da base nao tem retry; aqui o 403 passageiro da
        Cloudflare e o 429 do limite de 120/min merecem nova tentativa."""
        headers = dict(API_HEADERS, Referer=self.base_url + "/")
        return await self.fetch_json(self.abs_url(path), params={"page": page}, headers=headers)

    async def scrape(self) -> list[ScrapedItem]:
        # A SPA carrega a API depois do HTML; chegar na API sem ter passado
        # pela home e' o que menos parece navegador para a Cloudflare.
        try:
            await self.fetch(self.base_url + "/")
        except Exception as exc:
            logger.debug("[Montenegro] home nao carregou (%s); segue para a API", exc)

        agenda: dict[str, dict[str, Any]] = {}
        if str(self.cfg("fetch_auctions", True)).lower() in ("1", "true", "yes"):
            try:
                await self.delay()
                data = await self.api_json(self._api_path("dados-home"), 1)
                self.stats.pages += 1
                agenda = self.auctions_from_json(data)
                logger.info("[Montenegro] %d pregoes com veiculos em cartaz", len(agenda))
            except Exception as exc:
                self.stats.errors += 1
                logger.warning("[Montenegro] agenda falhou: %s", exc)

        items: list[ScrapedItem] = []
        max_pages = int(self.cfg("max_pages", 20))
        path = self._api_path("dados-home-lotes")
        page = 1
        while page <= max_pages:
            try:
                await self.delay()
                data = await self.api_json(path, page)
            except Exception as exc:
                self.stats.errors += 1
                self.stats.mark_partial(f"pagina {page} de lotes falhou: {exc}")
                break
            self.stats.pages += 1
            if not isinstance(data, list):
                # Rota errada ou erro do servidor vem como {"message": "Server Error"}
                self.stats.errors += 1
                self.stats.mark_partial(f"pagina {page}: resposta inesperada da API")
                break
            if not data:
                break  # `[]` e' o fim do catalogo
            got = self.parse_lots(data, agenda)
            items.extend(got)
            logger.debug("[Montenegro] pagina %d: %d lotes", page, len(got))
            if page == max_pages:
                self.stats.mark_partial(f"parou em {max_pages} paginas; pode haver mais lotes")
            page += 1

        if self.fetch_details and items:
            fetched = 0
            for it in items:
                # Lote encerrado nao muda mais: o detalhe so' vale para quem esta' em disputa.
                if it.status_hint not in ("open", "soon"):
                    continue
                if fetched >= self.max_details:
                    self.stats.notes.append(f"limite de {self.max_details} detalhes atingido")
                    break
                fetched += 1
                try:
                    await self.delay()
                    nav = {"Referer": self.base_url + "/", "Sec-Fetch-Site": "same-origin"}
                    page_data = self.parse_data_page(await self.fetch(it.official_url, headers=nav))
                    self.enrich_from_detail(it, page_data)
                    self.stats.details += 1
                except Exception as exc:
                    self.stats.errors += 1
                    logger.warning("[Montenegro] detalhe do lote %s falhou: %s", it.external_id, exc)
        return items

    # ── agenda ───────────────────────────────────────────────────────

    @staticmethod
    def auctions_from_json(data: Any) -> dict[str, dict[str, Any]]:
        """Indexa os pregoes por id. Serve de reserva quando o lote vem sem
        o objeto `leilao` embutido."""
        out: dict[str, dict[str, Any]] = {}
        for a in data or []:
            if isinstance(a, dict) and a.get("id") is not None:
                out[str(a["id"])] = a
        return out

    # ── listagem ─────────────────────────────────────────────────────

    def parse_lots(self, data: list[dict[str, Any]], agenda: dict[str, dict[str, Any]] | None = None) -> list[ScrapedItem]:
        out: list[ScrapedItem] = []
        for lot in data:
            try:
                item = self._map_lot(lot, agenda or {})
                if item:
                    out.append(item)
            except Exception as exc:
                self.stats.errors += 1
                logger.debug("[Montenegro] lote ignorado: %s", exc)
        return out

    def _map_lot(self, lot: dict[str, Any], agenda: dict[str, dict[str, Any]]) -> Optional[ScrapedItem]:
        lot_id = lot.get("id")
        title = self.clean_title(lot.get("titulo"))
        if not lot_id or not title:
            return None
        auction_id = str(lot.get("id_leilao") or "")
        leilao = lot.get("leilao") if isinstance(lot.get("leilao"), dict) else None
        leilao = leilao or agenda.get(auction_id) or {}
        if not auction_id:
            auction_id = str(leilao.get("id") or f"lot-{lot_id}")
        comitente = leilao.get("comitente") if isinstance(leilao.get("comitente"), dict) else {}
        committer = self.clean_text(comitente.get("nome_fantasia") or comitente.get("razao_social")) or None
        status = lot.get("status_lote") if isinstance(lot.get("status_lote"), dict) else {}
        vistoria = lot.get("vistoria_veicular") if isinstance(lot.get("vistoria_veicular"), dict) else {}
        sucata = str(vistoria.get("sucata") or "0") in ("1", "true", "True")

        inicial = self._num(lot.get("lance_inicial")) or self._num(lot.get("lance_minimo"))
        atual = self._num(lot.get("lanceAtual"))
        price, price_kind = inicial, "lance_inicial"
        if atual:
            price, price_kind = atual, "lance_atual"

        images = self._images(lot.get("imagens_lote"))
        status_hint = (STATUS_MAP.get(str(status.get("identificador") or "").upper())
                       or self.status_from_text(status.get("nome")) or "open")
        auction_type = "judicial" if JUDICIAL_RE.search(committer or "") else "extrajudicial"
        origem = "judicial" if auction_type == "judicial" else None
        if committer and re.match(r"^particular\b", unidecode(committer).lower()):
            # "Particular (108102)": pessoa fisica identificada so' pelo id interno
            origem, committer = "particular", None
        city, state = self.city_state_from_committer(committer)

        raw: dict[str, Any] = {
            "lance_inicial": str(inicial) if inicial else None,
            "lance_atual": str(atual) if atual else None,
            "incremento": str(self._num(lot.get("incremento")) or "") or None,
            "sequencia": lot.get("sequencia"),
            "comitente": committer,
            "tipo_leilao": self._int(leilao.get("tipo_leilao")),
            "comissao_pct": self._int(leilao.get("porcentagem_comissao")),
            "sucata": sucata,
            "origem": origem,
            "status_fonte": status.get("nome"),
            "venda_direta": True if str(leilao.get("venda_direta") or "0") == "1" else None,
        }
        raw = {k: v for k, v in raw.items() if v not in (None, "", [])}

        desc_parts = [title + "."]
        if committer:
            desc_parts.append(f"Comitente: {committer}.")
        if leilao.get("titulo"):
            desc_parts.append(f"Pregão: {self.clean_text(leilao['titulo'])}.")
        if sucata:
            desc_parts.append("Lote de sucata: arremate restrito a empresas habilitadas.")
        if status.get("nome"):
            desc_parts.append(f"Situação: {status['nome']}.")

        auction = ScrapedAuction(
            external_id=auction_id,
            title=self.clean_text(leilao.get("titulo")) or f"Leilão {auction_id}",
            auctioneer_name=self.display_name,
            committer_name=committer,
            modality=self._modality(leilao),
            auction_type=auction_type,
            official_url=f"{self.base_url}/leiloes/{auction_id}",
            sessions=self._sessions(leilao, lot, inicial),
        )
        return ScrapedItem(
            external_id=str(lot_id),
            title=title,
            official_url=self.lot_url(auction_id, lot_id),
            price=price,
            price_kind=price_kind,
            lot_number=str(lot["sequencia"]) if lot.get("sequencia") not in (None, "") else None,
            city=city,
            state=state,
            image_url=images[0] if images else None,
            images=images[:12],
            description=" ".join(desc_parts),
            raw_attributes=raw,
            category_hint="sucatas" if sucata else "veiculos",
            status_hint=status_hint,
            auction=auction,
            raw_payload=json.dumps(self._compact(lot), ensure_ascii=False),
        )

    def _sessions(self, leilao: dict[str, Any], lot: dict[str, Any], inicial: Optional[Decimal]) -> list[ScrapedSession]:
        p1 = self.parse_datetime_br(leilao.get("data_hora_inicio"))
        if str(leilao.get("dois_leiloes") or "0") == "1":
            p2 = self.parse_datetime_br(leilao.get("data_hora_inicio_segundo_leilao"))
            return [
                ScrapedSession(kind="1a_praca", starts_at=p1, min_bid=inicial),
                ScrapedSession(kind="2a_praca", starts_at=p2,
                               min_bid=self._num(lot.get("lance_inicial_segundo_leilao"))
                               or self._num(lot.get("lance_minimo_segundo_leilao"))),
            ]
        return [ScrapedSession(kind=self.session_kind(leilao.get("titulo")), starts_at=p1, min_bid=inicial)]

    @staticmethod
    def session_kind(title: str | None) -> str:
        """"(1ª Chamada)" no titulo do pregao e' a 1ª praca judicial; a 2ª
        chamada vem como outro pregao. Sem marcacao, sessao unica."""
        t = unidecode(title or "").lower()
        if re.search(r"\b1\s*[ao]?\s*(?:chamada|praca|leilao)", t):
            return "1a_praca"
        if re.search(r"\b2\s*[ao]?\s*(?:chamada|praca|leilao)", t):
            return "2a_praca"
        return "unica"

    @staticmethod
    def _modality(leilao: dict[str, Any]) -> Optional[str]:
        loc = leilao.get("localidade")
        nome = loc.get("nome") if isinstance(loc, dict) else None
        if nome:
            return "online" if unidecode(str(nome)).strip().lower() == "online" else None
        if str(leilao.get("id_localidade") or "") == ONLINE_LOCALIDADE_ID:
            return "online"
        return None

    def _images(self, entries: Any) -> list[str]:
        rows = [e for e in (entries or []) if isinstance(e, dict) and e.get("id_arquivo") and not e.get("inativado_em")]
        rows.sort(key=lambda e: self._int(e.get("sequencia")) or 0)
        out: list[str] = []
        for e in rows:
            u = self.media_url(str(e["id_arquivo"]))
            if u not in out:
                out.append(u)
        return out

    @staticmethod
    def _compact(lot: dict[str, Any]) -> dict[str, Any]:
        """O `leilao` embutido tem ~100 chaves (textos de pagamento, tempos de
        pregao...). Para `raw_items` basta o que identifica o pregao."""
        out = {k: v for k, v in lot.items() if k != "leilao"}
        leilao = lot.get("leilao") if isinstance(lot.get("leilao"), dict) else {}
        keep = ("id", "titulo", "tipo_leilao", "data_hora_inicio", "data_hora_inicio_segundo_leilao",
                "dois_leiloes", "id_localidade", "porcentagem_comissao", "venda_direta")
        out["leilao"] = {k: leilao.get(k) for k in keep if k in leilao}
        com = leilao.get("comitente") if isinstance(leilao.get("comitente"), dict) else {}
        if com:
            out["leilao"]["comitente"] = {"id": com.get("id"), "nome_fantasia": com.get("nome_fantasia")}
        st = leilao.get("status_leilao") if isinstance(leilao.get("status_leilao"), dict) else {}
        if st:
            out["leilao"]["status_leilao"] = {"nome": st.get("nome"), "identificador": st.get("identificador")}
        return out

    # ── detalhe ──────────────────────────────────────────────────────

    @staticmethod
    def parse_data_page(html_text: str) -> dict[str, Any]:
        m = DATA_PAGE_RE.search(html_text) or re.search(r'data-page="([^"]*)"', html_text)
        if not m:
            raise ValueError("data-page nao encontrado")
        return json.loads(html.unescape(m.group(1)))

    def enrich_from_detail(self, item: ScrapedItem, page: dict[str, Any]) -> ScrapedItem:
        props = page.get("props") if isinstance(page.get("props"), dict) else {}
        lote = props.get("loteInit") if isinstance(props.get("loteInit"), dict) else {}
        if not lote:
            raise ValueError("props.loteInit ausente")
        raw = item.raw_attributes

        vv = lote.get("vistoria_veicular") if isinstance(lote.get("vistoria_veicular"), dict) else {}
        for k, v in self.vehicle_attrs(vv).items():
            raw[k] = v
        sucata = str(vv.get("sucata") or "0") == "1"
        raw["sucata"] = sucata
        if sucata:
            item.category_hint = "sucatas"
        else:
            item.category_hint = TIPO_BEM_MAP.get(unidecode(str(vv.get("tipo_bem") or "")).lower().strip()) or "veiculos"

        blocks = self.text_blocks(lote.get("descricao"))
        if blocks:
            item.description = " ".join(blocks)[:4000]
            loc_block = next((b for b in blocks if re.match(r"localiza[cç][aã]o", unidecode(b).lower())), None)
            if loc_block:
                loc_text = re.sub(r"^\s*Localiza[cç][aã]o\s*:?\s*", "", loc_block, flags=re.I).strip(" .")
                item.location_text = loc_text[:200] or None
                found = CITY_STATE_RE.findall(loc_text)
                if found:
                    city, uf = found[-1]
                    city = self.reject_unknown(self.clean_text(city).title())
                    if city:
                        item.city, item.state = city, uf.upper()
            full = " ".join(blocks)
            m = CNJ_RE.search(full) or PROCESSO_RE.search(full)
            if m:
                raw["processo"] = m.group(1) if m.re is PROCESSO_RE else m.group(0)
            sit = next((b for b in blocks if re.match(r"situa[cç][aã]o\s*:", unidecode(b).lower())), None)
            if sit:
                raw["situacao_fonte"] = re.sub(r"^\s*Situa[cç][aã]o\s*:?\s*", "", sit, flags=re.I).strip(" .")[:120] or raw.get("situacao_fonte")

        # Lances: so' a contagem; o apelido de quem deu o lance fica de fora (RN-009)
        lances = lote.get("lances") if isinstance(lote.get("lances"), list) else []
        raw["n_lances"] = len(lances)
        inicial = self._num(lote.get("lance_inicial")) or self._num(lote.get("lance_minimo"))
        atual = self._num(lote.get("lanceAtual"))
        if inicial:
            raw["lance_inicial"] = str(inicial)
        if atual:
            raw["lance_atual"] = str(atual)
            item.price, item.price_kind = atual, "lance_atual"
        elif inicial:
            item.price, item.price_kind = inicial, "lance_inicial"

        taxas: dict[str, str] = {}
        for t in lote.get("taxas_lote") or []:
            if not isinstance(t, dict):
                continue
            titulo = self.clean_text((t.get("taxa") or {}).get("titulo") if isinstance(t.get("taxa"), dict) else None)
            valor = self._num(t.get("valor"))
            if titulo and valor:
                taxas[titulo.title()] = str(valor)
        if taxas:
            raw["taxas"] = taxas
        docs = [self.media_url(str(d["id_arquivo"])) for d in (lote.get("documentos_lote") or [])
                if isinstance(d, dict) and d.get("id_arquivo")]
        if docs:
            raw["edital_url"] = docs[0]
            raw["documentos"] = docs[:5]

        status = lote.get("status_lote") if isinstance(lote.get("status_lote"), dict) else {}
        if status.get("identificador"):
            item.status_hint = STATUS_MAP.get(str(status["identificador"]).upper()) or item.status_hint
            raw["status_fonte"] = status.get("nome") or raw.get("status_fonte")

        images = self._images(lote.get("imagens_lote"))
        if images and (not item.images or len(images) > len(item.images)):
            item.images, item.image_url = images[:12], images[0]

        leilao = lote.get("leilao") if isinstance(lote.get("leilao"), dict) else {}
        if item.auction and leilao:
            modality = self._modality(leilao)
            if modality:
                item.auction.modality = modality
            leiloeiro = leilao.get("leiloeiro") if isinstance(leilao.get("leiloeiro"), dict) else {}
            if leiloeiro.get("nome"):
                item.auction.auctioneer_name = self.clean_text(leiloeiro["nome"])
            if leiloeiro.get("matricula"):
                item.auction.auctioneer_registration = str(leiloeiro["matricula"])
        item.raw_attributes = {k: v for k, v in raw.items() if v not in (None, "", [], {})}
        return item

    def vehicle_attrs(self, vv: dict[str, Any]) -> dict[str, Any]:
        """`vistoria_veicular` do detalhe -> chaves que o motor deterministico
        ja' entende (marca, modelo, anos, km, cor, combustivel...)."""
        if not vv:
            return {}
        modelo = vv.get("modelo") if isinstance(vv.get("modelo"), dict) else {}
        marca = modelo.get("marca") if isinstance(modelo.get("marca"), dict) else {}
        placa = str(vv.get("placa") or "")
        fuel_src = self.clean_text(vv.get("combustivel")) or None
        fuel = FUEL_MAP.get(unidecode(fuel_src or "").lower()) if fuel_src else None
        comitente = vv.get("comitente") if isinstance(vv.get("comitente"), dict) else {}
        # A fonte escreve "-" quando nao sabe (marca da Dafra/TVS, por exemplo)
        raw: dict[str, Any] = {
            "marca": (self.reject_unknown(self.clean_text(marca.get("nome"))) or "").title() or None,
            "modelo": (self.reject_unknown(self.clean_text(modelo.get("nome"))) or "").title() or None,
            "ano_fabricacao": self._int(vv.get("ano_fabricacao")),
            "ano_modelo": self._int(vv.get("ano_modelo")),
            "km": self._int(vv.get("kilometragem")) or None,
            "cor": (self.reject_unknown(self.clean_text(vv.get("cor"))) or "").title() or None,
            "combustivel": fuel,
            "combustivel_fonte": fuel_src if fuel_src and fuel != unidecode(fuel_src).lower() else None,
            "funcionando": self._bool(vv.get("funcionando")),
            "chave_ignicao": self._bool(vv.get("chave_de_ignicao")),
            "tipo_bem": self.clean_text(vv.get("tipo_bem")) or None,
            "tipo_monta": self.reject_unknown(self.clean_text(vv.get("tipo_monta")) or None),
            "local_exposicao": self.clean_text(vv.get("local_de_exposicao"))[:200] or None,
            # So' a placa que a propria fonte ja' mascarou; em claro nao entra (RN-009)
            "placa_mascarada": placa if placa and "*" in placa else None,
            # A vara que remeteu o bem e' mais especifica que o tribunal do pregao
            "comitente": self.clean_text(comitente.get("nome_fantasia")) or None,
        }
        return {k: v for k, v in raw.items() if v not in (None, "")}

    @classmethod
    def text_blocks(cls, html_src: str | None) -> list[str]:
        """Paragrafos da descricao HTML como texto limpo, sem rotulos de
        partes do processo."""
        if not html_src:
            return []
        parts = re.split(r"<(?:/p|/li|/div|/h\d|br\s*/?|hr\s*/?)>", html_src, flags=re.I)
        out: list[str] = []
        for p in parts:
            # Tag inline some sem deixar espaco: o editor da fonte parte
            # numeros e palavras em <strong>/<span> adjacentes ("R$ 68" +
            # "0,00", "Fortaleza" + "/CE"). As demais viram espaco para nao
            # colar palavras; o espaco que sobra antes da pontuacao sai.
            p = re.sub(r"</?(?:span|strong|b|i|em|u|a|small|sup|sub|font|mark)\b[^>]*>", "", p, flags=re.I)
            text = cls.clean_text(html.unescape(re.sub(r"<[^>]+>", " ", p)))
            text = re.sub(r"\s+([,.;:!?)])", r"\1", text)
            text = re.sub(r"\(\s+", "(", text)
            if not text:
                continue
            if PARTY_RE.match(text):
                continue
            text = cls.clean_text(PARTY_RE.sub("", text))
            if text:
                out.append(text)
        return out

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def clean_title(text: str | None) -> str:
        t = BaseScraper.clean_text(text)
        return REPEAT_RE.sub(r"\1", t)

    @classmethod
    def city_state_from_committer(cls, committer: str | None) -> tuple[Optional[str], Optional[str]]:
        if not committer:
            return None, None
        m = COMMITTER_PLACE_RE.search(committer)
        if m:
            city = cls.reject_unknown(cls.clean_text(m.group(1)).title())
            return city, m.group(2).upper()
        m = COMMITTER_STATE_RE.search(committer)
        if m:
            return None, m.group(1)
        return None, None

    @staticmethod
    def _num(value: Any) -> Optional[Decimal]:
        """Valores da API vem como string decimal com ponto ("3000", "1552.5"),
        que `parse_brl` leria como milhar."""
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

    @staticmethod
    def _bool(value: Any) -> Optional[bool]:
        v = unidecode(str(value or "")).strip().lower()
        if v in ("sim", "s", "1", "true"):
            return True
        if v in ("nao", "n", "0", "false"):
            return False
        return None
