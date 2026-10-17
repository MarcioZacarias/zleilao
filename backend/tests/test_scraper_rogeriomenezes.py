from datetime import datetime
from decimal import Decimal

from app.scrapers.rogeriomenezes import RogerioMenezesScraper


def _scraper() -> RogerioMenezesScraper:
    return RogerioMenezesScraper(source_id=4, base_url=None, config={})


def test_rogeriomenezes_agenda(fixture):
    agenda = RogerioMenezesScraper.parse_agenda(fixture("rogeriomenezes_agenda.html"))
    assert len(agenda) == 12
    seg = next(a for a in agenda if a["id"] == 1631)
    assert seg["titulo"] == "LEILÃO ONLINE DE SEGURADORAS"
    assert seg["data"] == "2026-10-19 13:00:00" and seg["tipo"] == 0 and seg["aberto"] is True
    assert "Porto Seguro" in seg["nomes"]
    # casamento card -> leilao: titulo + data; a hora desempata
    hit = RogerioMenezesScraper._match_auction(agenda, "Leilão Online de Seguradoras", "2026-10-19", "13:00")
    assert hit and hit["id"] == 1631
    assert RogerioMenezesScraper._match_auction(agenda, "LEILÃO ONLINE DE SEGURADORAS", "2026-10-20", None) is None


def test_rogeriomenezes_listing(fixture):
    s = _scraper()
    agenda = s.parse_agenda(fixture("rogeriomenezes_agenda.html"))
    items = s.parse_listing(fixture("rogeriomenezes_listing.html"), "/categorias", agenda)
    assert len(items) == 9
    assert len({i.external_id for i in items}) == 9

    palio = next(i for i in items if i.external_id == "144272")
    assert palio.title == "FIAT PALIO FIRE ECONOMY 2010/2011 FLEX"
    assert palio.official_url == "https://rogeriomenezes.com.br/lote/144272/fiat-palio-fire-economy-2010-2011-flex"
    assert palio.price == Decimal("7000.00") and palio.price_kind == "lance_inicial"
    assert palio.lot_number == "97"
    assert palio.image_url and "static.suporteleiloes.com.br" in palio.image_url
    assert palio.raw_attributes["comitente"] == "Alamo"
    assert palio.raw_attributes["acessorios"] == "Ar, vidro, direção, chave reserva"
    assert palio.raw_attributes["ano_fabricacao"] == 2010 and palio.raw_attributes["ano_modelo"] == 2011
    assert palio.raw_attributes["combustivel"] == "flex"
    assert palio.raw_attributes["origem"] == "seguradora"
    assert "km" not in palio.raw_attributes
    assert palio.status_hint == "open"
    # `/categorias` nao diz a categoria; o detalhe ou o titulo decidem depois
    assert palio.category_hint is None
    a = palio.auction
    assert a.external_id == "1631" and a.title == "LEILÃO ONLINE DE SEGURADORAS"
    assert a.official_url == "https://rogeriomenezes.com.br/leilao/1631"
    assert a.modality == "online" and a.auction_type == "extrajudicial"
    assert a.auctioneer_name == "Rogério Menezes Nunes" and "JUCERJA" in a.auctioneer_registration
    assert "Porto Seguro" in a.committer_name and "Alamo" in a.committer_name
    assert [x.kind for x in a.sessions] == ["unica"]
    assert a.sessions[0].starts_at == datetime(2026, 10, 19, 13, 0)
    assert a.sessions[0].min_bid is None  # sessao e' do leilao; o lance do lote fica em `price`

    # km sai das specs do card
    with_km = next(i for i in items if "km" in i.raw_attributes)
    assert with_km.raw_attributes["km"] > 1000

    # card com lance ja' dado: label "Lance atual"
    atual = next(i for i in items if i.price_kind == "lance_atual")
    assert atual.price and atual.price > 0

    # hibrido: card sem numero de lote, leilao "Online e presencial"
    bmw = next(i for i in items if i.external_id == "144773")
    assert bmw.lot_number is None
    assert bmw.auction.external_id == "1635" and bmw.auction.modality == "hibrido"
    assert bmw.raw_attributes["tipo_pregao"] == "Online e presencial"

    # judicial: comitente institucional (tribunal), categoria da fonte no card
    imovel = next(i for i in items if i.external_id == "144543")
    assert imovel.auction.auction_type == "judicial" and imovel.auction.external_id == "1634"
    assert imovel.raw_attributes["origem"] == "judicial"
    assert imovel.raw_attributes["categoria_fonte"] == "Ponto Comercial"
    assert imovel.category_hint == "imoveis"
    assert "Tribunal" in imovel.raw_attributes["comitente"]
    assert imovel.price == Decimal("4300000.00")

    # leilao de materiais: hora sem comitente no card
    mat = next(i for i in items if i.auction.external_id == "1636")
    assert "comitente" not in mat.raw_attributes
    assert mat.auction.sessions[0].starts_at == datetime(2026, 10, 29, 9, 0)


