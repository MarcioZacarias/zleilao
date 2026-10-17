"""Parser genérico por seletores — o que permite cadastrar um leiloeiro novo
pelo admin, sem escrever código.

Duas fontes reais servem de fixture, ambas na estrutura de duas etapas (a
home lista pregões e cada pregão lista os lotes), que é o formato mais comum
entre leiloeiros de porte médio:

- Parque dos Leilões (capturado em 20/09/2026): o caso básico.
- Casa de Leilões, Campo Grande/MS (capturado em 17/10/2026): exercita as
  extensões — datas sem ano na capa, cabeçalho do pregão com abertura e
  encerramento (`page_fields`), cidade sem UF (`default_state`), judicial ou
  extrajudicial decidido pelo título (`auction_type: auto`), `map` e `sub`
  nos campos.
"""
from datetime import date, datetime
from decimal import Decimal

import pytest

from app.scrapers.generic_html import GenericHtmlScraper, parse_datetime_sem_ano

CONFIG = {
    "base_url": "https://www.parquedosleiloes.com.br",
    "auction_list": {
        "url": "/leiloes",
        "item_selector": ".auction-card",
        "link": {"selector": "a[href*='/leilao/']", "attr": "href"},
        "id_regex": r"/leilao/(\d+)",
        "title": {"selector": ".name"},
        "max_auctions": 20,
    },
    "item_selector": ".auction-lot-card",
    "fields": {
        "external_id": {"selector": "a[href*='/lote/']", "attr": "href", "regex": r"/lote/(\d+)"},
        "title": {"selector": ".name"},
        "url": {"selector": "a[href*='/lote/']", "attr": "href"},
        "image": {"selector": "img", "attr": "src"},
        "description": {"selector": ".comments-text p"},
        "status": {"selector": ".lot-status-color"},
        "lot_number": {"selector": ".badge-nr-lot b"},
    },
    "category_hint": "diversos",
    "auction_type": "extrajudicial",
}


def _scraper() -> GenericHtmlScraper:
    return GenericHtmlScraper(source_id=99, base_url=CONFIG["base_url"], config=CONFIG)


def test_parse_auction_list(fixture):
    """Primeira etapa: descobrir os pregões."""
    auctions = _scraper().parse_auction_list(fixture("generic_auctions.html"))
    assert len(auctions) >= 1
    a = auctions[0]
    assert a["external_id"].isdigit()
    assert a["url"].startswith("https://www.parquedosleiloes.com.br/leilao/")
    # o mesmo pregão aparece em vários links (detalhes, edital) e não duplica
    assert len({x["external_id"] for x in auctions}) == len(auctions)


def test_parse_lots_dentro_do_pregao(fixture):
    """Segunda etapa: os lotes herdam o pregão a que pertencem."""
    s = _scraper()
    auction = {"external_id": "1491", "url": "https://www.parquedosleiloes.com.br/leilao/1491/detalhes",
               "title": "Leilão de Diversos", "date": "25/09/2026 10:00", "modality": "Online"}
    items = s.parse_listing(fixture("generic_lots.html"), auction=auction)
    assert len(items) >= 2
    it = items[0]
    assert it.external_id.isdigit()
    assert "/lote/" in it.official_url
    assert it.title
    assert it.description and len(it.description) > 10
    assert it.lot_number
    # o pregão vem da primeira etapa, não do card do lote
    assert it.auction.external_id == "1491"
    assert it.auction.title == "Leilão de Diversos"
    assert it.auction.modality == "online"
    assert it.auction.sessions[0].starts_at is not None
    assert it.status_hint == "closed"      # "Lote encerrado"


def test_lotes_sem_pregao_nao_quebram(fixture):
    """Modo lista direta: sem `auction`, cada lote vira seu próprio pregão."""
    items = _scraper().parse_listing(fixture("generic_lots.html"))
    assert items
    assert items[0].auction.external_id.startswith("lot-")


def test_config_default_e_valida():
    """O admin pré-preenche o config com o default: ele precisa ser um ponto
    de partida coerente, não um esqueleto quebrado."""
    cfg = GenericHtmlScraper.default_config
    assert "item_selector" in cfg and "fields" in cfg
    for key in ("external_id", "title", "url"):
        assert key in cfg["fields"], f"campo obrigatorio ausente no default: {key}"


