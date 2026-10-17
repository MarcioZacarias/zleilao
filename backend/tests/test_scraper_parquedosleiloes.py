"""Parque dos Leilões: fixtures capturadas em 17/10/2026.

- parquedosleiloes_auctions.html: /leiloes-judiciais?searchMode=judicial&type_id=1 (2 abertos, 10 encerrados)
- parquedosleiloes_listing.html: /leilao/1499/detalhes (BANCOS E FINANCEIRAS, 28 lotes, 4 paginas)
- parquedosleiloes_listing_judicial.html: /leilao/1510/detalhes (judicial, 1ª praca, 1 lote)
- parquedosleiloes_detail.html: /leilao/1508/lote/84050 (encerrado com lance)
- parquedosleiloes_detail_open.html: /leilao/1510/lote/84164 (aberto, judicial)
"""
import asyncio
from datetime import datetime
from decimal import Decimal

from app.scrapers.parquedosleiloes import AuctionRef, ParqueDosLeiloesScraper, parse_date_pt


def _scraper(config: dict | None = None) -> ParqueDosLeiloesScraper:
    return ParqueDosLeiloesScraper(source_id=9, base_url=None, config=config or {})


def test_parse_date_pt():
    assert parse_date_pt("3 set 2026, 13:00") == datetime(2026, 9, 3, 13, 0)
    assert parse_date_pt("3 de set de 2026 às 13:00") == datetime(2026, 9, 3, 13, 0)
    assert parse_date_pt("9 nov 2026, 14:00") == datetime(2026, 11, 9, 14, 0)
    assert parse_date_pt("Lances On-Line até 28/10/26 14:00:00") == datetime(2026, 10, 28, 14, 0)
    assert parse_date_pt("2026-08-29 12:00:00") == datetime(2026, 8, 29, 12, 0)
    assert parse_date_pt(None) is None


def test_auction_list(fixture):
    s = _scraper()
    html = fixture("parquedosleiloes_auctions.html")
    refs = s.parse_auction_list(html, judicial=True)
    assert len(refs) == 12
    first = refs[0]
    assert first.external_id == "1510"
    assert first.url == "https://www.parquedosleiloes.com.br/leilao/1510/detalhes"
    assert first.status_hint == "open"
    assert first.starts_at == datetime(2026, 11, 9, 14, 0)
    assert first.category == "VEICULOS"
    assert first.judicial
    assert [r.status_hint for r in refs[:3]] == ["open", "open", "closed"]
    assert s._has_next(html)


def test_collect_auctions_stops_at_first_closed(fixture):
    """A listagem e' por data decrescente: o primeiro encerrado encerra a
    varredura sem torna-la parcial, porque todos os abertos ja' foram vistos."""
    s = _scraper({"auction_lists": ["/leiloes-judiciais?searchMode=judicial&type_id=1"]})
    calls: list[str] = []

    async def fake_fetch(url, params=None, headers=None):
        calls.append(url)
        return fixture("parquedosleiloes_auctions.html")

    s.fetch = fake_fetch  # type: ignore[method-assign]
    refs = asyncio.run(s.collect_auctions())
    assert [r.external_id for r in refs] == ["1510", "1507"]
    assert calls == ["https://www.parquedosleiloes.com.br/leiloes-judiciais?searchMode=judicial&type_id=1"]
    assert s.stats.complete
    assert s.stats.pages == 1

    # Com include_closed a pagina inteira entra e a paginacao segue ate' o limite.
    s2 = _scraper({"auction_lists": ["/leiloes-judiciais?searchMode=judicial&type_id=1"],
                   "include_closed": True, "max_list_pages": 2, "max_auctions": 50})
    s2.fetch = fake_fetch  # type: ignore[method-assign]
    s2.delay = _no_delay  # type: ignore[method-assign]
    refs2 = asyncio.run(s2.collect_auctions())
    assert len(refs2) == 12  # ids repetidos entre paginas (mesmo fixture) sao deduplicados
    assert not s2.stats.complete


