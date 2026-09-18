from decimal import Decimal

from app.scrapers.base import BaseScraper
from app.scrapers.freitas import FreitasScraper
from app.scrapers.leilo import LeiloScraper, parse_initial_state
from app.scrapers.megaleiloes import MegaLeiloesScraper


def test_helpers():
    assert BaseScraper.parse_brl("R$ 21.900,00") == Decimal("21900.00")
    assert BaseScraper.parse_brl("R$ 13.140,00") == Decimal("13140.00")
    assert BaseScraper.parse_brl(138000) == Decimal("138000.00")
    assert BaseScraper.parse_brl(None) is None
    dt = BaseScraper.parse_datetime_br("1ª Praça: 21/09/2026 às 10:00")
    assert (dt.year, dt.month, dt.day, dt.hour, dt.minute) == (2026, 9, 21, 10, 0)
    assert BaseScraper.parse_city_state("Guaratinguetá, SP") == ("Guaratinguetá", "SP")
    assert BaseScraper.parse_city_state("AV. DOS ESTADOS, 584 - PORTÃO 2 - UTINGA - SANTO ANDRÉ/SP")[1] == "SP"
    assert BaseScraper.strip_tracking("https://x.com/a?utm_source=1&b=2") == "https://x.com/a?b=2"
    assert BaseScraper.status_from_text("Aberto para lances") == "open"
    assert BaseScraper.status_from_text("Encerrado") == "closed"
    assert BaseScraper.status_from_text("Não arrematado") == "closed"
    assert BaseScraper.status_from_text("Arrematado") == "sold"
    # marcadores de "sem informacao" nao viram dado (RN-002)
    assert BaseScraper.reject_unknown("SI") is None
    assert BaseScraper.reject_unknown("Sem Informação") is None
    assert BaseScraper.reject_unknown("N/I") is None
    assert BaseScraper.reject_unknown("São Paulo") == "São Paulo"
    assert BaseScraper.reject_unknown("Sinop") == "Sinop"  # comeca com "si" mas e' cidade
    # placeholder da fonte nao e' foto do lote
    assert BaseScraper.reject_placeholder("https://www.megaleiloes.com.br/images/card-no-image-320x240.png") is None
    assert BaseScraper.reject_placeholder("https://cdn3.freitasleiloeiro.com.br/imagem-indisponivel.jpg") is None
    assert BaseScraper.reject_placeholder("https://cdn1.megaleiloes.com.br/batches/1/a_320x240.jpg") is not None


def test_megaleiloes_listing(fixture):
    s = MegaLeiloesScraper(source_id=1, base_url=None, config={})
    items = s.parse_listing(fixture("megaleiloes_listing.html"), "/veiculos")
    assert len(items) == 5
    fox = next(i for i in items if i.external_id == "128357")
    assert fox.title == "Carro Volkswagen Fox 1.6 - 2005"
    assert fox.price == Decimal("21900.00")
    assert fox.price_second == Decimal("13140.00")
    assert (fox.city, fox.state) == ("Guaratinguetá", "SP")
    assert fox.status_hint == "open"
    assert fox.official_url.startswith("https://www.megaleiloes.com.br/veiculos/carros/")
    assert "utm_" not in fox.official_url
    assert fox.image_url and fox.image_url.endswith(".jpg")
    assert fox.category_hint == "carros"
    assert fox.auction and fox.auction.external_id == "34578"
    kinds = [x.kind for x in fox.auction.sessions]
    assert kinds == ["1a_praca", "2a_praca"]
    assert fox.auction.sessions[0].starts_at.day == 21
    assert fox.auction.sessions[1].min_bid == Decimal("13140.00")
    assert fox.auction.auction_type == "judicial"
    assert s._has_next_page(fixture("megaleiloes_listing.html"), 1)