# ── Casa de Leilões (Campo Grande/MS) ────────────────────────────────

CASA_CONFIG = {
    "base_url": "https://www.casadeleiloes.com.br",
    "auction_list": {
        "url": "/",
        # o id 1 é o "SIMULADOR DE LEILÃO", que não é pregão
        "item_selector": "a[href^='/leilao/']:not([href$='/1'])",
        "link": {"attr": "href"},
        "id_regex": r"/leilao/[^/]+/(\d+)$",
        "title": {"selector": ".box-titulo"},
        # a capa só dá o encerramento, e sem ano: "Encerra a partir de: 21/10 16:00"
        "end_date": {"selector": ".box-subtitulo strong"},
        "max_auctions": 20,
    },
    # o cabeçalho do pregão é completo: abertura, encerramento e modalidade
    "page_fields": {
        "title": {"selector": "h3"},
        "date": {"selector": ".leilao-dados", "regex": r"Abertura\s*(\d{2}/\d{2}/\d{4}\s*\d{1,2}:\d{2})"},
        "end_date": {"selector": ".leilao-dados", "regex": r"Encerra[^:]*:\s*(\d{2}/\d{2}/\d{4}\s*\d{1,2}:\d{2})"},
        "modality": {"selector": ".leilao-dados", "regex": r"Modalidade\s*([A-Za-z]+)"},
    },
    "item_selector": "a.lote-lista",
    "fields": {
        "external_id": {"attr": "href", "regex": r"/(\d+)$"},
        "title": {"selector": "blockquote"},
        "url": {"attr": "href"},
        "price": {"selector": ".lote-lista-direita span.botao-azul[style*='display: block']"},
        # a listagem traz a miniatura (…190332p.jpeg); sem o "p" é a foto cheia
        "image": {"selector": ".lazy", "attr": "data-src", "sub": [r"p\.(jpe?g|png)$", r".\1"]},
        "location": {"selector": ".col-md-6 b"},
        "lot_number": {"selector": ".col-md-6", "regex": r"Lote:\s*(\d+)"},
        "status": {"selector": ".circulo-item-grande", "map": {"em leilao": "open"}},
        # "MOTOCICLETA » CIRCULAÇÃO", "VEÍCULO » CIRCULAÇÃO", "BENS MÓVEIS » MÓVEIS COMERCIAIS"
        "category": {"selector": ".col-md-6", "regex": r"^(.*?)\s*»",
                     "map": {"veiculo": "veiculos", "motocicleta": "motos", "caminhao": "caminhoes",
                             "sucata": "sucatas", "imovel": "imoveis"}},
    },
    "category_hint": "diversos",
    "auction_type": "auto",
    "default_state": "MS",
    "fetch_details": False,
    "detail": {"images_regex": r"/envios/leilao_lote_imagem\d+\.jpe?g"},
}


@pytest.fixture
def casa(monkeypatch) -> GenericHtmlScraper:
    # a capa não traz o ano: a data de referência precisa ser a da captura
    monkeypatch.setattr(GenericHtmlScraper, "_today", lambda self: date(2026, 10, 17))
    return GenericHtmlScraper(source_id=98, base_url=CASA_CONFIG["base_url"], config=CASA_CONFIG)


def test_casa_capa_lista_pregoes_sem_o_simulador(fixture, casa):
    auctions = casa.parse_auction_list(fixture("casa_home.html"))
    ids = [a["external_id"] for a in auctions]
    assert len(ids) == 12
    assert "1" not in ids                      # simulador excluído pelo seletor
    assert ids[0] == "14695" and "14703" in ids and "14699" in ids
    a = auctions[0]
    assert a["url"] == "https://www.casadeleiloes.com.br/leilao/leilao-de-bens-moveis-de-extrajudicial-ms/14695"
    assert a["title"] == "LEILÃO DE BENS MÓVEIS - EXTRAJUDICIAL (MS)"
    assert a["end_date"].startswith("Encerra a partir de: 21/10 16:00")
    assert a["date"] is None                   # a capa não dá a abertura


