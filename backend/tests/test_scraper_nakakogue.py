"""Nakakogue Leilões — fixtures capturadas em 17/10/2026 de
https://www.nakakogueleiloes.com.br (capa, lotes/consulta/2 e detalhe do lote
137585/1106: casca HTML + JSON de proximo_lote.php).
"""
import json
from decimal import Decimal

from app.scrapers.nakakogue import NakakogueScraper


def _scraper() -> NakakogueScraper:
    return NakakogueScraper(source_id=9, base_url=None, config={})


def test_nakakogue_helpers():
    N = NakakogueScraper
    # UTF-8 servido como latin-1 e' reparado; latin-1 legitimo fica como esta'
    assert N.fix_mojibake("1Âº LeilÃ£o") == "1º Leilão"
    assert N.fix_mojibake("2ª Vara") == "2ª Vara"
    assert N.fix_mojibake("Ã\x80 Venda") == "À Venda"
    # "°" nao pode virar "deg" antes de ler o numero da praca
    assert N.session_kind_from_title("2°Leilão - Vara Cível - Tomazina") == "2a_praca"
    assert N.session_kind_from_title("1º Leilão - Divisão de Hastas Públicas") == "1a_praca"
    assert N.session_kind_from_title("3º Leilão - Massa Falida de X") == "2a_praca"
    assert N.session_kind_from_title("Hasta Única - Varas do Trabalho") == "unica"
    assert N.session_kind_from_title("VENDA DIRETA - 2ª Vara do Trabalho") == "repasse"
    assert N.auction_type_from_text("1º LEILÃO - EXTRAJUDICIAL SICOOB ALIANÇA") == "extrajudicial"
    assert N.auction_type_from_text("Juizado Especial Cível de Araucária") == "judicial"
    assert N.auction_type_from_text("Companhia Paranaense de Energia - COPEL") is None
    assert N.status_from_situacao("À Venda") == "open"
    assert N.status_from_situacao("Vendido") == "sold"
    assert N.status_from_situacao("Suspenso") == "withdrawn"
    # marca/modelo so' como dica; "1999/19" cortado nao vira ano/modelo
    v = N._vehicle_from_title("Veiculo REB/LINSHALM SRF2ECL, Especie: Carga, Placa AJA-9878, Ano/Modelo 1999/19")
    assert (v["marca"], v["modelo"], v["ano_fabricacao"]) == ("Reb", "Linshalm Srf2Ecl", 1999)
    assert "ano_modelo" not in v
    assert N._vehicle_from_title("IMOVEL EM CURITIBA/PR") == {}
    assert N._vehicle_from_title("Veículo MITSUBISHI/PAJERO-TRF4, 2.0/FLEX-16V, 2010/2011")["modelo"] == "Pajero-Trf4"
    assert N._best_committer("DIVISAO DE HASTAS PUBLI", "1º Leilão - Divisão de Hastas Públicas - Hyundai") == "Divisão de Hastas Públicas"
    assert N._best_committer("02ª Vara do Trabalho de Curitiba", None) == "2ª Vara do Trabalho de Curitiba"


def test_nakakogue_home(fixture):
    s = _scraper()
    auctions = s.parse_home(fixture("nakakogue_home.html"))
    assert len(auctions) == 33
    tucson = auctions["137585"]
    assert tucson["title"] == "1º Leilão - Divisão de Hastas Públicas - Hyundai Tucson 2012/2013"
    assert (tucson["starts_at"].day, tucson["starts_at"].hour) == (17, 11)
    assert tucson["modality"] == "online"
    assert tucson["edital_url"].endswith("/arquivos/L137585/20261013_25981.pdf")
    # pregao em hotel: tambem recebe lance pelo site
    assert auctions["137576"]["modality"] == "hibrido"
    assert "Paranaguá" in auctions["137576"]["local"]