def test_megaleiloes_detail(fixture):
    s = MegaLeiloesScraper(source_id=1, base_url=None, config={})
    items = s.parse_listing(fixture("megaleiloes_listing.html"), "/veiculos")
    fox = next(i for i in items if i.external_id == "128357")
    s.enrich_from_detail(fox, fixture("megaleiloes_detail.html"))
    assert fox.description and "Fox 1.6" in fox.description
    assert "HCM2183" in fox.description  # placa em claro na fonte -> mascarada depois pelo normalizador
    assert fox.auction.auctioneer_name.startswith("Fernando")
    assert "JUCESP" in (fox.auction.auctioneer_registration or "")
    assert fox.auction.committer_name and "Vara" in fox.auction.committer_name
    assert fox.location_text and "Guaratinguetá" in fox.location_text
    assert len(fox.images) >= 3
    assert fox.raw_attributes.get("valor_avaliacao") == "21900.00"


def test_freitas_listing(fixture):
    s = FreitasScraper(source_id=2, base_url=None, config={})
    items = s.parse_listing(fixture("freitas_listing.html"))
    assert len(items) == 12
    first = items[0]
    assert first.external_id.startswith("8048-")
    assert "PLACA" in first.title
    assert first.price is not None and first.price > 0
    assert first.price_kind == "lance_inicial"
    assert first.official_url.startswith("https://www.freitasleiloeiro.com.br/Leiloes/LoteDetalhes?leilaoId=8048")
    assert first.auction.external_id == "8048"
    assert first.auction.sessions[0].kind == "unica"
    assert first.auction.sessions[0].starts_at is not None
    assert first.status_hint == "open"
    assert first.raw_attributes["origem"] in ("financeira", "seguradora", None)
    assert first.image_url and "cdn3.freitasleiloeiro" in first.image_url


def test_freitas_detail(fixture):
    s = FreitasScraper(source_id=2, base_url=None, config={})
    items = s.parse_listing(fixture("freitas_listing.html"))
    lot = items[0]
    s.enrich_from_detail(lot, fixture("freitas_detail.html"))
    assert lot.description and "SANDERO" in lot.description.upper()
    assert lot.auction.auctioneer_name and "Freitas" in lot.auction.auctioneer_name
    assert lot.auction.modality == "hibrido"
    assert lot.state == "SP"
    assert lot.raw_attributes.get("comissao_pct") == "5"


def test_leilo_state(fixture):
    html = fixture("leilo_state.html")
    state = parse_initial_state(html)
    assert state["elastic"]["totalRegistros"] == 221
    s = LeiloScraper(source_id=3, base_url=None, config={})
    items = s.items_from_state(state)
    assert len(items) == 6
    transit = next(i for i in items if "TRANSIT" in i.title)
    assert transit.official_url == "https://www.leilo.com.br/leilao?lote=7dd2938a-02d7-4e4a-ad0e-0dbd582e6a62"
    assert transit.price == Decimal("138000.00")
    assert transit.state == "SP" and transit.city == "São Carlos"
    assert transit.raw_attributes["marca"] == "Ford"
    # sufixo de portas da base Infocar nao entra no modelo
    assert LeiloScraper._clean_model("GOL TRENDLINE MB (2P/4P)") == "Gol Trendline Mb"
    assert LeiloScraper._clean_model("SAVEIRO CS (2P)") == "Saveiro Cs"
    assert LeiloScraper._clean_model("HB20S COMFORTLINE") == "Hb20S Comfortline"
    assert transit.raw_attributes["ano_modelo"] == 2025
    assert transit.raw_attributes["km"] == 49653
    assert transit.raw_attributes["origem"] == "frota"
    assert transit.raw_attributes["laudo_cautelar"] == "reprovado"
    assert transit.category_hint == "caminhoes"
    assert transit.status_hint == "open"
    from app.scrapers.leilo import SITUACAO_MAP
    assert SITUACAO_MAP["naoarrematado"] == "closed" and SITUACAO_MAP["agpagamento"] == "sold"
    assert transit.auction.sessions[0].kind == "repasse"
    # 12:30Z -> 09:30 BRT
    assert transit.auction.sessions[0].starts_at.hour == 9
    assert len(transit.images) == 4