def test_casa_lotes_com_cabecalho_do_pregao(fixture, casa):
    """Etapa 2: os lotes herdam o pregão e o cabeçalho da página (`page_fields`)
    sobrepõe o resumo da capa."""
    auction = next(a for a in casa.parse_auction_list(fixture("casa_home.html")) if a["external_id"] == "14703")
    items = casa.parse_listing(fixture("casa_leilao.html"), auction=auction)
    assert len(items) == 10
    it = items[0]
    assert it.external_id == "67019"
    assert it.lot_number == "001"
    assert it.title.startswith("TOYOTA ETIOS SD PLATINUM - 2015/2016 (PRETA)")
    assert it.official_url == ("https://www.casadeleiloes.com.br/lote/lote-001/"
                               "toyota-etios-sd-platinum-2015-2016-preta-para-circular-com-direito-a-documentacao/67019")
    assert it.price == Decimal("11975.00")     # só o span visível ("Lance inicial")
    assert it.status_hint == "open"            # "EM LEILÃO" via `map`
    # cidade sem UF na fonte: `default_state` completa
    assert (it.city, it.state) == ("Campo Grande", "MS")
    assert it.location_text == "CAMPO GRANDE"
    # miniatura virou foto cheia (`sub`) e o caminho relativo virou absoluto
    assert it.image_url == "https://www.casadeleiloes.com.br/envios/leilao_lote_imagem190332.jpeg"
    assert it.images == [it.image_url]
    # categoria vem do card, não de uma dica única da config
    assert it.category_hint == "veiculos"
    assert {x.category_hint for x in items} == {"veiculos", "motos"}
    # pregão: id e URL da capa; título, datas e modalidade do cabeçalho da página
    a = it.auction
    assert a.external_id == "14703"
    assert a.official_url.endswith("/leilao/veiculos-para-circulacao-de-campo-grande-ms/14703")
    assert a.title == "VEÍCULOS PARA CIRCULAÇÃO - CAMPO GRANDE (MS)"
    assert a.modality == "online"
    assert a.auction_type == "extrajudicial"   # DETRAN, sem vara no título
    assert len(a.sessions) == 1
    assert a.sessions[0].starts_at == datetime(2026, 10, 16, 10, 0)
    assert a.sessions[0].ends_at == datetime(2026, 11, 3, 16, 0)
    # o id de cada lote é único e todos apontam para o mesmo pregão
    assert len({x.external_id for x in items}) == 10
    assert {x.auction.external_id for x in items} == {"14703"}


def test_casa_sem_page_fields_usa_a_capa_com_ano_assumido(fixture, casa):
    """Sem `page_fields`, vale o que a capa trouxe: só o encerramento, sem ano,
    que ganha o ano corrente."""
    casa.config = {**CASA_CONFIG, "page_fields": {}}
    auction = next(a for a in casa.parse_auction_list(fixture("casa_home.html")) if a["external_id"] == "14703")
    items = casa.parse_listing(fixture("casa_leilao.html"), auction=auction)
    s = items[0].auction.sessions[0]
    assert s.starts_at is None
    assert s.ends_at == datetime(2026, 11, 3, 16, 0)
    assert items[0].auction.title == "VEÍCULOS PARA CIRCULAÇÃO - CAMPO GRANDE (MS)"


def test_casa_tipo_de_pregao_pelo_titulo(casa):
    """`auction_type: auto` — a Casa mistura DETRAN, prefeitura e varas no mesmo
    site; o título do pregão é o que separa judicial de extrajudicial."""
    assert casa.resolve_auction_type("14ª VARA CÍVEL - CAMPO GRANDE (MS)") == "judicial"
    assert casa.resolve_auction_type("VARA ÚNICA DO TRABALHO - CORUMBÁ (MS)") == "judicial"
    assert casa.resolve_auction_type("2ª VARA DO JUIZADO ESPECIAL CENTRAL - CAMPO GRANDE (MS)") == "judicial"
    assert casa.resolve_auction_type(
        "COMISSÃO DE ALIENAÇÃO DE BENS APREENDIDOS EM AÇÕES PENAIS - CORREGEDORIA GERAL DE JUSTIÇA TJ/MS") == "judicial"
    assert casa.resolve_auction_type("LEILÃO DE BENS MÓVEIS - EXTRAJUDICIAL (MS)") == "extrajudicial"
    assert casa.resolve_auction_type("VEÍCULOS PARA CIRCULAÇÃO - CAMPO GRANDE (MS)") == "extrajudicial"
    assert casa.resolve_auction_type(None) == "extrajudicial"
    # config fixa continua mandando, como antes da extensão
    casa.config = {**CASA_CONFIG, "auction_type": "judicial"}
    assert casa.resolve_auction_type("VEÍCULOS PARA CIRCULAÇÃO") == "judicial"


