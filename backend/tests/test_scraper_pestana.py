"""Pestana Leilões: parser offline sobre os JSONs da API do portal (fixtures
recortadas de respostas reais de 17/10/2026)."""
import json
from decimal import Decimal

import pytest

from app.scrapers.pestana import PestanaScraper


@pytest.fixture
def pestana(fixture):
    s = PestanaScraper(source_id=9, base_url=None, config={})
    auctions = json.loads(fixture("pestana_auctions.json"))
    lots = json.loads(fixture("pestana_listing.json"))
    tipos = s.tipos_from_json(json.loads(fixture("pestana_caracteristica_tipo.json")))
    parceiros = s.parceiros_from_json(json.loads(fixture("pestana_parceiros.json")))
    return s, auctions, lots, tipos, parceiros


def test_select_auctions(pestana):
    s, auctions, *_ = pestana
    # so' pregoes com veiculos, publicos, do mais proximo ao mais distante
    assert [a["id"] for a in s.select_auctions(auctions)] == [6260, 6320, 6314]
    s_priv = PestanaScraper(source_id=9, base_url=None, config={"include_private": True})
    assert [a["id"] for a in s_priv.select_auctions(auctions)][0] == 1816
    s_all = PestanaScraper(source_id=9, base_url=None, config={"tipo_bem": None})
    assert 6334 in [a["id"] for a in s_all.select_auctions(auctions)]
    s_imoveis = PestanaScraper(source_id=9, base_url=None, config={"tipo_bem": "462"})
    assert [a["id"] for a in s_imoveis.select_auctions(auctions)] == [6334, 6314]


def test_auction_from_json(pestana):
    s, auctions, lots, tipos, parceiros = pestana
    by_id = {a["id"]: a for a in auctions}
    a = s.auction_from_json(by_id[6260], parceiros, lots[0])
    assert a.external_id == "6260"
    assert a.title == "Leilão de Veículos Retomados"
    assert a.modality == "online"
    assert a.auction_type == "extrajudicial"
    assert a.official_url == "https://www.pestanaleiloes.com.br/lote/6260"
    assert a.auctioneer_name and "Leiloeira Oficial" in a.auctioneer_name
    assert a.committer_name == "Banco Bradesco Financiamentos S/A"  # parceiro 1458 do lote
    assert [x.kind for x in a.sessions] == ["unica"]
    assert a.sessions[0].starts_at.strftime("%Y-%m-%d %H:%M") == "2026-10-21 10:00"
    assert s.auction_from_json(by_id[6320], parceiros).modality == "hibrido"
    assert s.auction_from_json(by_id[6314], parceiros).auction_type == "judicial"


def test_parse_lots(pestana):
    s, auctions, lots, tipos, parceiros = pestana
    auction = next(a for a in auctions if a["id"] == 6260)
    items = s.parse_lots(lots, auction, tipos, parceiros)
    assert len(items) == 5
    assert s.stats.errors == 0

    palio = next(i for i in items if i.external_id == "441880")
    assert palio.title == "Fiat Palio FIRE FLEX 2006 2006 Gas/Alc"
    assert palio.official_url == "https://www.pestanaleiloes.com.br/lote/6260/441880/fiat-palio-fire-flex-2006-2006-gas-alc"
    assert palio.price == Decimal("9600.00") and palio.price_kind == "lance_inicial"
    assert palio.lot_number is None  # numero null na fonte: nao inventar (RN-002)
    assert (palio.city, palio.state) == ("Nova Santa Rita", "RS")
    assert palio.location_text and "BR 386" in palio.location_text
    assert palio.image_url == "https://ged.pestanaleiloes.com.br/ged/20611165.jpg"
    assert len(palio.images) == 3
    assert palio.category_hint == "carros"
    assert palio.status_hint == "open"
    raw = palio.raw_attributes
    assert raw["marca"] == "Fiat" and raw["modelo"] == "Palio" and raw["versao"] == "FIRE FLEX"
    assert raw["ano_fabricacao"] == 2006 and raw["ano_modelo"] == 2006
    assert "km" not in raw  # "Indisponivel"
    assert raw["combustivel"] == "flex" and raw["combustivel_fonte"] == "Gas/Alc"
    assert raw["cambio"] == "manual"
    assert raw["origem"] == "financeira" and raw["origem_fonte"] == "Retomado"
    assert "condicao" not in raw  # monta "Nao se aplica" nao afirma que e' normal
    assert raw["placa_mascarada"] == "I*****0"  # ja' mascarada pela fonte
    assert raw["ipva_pago"] is True and raw["comissao_pct"] == 5
    assert raw["taxa_administrativa"] == "2350.00"
    assert raw["comitente"] == "Banco Bradesco Financiamentos S/A"
    assert "CHASSI REMARCADO" in palio.description
    assert "00875534953" not in palio.description  # RENAVAM em claro na fonte, removido (RN-009)
    assert "Marca: Fiat" in palio.description
    assert palio.auction and palio.auction.external_id == "6260"

    daf = next(i for i in items if i.external_id == "441977")
    assert daf.title.startswith("Lote contendo Caminhao/Trator DAF")
    assert daf.lot_number == "110"
    assert daf.price == Decimal("360000.00")
    assert daf.category_hint == "caminhoes"
    assert daf.raw_attributes["n_bens"] == 4  # cavalo + 3 semirreboques
    assert "Renavam" not in daf.description and "01254007595" not in daf.description
    assert len(daf.official_url.rsplit("/", 1)[1]) <= 100

    kwid = next(i for i in items if i.external_id == "441935")
    assert kwid.lot_number == "90"
    assert kwid.raw_attributes["lance_atual"] == "15900.00"
    assert kwid.price == Decimal("15900.00")  # lance inicial (aqui o lance corrente coincide)
    # arrematante (mesmo mascarado pela fonte) nao e' copiado para dado estruturado
    assert "m***v" not in json.dumps(kwid.raw_attributes) and "m***v" not in kwid.description

    moto = next(i for i in items if i.external_id == "442117")
    assert moto.category_hint == "motos"
    captiva = next(i for i in items if i.external_id == "441837")
    assert captiva.category_hint == "carros" and captiva.raw_attributes["sub_tipo_bem"] == "Camionetas"


