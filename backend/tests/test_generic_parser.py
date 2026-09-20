"""Parser genérico por seletores — o que permite cadastrar um leiloeiro novo
pelo admin, sem escrever código.

As fixtures vêm do Parque dos Leilões (capturado em 20/09/2026), que usa a
estrutura de duas etapas: a home lista pregões e cada pregão lista os lotes.
É o formato mais comum entre leiloeiros de porte médio.
"""
from app.scrapers.generic_html import GenericHtmlScraper

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