def test_default_state_nao_inventa_uf_sem_cidade(fixture, casa):
    """RN-002: a UF padrão completa a cidade, não substitui o 'não informado'."""
    casa.config = {**CASA_CONFIG, "fields": {**CASA_CONFIG["fields"], "location": {"selector": ".nao-existe"}}}
    items = casa.parse_listing(fixture("casa_leilao.html"))
    assert items and items[0].city is None and items[0].state is None


def test_detalhe_imagens_relativas_viram_absolutas(fixture, casa):
    """A página do lote referencia as fotos por caminho relativo e repete a
    mesma foto no carrossel e no modal: absoluta, sem repetição."""
    html = """<div class="carousel"><img src="/envios/leilao_lote_imagem190295.jpeg">
    <img src="/envios/leilao_lote_imagem190296.jpeg"><img src="/envios/leilao_lote_imagem190295.jpeg"></div>
    <div class="desc">Descrição: Endereço para visitação: R. Barreiras, 221.</div>"""
    casa.config = {**CASA_CONFIG, "detail": {**CASA_CONFIG["detail"], "description_selector": ".desc"}}
    it = casa.parse_listing(fixture("casa_leilao.html"))[0]
    casa.enrich_from_detail(it, html)
    assert it.images == ["https://www.casadeleiloes.com.br/envios/leilao_lote_imagem190295.jpeg",
                         "https://www.casadeleiloes.com.br/envios/leilao_lote_imagem190296.jpeg"]
    assert it.description.startswith("Descrição: Endereço para visitação")


@pytest.mark.parametrize("text,today,expected", [
    ("Encerra a partir de: 21/10 16:00 (Horário de Brasília)", date(2026, 10, 17), datetime(2026, 10, 21, 16, 0)),
    ("Encerra: 04/11 11:03 2ª praça: 11/11 11:03", date(2026, 10, 17), datetime(2026, 11, 4, 11, 3)),
    ("Encerra: 31/12 10:00", date(2026, 10, 17), datetime(2026, 12, 31, 10, 0)),
    # virada de ano: em dezembro, "05/01" é janeiro do ano seguinte
    ("05/01 10:00", date(2026, 12, 20), datetime(2027, 1, 5, 10, 0)),
    # passou há poucos dias: ainda é o ano corrente (pregão recém-encerrado)
    ("20/09 10:00", date(2026, 10, 17), datetime(2026, 9, 20, 10, 0)),
    # passou há mais de 30 dias: só pode ser o ano que vem
    ("01/09", date(2026, 10, 17), datetime(2027, 9, 1, 0, 0)),
    ("16/10/2026 10:00", date(2026, 10, 17), None),    # data completa não é deste helper
    ("sem data", date(2026, 10, 17), None),
    ("", date(2026, 10, 17), None),
    ("31/02 10:00", date(2026, 10, 17), None),         # dia inválido
])
def test_data_sem_ano(text, today, expected):
    assert parse_datetime_sem_ano(text, today) == expected


def test_parse_date_prefere_data_completa(casa):
    assert casa.parse_date("Abertura 16/10/2026 10:00") == datetime(2026, 10, 16, 10, 0)
    assert casa.parse_date("Encerra: 21/10 16:00") == datetime(2026, 10, 21, 16, 0)
    assert casa.parse_date(None) is None


def test_map_e_sub_nos_campos(casa):
    from bs4 import BeautifulSoup
    el = BeautifulSoup('<div><span class="s">Em Leilão</span><img src="/f/12p.jpeg"></div>', "lxml")
    assert casa._extract(el, {"selector": ".s", "map": {"em leilao": "open"}}) == "open"
    # sem correspondência o texto passa como veio
    assert casa._extract(el, {"selector": ".s", "map": {"vendido": "sold"}}) == "Em Leilão"
    assert casa._extract(el, {"selector": "img", "attr": "src", "sub": [r"p\.(jpe?g)$", r".\1"]}) == "/f/12.jpeg"