async def _no_delay():
    return None


def test_auction_page_extrajudicial(fixture):
    s = _scraper()
    ref = AuctionRef(external_id="1499", url="https://www.parquedosleiloes.com.br/leilao/1499/detalhes",
                     title="BANCOS E FINANCEIRAS", status_hint="closed", category="VEICULOS")
    ctx = s.parse_auction_page(fixture("parquedosleiloes_listing.html"), ref)
    a = ctx.auction
    assert a.external_id == "1499"
    assert a.title == "BANCOS E FINANCEIRAS"
    assert a.auction_type == "extrajudicial"
    assert a.committer_name is None
    assert ctx.praca_kind == "unica"
    assert [x.kind for x in a.sessions] == ["unica"]
    assert a.sessions[0].starts_at == datetime(2026, 9, 3, 13, 0)
    assert ctx.category == "VEICULOS"
    # patio de exposicao citado na visitacao
    assert (ctx.city, ctx.state) == ("Brasília", "DF")
    assert ctx.location_text and "TAGUATINGA" in ctx.location_text
    assert ctx.price_second is None


def test_auction_page_judicial(fixture):
    s = _scraper()
    ref = AuctionRef(external_id="1510", url="https://www.parquedosleiloes.com.br/leilao/1510/detalhes",
                     title="x", status_hint="open", judicial=True)
    ctx = s.parse_auction_page(fixture("parquedosleiloes_listing_judicial.html"), ref)
    a = ctx.auction
    assert a.auction_type == "judicial"
    assert a.title.endswith("BRASÍLIA - 1ª PRAÇA")
    assert a.committer_name == "2ª VARA DE EXECUÇÃO DE TÍTULOS EXTRAJUDICIAIS E CONFLITOS ARBITRAIS DE BRASÍLIA"
    assert ctx.praca_kind == "1a_praca"
    kinds = [(x.kind, x.starts_at, x.min_bid) for x in a.sessions]
    assert kinds == [
        ("1a_praca", datetime(2026, 11, 9, 14, 0), Decimal("5000.00")),
        ("2a_praca", datetime(2026, 11, 12, 14, 0), Decimal("2500.00")),  # "R$ 2 .500,00" na fonte
    ]
    assert ctx.price_second == Decimal("2500.00")
    assert ctx.extra["processo"] == "0704908-50.2024.8.07.0001"
    # visitacao vazia: sem cidade da pagina (o default da config entra no lote)
    assert (ctx.city, ctx.state) == (None, None)


def test_lots_listing(fixture):
    s = _scraper()
    html = fixture("parquedosleiloes_listing.html")
    ref = AuctionRef(external_id="1499", url="https://www.parquedosleiloes.com.br/leilao/1499/detalhes",
                     title="BANCOS E FINANCEIRAS", category="VEICULOS")
    ctx = s.parse_auction_page(html, ref)
    lots = s.parse_lots(html, ctx)
    assert len(lots) == 28
    assert s._has_next(html)
    assert s.stats.errors == 0

    bmw = lots[0]
    assert bmw.external_id == "83314"
    assert bmw.title == "I/BMW X3 XDRIVE30I 2017/2018 CINZA"
    assert bmw.official_url == "https://www.parquedosleiloes.com.br/leilao/1499/lote/83314"
    assert bmw.lot_number == "1"
    assert bmw.price is None  # so' no detalhe
    assert bmw.status_hint == "closed"
    assert bmw.category_hint == "veiculos"
    assert (bmw.city, bmw.state) == ("Brasília", "DF")
    # miniatura do card -> foto cheia (sem o prefixo thumb-)
    assert bmw.image_url == "https://www.parquedosleiloes.com.br/storage/vehicles/36035/images/6794befad9f091149c8359d0b08bcb59.webp"
    assert bmw.description and bmw.description.startswith("DOCUMENTO CRLV")
    assert bmw.auction.external_id == "1499" and bmw.auction.modality == "online"
    assert bmw.raw_attributes["status_lote_id"] == "7"
    # cada lote tem a sua copia do pregao
    assert bmw.auction is not lots[1].auction
    assert bmw.auction.sessions[0] is not lots[1].auction.sessions[0]

    # "Cancelado" vem como texto/classe sobre o id 2 (aberto): o texto manda
    crossfox = next(x for x in lots if x.external_id == "83330")
    assert crossfox.status_hint == "withdrawn"
    assert crossfox.raw_attributes["status_lote_id"] == "2"
    assert crossfox.raw_attributes["comitente"] == "SANTANDER"
    assert sum(1 for x in lots if x.status_hint == "withdrawn") == 4