def test_nakakogue_listing(fixture):
    s = _scraper()
    auctions = s.parse_home(fixture("nakakogue_home.html"))
    items = s.parse_listing(fixture("nakakogue_listing.html"), auctions)
    assert len(items) == 18
    assert s.stats.errors == 0
    assert len({i.external_id for i in items}) == 18

    tuc = next(i for i in items if i.external_id == "137585-1106")
    assert tuc.title == "HYUNDAI/TUCSON GLSB, 2012/2013 - AGENDE SUA VISITA!"
    assert tuc.official_url == "https://www.nakakogueleiloes.com.br/detalhe-lote/137585/1106/"
    assert tuc.lot_number == "1106"
    # 1º leilao judicial: lance nao fica abaixo da avaliacao; o "Valor Mínimo"
    # da fonte e' o piso da 2ª praca
    assert tuc.price == Decimal("47436.00")
    assert tuc.price_second == Decimal("23718.00")
    assert tuc.price_kind == "lance_inicial"
    assert tuc.category_hint == "veiculos"
    assert tuc.status_hint == "open"
    assert tuc.image_url is None  # a listagem nao traz foto
    assert tuc.raw_attributes["marca"] == "Hyundai"
    assert tuc.raw_attributes["ano_modelo"] == 2013
    assert tuc.raw_attributes["valor_avaliacao"] == "47436.00"
    assert tuc.auction.external_id == "137585"
    assert tuc.auction.auction_type == "judicial"
    assert tuc.auction.modality == "online"
    assert tuc.auction.committer_name == "Divisão de Hastas Públicas"  # rotulo cortado completado pelo titulo
    assert tuc.auction.official_url == "https://www.nakakogueleiloes.com.br/lotes/137585/"
    assert [x.kind for x in tuc.auction.sessions] == ["1a_praca"]
    assert tuc.auction.sessions[0].starts_at.month == 11

    # 2º leilao: o minimo da fonte ja' e' o da praca corrente
    gol = next(i for i in items if i.external_id == "137546-711")
    assert gol.price == Decimal("6700.00") and gol.price_second is None
    assert gol.auction.sessions[0].kind == "2a_praca"
    assert gol.auction.committer_name == "Vara Cível de Tomazina"

    # venda direta vira repasse; ordinal sem zero a esquerda
    reb = next(i for i in items if i.external_id == "137401-411")
    assert reb.auction.sessions[0].kind == "repasse"
    assert reb.raw_attributes.get("venda_direta") is True
    assert reb.auction.committer_name == "2ª Vara do Trabalho de Curitiba"

    # titulo que a fonte poe num <p> dentro do <h3>
    pajero = next(i for i in items if i.external_id == "137582-3311")
    assert "MITSUBISHI/PAJERO" in pajero.title

    # sucata e' veiculo baixado
    sucata = next(i for i in items if i.external_id == "137590-3111")
    assert sucata.category_hint == "sucatas"

    # leilao ausente da capa: titulo generico, sessao unica sem data
    sem_capa = next(i for i in items if i.external_id == "137588-3421")
    assert sem_capa.auction.title == "Leilão 137588"
    assert sem_capa.auction.auction_type == "judicial"  # pelo comitente (Juizado)
    assert sem_capa.auction.sessions[0].starts_at is None

    # nada de nome de pessoa fisica nos campos estruturados (RN-009)
    for it in items:
        assert "placa" not in it.raw_attributes and "chassi" not in it.raw_attributes


def test_nakakogue_listing_sem_capa(fixture):
    s = _scraper()
    items = s.parse_listing(fixture("nakakogue_listing.html"))
    tuc = next(i for i in items if i.external_id == "137585-1106")
    # sem a praca conhecida, fica o minimo que a fonte mostra
    assert tuc.price == Decimal("23718.00") and tuc.price_second is None
    assert tuc.auction.committer_name == "DIVISAO DE HASTAS PUBLI"
    assert tuc.auction.sessions[0].kind == "unica"


def test_nakakogue_detail(fixture):
    s = _scraper()
    auctions = s.parse_home(fixture("nakakogue_home.html"))
    items = s.parse_listing(fixture("nakakogue_listing.html"), auctions)
    tuc = next(i for i in items if i.external_id == "137585-1106")
    payload = json.loads(fixture("nakakogue_detail.json"))
    s.enrich_from_detail(tuc, fixture("nakakogue_detail.html"), payload)

    assert tuc.description and "TUCSON" in tuc.description
    assert "Detalhes Especiais" not in tuc.description  # rodape repetido da fonte
    assert "BCC-2C09" in tuc.description  # placa em claro na fonte -> mascarada depois pelo normalizador
    assert (tuc.city, tuc.state) == ("Curitiba", "PR")
    assert tuc.raw_attributes["combustivel"] == "Alcool/Gasolina"
    assert tuc.raw_attributes["cor"] == "Prata"
    assert tuc.raw_attributes["processo"] == "0000230-39.2016.5.09.0088"
    assert tuc.raw_attributes["id_interno"] == "1398126"
    assert "placa" not in tuc.raw_attributes and "renavam" not in tuc.raw_attributes
    assert len(tuc.images) == 4
    assert tuc.image_url == "https://www.nakakogueleiloes.com.br/arquivos/C475/L1398126/p95779/20261008_28915_95779.jpg"

    kinds = [(x.kind, x.starts_at.day, x.min_bid) for x in tuc.auction.sessions]
    assert kinds == [("1a_praca", 17, Decimal("47436.00")), ("2a_praca", 24, Decimal("23718.00"))]
    assert tuc.price == Decimal("47436.00")
    assert tuc.price_second == Decimal("23718.00")
    assert tuc.auction.auction_type == "judicial"
    assert tuc.auction.modality == "online"
    assert "<!-- detail -->" in tuc.raw_payload


def test_nakakogue_detail_sem_capa(fixture):
    """Sem indice da capa, o detalhe sozinho recupera titulo, pracas e tipo."""
    s = _scraper()
    items = s.parse_listing(fixture("nakakogue_listing.html"))
    tuc = next(i for i in items if i.external_id == "137585-1106")
    s.enrich_from_detail(tuc, fixture("nakakogue_detail.html"), json.loads(fixture("nakakogue_detail.json")))
    assert [x.kind for x in tuc.auction.sessions] == ["1a_praca", "2a_praca"]
    assert tuc.price == Decimal("47436.00") and tuc.price_second == Decimal("23718.00")
    assert tuc.auction.auction_type == "judicial"
