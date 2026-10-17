"""Palácio dos Leilões — PHP com a listagem servida por AJAX. Um unico
`POST site/camada_ajax/coluna_esquerda_m.php` com `opcao=listar_lote`,
`categoria_pesquisa=N` e `paginacao=-1` ("Exibir todos") devolve TODOS os
cards da categoria (~1 MB para a 1 = Automovel; 15 = Eletro; 14 = Materiais).
Pede-se `tipo_exibicao=lista` porque o grid trunca o titulo com reticencias.

Card em modo lista = par de divs irmas: `.col-6.col-md-4` com
`onclick='exibir_lote(COD_LOTE,COD_LEILAO)'` e a foto, e `.col-6.col-md-8`
com titulo ("MARCA/MODELO ANO_FAB ANO_MOD"), condicao, comitente, patio, data
com ano de 2 digitos, "Sequencia N" | "Lote N" | vazio e preco com rotulo
("lance inicial" | "ultimo lance"). Preco "0,00" = sem lance minimo publicado.

Detalhe (opcional): `POST site/camada_ajax/lote.php` com
`opcao=exibir_lote_2&cod_lote=N` -> fragmento com fotos, ficha (situacao,
combustivel, origem, marca/modelo, km, anos, potencia, cilindradas, media de
mercado), observacao e numero do lote. URL publica do lote (RN-001):
`site/lotem.php?cl=COD_LOTE`, a mesma que o proprio site compartilha.

Tudo extrajudicial (PAN, Honda, Mapfre, Movida, Porto, Localiza, Bradesco...).
robots.txt: `Allow: /`, so' `/documents/` bloqueado; sem termos de uso
publicos. Resposta em ISO-8859-1 com charset no header. Verificado em
17/10/2026.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from unidecode import unidecode

from app.scrapers.base import BaseScraper, ScrapedAuction, ScrapedItem, ScrapedSession

logger = logging.getLogger("zleilao.scraper.palacio")

AJAX_LISTING = "camada_ajax/coluna_esquerda_m.php"
AJAX_LOT = "camada_ajax/lote.php"

# Categorias da fonte -> dica de categoria nossa. Fora de veiculos a fonte
# mistura de tudo ("Eletro" vai de sofa a TV); o titulo decide.
CATEGORY_HINTS = {1: "veiculos", 14: "diversos", 15: "diversos"}

# Origem do bem pelo comitente, so' para a listagem: o detalhe traz "Origem"
# explicita e prevalece. Seguradoras vem antes das financeiras porque
# "BRADESCO SEGUROS" nao e' "BANCO BRADESCO". "HONDA" aqui e' o Banco Honda
# (pregao "motocicletas recuperadas de financiamento"); "BEM PROTEGE" e'
# protecao veicular, que para a origem do bem equivale a seguradora.
# Revendas (PROAUTO, AUTO VENDE, USECAR...) ficam sem origem: nao ha' enum
# para elas e inventar uma violaria a RN-002.
ORIGEM_COMITENTE = [
    (r"\bSEGUR|\bMAPFRE\b|\bPORTO\b|\bSOMPO\b|\bAZUL\b|\bALLIANZ\b|\bTOKIO\b|\bHDI\b|\bLIBERTY\b|\bSUHAI\b|\bBEM PROTEGE\b", "seguradora"),
    (r"^BANCO\b|\bPAN\b|^BV\b|\bITAPEVA\b|\bHONDA\b|\bSANTANDER\b|\bITAU\b|\bSAFRA\b|\bOMNI\b|\bDAYCOVAL\b|\bFINANC|\bCONSORCIO\b|\bBRADESCO\b", "financeira"),
    (r"\bLOCALIZA\b|\bMOVIDA\b|\bUNIDAS\b|\bLOCADORA\b|\bRENT\b", "locadora"),
    (r"^VALE\b|\bFROTA\b", "frota"),
]

# "Origem" da ficha do detalhe -> enum do extrator deterministico. "empresa"
# e' o bem da propria empresa comitente (Vale vendendo varredeira): frota, no
# nosso vocabulario. Palavra fora do mapa fica so' em `origem_fonte`.
ORIGEM_FONTE = {
    "financeira": "financeira", "banco": "financeira", "seguradora": "seguradora",
    "locadora": "locadora", "empresa": "frota", "frota": "frota", "judicial": "judicial",
}

# Rotulos da ficha do detalhe (unidecode, minusculo) que viram atributo.
# "Final Placa" fica de fora de proposito: um digito nao identifica ninguem,
# mas a chave conteria "placa" e o mascaramento (RN-009) trata isso como
# dado sensivel. "Arrematante" tambem nao entra (RN-009).
DETAIL_LABELS = {
    "leilao", "data", "lote", "seq", "visitacao", "situacao", "combustivel doc.", "combustivel",
    "origem", "marca modelo", "km", "fabricacao", "modelo", "potencia", "cilindradas",
    "acessorios", "media mercado", "local leilao", "local lote",
}


class PalacioScraper(BaseScraper):
    display_name = "Palácio dos Leilões"
    default_config = {
        "categorias": [1],  # 1 = Automovel; 15 = Eletro; 14 = Materiais
        "fetch_details": True,
        "max_details_per_run": 60,
        # Rotulo do patio no card -> [cidade, UF]. "Externo" nao esta' aqui de
        # proposito: o bem fica fora dos patios e a fonte nao diz onde. O patio
        # "Salvador" fica fisicamente em Simoes Filho/BA (rodape do site), mas
        # a cidade exibida e' a que a fonte rotula.
        "patios": {"Juatuba": ["Juatuba", "MG"], "Salvador": ["Salvador", "BA"], "Cajamar": ["Cajamar", "SP"]},
    }

    YEARS_RE = re.compile(r"^(.*?)\s+((?:19|20)\d{2})\s+((?:19|20)\d{2})\s*$")

    @property
    def default_base_url(self) -> str:
        return "https://www.palaciodosleiloes.com.br"

    # Tudo da fonte mora em /site/: os `src` relativos dos cards resolvem
    # contra ele, nao contra a raiz do dominio.
    def site_url(self, href: str) -> str:
        return urljoin(f"{self.base_url}/site/", href)

    def lot_url(self, cod_lote: str) -> str:
        return f"{self.base_url}/site/lotem.php?cl={cod_lote}"

    def auction_url(self, cod_leilao: str) -> str:
        return f"{self.base_url}/site/leilao.php?cl={cod_leilao}"

    # ── transporte ───────────────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.ReadTimeout)),
        reraise=True,
    )
    async def post_form(self, url: str, data: dict[str, Any]) -> str:
        """`BaseScraper.fetch` so' faz GET; a camada AJAX da fonte so' responde
        a POST de formulario. Mesmo retry e mesmos status tratados da base."""
        assert self.client is not None, "use 'async with scraper:'"
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{self.base_url}/site/",
            "Accept": "text/html, */*; q=0.01",
        }
        resp = await self.client.post(url, data=data, headers=headers)
        if resp.status_code in (403, 429, 503):
            raise httpx.HTTPStatusError(f"{resp.status_code} em {url}", request=resp.request, response=resp)
        resp.raise_for_status()
        return self._decode(resp)

    @staticmethod
    def listing_form(categoria: int) -> dict[str, str]:
        """Mesmo corpo que o JS da fonte monta ao filtrar por categoria;
        `paginacao=-1` e' o botao "Exibir todos"."""
        return {
            "opcao": "listar_lote", "categoria_pesquisa": str(categoria), "tipo_exibicao": "lista",
            "paginacao": "-1", "subcategoria_pesquisa": "", "marca_pesquisa": "", "situacao_pesquisa": "",
            "local_pesquisa": "", "modelo_pesquisa": "", "ano_pesquisa": "", "cidade_site_pesquisa": "",
            "estado_site_pesquisa": "", "grupo_site_pesquisa": "", "txt_pesquisa_lote": "", "leilao_pesquisa": "",
            "total_paginas": "0", "somente_pesquisa": "0", "e_categoria": "1", "e_leilao": "0",
            "e_subcategoria": "0", "e_marca": "0", "e_modelo": "0", "e_ano": "0", "e_situacao": "0",
            "e_local": "0", "e_grupo": "0", "e_estado": "0", "e_cidade": "0",
        }

    # ── coleta ───────────────────────────────────────────────────────

    async def scrape(self) -> list[ScrapedItem]:
        items: list[ScrapedItem] = []
        categorias = self.cfg("categorias") or [1]
        for idx, cat in enumerate(categorias):
            if idx:
                await self.delay()
            try:
                html = await self.post_form(self.site_url(AJAX_LISTING), self.listing_form(int(cat)))
            except Exception as exc:
                self.stats.errors += 1
                self.stats.mark_partial(f"categoria {cat} falhou: {str(exc)[:120]}")
                logger.warning("[Palacio] categoria %s falhou: %s", cat, exc)
                continue
            self.stats.pages += 1
            parsed = self.parse_listing(html, int(cat))
            total = self.total_from_listing(html)
            logger.info("[Palacio] categoria %s: %d cards (fonte anuncia %s)", cat, len(parsed), total)
            # A fonte diz quantos lotes tem; ler menos que isso significa que
            # o catalogo nao foi visto inteiro (RN-005 so' conclui sumico em
            # varredura completa).
            if total is not None and len(parsed) < total:
                self.stats.mark_partial(f"categoria {cat}: {len(parsed)} de {total} lotes lidos")
            items.extend(parsed)

        if self.fetch_details:
            fetched = 0
            for it in items:
                if fetched >= self.max_details:
                    self.stats.notes.append(f"limite de {self.max_details} detalhes atingido")
                    break
                try:
                    await self.delay()
                    html = await self.post_form(self.site_url(AJAX_LOT), {"opcao": "exibir_lote_2", "cod_lote": it.external_id})
                    # O JS da fonte trata "0" como lote inexistente.
                    if html.strip() in ("", "0"):
                        raise ValueError("fragmento vazio")
                    self.enrich_from_detail(it, html)
                    fetched += 1
                    self.stats.details += 1
                except Exception as exc:
                    self.stats.errors += 1
                    logger.warning("[Palacio] detalhe falhou %s: %s", it.external_id, exc)
        return items

    # ── listagem ─────────────────────────────────────────────────────

    @staticmethod
    def total_from_listing(html: str) -> Optional[int]:
        m = re.search(r"id=['\"]total_lotes['\"]\s+value=['\"](\d+)['\"]", html)
        return int(m.group(1)) if m else None

    def parse_listing(self, html: str, categoria: int = 1) -> list[ScrapedItem]:
        soup = BeautifulSoup(html, "lxml")
        out: list[ScrapedItem] = []
        # So' o modo lista poe o onclick na coluna da foto; no grid ele fica
        # em `.i-c`, entao o seletor nao confunde os dois.
        for photo in soup.select("div.col-md-4[onclick^='exibir_lote(']"):
            info = photo.find_next_sibling("div")
            if not info or "col-md-8" not in (info.get("class") or []):
                continue
            try:
                item = self._parse_card(photo, info, categoria)
                if item:
                    out.append(item)
            except Exception as exc:  # um card quebrado nao derruba a categoria
                self.stats.errors += 1
                logger.debug("[Palacio] card ignorado: %s", exc)
        return out

    def _icon_text(self, info, icon_cls: str) -> str:
        """Texto da div cujo icone identifica o campo (`<div><i class='fas fa-user-tie'></i> MAPFRE</div>`)."""
        i = info.select_one(f"i.{icon_cls}")
        return self.clean_text(i.parent.get_text(" ")) if i is not None and i.parent is not None else ""

    def _patios(self) -> dict[str, tuple[str, str]]:
        raw = self.cfg("patios") or self.default_config["patios"]
        return {unidecode(k).strip().lower(): (v[0], v[1]) for k, v in raw.items() if isinstance(v, (list, tuple)) and len(v) >= 2}

    def _parse_card(self, photo, info, categoria: int) -> Optional[ScrapedItem]:
        m = re.search(r"exibir_lote\((\d+)\s*,\s*(\d+)\)", photo.get("onclick", ""))
        if not m:
            return None
        cod_lote, cod_leilao = m.group(1), m.group(2)

        img = photo.select_one("img[src]")
        image_url = self.reject_placeholder(self.site_url(img["src"])) if img else None

        title_el = info.select_one("div.quebraln.my-0")
        raw_title = self.clean_text(title_el.get_text(" ")) if title_el else ""
        title, vehicle = self.split_title(raw_title or f"Lote {cod_lote}")

        cond_el = info.select_one("div.quebraln.mb-1")
        condicao_fonte = self.clean_text(cond_el.get_text(" ")) if cond_el else ""
        condicao = self.condition_from_text(condicao_fonte)

        comitente = self._icon_text(info, "fa-user-tie")
        patio = self._icon_text(info, "fa-map-marker-alt")
        starts_at = self.parse_date_short(self._icon_text(info, "fa-calendar-alt"))

        # "Sequencia N" = ordem no pregao ja' montado; "Lote N" = numero do
        # lote (pregoes futuros e bens externos); vazio em parte dos cards.
        seq_txt = self._icon_text(info, "fa-list-ol")
        lot_number = sequencia = None
        ms = re.search(r"sequ[eê]ncia\s*(\d+)", seq_txt, re.I)
        if ms:
            sequencia = int(ms.group(1))
        ml = re.search(r"\blote\s*(\d+)", seq_txt, re.I)
        if ml:
            lot_number = str(int(ml.group(1)))

        price_el = info.select_one(".h3")
        label_el = price_el.select_one(".peq") if price_el else None
        label = unidecode(self.clean_text(label_el.get_text())).lower() if label_el else ""
        price = self.parse_brl(price_el.get_text(" ")) if price_el else None
        price_kind = "lance_atual" if ("ultimo" in label or "atual" in label) else "lance_inicial"
        sem_lance_minimo = False
        if price is not None and price == 0:
            # "0,00 lance inicial" e' lance livre: zero nao e' preco (RN-002).
            price, sem_lance_minimo = None, True

        city = state = location_text = None
        if patio:
            loc = self._patios().get(unidecode(patio).strip().lower())
            if loc:
                city, state = loc
                location_text = f"Pátio {patio} — {city}/{state}"
            else:
                location_text = patio

        origem = self.origem_from_committer(comitente)
        category_hint = "sucatas" if condicao == "sucata" else CATEGORY_HINTS.get(categoria, "diversos")

        attrs: dict[str, Any] = {
            "comitente": comitente or None,
            "origem": origem,
            "condicao": condicao,  # enum do motor; None quando a fonte so' diz "no estado que se encontra"
            "condicao_fonte": condicao_fonte or None,
            "patio": patio or None,
            "sequencia": sequencia,
            "cod_leilao": cod_leilao,
            "categoria_fonte": categoria,
            **vehicle,
        }
        if sem_lance_minimo:
            attrs["sem_lance_minimo"] = True
        attrs = {k: v for k, v in attrs.items() if v is not None}

        auction = ScrapedAuction(
            external_id=cod_leilao,
            title=f"Leilão {cod_leilao}" + (f" — {starts_at:%d/%m/%Y}" if starts_at else ""),
            # Nome fantasia do leiloeiro, nao a pessoa fisica (RN-009); a
            # matricula e' registro publico e cumpre a RN-001.
            auctioneer_name="Palácio dos Leilões",
            auctioneer_registration="JUCEMG 394",
            auction_type="extrajudicial",
            official_url=self.auction_url(cod_leilao),
            sessions=[ScrapedSession(kind="unica", starts_at=starts_at)],
            # Um pregao reune varios comitentes; o do item fica tambem em
            # raw_attributes["comitente"], que e' o dado confiavel por lote.
            committer_name=comitente or None,
        )
        return ScrapedItem(
            external_id=cod_lote,
            title=title,
            official_url=self.lot_url(cod_lote),
            price=price,
            price_kind=price_kind,
            lot_number=lot_number,
            city=city,
            state=state,
            location_text=location_text,
            image_url=image_url,
            images=[image_url] if image_url else [],
            raw_attributes=attrs,
            category_hint=category_hint,
            # A fonte so' lista pregoes futuros/em curso e aceita pre-lance
            # em todos eles.
            status_hint="open",
            auction=auction,
            raw_payload=str(photo) + "\n" + str(info),
        )

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def parse_date_short(text: str | None) -> Optional[datetime]:
        """'17/10/26' (ano de 2 digitos, como a fonte mostra) -> 2026-10-17.
        `parse_datetime_br` da base exige 4 digitos; aceita-os tambem."""
        m = re.search(r"(\d{2})/(\d{2})/(\d{4}|\d{2})\b", text or "")
        if not m:
            return None
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        try:
            return datetime(y, mo, d)
        except ValueError:
            return None

    @classmethod
    def split_title(cls, raw: str) -> tuple[str, dict[str, Any]]:
        """'FIAT/TORO VOLC TD450 AT 2026 2026' -> ('FIAT/TORO VOLC TD450 AT 2026/2026',
        {marca, modelo, ano_fabricacao, ano_modelo}). Titulos colados sem anos
        ('GMMONTANA', 'VOLKSWAGENPOLO') ficam como estao: separar marca de
        modelo ali seria chute."""
        raw = BaseScraper.clean_text(raw)
        m = cls.YEARS_RE.match(raw)
        if not m:
            return raw, {}
        base, fab, mod = m.group(1).strip(), int(m.group(2)), int(m.group(3))
        attrs: dict[str, Any] = {"ano_fabricacao": fab, "ano_modelo": mod}
        attrs.update(cls.brand_model(base))
        return f"{base} {fab}/{mod}", attrs

    @staticmethod
    def brand_model(base: str) -> dict[str, Any]:
        """'FIAT/TORO VOLC TD450 AT' -> marca/modelo em Title Case (so' dica,
        como nas outras fontes). 'I/' e' o prefixo DENATRAN de importado, nao
        marca: a marca passa a ser a primeira palavra do resto."""
        if "/" not in base:
            return {}
        marca, modelo = (p.strip() for p in base.split("/", 1))
        out: dict[str, Any] = {}
        if marca.upper() == "I":
            out["importado"] = True
            marca, _, modelo = modelo.partition(" ")
        if marca:
            out["marca"] = marca.title()
        if modelo:
            out["modelo"] = modelo.title()
        return out

    @staticmethod
    def origem_from_committer(comitente: str | None) -> Optional[str]:
        t = unidecode(comitente or "").upper().strip()
        if not t:
            return None
        for pattern, origem in ORIGEM_COMITENTE:
            if re.search(pattern, t):
                return origem
        return None

    @staticmethod
    def condition_from_text(text: str | None) -> Optional[str]:
        """Condicao da fonte -> enum do extrator deterministico. "no estado que
        se encontra" e' clausula padrao de leilao, nao condicao: fica None."""
        t = unidecode(text or "").lower()
        if not t:
            return None
        if "sucata" in t:
            return "sucata"
        if "grande monta" in t:
            return "sinistro_grande_monta"
        if "media monta" in t:
            return "sinistro_media_monta"
        if "pequena monta" in t or "sinistr" in t:
            return "sinistro_recuperavel"
        return None

    # ── detalhe ──────────────────────────────────────────────────────

    def enrich_from_detail(self, item: ScrapedItem, html: str) -> None:
        soup = BeautifulSoup(html, "lxml")
        attrs = item.raw_attributes

        # Ficha: <td>Rotulo<br/>Valor</td> (KM vem como <td>KM<div>15</div></td>).
        # Celulas com tabela dentro sao caixas de texto, nao campos.
        fields: dict[str, str] = {}
        for td in soup.select("td"):
            if td.find("table"):
                continue
            parts = [self.clean_text(s) for s in td.stripped_strings]
            parts = [p for p in parts if p]
            if len(parts) != 2:
                continue
            label = unidecode(parts[0]).lower().strip()
            if label in DETAIL_LABELS:
                fields[label] = parts[1]

        def _int(v: str | None) -> Optional[int]:
            digits = re.sub(r"\D", "", v or "")
            return int(digits) if digits else None

        if fields.get("lote"):
            item.lot_number = fields["lote"].lstrip("0") or fields["lote"]
        if _int(fields.get("seq")) is not None:
            attrs["sequencia"] = _int(fields["seq"])
        if fields.get("visitacao"):
            visit = self.parse_date_short(fields["visitacao"])
            if visit:
                attrs["visitacao"] = visit.date().isoformat()
        if fields.get("situacao"):
            attrs["condicao_fonte"] = fields["situacao"]
            cond = self.condition_from_text(fields["situacao"])
            if cond:
                attrs["condicao"] = cond
        comb = fields.get("combustivel doc.") or fields.get("combustivel")
        if comb:
            attrs["combustivel"] = comb
        if fields.get("origem"):
            # A fonte e' explicita aqui ("seguradora", "locadora", "empresa");
            # vale mais que a inferencia pelo comitente. Fora do mapa, fica
            # so' o texto dela: sem chute (RN-002).
            origem_fonte = unidecode(fields["origem"]).lower().strip()
            attrs["origem_fonte"] = origem_fonte
            if ORIGEM_FONTE.get(origem_fonte):
                attrs["origem"] = ORIGEM_FONTE[origem_fonte]
        if _int(fields.get("km")) is not None:
            attrs["km"] = _int(fields["km"])
        if _int(fields.get("fabricacao")):
            attrs["ano_fabricacao"] = _int(fields["fabricacao"])
        if _int(fields.get("modelo")):
            attrs["ano_modelo"] = _int(fields["modelo"])
        # Depois dos anos: o titulo refeito abaixo os usa.
        if fields.get("marca modelo") and "/" in fields["marca modelo"] and "marca" not in attrs:
            # Titulo colado na listagem ("GMMONTANA"): quando o detalhe traz a
            # forma "marca/modelo", ela corrige titulo, marca e modelo.
            mm = fields["marca modelo"].upper()
            attrs.update(self.brand_model(mm))
            years = (attrs.get("ano_fabricacao"), attrs.get("ano_modelo"))
            item.title = mm + (f" {years[0]}/{years[1]}" if all(years) else "")
        if _int(fields.get("potencia")):
            attrs["potencia_cv"] = _int(fields["potencia"])
        if _int(fields.get("cilindradas")):
            attrs["cilindradas"] = _int(fields["cilindradas"])
        if fields.get("acessorios"):
            attrs["acessorios"] = fields["acessorios"]
        media = self.parse_brl(fields.get("media mercado"))
        if media:
            # Referencia de mercado que a propria fonte publica; nao e' avaliacao
            # judicial nem o nosso preco de referencia (RN-010).
            attrs["valor_mercado_fonte"] = str(media)
        if fields.get("local leilao"):
            attrs["local_leilao"] = fields["local leilao"]
        local_lote = self.reject_unknown(fields.get("local lote"))
        if local_lote:
            item.location_text = local_lote
            if not item.city or not item.state:
                city, state = self.parse_city_state(local_lote)
                item.city, item.state = item.city or city, item.state or state

        # Observacao do lote (caixa amarela): unico texto livre da ficha.
        obs_box = soup.select_one("div[style*='FFF9C4'] td:last-child")
        obs = self.clean_text(obs_box.get_text(" ")) if obs_box else ""
        if obs:
            item.description = obs
            attrs["observacoes"] = obs

        page_text = self.clean_text(soup.get_text(" "))
        m = re.search(r"Lances\s*\((\d+)\)", page_text)
        lances = int(m.group(1)) if m else None
        if lances is not None:
            attrs["lances"] = lances
        m = re.search(r"Visualiza[cç][oõ]es\s*\((\d+)\)", page_text)
        if m:
            attrs["visualizacoes"] = int(m.group(1))
        comissao = soup.select_one("input#val_comissao")
        if comissao and comissao.get("value"):
            attrs["comissao_pct"] = comissao["value"]
        # "Despesas": valor fixo em R$ que a fonte soma ao lance junto com a
        # comissao na confirmacao do lance (lance + despesas + comissao).
        despesa = self.parse_brl((soup.select_one("input#val_despesa") or {}).get("value"))
        if despesa:
            attrs["despesas_fixas"] = str(despesa)
        # Ultimo lance do detalhe e' mais fresco que o card; so' quando houve lance.
        ultimo = self.parse_brl((soup.select_one("input#ultimo_valor") or {}).get("value"))
        if ultimo and lances:
            item.price, item.price_kind = ultimo, "lance_atual"

        if item.auction:
            if fields.get("data") and item.auction.sessions and item.auction.sessions[0].starts_at is None:
                item.auction.sessions[0].starts_at = self.parse_date_short(fields["data"])

        imgs: list[str] = []
        for img in soup.select("img.img_lote[src]"):
            u = self.site_url(img["src"])
            if u not in imgs:
                imgs.append(u)
        if imgs:
            item.images = imgs[:12]
            item.image_url = item.image_url or imgs[0]
        item.raw_payload = (item.raw_payload or "") + "\n<!-- detail -->\n" + html[:60_000]