def test_lots_judicial_with_default_location(fixture):
    s = _scraper()
    html = fixture("parquedosleiloes_listing_judicial.html")
    ref = AuctionRef(external_id="1510", url="https://www.parquedosleiloes.com.br/leilao/1510/detalhes", title="x", judicial=True)
    ctx = s.parse_auction_page(html, ref)
    lots = s.parse_lots(html, ctx)
    assert len(lots) == 1
    lot = lots[0]
    assert lot.external_id == "84164"
    assert lot.status_hint == "open"
    assert lot.price_second == Decimal("2500.00")
    assert (lot.city, lot.state) == ("Brasília", "DF")  # default da config
    assert lot.raw_attributes["praca"] == "1a_praca"
    assert lot.raw_attributes["processo"] == "0704908-50.2024.8.07.0001"

    # operador pode limpar o padrao
    s2 = _scraper({"default_city": "", "default_state": ""})
    lot2 = s2.parse_lots(html, s2.parse_auction_page(html, ref))[0]
    assert (lot2.city, lot2.state) == (None, None)


def test_detail_closed_with_bids(fixture):
    s = _scraper()
    html = fixture("parquedosleiloes_listing.html")
    ref = AuctionRef(external_id="1499", url="https://www.parquedosleiloes.com.br/leilao/1499/detalhes", title="BANCOS E FINANCEIRAS")
    lot = s.parse_lots(html, s.parse_auction_page(html, ref))[0]
    s.enrich_from_detail(lot, fixture("parquedosleiloes_detail.html"))
    assert lot.price == Decimal("90500.00")
    assert lot.price_kind == "lance_inicial"
    assert lot.status_hint == "sold"  # encerrado com maior lance
    r = lot.raw_attributes
    assert r["maior_lance"] == "124500.00"
    assert r["incremento"] == "1000.00"
    assert r["marca"] == "Byd" and r["modelo"] == "King Gs Dm"
    assert (r["ano_fabricacao"], r["ano_modelo"]) == (2026, 2027)
    assert r["km"] == 20146
    assert r["cor"] == "Preta"
    assert r["combustivel"] == "Gasolina/Eletrico"  # tabela diz "-", descricao informa
    assert r["sinistro"] is False
    assert r["valor_mercado"] == "160733.00" and r["valor_mercado_ref"] == "outubro de 2026"
    assert "importado" not in r
    assert "CÂMBIO AUTOMÁTICO" in r["acessorios"]
    assert r["abertura_lances"] == "2026-10-03T09:00:00"
    assert lot.auction.sessions[0].ends_at == datetime(2026, 10, 7, 13, 0)
    assert lot.auction.sessions[0].min_bid == Decimal("90500.00")
    # banner do vendedor (storage/auction-sellers) fica fora das fotos
    assert len(lot.images) == 10
    assert all("/storage/vehicles/" in u for u in lot.images)
    assert lot.image_url == lot.images[0]
    assert "Acessórios:" in lot.description
    assert "<!-- detail -->" in lot.raw_payload


