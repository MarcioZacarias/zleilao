"""Pestana Leilões — portal React (SPA): o HTML de qualquer rota e' so' uma
casca de 5 KB; os dados vem de endpoints JSON no proprio dominio, que fazem
proxy para a API SGL (api.pestanaleiloes.com.br/sgl/v1):

  GET /api/v2/leilao                      pregoes em cartaz (com ids dos lotes)
  GET /api/v2/lote/por-leilao?idLeilao=N  TODOS os lotes do pregao, ja' completos
  GET /api/v2/lote/caracteristica/tipo    nome dos atributos (o lote so' traz o id)
  GET /api/v2/parceiro                    nome dos comitentes (o lote so' traz o id)

Nao ha' paginacao nem pagina de detalhe: `por-leilao` devolve as mesmas chaves
que o detalhe do site usa (`POST /api/v2/lote/por-ids`). Custo da coleta:
3 requisicoes fixas + 1 por pregao (~1 MB para 120 lotes).

Link publico do lote (rota da SPA; constante ROUTE="lote" no bundle):
  /lote/{idLeilao}/{idLote}/{slug(descricao)}   — pregao: /lote/{idLeilao}
Imagens: https://ged.pestanaleiloes.com.br/ged/{media}

Dados pessoais (RN-009): a placa ja' vem mascarada pela fonte ("I*****0") e o
arrematante tambem ("m***v"; nao e' copiado). O RENAVAM vem em claro na
descricao do bem e e' removido aqui. Comitente so' entra quando e' pessoa
juridica reconhecivel; partes de processo ("A X B") ficam de fora.

robots.txt: `Disallow:` vazio. Termos de Uso (/pdf/termo-uso.pdf) vedam ao
USUARIO cadastrado "software de inteligencia artificial ou robos para
navegacao, realizacao de ofertas e/ou operacionalizacao da PLATAFORMA".

Verificado em 17/10/2026.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from decimal import Decimal
from typing import Any, Optional

from unidecode import unidecode

from app.scrapers.base import BaseScraper, ScrapedAuction, ScrapedItem, ScrapedSession

logger = logging.getLogger("zleilao.scraper.pestana")

TIPO_BEM_VEICULOS = 421  # 461 = Bens Diversos, 462 = Imoveis

# subTipoBem da fonte -> slug de categoria do projeto. E' so' dica: o titulo decide.
SUBTIPO_MAP = {
    "automoveis": "carros", "camionetas": "carros", "motos": "motos",
    "caminhoes": "caminhoes", "reboques": "caminhoes", "onibus": "onibus",
    "trator": "maquinas-agricolas", "trator de rodas": "maquinas-agricolas",
    "motor_casa": "outros-veiculos",
}

# situacaoId do lote (constantes SITUACAO_LOTE_* do bundle da SPA). O id vem
# antes do texto porque "Nao vendido" contem "vendido" e enganaria o helper.
SITUACAO_MAP = {
    1: "open",       # Disponivel
    2: "open",       # Em pregao
    3: "sold",       # Vendido
    4: "closed",     # Nao vendido
    5: "open",       # Condicional: lance abaixo do minimo aguarda o comitente; lote segue em disputa
    6: "open",       # Aguardando repasse
    7: "withdrawn",  # Cancelado
    8: "withdrawn",  # Retirado
}
STATUS_TEXT_MAP = {
    "disponivel": "open", "em pregao": "open", "condicional": "open", "aguardando repasse": "open",
    "vendido": "sold", "nao vendido": "closed", "cancelado": "withdrawn", "retirado": "withdrawn",
}

# Nome do atributo na fonte -> chave em raw_attributes. As chaves com sufixo
# `_fonte` guardam o texto original; a versao sem sufixo e' o enum da categoria.
CARACTERISTICA_KEYS = {
    "marca": "marca", "modelo": "modelo", "versao": "versao", "ano": "ano_fabricacao",
    "mod.": "ano_modelo", "km": "km", "cor": "cor", "combustivel": "combustivel_fonte",
    "cambio": "cambio_fonte", "qtd. portas": "portas", "direcao": "direcao",
    "ar condicionado": "ar_condicionado", "chaves": "chaves", "estepe": "estepe",
    "blindagem": "blindagem", "monta": "monta", "condicao do bem": "condicao_bem",
    "origem": "origem_fonte", "tipo": "tipo", "placa": "placa_mascarada",
}

# Ids dos tipos de caracteristica vistos em 17/10/2026: usados so' quando o
# endpoint `caracteristica/tipo` falha, para a rodada nao perder marca/modelo.
CARACTERISTICA_TIPOS_FALLBACK = {
    1759180624569: "Marca", 1759180626601: "Modelo", 1759180628637: "Versão", 12345: "Ano",
    1759180634701: "Mod.", 1759180616374: "KM", 1759180623535: "Cor", 1759180641842: "Combustível",
    1759180621467: "Câmbio", 1759180639803: "Qtd. Portas", 1759180614340: "Direção",
    1759180612302: "Ar Condicionado", 1759180618408: "Chaves", 1759180620439: "Estepe",
    1759180637768: "Blindagem", 1759180609270: "Monta", 1759180636735: "Condição do bem",
    1759180608235: "Origem", 1759180506907: "Tipo", 1759180622503: "Placa",
}

# Valores da fonte -> enums de seed.VEHICLE_FIELDS (o que nao casa fica so' em `*_fonte`)
COMBUSTIVEL_MAP = {
    "gas/alc": "flex", "flex": "flex", "gasolina": "gasolina", "alcool": "etanol", "etanol": "etanol",
    "diesel": "diesel", "gnv": "gnv", "eletrico": "eletrico", "hibrido": "hibrido",
}
CAMBIO_MAP = {"manual": "manual", "automatico": "automatico", "automatizado": "automatizado", "cvt": "cvt"}
ORIGEM_MAP = {
    "retomado": "financeira", "sinistrado": "seguradora", "ativo imobilizado": "frota",
    "judicial": "judicial", "frota": "frota", "locadora": "locadora",
}
MONTA_MAP = {"pequena": "sinistro_recuperavel", "media": "sinistro_media_monta", "grande": "sinistro_grande_monta"}

# Marcas de pessoa juridica (texto sem acento, minusculo). Comitente sem
# nenhuma delas pode ser pessoa fisica e nao e' gravado (RN-009).
INSTITUTIONAL_RE = re.compile(
    r"\b(ltda|s\.?a\.?|s/a|eireli|epp|me|cia|banco|financ\w*|cooperativa|coop|sicredi|sicoob|"
    r"consorci\w*|segur\w*|fundo|municipio|prefeitura|associacao|companhia|comercio|industri\w*|"
    r"administradora|locadora|leasing|empreendimentos|participacoes|incorporacoes|transportes|"
    r"mineracao|credito|condominio|fundacao|instituto|universidade|hospital|grupo|holding|"
    r"distribuidora|servicos|engenharia|construcoes|construtora|sociedade|caixa|governo|estado|"
    r"uniao|tribunal|vara|juizo)\b"
)
# RENAVAM (9 a 11 digitos), com ou sem rotulo. Um telefone de 10/11 digitos
# cai junto, e tambem nao deveria estar na descricao.
RENAVAM_RE = re.compile(r"(?i)\brenavam\s*:?\s*\d{9,11}\b|\b\d{9,11}\b")


class PestanaScraper(BaseScraper):
    display_name = "Pestana Leilões"
    default_config = {
        "tipo_bem": TIPO_BEM_VEICULOS,  # 421 Veiculos | 461 Bens diversos | 462 Imoveis | null = todos
        "max_auctions": 10,             # pregoes por rodada, do mais proximo ao mais distante
        "include_private": False,       # pregoes privados/restritos: so' convidados dao lance
        "fetch_details": False,         # nao ha' pagina de detalhe: por-leilao ja' e' o lote completo
        "max_details_per_run": 0,
    }
    cdn_url = "https://ged.pestanaleiloes.com.br/ged/"

    @property
    def default_base_url(self) -> str:
        return "https://www.pestanaleiloes.com.br"

    def _json_headers(self) -> dict[str, str]:
        return {"Referer": f"{self.base_url}/"}

    @property
    def tipo_bem(self) -> Optional[int]:
        v = self.cfg("tipo_bem", TIPO_BEM_VEICULOS)
        if v in (None, "", "null", "todos", "all"):
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return TIPO_BEM_VEICULOS

    # ── coleta ───────────────────────────────────────────────────────

    async def scrape(self) -> list[ScrapedItem]:
        items: list[ScrapedItem] = []
        try:
            data = await self.fetch_json(f"{self.base_url}/api/v2/leilao", headers=self._json_headers())
        except Exception as exc:
            self.stats.errors += 1
            self.stats.mark_partial(f"falha ao listar pregoes: {exc}")
            logger.warning("[Pestana] falha ao listar pregoes: %s", exc)
            return items
        self.stats.pages += 1
        auctions = self.select_auctions(data)
        logger.info("[Pestana] %d pregoes em cartaz, %d com tipoBem=%s", len(data or []), len(auctions), self.tipo_bem)

        tipos = await self._load_tipos()
        parceiros = await self._load_parceiros()

        max_auctions = int(self.cfg("max_auctions", 10))
        for idx, auction in enumerate(auctions):
            if idx >= max_auctions:
                self.stats.mark_partial(f"parou em {max_auctions} pregoes de {len(auctions)} em cartaz")
                break
            await self.delay()
            try:
                lots = await self.fetch_json(
                    f"{self.base_url}/api/v2/lote/por-leilao",
                    params={"idLeilao": auction["id"]}, headers=self._json_headers(),
                )
            except Exception as exc:
                self.stats.errors += 1
                # Sem os lotes deste pregao a varredura nao e' completa (RN-005)
                self.stats.mark_partial(f"pregao {auction['id']} nao lido: {exc}")
                logger.warning("[Pestana] pregao %s falhou: %s", auction["id"], exc)
                continue
            self.stats.pages += 1
            parsed = self.parse_lots(lots, auction, tipos, parceiros)
            logger.info("[Pestana] pregao %s (%s): %d lotes, %d aproveitados",
                        auction["id"], auction.get("nome"), len(lots or []), len(parsed))
            items.extend(parsed)
        return items

    async def _load_tipos(self) -> dict[int, str]:
        try:
            data = await self.fetch_json(f"{self.base_url}/api/v2/lote/caracteristica/tipo", headers=self._json_headers())
            tipos = self.tipos_from_json(data)
            if tipos:
                return tipos
        except Exception as exc:
            self.stats.errors += 1
            logger.warning("[Pestana] caracteristica/tipo falhou, usando mapa fixo: %s", exc)
        self.stats.notes.append("nomes de caracteristicas pelo mapa fixo")
        return dict(CARACTERISTICA_TIPOS_FALLBACK)

    async def _load_parceiros(self) -> dict[int, str]:
        try:
            data = await self.fetch_json(f"{self.base_url}/api/v2/parceiro", headers=self._json_headers())
            return self.parceiros_from_json(data)
        except Exception as exc:
            self.stats.errors += 1
            logger.warning("[Pestana] parceiro falhou, lotes ficam sem comitente: %s", exc)
            return {}

    # ── pregoes ──────────────────────────────────────────────────────

    def select_auctions(self, data: list[dict]) -> list[dict]:
        """Pregoes do tipo de bem configurado, do mais proximo ao mais distante,
        para que uma rodada limitada por `max_auctions` cubra os eventos iminentes."""
        tipo = self.tipo_bem
        include_private = str(self.cfg("include_private", False)).lower() in ("1", "true", "yes")
        out: list[dict] = []
        for a in data or []:
            if not a.get("id"):
                continue
            if not include_private and (a.get("privado") or a.get("leilaoRestrito")):
                continue
            subtipos = a.get("subTipoBens") or []
            if tipo is not None and not any(self._int((s or {}).get("tipoBem")) == tipo for s in subtipos):
                continue
            out.append(a)
        out.sort(key=lambda a: a.get("data") or "9999")
        return out

    @staticmethod
    def tipos_from_json(data: Any) -> dict[int, str]:
        out: dict[int, str] = {}
        for t in data or []:
            if isinstance(t, dict) and t.get("id") is not None and t.get("nome"):
                out[int(t["id"])] = str(t["nome"])
        return out

    @staticmethod
    def parceiros_from_json(data: Any) -> dict[int, str]:
        out: dict[int, str] = {}
        for p in data or []:
            if isinstance(p, dict) and p.get("id") is not None and p.get("nome"):
                out[int(p["id"])] = str(p["nome"]).strip()
        return out

    def auction_from_json(self, a: dict, parceiros: dict[int, str] | None = None, lot: dict | None = None) -> ScrapedAuction:
        nome = self.clean_text(a.get("nome"))
        mod = unidecode(((a.get("modalidadeLeilao") or {}).get("descricao") or "")).lower()
        if "presencial" in mod and ("online" in mod or "eletron" in mod):
            modality = "hibrido"
        elif "presencial" in mod:
            modality = "presencial"
        else:
            modality = "online" if mod else None  # "Eletronico" e "Online" sao ambos pela internet

        partner_raw = self._partner_name(a, lot, parceiros or {})
        return ScrapedAuction(
            external_id=str(a["id"]),
            title=nome[:300] or None,
            auctioneer_name=self.clean_text(a.get("leiloeiro"))[:200] or None,
            committer_name=self.institutional_name(partner_raw),
            modality=modality,
            auction_type=self._auction_type(nome, partner_raw, lot),
            official_url=f"{self.base_url}/lote/{a['id']}",
            sessions=self._sessions(a, lot),
        )

    @staticmethod
    def _partner_name(a: dict, lot: dict | None, parceiros: dict[int, str]) -> Optional[str]:
        pid = ((lot or {}).get("parceiro") or {}).get("id")
        if pid is None and len(a.get("parceiros") or []) == 1:
            pid = (a["parceiros"][0] or {}).get("id")
        if pid is None:
            return None
        try:
            return parceiros.get(int(pid))
        except (TypeError, ValueError):
            return None

    @classmethod
    def institutional_name(cls, name: str | None) -> Optional[str]:
        """Devolve o nome so' quando e' claramente pessoa juridica. "A X B" sao
        partes de processo e podem ser pessoas fisicas: nunca entram."""
        if not name:
            return None
        text = " ".join(name.split())
        if re.search(r"\s[xX]\s", text):
            return None
        norm = unidecode(text).lower()
        return text[:200] if INSTITUTIONAL_RE.search(norm) else None

    @staticmethod
    def _auction_type(nome: str, partner_raw: str | None, lot: dict | None) -> str:
        n = unidecode(nome or "").lower()
        if "judicial" in n and "extrajudicial" not in n:
            return "judicial"
        if partner_raw and re.search(r"\s[xX]\s", partner_raw):
            return "judicial"  # comitente "Autor X Reu"
        origens = {unidecode(str(b.get("origem") or "")).lower() for b in (lot or {}).get("bens") or []}
        if "judicial" in origens:
            return "judicial"
        return "extrajudicial"

    def _sessions(self, a: dict, lot: dict | None) -> list[ScrapedSession]:
        lei = a.get("informacoesLei9514") or {}
        lot_lei = (lot or {}).get("informacoesLei9514") or {}
        sessions: list[ScrapedSession] = []
        # Lei 9.514 (alienacao fiduciaria de imovel): duas datas. Veiculo e' sessao unica.
        if lei.get("pertenceLei") and (lei.get("dataLeilao1") or lei.get("dataLeilao2")):
            if lei.get("dataLeilao1"):
                sessions.append(ScrapedSession(kind="1a_praca", starts_at=self.parse_datetime_br(lei["dataLeilao1"]),
                                               min_bid=self._money(lot_lei.get("valorLeilao1"))))
            if lei.get("dataLeilao2"):
                sessions.append(ScrapedSession(kind="2a_praca", starts_at=self.parse_datetime_br(lei["dataLeilao2"]),
                                               min_bid=self._money(lot_lei.get("valorLeilao2"))))
        else:
            sessions.append(ScrapedSession(kind="unica", starts_at=self.parse_datetime_br(a.get("data"))))
        return sessions

    # ── lotes ────────────────────────────────────────────────────────

    def parse_lots(self, lots: list[dict], auction: dict, tipos: dict[int, str] | None = None,
                   parceiros: dict[int, str] | None = None) -> list[ScrapedItem]:
        tipos = tipos or dict(CARACTERISTICA_TIPOS_FALLBACK)
        parceiros = parceiros or {}
        out: list[ScrapedItem] = []
        for lot in lots or []:
            try:
                item = self._map_lot(lot, auction, tipos, parceiros)
                if item:
                    out.append(item)
            except Exception as exc:  # um lote quebrado nao derruba o pregao
                self.stats.errors += 1
                logger.debug("[Pestana] lote ignorado: %s", exc)
        return out

    def _map_lot(self, lot: dict, auction: dict, tipos: dict[int, str], parceiros: dict[int, str]) -> Optional[ScrapedItem]:
        lot_id = lot.get("id")
        if not lot_id or lot.get("visivel") is False:
            return None
        bens = sorted(lot.get("bens") or [], key=lambda b: self._int(b.get("ordem")) or 0)
        tipo = self.tipo_bem
        if tipo is not None and not any(self._bem_tipo(b) == tipo for b in bens):
            return None
        principal = next((b for b in bens if tipo is None or self._bem_tipo(b) == tipo), bens[0] if bens else {})

        title = self._strip_ids(self.clean_text(lot.get("descricao"))) or self._strip_ids(self.clean_text(principal.get("descricao")))
        if not title:
            return None
        leilao_id = lot.get("leilao") or auction.get("id")
        slug = self.slugify(lot.get("descricao"))
        url = f"{self.base_url}/lote/{leilao_id}/{lot_id}" + (f"/{slug}" if slug else "")

        auction_obj = self.auction_from_json(auction, parceiros, lot)
        moeda = lot.get("tipoMoeda") or "REAL"
        price = None
        if moeda == "REAL":
            price = self._money(lot.get("lanceInicial")) or self._money(lot.get("lanceMinimo")) or self._money(lot.get("valorInicial"))
        lot_lei = lot.get("informacoesLei9514") or {}
        price_second = self._money(lot_lei.get("valorLeilao2")) if moeda == "REAL" else None

        raw = self._attributes(principal, tipos)
        lance_atual = self._money(lot.get("valor"))
        raw.update({
            "sub_tipo_bem": (principal.get("subTipoBem") or {}).get("nome"),
            "n_bens": len(bens) if len(bens) > 1 else None,
            "lance_atual": str(lance_atual) if lance_atual and moeda == "REAL" else None,
            "incremento_minimo": lot.get("incrementoMinimo") or None,
            "comissao_pct": self._commission(lot, principal),
            "taxa_administrativa": self._admin_fee(lot, principal, price, raw.get("ano_fabricacao")),
            "ipva_pago": True if lot.get("seloIpvaPago") else None,
            "liga_partida": True if lot.get("seloLigaPartida") else None,
            "permite_financiamento": True if lot.get("seloFinanciamento") else None,
            "enchente": True if lot.get("tarjaEnchente") else None,
            "situacao": lot.get("status"),
            "moeda": moeda if moeda != "REAL" else None,
            "comitente": auction_obj.committer_name,
            "tipo_leilao": auction_obj.auction_type,
            "modalidade": (auction.get("modalidadeLeilao") or {}).get("descricao"),
        })
        raw = {k: v for k, v in raw.items() if v not in (None, "", [], {})}

        city = self.reject_unknown(self._name(principal.get("cidade")))
        state = self.reject_unknown(self._name(principal.get("estado")))
        if not city and not state and len(auction.get("exposicao") or []) == 1:
            # Pregao com um unico patio: o bem esta' la'. Com varios, nao da' para saber.
            expo = auction["exposicao"][0] or {}
            city, state = self.reject_unknown(expo.get("cidade")), self.reject_unknown(expo.get("estado"))
        state = state.strip().upper()[:2] if state else None
        city = self.clean_text(city) or None
        location_text = self.clean_text(((principal.get("exposicao") or {}).get("endereco"))) or None

        images = self._images(bens)
        if lot.get("exibirMensagemRetirada") and lot.get("mensagemRetirada"):
            status = "withdrawn"
        else:
            status = self.status_from_situacao(lot.get("situacaoId"), lot.get("status"))

        return ScrapedItem(
            external_id=str(lot_id),
            title=title[:300],
            official_url=url,
            price=price,
            price_kind="lance_inicial",
            price_second=price_second,
            lot_number=str(lot["numero"]).strip() if lot.get("numero") not in (None, "") else None,
            city=city,
            state=state,
            location_text=location_text,
            image_url=images[0] if images else None,
            images=images[:12],
            description=self._describe(lot, bens, tipos, auction_obj.committer_name, raw),
            raw_attributes=raw,
            category_hint=self._category_hint(principal),
            status_hint=status,
            auction=auction_obj,
            raw_payload=json.dumps(lot, ensure_ascii=False),
        )

    # ── helpers de lote ──────────────────────────────────────────────

    @staticmethod
    def _int(v: Any) -> Optional[int]:
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _bem_tipo(cls, bem: dict) -> Optional[int]:
        return cls._int(((bem.get("tipoBem") or {}).get("id")))

    @staticmethod
    def _name(v: Any) -> Optional[str]:
        if isinstance(v, dict):
            return v.get("name") or v.get("nome")
        return str(v) if v else None

    @classmethod
    def _money(cls, value: Any) -> Optional[Decimal]:
        if isinstance(value, bool) or value in (None, "", 0):
            return None
        d = cls.parse_brl(value)
        return d if d and d > 0 else None

    @staticmethod
    def _brl(value: Any) -> str:
        """Decimal('2350.00') -> 'R$ 2.350,00' (texto da descricao, legivel para o usuario)."""
        d = Decimal(str(value)).quantize(Decimal("0.01"))
        inteiro, cents = f"{d:.2f}".split(".")
        inteiro = f"{int(inteiro):,}".replace(",", ".")
        return f"R$ {inteiro},{cents}"

    @staticmethod
    def _strip_ids(text: str) -> str:
        return re.sub(r"\s{2,}", " ", RENAVAM_RE.sub("", text or "")).strip(" -,;")

    @staticmethod
    def slugify(text: str | None) -> str:
        """Mesma funcao do bundle da SPA: NFD sem acentos, [^a-z0-9]+ -> '-', 100 chars."""
        if not text:
            return ""
        t = unicodedata.normalize("NFD", str(text))
        t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn").lower().strip()
        return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:100].rstrip("-")

    @staticmethod
    def status_from_situacao(situacao_id: Any, status_text: str | None) -> str:
        sid = PestanaScraper._int(situacao_id)
        if sid in SITUACAO_MAP:
            return SITUACAO_MAP[sid]
        text = unidecode(status_text or "").strip().lower()
        return STATUS_TEXT_MAP.get(text) or BaseScraper.status_from_text(text) or "open"

    def _category_hint(self, bem: dict) -> Optional[str]:
        sub = unidecode(((bem.get("subTipoBem") or {}).get("nome")) or "").strip().lower()
        if self._bem_tipo(bem) == TIPO_BEM_VEICULOS:
            return SUBTIPO_MAP.get(sub, "veiculos")
        return sub or None

    def _attributes(self, bem: dict, tipos: dict[int, str]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for c in bem.get("caracteristicas") or []:
            nome = c.get("nome") or tipos.get(self._int(c.get("tipo")))
            valor = self.clean_text(str(c.get("valor") or ""))
            if not nome or not valor:
                continue
            key = CARACTERISTICA_KEYS.get(unidecode(nome).strip().lower())
            if not key:
                continue
            if key in ("ano_fabricacao", "ano_modelo"):
                m = re.search(r"\b(?:19|20)\d{2}\b", valor)
                out[key] = int(m.group(0)) if m else None
            elif key == "km":
                digits = re.sub(r"\D", "", valor)  # "Indisponivel" vira None
                out[key] = int(digits) if digits else None
            else:
                out[key] = self.reject_unknown(valor)
        if out.get("combustivel_fonte"):
            out["combustivel"] = COMBUSTIVEL_MAP.get(unidecode(out["combustivel_fonte"]).lower())
        if out.get("cambio_fonte"):
            out["cambio"] = CAMBIO_MAP.get(unidecode(out["cambio_fonte"]).lower())
        origem_src = out.get("origem_fonte") or bem.get("origem")
        if origem_src:
            out["origem_fonte"] = origem_src
            out["origem"] = ORIGEM_MAP.get(unidecode(str(origem_src)).lower())
        # Condicao: a fonte classifica a monta do sinistro. "Nao se aplica" nao
        # afirma que o bem e' normal — isso fica para o normalizador decidir.
        cond_bem = unidecode(out.get("condicao_bem") or "").lower()
        monta = unidecode(out.get("monta") or "").lower()
        if "sucata" in cond_bem:
            out["condicao"] = "sucata"
        else:
            out["condicao"] = next((v for k, v in MONTA_MAP.items() if k in monta), None)
        if out.get("placa_mascarada") and "*" not in out["placa_mascarada"]:
            del out["placa_mascarada"]  # placa em claro: nao gravar; o normalizador mascara o texto
        return {k: v for k, v in out.items() if v not in (None, "")}

    @classmethod
    def _commission(cls, lot: dict, bem: dict) -> Optional[float]:
        va = lot.get("valoresAdicionais") or {}
        for b in va.get("bens") or []:
            if cls._int(b.get("idBem")) == cls._int(bem.get("id")) and b.get("percentualComissao"):
                return b["percentualComissao"]
        return va.get("percentualComissao") or None

    @classmethod
    def _admin_fee(cls, lot: dict, bem: dict, price: Decimal | None, ano: int | None) -> Optional[str]:
        """Taxa administrativa por faixa (tipo de bem, valor e ano). So' devolve
        quando uma unica faixa casa: ambiguidade vira 'nao informado'."""
        va = lot.get("valoresAdicionais") or {}
        if va.get("valorTaxaAdministrativa"):
            return str(cls.parse_brl(va["valorTaxaAdministrativa"]))
        sub_id = cls._int((bem.get("subTipoBem") or {}).get("id"))
        faixas = (va.get("taxasAdministrativas") or {}).get("taxasPorFaixaValor") or []
        hits = []
        for f in faixas:
            if not f.get("valorTaxa"):
                continue
            tipo = cls._int(f.get("idTipoBem"))
            if tipo not in (None, 0, sub_id):
                continue
            if price is not None and f.get("valorFinal") is not None:
                lo, hi = Decimal(str(f.get("valorInicial") or 0)), Decimal(str(f["valorFinal"]))
                if not (lo <= price <= hi):
                    continue
            if ano and f.get("anoInicial") and f.get("anoFinal") and not (f["anoInicial"] <= ano <= f["anoFinal"]):
                continue
            hits.append(f["valorTaxa"])
        return str(cls.parse_brl(hits[0])) if len(hits) == 1 else None

    def _images(self, bens: list[dict]) -> list[str]:
        out: list[str] = []
        for b in bens:
            imgs = sorted(b.get("imagens") or [], key=lambda i: (not i.get("destaque"), self._int(i.get("ordem")) or 0))
            for i in imgs:
                media = i.get("media") or i.get("original") or i.get("pequena")
                if not media:
                    continue
                url = media if str(media).startswith("http") else self.cdn_url + str(media)
                if url not in out:
                    out.append(url)
        return out

    def _describe(self, lot: dict, bens: list[dict], tipos: dict[int, str], committer: str | None, raw: dict) -> str:
        parts: list[str] = []
        for b in bens:
            for field in ("descricao", "observacao"):
                txt = self._strip_ids(self.clean_text(b.get(field)))
                if txt:
                    parts.append(txt if txt.endswith(".") else txt + ".")
            feats = []
            for c in b.get("caracteristicas") or []:
                nome = c.get("nome") or tipos.get(self._int(c.get("tipo")))
                valor = self.clean_text(str(c.get("valor") or ""))
                if nome and valor and unidecode(nome).lower() != "placa":
                    feats.append(f"{nome}: {valor}")
            if feats:
                parts.append("Características: " + "; ".join(feats) + ".")
        if lot.get("tarjaEnchente"):
            parts.append("Veículo sinalizado pela fonte como atingido por enchente.")
        if lot.get("seloLigaPartida"):
            parts.append("Liga e dá partida (teste de ignição no pátio do leiloeiro).")
        if lot.get("seloIpvaPago"):
            parts.append("IPVA do ano vigente pago.")
        if lot.get("exibirMensagemRetirada") and lot.get("mensagemRetirada"):
            parts.append(self.clean_text(lot["mensagemRetirada"]))
        if committer:
            parts.append(f"Comitente: {committer}.")
        if raw.get("comissao_pct"):
            parts.append(f"Comissão do leiloeiro: {raw['comissao_pct']}%.")
        if raw.get("taxa_administrativa"):
            parts.append(f"Taxa administrativa: {self._brl(raw['taxa_administrativa'])}.")
        if lot.get("status"):
            parts.append(f"Situação: {lot['status']}.")
        return " ".join(parts)