def test_rogeriomenezes_listing_category_path_and_no_agenda(fixture):
    s = _scraper()
    items = s.parse_listing(fixture("rogeriomenezes_listing.html"), "/categorias/carros", None)
    palio = next(i for i in items if i.external_id == "144272")
    assert palio.category_hint == "carros"
    # sem agenda: id sintetico estavel por data + titulo, modalidade pelo data-tipo do card
    assert palio.auction.external_id == "2026-10-19-leilao-online-de-seguradoras"
    assert palio.auction.modality == "online"
    assert palio.auction.committer_name == "Alamo"
    assert palio.status_hint is None
    bmw = next(i for i in items if i.external_id == "144773")
    assert bmw.auction.modality == "hibrido"
    imovel = next(i for i in items if i.external_id == "144543")
    assert imovel.auction.auction_type == "judicial" and imovel.auction.modality is None


def test_rogeriomenezes_detail(fixture):
    s = _scraper()
    agenda = s.parse_agenda(fixture("rogeriomenezes_agenda.html"))
    items = s.parse_listing(fixture("rogeriomenezes_listing.html"), "/categorias", agenda)
    palio = next(i for i in items if i.external_id == "144272")
    s.enrich_from_detail(palio, fixture("rogeriomenezes_detail.html"))

    assert palio.description.startswith("Ar, vidro, direção, chave reserva")
    assert "Observações: Etiqueta do motor ausente" in palio.description
    raw = palio.raw_attributes
    assert raw["observacoes"].endswith("media monta")
    assert raw["marca"] == "Fiat"
    assert raw["ano_fabricacao"] == 2010 and raw["ano_modelo"] == 2011
    assert raw["categoria_fonte"] == "Veículos Leves"
    assert palio.category_hint == "carros"  # derivado da categoria da fonte quando a URL nao dizia
    assert raw["lance_inicial"] == "7000.00" and raw["incremento"] == "200.00"
    assert raw["comissao_pct"] == "5"
    assert raw["origem"] == "seguradora"
    assert raw["edital_url"].startswith("https://cdn.rogeriomenezes.com.br/leiloes/1631/documentos/") and raw["edital_url"].endswith(".pdf")
    assert raw["visitacao"].startswith("No dia do leilão")
    assert raw["retirada"].startswith("Um dia após o leilão")
    assert raw["instancia"] == 1
    assert palio.status_hint == "open"
    # patio do leiloeiro: "Campo Grande / RJ" e' bairro do Rio, nao cidade
    assert palio.location_text and "Av. Brasil, 51.467" in palio.location_text
    assert (palio.city, palio.state) == ("Rio de Janeiro", "RJ")
    assert len(palio.images) == 12 and all(u.startswith("https://static.suporteleiloes.com.br/") for u in palio.images)
    assert palio.image_url and palio.image_url.endswith(".jpg")
    a = palio.auction
    assert a.external_id == "1631" and a.modality == "online" and a.auction_type == "extrajudicial"
    assert a.sessions[0].starts_at == datetime(2026, 10, 19, 13, 0)
    assert "<!-- detail -->" in palio.raw_payload and '"valorInicial": "7000.00"' in palio.raw_payload


def test_rogeriomenezes_helpers():
    S = RogerioMenezesScraper
    assert S._hint_from_path("/categorias/motos") == "motos"
    assert S._hint_from_path("/categorias") is None
    assert S._hint_from_categoria_fonte("Veículos Pesados") == "caminhoes"
    assert S._hint_from_categoria_fonte("Sucata") == "sucatas"
    assert S._hint_from_categoria_fonte(None) is None
    assert S._title_facts("BYD DOLPHIN PLUS 310EV 2024/2025 ELÉTRICO FONTE EXTERNA") == {
        "ano_fabricacao": 2024, "ano_modelo": 2025, "combustivel": "eletrico"}
    assert S._title_facts("3 AR CONDICIONADOS") == {}
    assert S._origem("LEILÃO ONLINE E PRESENCIAL FINANCEIRAS") == "financeira"
    assert S._origem("MATERIAIS E EQUIPAMENTOS DIVERSOS") is None
    assert S._city_state("No dia do leilão, das 08 às 13 horas, na Av. Brasil, 51.467, Campo Grande / RJ") == ("Rio de Janeiro", "RJ")
    assert S._city_state("Rua das Flores, 10 - Centro - Niterói/RJ") == ("Niterói", "RJ")
    assert S._city_state("Online") == (None, None)
    assert S._slug("LEILÃO ONLINE DE SEGURADORAS") == "leilao-online-de-seguradoras"