def test_detail_open_judicial(fixture):
    s = _scraper()
    html = fixture("parquedosleiloes_listing_judicial.html")
    ref = AuctionRef(external_id="1510", url="https://www.parquedosleiloes.com.br/leilao/1510/detalhes", title="x", judicial=True)
    lot = s.parse_lots(html, s.parse_auction_page(html, ref))[0]
    s.enrich_from_detail(lot, fixture("parquedosleiloes_detail_open.html"))
    assert lot.price == Decimal("5000.00")
    assert lot.price_second == Decimal("2500.00")
    assert lot.status_hint == "open"
    r = lot.raw_attributes
    assert r["marca"] == "Fiat" and r["modelo"] == "Palio Edx"
    assert "km" not in r  # "-" na fonte nao vira zero
    assert r["documentos"] == "Auto de Penhora"
    assert r["status_detalhe"] == "Leilão aberto para lances"
    first = lot.auction.sessions[0]
    assert first.kind == "1a_praca"
    assert first.starts_at == datetime(2026, 11, 9, 14, 0)
    assert first.ends_at == datetime(2026, 11, 9, 14, 0)
    assert first.min_bid == Decimal("5000.00")
    assert lot.auction.sessions[1].kind == "2a_praca"
    assert lot.auction.modality == "online"
    assert lot.images and all("/storage/vehicles/" in u for u in lot.images)


def test_scrape_drops_lots_without_detail(fixture):
    """Com fetch_details, lote sem detalhe nao e' emitido: sem preco, ele
    apagaria o preco gravado no ciclo anterior."""
    s = _scraper({"auction_lists": ["/leiloes-judiciais?searchMode=judicial&type_id=1"],
                  "include_closed": True, "max_list_pages": 1, "max_auctions": 1,
                  "max_details_per_run": 1})

    async def fake_fetch(url, params=None, headers=None):
        if "/lote/" in url:
            return fixture("parquedosleiloes_detail.html")
        if "/leilao/" in url:
            return fixture("parquedosleiloes_listing.html")  # 28 lotes, 1 pagina lida
        return fixture("parquedosleiloes_auctions.html")

    s.fetch = fake_fetch  # type: ignore[method-assign]
    s.delay = _no_delay  # type: ignore[method-assign]
    items = asyncio.run(s.run())
    assert len(items) == 1
    assert items[0].price == Decimal("90500.00")
    assert not s.stats.complete
    assert any("detalhes atingido" in n for n in s.stats.notes)
    assert s.stats.details == 1


def test_helpers():
    s = ParqueDosLeiloesScraper
    assert s._praca_kind("BANCO DE BRASÍLIA S.A - BRB - 2ª PRAÇA") == "2a_praca"
    assert s._praca_kind("BANCOS E FINANCEIRAS") == "unica"
    assert s._modality("Presencial e Online") == "hibrido"
    assert s._lot_status("Lote encerrado", "7", ["badge"]) == "closed"
    assert s._lot_status("Lances On-Line até 28/10/26 14:00:00", "2", ["badge"]) == "open"
    assert s._lot_status("O leilão começará em breve", "1", None) == "soon"
    assert s._lot_status("Cancelado", "2", ["badge", "canceled"]) == "withdrawn"
    assert s._category_hint("https://x/storage/properties/524/images/thumb-a.webp", "VEICULOS") == "imoveis"
    assert s._category_hint(None, "BENS E EQUIPAMENTOS") == "equipamentos"
    assert s._category_hint(None, "CASA GUARA/DF") == "casa guara/df"
    assert s._committer_from_description("(SANTANDER) DOCUMENTO CRLV") == "SANTANDER"
    assert s._committer_from_description("(João da Silva) carro") is None
    assert s._full_image("https://x/storage/vehicles/1/images/thumb-6794befad9f091149c8359d0b08bcb59.webp") == \
        "https://x/storage/vehicles/1/images/6794befad9f091149c8359d0b08bcb59.webp"
