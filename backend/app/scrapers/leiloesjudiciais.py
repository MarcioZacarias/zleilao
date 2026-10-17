"""Leilões Judiciais (leiloesjudiciais.com.br) — portal que divulga e gere os
leilões judiciais de leiloeiros oficiais de todo o Brasil (varas estaduais,
federais e do trabalho). Os lances sao dados no site de cada leiloeiro; aqui
so' se divulga.

Nuxt 3 com SSR. A listagem (`/veiculos`, `/veiculos/carros`,
`/veiculos/estado/SP`, `/veiculos?ordenacao=min&valmin=5000&valmax=25000`)
vem renderizada no servidor com os cards `.base-card` e com o payload
`__NUXT_DATA__` (formato devalue), que carrega o JSON completo dos 42 lotes
da pagina: titulo, avaliacao, lance minimo da etapa atual, lance da 2a
praca, fechamento, cidade/UF, status, leiloeiro, subcategoria, fotos e
anexos. O parser le o payload e so' recorre aos cards se ele faltar.

As datas das pracas e a Vara (comitente) ficam no registro do leilao
(`dadosLeilao-{id}`), que vem no payload de `/leilao/{id}` junto com o JSON
de ate' 40 lotes daquele leilao. Por isso o "detalhe" aqui e' por leilao,
nao por lote: uma pagina (1,2 MB, quase tudo CSS inline) enriquece todos os
lotes irmaos e ainda rende os que nao cabiam na listagem.

robots.txt (17/10/2026): `Disallow: /*?pagina=` e `/busca`. Filtros por
caminho e por query (`/veiculos/carros`, `/veiculos/estado/SP`,
`?ordenacao=min`, `?valmin=&valmax=`) nao sao proibidos; por isso
`max_pages` vale 1 por padrao e a cobertura se amplia fatiando o catalogo
em `pages` (subcategoria x UF x faixa de valor), nao paginando. A API
publica (MCP em `/api/mcp/messages`) so' faz busca por palavra-chave com 10
resultados e nao serve de catalogo.

Semantica dos valores da fonte (confirmada contra os cards e o detalhe):
`vl_lanceminimo` e' a AVALIACAO; `vl_lanceinicial` e' o lance minimo da
etapa atual; `vl_lanceinicialsegundoleilao` e' o lance minimo da 2a praca.
Quando os dois ultimos coincidem, o lote ja' esta' na 2a praca.

RN-009: a descricao traz "Autor(es)/Exequente(s)", "Réu(s)/Executado(s)",
advogados, depositario e ate' CPF; essas linhas sao descartadas antes de
guardar. A Vara ("Cartório: ...") e' mantida como comitente.

Verificado em 17/10/2026.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from bs4 import BeautifulSoup
from unidecode import unidecode

from app.scrapers.base import BaseScraper, ScrapedAuction, ScrapedItem, ScrapedSession

logger = logging.getLogger("zleilao.scraper.leiloesjudiciais")

NUXT_DATA_RE = re.compile(r'<script[^>]+id="__NUXT_DATA__"[^>]*>(.*?)</script>', re.S)

#: Subcategoria da fonte -> slug do ZConnect, so' quando inequivoca. O resto
#: vai como texto e o titulo decide (engine/classifier.py).
CATEGORY_HINTS = {
    "carros": "carros", "motos": "motos", "caminhoes": "caminhoes", "onibus": "onibus",
    "veiculos pesados": "caminhoes", "tratores e colheitadeiras": "maquinas-agricolas",
    "implementos agricolas": "maquinas-agricolas", "aeronaves": "outros-veiculos",
    "veiculos nauticos": "outros-veiculos",
}
SEGMENT_HINTS = {"veiculos": "veiculos", "imoveis": "imoveis", "maquinas e equipamentos": "maquinas-equipamentos",
                 "bens diversos": "diversos"}

#: statuslote_id da fonte -> status do ZConnect (texto como reserva)
STATUS_BY_ID = {1: "open", 15: "withdrawn", 19: "soon"}
STATUS_BY_TEXT = {"excluido": "withdrawn", "aguardando": "soon", "condicional": "open"}

#: Rotulos de linha que identificam partes do processo (RN-009). Testados
#: sobre o rotulo sem acento, minusculo e sem "(a)(s)/(es)".
PARTY_RE = re.compile(
    r"\b(autor(?:a|es|as)?|r[eé]us?|exequentes?|executad[oa]s?|requerentes?|requerid[oa]s?|"
    r"reclamantes?|reclamad[oa]s?|embargantes?|embargad[oa]s?|agravantes?|agravad[oa]s?|"
    r"inventariantes?|herdeir[oa]s?|credor(?:a|es)?|devedor(?:a|es)?|falid[oa]|massa falida|"
    r"administradora? judicial|advogad[oa]s?|representante legal|proprietari[oa]s?|"
    r"depositari[oa]s?|interessad[oa]s?|impugnantes?|impugnad[oa]s?|espolio|arrematantes?|"
    r"fiador(?:a|es)?|avalistas?|cpf)\b"
)
COURT_RE = re.compile(r"\b(vara|juizo|comarca|justica|tribunal|trt|trf|forum|cartorio|juizado|turma)\b")
#: "85ª VT São Paulo/SP", "2ª Vara Cível de Vespasiano/MG", "16ª Vara Federal de Porto Alegre/RS"
COURT_INLINE_RE = re.compile(r"\b(\d{1,3}\s*[ªa°º]?\s*(?:VT|Vara(?:\s+(?:do|da|de|dos|das|Federal|Civel|Cível|Criminal|Unica|Única|Generica|Genérica|Empresarial|Fazenda|Familia|Família|Trabalho|Regional|Judicial|Execucoes|Execuções|Fiscal|Fiscais|Orfaos|Órfãos|Sucessoes|Sucessões|Publica|Pública|e)\b)*)[^()\n;,.]{0,60}?)(?=\s*[()\n;,.]|$)", re.I)
#: numero unico de processo judicial (CNJ): 7001655-20.2024.8.22.0013
CNJ_RE = re.compile(r"\b\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b")
#: "CPF DO PROPRIETARIO 123.456.789-00" ou o numero solto
CPF_RE = re.compile(r"\bCPF\b[^,;\n]{0,40}?\d{3}\.?\d{3}\.?\d{3}-?\d{2}|\b\d{3}\.\d{3}\.\d{3}-\d{2}\b", re.I)
#: sobra de quebra de linha da lista de advogados: "(21202DF)"
OAB_FRAGMENT_RE = re.compile(r"^\(?\d{3,7}[A-Z]{2}\)?[,;.]?$")
#: "- 10/10 -" ou "- 2021/2021 -" no titulo; "6x2" e "1/2" nao passam
YEARS_RE = re.compile(r"(?:^|[\s\-–])(\d{2}|\d{4})/(\d{2}|\d{4})(?=$|[\s\-–,])")
YEARS_TEXT_RE = re.compile(r"(?:fabrica[cç][aã]o|modelo)[^0-9]{0,25}(\d{4})\s*/\s*(\d{4})", re.I)
YEAR_RE = re.compile(r"\bano\s+(?:de\s+)?(?:fabrica[cç][aã]o\s+)?(\d{4})\b", re.I)


def _devalue(data: list) -> Any:
    """Desfaz o formato devalue do Nuxt 3: um vetor plano onde objetos e
    arrays guardam indices de outros elementos; arrays que abrem com string
    sao tipos especiais (Reactive, Ref, Date, Set...)."""
    memo: dict[int, Any] = {}

    def rec(i: Any) -> Any:
        if isinstance(i, bool) or not isinstance(i, int):
            return i
        if i < 0 or i >= len(data):  # -1 undefined, -3 NaN, -4/-5 Infinity, -6 -0
            return None
        if i in memo:
            return memo[i]
        v = data[i]
        if isinstance(v, list):
            if v and isinstance(v[0], str):
                tag = v[0]
                if tag in ("Reactive", "ShallowReactive", "Ref", "ShallowRef"):
                    memo[i] = rec(v[1]) if len(v) > 1 else None
                elif tag in ("EmptyRef", "EmptyShallowRef"):
                    try:
                        memo[i] = json.loads(v[1]) if len(v) > 1 and isinstance(v[1], str) else None
                    except ValueError:
                        memo[i] = None
                elif tag == "Set":
                    memo[i] = [rec(x) for x in v[1:]]
                elif tag == "Map":
                    memo[i] = [[rec(v[j]), rec(v[j + 1])] for j in range(1, len(v) - 1, 2)]
                elif tag in ("Date", "BigInt", "RegExp"):
                    memo[i] = v[1] if len(v) > 1 else None
                else:
                    memo[i] = rec(v[1]) if len(v) > 1 and isinstance(v[1], int) else None
                return memo[i]
            out: list = []
            memo[i] = out
            out.extend(rec(x) for x in v)
            return out
        if isinstance(v, dict):
            obj: dict = {}
            memo[i] = obj
            for k, x in v.items():
                obj[k] = rec(x)
            return obj
        memo[i] = v
        return v

    return rec(0)


def parse_nuxt_payload(html: str) -> Optional[dict]:
    """Devolve o `__NUXT_DATA__` decodificado (dict com `data`) ou None."""
    m = NUXT_DATA_RE.search(html or "")
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return None
    if not isinstance(data, list) or not data:
        return None
    root = _devalue(data)
    return root if isinstance(root, dict) else None


class LeiloesJudiciaisScraper(BaseScraper):
    display_name = "Leilões Judiciais"
    default_config = {
        # Cada entrada e' uma listagem SSR; aceita subcategoria, UF e query de
        # ordenacao/faixa de valor para fatiar o catalogo sem paginar.
        "pages": ["/veiculos"],
        # Opcional: ["SP", "MG"] expande cada page em /{page}/estado/{UF}.
        "states": [],
        # >1 usa ?pagina=N, que o robots.txt do site proibe. So' vale com
        # `allow_pagination: true`, uma chave que o `--max-pages` do agente
        # de coleta nao toca: o ciclo de hora em hora passa 2 e a varredura
        # profunda 12 para TODAS as fontes, e sem a trava o limite viraria
        # violacao do robots sem ninguem decidir.
        "max_pages": 1,
        "allow_pagination": False,
        "fetch_details": True,
        # Paginas de LEILAO (uma por leilao, ~1,2 MB cada), nao de lote.
        "max_details_per_run": 40,
        # Lotes irmaos que a pagina do leilao traz e a listagem nao mostrou.
        "harvest_auction_lots": True,
        # Segmentos aceitos na colheita (nm_segmento da fonte, sem acento).
        "segments": ["veiculos"],
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_meta: dict[str, Any] = {}
        # JSON de cada lote visto, para refazer as sessoes quando o leilao chega
        self._lots: dict[str, dict] = {}
        # Lotes cujo comitente veio do titulo do leilao (reserva fraca), nao da
        # descricao: o cadastro do leilao pode substitui-lo.
        self._weak_committer: set[str] = set()

    @property
    def default_base_url(self) -> str:
        return "https://www.leiloesjudiciais.com.br"

    # ── coleta ───────────────────────────────────────────────────────

    def _listing_paths(self) -> list[str]:
        pages = self.cfg("pages") or ["/veiculos"]
        states = [str(s).strip().upper() for s in (self.cfg("states") or []) if str(s).strip()]
        if not states:
            return list(pages)
        out = []
        for path in pages:
            base, _, query = path.partition("?")
            for uf in states:
                out.append(f"{base.rstrip('/')}/estado/{uf}" + (f"?{query}" if query else ""))
        return out

    def _page_url(self, path: str, page: int) -> str:
        url = self.abs_url(path)
        if page > 1:
            url = f"{url}{'&' if '?' in url else '?'}pagina={page}"
        return url

    def has_next_page(self, page: int) -> bool:
        try:
            return int(self.last_meta.get("totalPages") or 1) > page
        except (TypeError, ValueError):
            return False

    async def scrape(self) -> list[ScrapedItem]:
        items: list[ScrapedItem] = []
        max_pages = max(1, int(self.cfg("max_pages", 1))) if self.cfg("allow_pagination", False) else 1
        for path in self._listing_paths():
            for page in range(1, max_pages + 1):
                url = self._page_url(path, page)
                try:
                    html = await self.fetch(url)
                except Exception as exc:
                    self.stats.errors += 1
                    logger.warning("[LeiloesJudiciais] falha na pagina %s: %s", url, exc)
                    break
                self.stats.pages += 1
                parsed = self.parse_listing(html, path)
                logger.info("[LeiloesJudiciais] %s pagina %d: %d lotes (total %s em %s paginas)",
                            path, page, len(parsed), self.last_meta.get("totalItems"), self.last_meta.get("totalPages"))
                items.extend(parsed)
                if not parsed or not self.has_next_page(page):
                    break
                if page == max_pages:
                    self.stats.mark_partial(
                        f"parou em {max_pages} de {self.last_meta.get('totalPages')} paginas de {path} "
                        "(robots.txt proibe ?pagina=; fatie por subcategoria/UF/faixa de valor em pages)")
                    break
                await self.delay()

        if self.fetch_details:
            await self._enrich_by_auction(items)
        return items

    async def _enrich_by_auction(self, items: list[ScrapedItem]) -> None:
        groups: dict[str, list[ScrapedItem]] = {}
        for it in items:
            if it.auction:
                groups.setdefault(it.auction.external_id, []).append(it)
        known = {it.external_id for it in items}
        segments = {unidecode(str(s)).lower().strip() for s in (self.cfg("segments", ["veiculos"]) or [])}
        harvest = str(self.cfg("harvest_auction_lots", True)).lower() in ("1", "true", "yes")
        fetched = 0
        for auction_id, group in groups.items():
            if fetched >= self.max_details:
                self.stats.notes.append(f"limite de {self.max_details} leiloes detalhados atingido")
                break
            try:
                await self.delay()
                html = await self.fetch(f"{self.base_url}/leilao/{auction_id}")
                rec, lots = self.parse_auction_page(html)
                if rec is None:
                    raise ValueError("payload do leilao ausente")
                for it in group:
                    self.apply_auction(it, rec)
                if harvest:
                    for lot in lots:
                        lot_id = str(lot.get("lote_id") or "")
                        if not lot_id or lot_id in known:
                            continue
                        segment = unidecode(str(lot.get("nm_segmento") or "")).lower().strip()
                        if segments and segment not in segments:
                            continue
                        extra = self.item_from_lot(lot)
                        if extra:
                            self.apply_auction(extra, rec)
                            items.append(extra)
                            known.add(lot_id)
                fetched += 1
                self.stats.details += 1
            except Exception as exc:
                self.stats.errors += 1
                logger.warning("[LeiloesJudiciais] leilao %s falhou: %s", auction_id, exc)

    # ── listagem ─────────────────────────────────────────────────────

    def parse_listing(self, html: str, path: str = "") -> list[ScrapedItem]:
        self.last_meta = {}
        lots = self._lots_from_payload(html)
        if lots is None:
            # Sem payload (mudou o front?): os cards SSR ainda dao o essencial.
            lots = self._lots_from_cards(html)
            self.stats.notes.append("payload __NUXT_DATA__ ausente; cards usados como reserva")
        out: list[ScrapedItem] = []
        for lot in lots:
            try:
                item = self.item_from_lot(lot)
                if item:
                    out.append(item)
            except Exception as exc:  # um lote quebrado nao derruba a pagina
                self.stats.errors += 1
                logger.debug("[LeiloesJudiciais] lote ignorado: %s", exc)
        return out

    def _lots_from_payload(self, html: str) -> Optional[list[dict]]:
        root = parse_nuxt_payload(html)
        data = root.get("data") if root else None
        if not isinstance(data, dict):
            return None
        for key, value in data.items():
            if not key.startswith("busca_ssr") or not isinstance(value, dict):
                continue
            geral = value.get("dadosGeral") if isinstance(value.get("dadosGeral"), dict) else {}
            self.last_meta = {k: geral.get(k) for k in ("totalItems", "totalPages", "currentPage", "itemsPerPage")}
            lots = geral.get("items")
            if not isinstance(lots, list):
                lots = value.get("lotes") if isinstance(value.get("lotes"), list) else []
            return [lot for lot in lots if isinstance(lot, dict)]
        return None

    def _lots_from_cards(self, html: str) -> list[dict]:
        """Monta, a partir dos cards, o mesmo dict que o payload daria. O card
        chama de "Lance mínimo" o menor valor possivel (o da 2a praca, quando
        ha'), nao o da etapa atual; sem o JSON nao da' para separar as duas,
        entao o lote fica com esse valor e sem 2a praca."""
        soup = BeautifulSoup(html, "lxml")
        out: list[dict] = []
        info = soup.select_one(".info-paginacao-figma")
        if info:
            m = re.search(r"de\s+(\d+)\s*\S?\s*Exibindo\s+(\d+)\s+de\s+(\d+)", self.clean_text(info.get_text()))
            if m:
                self.last_meta = {"totalPages": int(m.group(1)), "itemsPerPage": int(m.group(2)), "totalItems": int(m.group(3))}
        for card in soup.select(".base-card"):
            link = card.select_one("a[href*='/lote/']")
            m = re.search(r"/lote/(\d+)/(\d+)", link.get("href", "")) if link else None
            if not m:
                continue
            title_el = card.select_one(".card-header-titulo")
            values: dict[str, str] = {}
            for lv in card.select(".label-valor"):
                spans = lv.find_all("span")
                if len(spans) >= 2:
                    values[unidecode(self.clean_text(spans[0].get_text())).lower()] = self.clean_text(spans[1].get_text())
            loc = card.select_one(".cidade-estado")
            city, state = self.parse_city_state(loc.get_text()) if loc else (None, None)
            img = card.select_one("img.imagem__lote")
            status = card.select_one(".status span") or card.select_one(".status")
            out.append({
                "leilao_id": int(m.group(1)), "lote_id": int(m.group(2)),
                "nm_titulo_lote": (title_el.get("title") or title_el.get_text()) if title_el else None,
                "vl_lanceminimo": values.get("avaliacao"), "vl_lanceinicial": values.get("lance minimo"),
                "vl_lance": values.get("lance atual"),
                "nm_statuslote": self.clean_text(status.get_text()) if status else None,
                "nm_cidade": city, "nm_estado": state,
                "fotos": [{"nm_path_completo": img.get("src")}] if img and img.get("src") else [],
                "_card": str(card),
            })
        return out

    # ── lote ─────────────────────────────────────────────────────────

    @staticmethod
    def _dec(value: Any) -> Optional[Decimal]:
        """A fonte manda '182003.45' (ponto decimal) no JSON e 'R$ 182.003,45'
        nos cards; parse_brl so' entende o segundo."""
        if value is None or value == "":
            return None
        if isinstance(value, (int, float, Decimal)):
            try:
                return Decimal(str(value)).quantize(Decimal("0.01"))
            except InvalidOperation:
                return None
        s = str(value).strip()
        if re.fullmatch(r"-?\d+(?:\.\d+)?", s):
            try:
                return Decimal(s).quantize(Decimal("0.01"))
            except InvalidOperation:
                return None
        return BaseScraper.parse_brl(s)

    @staticmethod
    def _year(s: str) -> Optional[int]:
        n = int(s)
        if len(s) == 4:
            return n if 1900 <= n <= 2100 else None
        return 2000 + n if n <= datetime.now().year % 100 + 1 else 1900 + n

    @classmethod
    def _years(cls, title: str, description: str = "") -> tuple[Optional[int], Optional[int]]:
        """'VW/24220 - 10/10 - Vespasiano/MG' -> (2010, 2010); 'Ano 1998' -> (1998, 1998)."""
        for m in YEARS_RE.finditer(title or ""):
            a, b = m.group(1), m.group(2)
            if len(a) != len(b):
                continue
            ya, yb = cls._year(a), cls._year(b)
            if ya and yb and 0 <= yb - ya <= 1:
                return ya, yb
        m = YEARS_TEXT_RE.search(description or "")
        if m and 1900 <= int(m.group(1)) <= 2100 and 0 <= int(m.group(2)) - int(m.group(1)) <= 1:
            return int(m.group(1)), int(m.group(2))
        m = YEAR_RE.search(title or "") or YEAR_RE.search(description or "")
        if m and 1900 <= int(m.group(1)) <= 2100:
            return int(m.group(1)), int(m.group(1))
        return None, None

    @staticmethod
    def _auction_type_from_text(auction_title: str | None, description: str | None) -> Optional[str]:
        """O portal e' judicial, mas abriga vendas administrativas (PRF, orgaos
        publicos). Sem Vara no titulo nem numero CNJ na descricao, fica em
        aberto ate' o cadastro do leilao (tp_judicial_extrajudicial) decidir."""
        t = unidecode(auction_title or "").lower()
        if "extrajudicial" in t:
            return "extrajudicial"
        if "judicial" in t or COURT_RE.search(t) or CNJ_RE.search(description or ""):
            return "judicial"
        return None

    @staticmethod
    def _html_lines(html: str | None) -> list[str]:
        if not html:
            return []
        if "<" not in html:  # texto puro: o BeautifulSoup avisaria "parece um nome de arquivo"
            return [re.sub(r"\s+", " ", line).strip() for line in html.split("\n") if line.strip()]
        soup = BeautifulSoup(html, "lxml")
        for br in soup.find_all("br"):
            br.replace_with("\n")
        for tag in soup.find_all(["p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5"]):
            tag.append("\n")
        return [re.sub(r"\s+", " ", line).strip() for line in soup.get_text().split("\n") if line.strip()]

    def clean_description(self, html: str | None) -> tuple[str, Optional[str]]:
        """Texto da descricao sem as partes do processo (RN-009) e a Vara,
        quando a fonte a escreve como 'Cartório: ...' / 'Vara: ...' ou dentro
        do texto ('Proc. 1001955-35.2025.5.02.0085 - 85ª VT São Paulo/SP')."""
        kept: list[str] = []
        court: Optional[str] = None
        for line in self._html_lines(html):
            if OAB_FRAGMENT_RE.match(line):
                continue
            if ":" in line[:60]:
                label, _, value = line.partition(":")
                norm = re.sub(r"\([a-z]{1,3}\)", "", unidecode(label).lower())
                if PARTY_RE.search(norm):
                    continue
                if court is None and COURT_RE.search(norm) and value.strip():
                    court = self.clean_text(value)[:200]
            line = CPF_RE.sub("", line)
            line = self.clean_text(re.sub(r"\s*,\s*([.;])", r"\1", re.sub(r"\(\s*\)", "", line)))
            if line:
                kept.append(line)
        text = "\n".join(kept)
        if court is None:
            m = COURT_INLINE_RE.search(text)
            if m:
                court = self.clean_text(m.group(1))[:200]
        return text, court

    def _images(self, lot: dict) -> list[str]:
        out: list[str] = []
        for foto in lot.get("fotos") or []:
            if not isinstance(foto, dict):
                continue
            base, name = foto.get("nm_path_incompleto"), foto.get("nm_path")
            # o card usa 640x480; a API aponta a miniatura 196x146
            url = f"{base}640x480/{name}" if base and name else foto.get("nm_path_completo")
            url = self.reject_placeholder(url)
            if url and "nao-disponivel" not in url.lower() and url not in out:
                out.append(url)
        return out

    @staticmethod
    def _category_hint(subcategory: str | None, segment: str | None) -> Optional[str]:
        sub = unidecode(subcategory or "").lower().strip()
        if sub in CATEGORY_HINTS:
            return CATEGORY_HINTS[sub]
        seg = unidecode(segment or "").lower().strip()
        if seg in SEGMENT_HINTS:
            return SEGMENT_HINTS[seg]
        return sub or None

    @staticmethod
    def _sessions(current: Optional[Decimal], second: Optional[Decimal], closes: Optional[datetime],
                  first_at: Optional[datetime] = None, second_at: Optional[datetime] = None) -> list[ScrapedSession]:
        """Sem valor de 2a praca nem data dela, e' etapa unica. Quando o lance
        da 2a praca ja' e' o lance minimo atual, a 1a praca passou: o fechamento
        do lote pertence a' 2a."""
        if second is None and second_at is None:
            if first_at and closes and closes < first_at:
                closes = None
            return [ScrapedSession(kind="unica", starts_at=first_at, ends_at=closes, min_bid=current)]
        in_second = second is not None and current is not None and second >= current
        first = ScrapedSession(kind="1a_praca", starts_at=first_at,
                               ends_at=None if in_second else closes, min_bid=None if in_second else current)
        sec = ScrapedSession(kind="2a_praca", starts_at=second_at,
                             ends_at=closes if in_second else None, min_bid=second)
        out = [s for s in (first, sec) if s.starts_at or s.ends_at or s.min_bid is not None]
        for s in out:
            # fechamento do lote estagnado na fonte (leilao unificado remarcado):
            # nao pode terminar antes de comecar
            if s.starts_at and s.ends_at and s.ends_at < s.starts_at:
                s.ends_at = None
        return out

    @staticmethod
    def _status(lot: dict) -> Optional[str]:
        if LeiloesJudiciaisScraper._dec(lot.get("vl_venda")):
            return "sold"
        try:
            by_id = STATUS_BY_ID.get(int(lot.get("statuslote_id")))
        except (TypeError, ValueError):
            by_id = None
        if by_id:
            return by_id
        text = unidecode(str(lot.get("nm_statuslote") or "")).lower()
        for key, status in STATUS_BY_TEXT.items():
            if key in text:
                return status
        return BaseScraper.status_from_text(text)

    def item_from_lot(self, lot: dict) -> Optional[ScrapedItem]:
        lot_id, auction_id = lot.get("lote_id"), lot.get("leilao_id")
        if not lot_id or not auction_id:
            return None
        nu = lot.get("nu")
        auction_title = self.clean_text(lot.get("nm_titulo_leilao")) or None
        title = self.clean_text(lot.get("nm_titulo_lote")) or auction_title or f"Lote {nu or lot_id}"
        if "simulacao" in unidecode(f"{title} {auction_title or ''}").lower():
            return None  # o portal mantem um "LEILÃO SIMULAÇÃO - TESTE TRANSMISSÃO" publico
        url = f"{self.base_url}/lote/{auction_id}/{lot_id}"

        avaliacao = self._dec(lot.get("vl_lanceminimo")) if lot.get("bn_exibeavaliacao", True) is not False else None
        current = self._dec(lot.get("vl_lanceinicial"))
        if current is not None and current <= 0:  # "R$ 0,00" e' "nao definido"
            current = None
        second = self._dec(lot.get("vl_lanceinicialsegundoleilao"))
        bid = self._dec(lot.get("vl_lance"))
        sold_for = self._dec(lot.get("vl_venda"))
        price = current if current is not None else (second if second is not None else avaliacao)
        price_second = second if (second is not None and current is not None and second < current) else None
        closes = self.parse_datetime_br(lot.get("dt_fechamento"))

        description, court = self.clean_description(lot.get("nm_descricao"))
        auction_type = self._auction_type_from_text(auction_title, description)
        weak_committer = False
        if not court and auction_title and COURT_RE.search(unidecode(auction_title).lower()):
            court, weak_committer = auction_title[:200], True

        subcategory = self.clean_text(lot.get("nm_subcategoria")) or None
        segment = self.clean_text(lot.get("nm_segmento")) or None
        year_fab, year_model = self._years(title, description)
        attachments = {self.clean_text(a.get("nm")).upper(): a.get("nm_path_completo")
                       for a in (lot.get("anexos") or []) if isinstance(a, dict) and a.get("nm_path_completo")}
        parcels = lot.get("nu_parcelas")
        raw: dict[str, Any] = {
            "valor_avaliacao": str(avaliacao) if avaliacao is not None else None,
            "lance_minimo_atual": str(current) if current is not None else None,
            "lance_2a_praca": str(second) if second is not None else None,
            "lance_atual": str(bid) if bid else None,
            "valor_venda": str(sold_for) if sold_for else None,
            "incremento": str(self._dec(lot.get("vl_incremento")) or "") or None,
            "qtd_lances": lot.get("nu_qtdelances"),
            "visitas": lot.get("nu_visitas"),
            "parcelas": parcels,
            "entrada_pct": lot.get("vl_percentualentrada") if parcels else None,
            "indice_correcao": lot.get("indice_correcao") if parcels else None,
            "fechamento": closes.isoformat() if closes else None,
            "status_fonte": self.clean_text(lot.get("nm_statuslote")) or None,
            "subcategoria": subcategory,
            "segmento": segment,
            "leiloeiro_site": lot.get("nm_url_leiloeiro"),
            "edital_url": attachments.get("EDITAL"),
            "laudo_avaliacao_url": attachments.get("AVALIAÇÃO") or attachments.get("AVALIACAO"),
            "ano_fabricacao": year_fab,
            "ano_modelo": year_model,
            "origem": "judicial" if auction_type == "judicial" else None,
        }
        raw = {k: v for k, v in raw.items() if v not in (None, "", [])}

        status_hint = self._status(lot)
        images = self._images(lot)
        auction = ScrapedAuction(
            external_id=str(auction_id),
            title=auction_title,
            auctioneer_name=(self.clean_text(lot.get("nm_leiloeiro")) or None),
            committer_name=court,
            modality="online",
            auction_type=auction_type,
            official_url=f"{self.base_url}/leilao/{auction_id}",
            sessions=self._sessions(current, second, closes),
        )
        payload = {k: v for k, v in lot.items() if k != "_card"}
        item = ScrapedItem(
            external_id=str(lot_id),
            title=title,
            official_url=url,
            price=price,
            price_kind="lance_inicial",
            price_second=price_second,
            lot_number=str(nu) if nu else None,
            city=self.reject_unknown(self.clean_text(lot.get("nm_cidade")) or None),
            state=(str(lot.get("nm_estado") or "").strip().upper()[:2] or None),
            image_url=images[0] if images else None,
            images=images[:12],
            description=description or None,
            raw_attributes=raw,
            category_hint=self._category_hint(subcategory, segment),
            status_hint=status_hint,
            auction=auction,
            raw_payload=lot.get("_card") or json.dumps(payload, ensure_ascii=False, default=str),
        )
        self._lots[item.external_id] = lot
        if weak_committer:
            self._weak_committer.add(item.external_id)
        else:
            self._weak_committer.discard(item.external_id)
        return item

    # ── leilao (detalhe) ─────────────────────────────────────────────

    def parse_auction_page(self, html: str) -> tuple[Optional[dict], list[dict]]:
        """(registro do leilao, lotes do leilao) a partir do payload de
        /leilao/{id}. Em /lote/{leilao}/{lote} vem o mesmo registro e um unico lote."""
        root = parse_nuxt_payload(html)
        data = root.get("data") if root else None
        if not isinstance(data, dict):
            return None, []
        record: Optional[dict] = None
        lots: list[dict] = []
        for key, value in data.items():
            if not isinstance(value, dict):
                continue
            if key.startswith("dadosLeilao-") and value.get("id"):
                record = value
            elif key.startswith("dadosLotes-"):
                found = value.get("items")
                if not isinstance(found, list):
                    single = value.get("lote")
                    found = [single] if isinstance(single, dict) and single.get("lote_id") else []
                lots = [lot for lot in found if isinstance(lot, dict) and lot.get("lote_id")]
        return record, lots

    def apply_auction(self, item: ScrapedItem, record: dict) -> None:
        if not item.auction:
            return
        a = item.auction
        first_at = self.parse_datetime_br(f"{record.get('dt_formatada') or ''} {record.get('hr_formatada') or ''}")
        second_at = self.parse_datetime_br(f"{record.get('dt_segundoleilao_data') or ''} {record.get('dt_segundoleilao_hora') or ''}")
        lot = self._lots.get(item.external_id) or {}
        current = self._dec(lot.get("vl_lanceinicial"))
        if current is not None and current <= 0:
            current = None
        second = self._dec(lot.get("vl_lanceinicialsegundoleilao"))
        closes = self.parse_datetime_br(lot.get("dt_fechamento"))
        a.sessions = self._sessions(current, second, closes, first_at, second_at)

        a.title = self.clean_text(record.get("nm")) or a.title
        kind = self.clean_text(record.get("nm_statusleilao"))  # "Judicial Online", "Venda Direta"...
        norm = unidecode(f"{kind} {a.title or ''}").lower()
        # tp_judicial_extrajudicial: 1 = extrajudicial (PRF, orgaos publicos), 2 = judicial
        flag = record.get("tp_judicial_extrajudicial")
        if flag in (1, "1"):
            a.auction_type = "extrajudicial"
        elif flag in (2, "2"):
            a.auction_type = "judicial"
        else:
            a.auction_type = self._auction_type_from_text(a.title, item.description) or ("extrajudicial" if "extrajudicial" in norm else a.auction_type)
        if a.auction_type == "judicial":
            item.raw_attributes["origem"] = "judicial"
        else:
            item.raw_attributes.pop("origem", None)
        if "online" in norm and "presencial" in norm:
            a.modality = "hibrido"
        elif "presencial" in norm:
            a.modality = "presencial"
        else:
            a.modality = "online"

        # Comitente do cadastro e' a Vara do leilao. A Vara escrita na descricao
        # do lote vale mais: leiloes unificados (TRT) listam dezenas de varas e
        # ha' cadastros com placeholder. O titulo do leilao e' so' reserva fraca.
        committers = record.get("comitente")
        if isinstance(committers, dict):
            committers = [committers]
        names = [self.clean_text(c.get("nm")) for c in (committers or []) if isinstance(c, dict) and c.get("nm")]
        current_is_weak = not a.committer_name or item.external_id in self._weak_committer
        if names and current_is_weak and (len(names) == 1 or not a.committer_name):
            a.committer_name = names[0][:200]
            self._weak_committer.discard(item.external_id)

        if kind:
            item.raw_attributes["tipo_leilao"] = kind
        if record.get("vl_percentualdepreciacao") is not None:
            item.raw_attributes["desconto_2a_praca_pct"] = record.get("vl_percentualdepreciacao")
        ufs = [u for u in (record.get("uf") or []) if isinstance(u, str)]
        if ufs:
            item.raw_attributes["ufs_leilao"] = ",".join(ufs)
        if record.get("bn_aceitelanceparcelado"):
            item.raw_attributes["parcelamento_leilao"] = f"ate {record.get('nu_limiteparcelas')}x"