def test_filters_and_fallbacks(pestana):
    s, auctions, lots, tipos, parceiros = pestana
    auction = next(a for a in auctions if a["id"] == 6260)
    # sem o endpoint de tipos, o mapa fixo ainda nomeia marca/modelo
    items = s.parse_lots(lots, auction, None, parceiros)
    assert items[0].raw_attributes["marca"] == "Fiat"
    # pregao de imoveis configurado: lotes de veiculo saem
    s_imoveis = PestanaScraper(source_id=9, base_url=None, config={"tipo_bem": 462})
    assert s_imoveis.parse_lots(lots, auction, tipos, parceiros) == []
    # lote invisivel e lote retirado
    hidden = dict(lots[0], visivel=False)
    assert s.parse_lots([hidden], auction, tipos, parceiros) == []
    retirado = dict(lots[0], exibirMensagemRetirada=True, mensagemRetirada="Lote retirado a pedido do comitente")
    assert s.parse_lots([retirado], auction, tipos, parceiros)[0].status_hint == "withdrawn"


def test_helpers():
    assert PestanaScraper.status_from_situacao(1, "Disponível") == "open"
    assert PestanaScraper.status_from_situacao(3, "Vendido") == "sold"
    assert PestanaScraper.status_from_situacao(4, "Não Vendido") == "closed"
    assert PestanaScraper.status_from_situacao(5, "Condicional") == "open"
    assert PestanaScraper.status_from_situacao(8, "Retirado") == "withdrawn"
    assert PestanaScraper.status_from_situacao(None, "Não vendido") == "closed"  # texto nao engana
    assert PestanaScraper.status_from_situacao(None, "Vendido") == "sold"
    assert PestanaScraper.slugify("Lote contendo Caminhão/Trator DAF  XF ") == "lote-contendo-caminhao-trator-daf-xf"
    assert PestanaScraper.slugify("a" * 150) == "a" * 100
    assert PestanaScraper.slugify(None) == ""
    assert PestanaScraper._brl("2350.00") == "R$ 2.350,00"
    assert PestanaScraper._brl(Decimal("629074.74")) == "R$ 629.074,74"
    # comitente: so' pessoa juridica; partes de processo nunca (RN-009)
    assert PestanaScraper.institutional_name("Banco Pan S/A") == "Banco Pan S/A"
    assert PestanaScraper.institutional_name("Município de Ivoti") == "Município de Ivoti"
    assert PestanaScraper.institutional_name("Banco Exemplo S.A. X Fulano de Tal e Outros") is None
    assert PestanaScraper.institutional_name("Fulana de Tal") is None
    assert PestanaScraper.institutional_name(None) is None
    assert PestanaScraper._strip_ids("Reboque Facchini 2020 Preta Renavam:01254014737 Retomado") == "Reboque Facchini 2020 Preta Retomado"
    assert PestanaScraper._strip_ids("Palio 2006 Vermelha 00875534953 Retomado") == "Palio 2006 Vermelha Retomado"
