"""Montenegro Leilões: parser offline sobre a API JSON publica e a pagina do
lote (fixtures recortadas de respostas reais de 17/10/2026)."""
import json
from decimal import Decimal

import pytest

from app.scrapers.montenegro import MontenegroScraper


@pytest.fixture
def montenegro(fixture):
    s = MontenegroScraper(source_id=11, base_url=None, config={})
    lots = json.loads(fixture("montenegro_lotes.json"))
    agenda = s.auctions_from_json(json.loads(fixture("montenegro_leiloes.json")))
    return s, lots, agenda


def test_auctions_from_json(montenegro):
    s, lots, agenda = montenegro
    assert len(agenda) == 6
    assert agenda["2627"]["lotes_count"] == 13  # conta imoveis e materiais, nao so' veiculos
    assert agenda["2681"]["comitente"]["nome_fantasia"] == "PREFEITURA MUNICIPAL DE IPUEIRAS/CE"
    assert s.auctions_from_json(None) == {}
    assert s.auctions_from_json([{"sem_id": 1}, "lixo"]) == {}


def test_parse_lots(montenegro):
    s, lots, agenda = montenegro
    items = s.parse_lots(lots, agenda)
    assert len(items) == 8
    assert s.stats.errors == 0

    moto = next(i for i in items if i.external_id == "102565")
    assert moto.title == "Yamaha Factor YBR125 E 2009/2010"
    assert moto.official_url == "https://montenegroleiloes.com.br/leiloes/2627/lotes/102565"
    assert moto.price == Decimal("3300.00") and moto.price_kind == "lance_atual"
    assert moto.raw_attributes["lance_inicial"] == "3000.00"
    assert moto.raw_attributes["lance_atual"] == "3300.00"
    assert moto.raw_attributes["incremento"] == "100.00"
    assert moto.lot_number == "2"
    assert (moto.city, moto.state) == (None, None)  # TJCE nao diz a cidade; o detalhe diz
    assert moto.image_url == "https://montenegroleiloes.com.br/midia/1c0b86db-8e25-4a39-ae1b-075aca81f291"
    assert len(moto.images) == 3
    assert moto.category_hint == "veiculos"
    assert moto.status_hint == "open"
    assert moto.raw_attributes["sucata"] is False
    assert moto.raw_attributes["comitente"] == "TRIBUNAL DE JUSTIÇA DO ESTADO DO CEARÁ"
    assert moto.raw_attributes["origem"] == "judicial"
    assert moto.raw_attributes["tipo_leilao"] == 7 and moto.raw_attributes["comissao_pct"] == 5
    assert "Comitente: TRIBUNAL DE JUSTIÇA" in moto.description
    a = moto.auction
    assert a.external_id == "2627"
    assert a.title.startswith("Imóveis, Veículos e Materais - Tribunal de Justiça")
    assert a.auction_type == "judicial"
    assert a.modality == "online"
    assert a.committer_name == "TRIBUNAL DE JUSTIÇA DO ESTADO DO CEARÁ"
    assert a.auctioneer_name == "Montenegro Leilões"
    assert a.official_url == "https://montenegroleiloes.com.br/leiloes/2627"
    assert [x.kind for x in a.sessions] == ["1a_praca"]  # "(1ª Chamada)" no titulo
    assert a.sessions[0].starts_at.strftime("%Y-%m-%d %H:%M") == "2026-10-20 10:00"
    assert a.sessions[0].min_bid == Decimal("3000.00")
    payload = json.loads(moto.raw_payload)
    assert payload["leilao"]["comitente"]["nome_fantasia"] and "descricao_do_pagamento" not in payload["leilao"]

    sucata = next(i for i in items if i.external_id == "102903")
    assert sucata.category_hint == "sucatas" and sucata.raw_attributes["sucata"] is True
    assert sucata.price == Decimal("240.00") and sucata.price_kind == "lance_inicial"
    assert "lance_atual" not in sucata.raw_attributes
    assert "sucata" in sucata.description.lower()

    nao_vendido = next(i for i in items if i.external_id == "103440")
    assert nao_vendido.status_hint == "closed"  # "Não Vendido" nao pode virar "sold"
    assert nao_vendido.auction.auction_type == "judicial"  # TRT 7ª Regiao
    assert (nao_vendido.city, nao_vendido.state) == (None, "CE")
    assert [x.kind for x in nao_vendido.auction.sessions] == ["unica"]

    decimal_bid = next(i for i in items if i.external_id == "103661")
    assert decimal_bid.price == Decimal("1552.50")  # "1552.5" na API: ponto decimal, nao milhar

    prefeitura = next(i for i in items if i.external_id == "103428")
    assert prefeitura.auction.auction_type == "extrajudicial"
    assert (prefeitura.city, prefeitura.state) == ("Ipueiras", "CE")
    assert "origem" not in prefeitura.raw_attributes
    assert prefeitura.auction.sessions[0].starts_at.strftime("%d/%m/%Y %H:%M") == "26/10/2026 10:00"

    repetido = next(i for i in items if i.external_id == "103676")
    assert repetido.title == "GM/BLAZER ADVANTAGE 2005/2005"

    particular = next(i for i in items if i.external_id == "103931")
    assert particular.auction.committer_name is None  # "Particular (108102)" e' pessoa fisica
    assert "comitente" not in particular.raw_attributes
    assert particular.raw_attributes["origem"] == "particular"
    assert particular.auction.auction_type == "extrajudicial"
    assert particular.price == Decimal("53000.00")


def test_fallbacks(montenegro):
    s, lots, agenda = montenegro
    # lote sem `leilao` embutido: a agenda cobre
    orfao = dict(lots[0], leilao=None)
    item = s.parse_lots([orfao], agenda)[0]
    assert item.auction.title.startswith("Imóveis, Veículos e Materais")
    assert item.auction.committer_name == "TRIBUNAL DE JUSTIÇA DO ESTADO DO CEARÁ"
    assert item.auction.sessions[0].starts_at.strftime("%Y-%m-%d") == "2026-10-20"
    # sem agenda e sem leilao: ainda sai, com o minimo
    item = s.parse_lots([orfao], {})[0]
    assert item.auction.external_id == "2627" and item.auction.title == "Leilão 2627"
    assert item.auction.modality is None
    # duas pracas quando a API as mostra
    leilao2 = dict(lots[0]["leilao"], dois_leiloes="1", data_hora_inicio_segundo_leilao="2026-11-03 10:00:00")
    duas = dict(lots[0], leilao=leilao2, lance_inicial_segundo_leilao="1500")
    sessions = s.parse_lots([duas], agenda)[0].auction.sessions
    assert [x.kind for x in sessions] == ["1a_praca", "2a_praca"]
    assert sessions[0].min_bid == Decimal("3000.00") and sessions[1].min_bid == Decimal("1500.00")
    assert sessions[1].starts_at.strftime("%d/%m/%Y") == "03/11/2026"
    # lote sem titulo ou sem id nao entra
    assert s.parse_lots([dict(lots[0], titulo=""), dict(lots[0], id=None)], agenda) == []
    # status desconhecido cai no texto
    retirado = dict(lots[0], status_lote={"nome": "Retirado", "identificador": "XPTO"})
    assert s.parse_lots([retirado], agenda)[0].status_hint == "withdrawn"


def test_detail(montenegro, fixture):
    s, lots, agenda = montenegro
    item = s.parse_lots(lots[:1], agenda)[0]
    page = s.parse_data_page(fixture("montenegro_detail.html"))
    assert page["component"] == "Lote" and page["url"] == "/leiloes/2627/lotes/102565"
    s.enrich_from_detail(item, page)
    raw = item.raw_attributes
    assert raw["marca"] == "Yamaha" and raw["modelo"] == "Factor Ybr125 E"
    assert raw["ano_fabricacao"] == 2009 and raw["ano_modelo"] == 2010
    assert raw["km"] == 10546 and raw["cor"] == "Vermelha"
    assert raw["combustivel"] == "gasolina" and "combustivel_fonte" not in raw
    assert "funcionando" not in raw  # "Desconhecido" nao afirma nada
    assert raw["chave_ignicao"] is False
    assert raw["tipo_bem"] == "Moto" and "tipo_monta" not in raw  # "-"
    assert raw["local_exposicao"] == "Matriz"
    assert raw["placa_mascarada"] == "******1"
    assert raw["comitente"] == "15ª VARA CRIMINAL DA COMARCA DE FORTALEZA-CE"  # a vara, nao o tribunal
    assert raw["processo"] == "0251626-92.2024.8.06.0001"
    assert raw["situacao_fonte"] == "Veículo regularizável"
    assert raw["n_lances"] == 4
    assert raw["taxas"] == {"Despesa De Logistica": "150.00", "Despesas Administrativa": "360.00"}
    assert raw["edital_url"] == "https://montenegroleiloes.com.br/midia/d37f1f42-7c9d-41e4-acd4-d555418df424"
    assert item.category_hint == "motos"
    assert item.price == Decimal("3300.00") and item.price_kind == "lance_atual"
    assert (item.city, item.state) == ("Fortaleza", "CE")
    assert item.location_text.startswith("Montenegro Leilões (Rua Ademar Paula")
    assert "regularizável" in item.description and "<" not in item.description
    assert "Ressarcimento de despesas com logística" in item.description
    # a fonte parte "R$ 680,00" e "Fortaleza/CE" em tags inline adjacentes
    assert "R$ 680,00 para veículos" in item.description
    assert "Comarca de Fortaleza/CE" in item.description
    assert len(item.images) == 11 and item.image_url.endswith("/midia/1c0b86db-8e25-4a39-ae1b-075aca81f291")
    assert item.status_hint == "open" and raw["status_fonte"] == "Aberto"
    assert item.auction.modality == "online"
    # apelidos dos licitantes ficam fora de tudo (RN-009); chassi mascarado tambem nao entra
    dump = json.dumps(raw, ensure_ascii=False) + item.description
    assert "***" not in dump.replace("******1", "") and "username" not in dump
    assert "chassi" not in raw


def test_helpers():
    M = MontenegroScraper
    assert M.clean_title("FIAT UNO WAY 1 0 FIAT UNO WAY 1 0 2011/2012") == "FIAT UNO WAY 1 0 2011/2012"
    assert M.clean_title("Honda CG 125 Fan KS 2009/2010") == "Honda CG 125 Fan KS 2009/2010"
    assert M.clean_title("  02  M.BENZ MPOLO  TORINO ") == "02 M.BENZ MPOLO TORINO"
    assert M.clean_title(None) == ""
    assert M.city_state_from_committer("15ª VARA CRIMINAL DA COMARCA DE FORTALEZA-CE") == ("Fortaleza", "CE")
    assert M.city_state_from_committer("PREFEITURA MUNICIPAL DE IPUEIRAS/CE") == ("Ipueiras", "CE")
    assert M.city_state_from_committer("TRIBUNAL REGIONAL DO TRABALHO DA 7ª REGIÃO (CE)") == (None, "CE")
    assert M.city_state_from_committer("TRIBUNAL DE JUSTIÇA DO ESTADO DO CEARÁ") == (None, None)
    assert M.city_state_from_committer(None) == (None, None)
    assert M.session_kind("Imóvel e Veículos - TJCE (1ª Chamada)") == "1a_praca"
    assert M.session_kind("Veículos - TJCE (2ª Chamada)") == "2a_praca"
    assert M.session_kind("TRT 7ª Região/CE - Alienação por Iniciativa Particular") == "unica"
    assert M.session_kind(None) == "unica"
    assert M._num("3000") == Decimal("3000.00")
    assert M._num("1552.5") == Decimal("1552.50")
    assert M._num("0") is None and M._num(None) is None and M._num("abc") is None
    assert M._int("2009") == 2009 and M._int("7") == 7 and M._int("") is None
    assert M._bool("Sim") is True and M._bool("Não") is False and M._bool("Desconhecido") is None
    blocks = M.text_blocks("<p><strong>Exequente:</strong> Banco X S.A.</p><p>Executado: Fulano de Tal.</p>"
                           "<p>01 Carro <b>VW Gol</b>, cor Prata.<br>Situação: Regular. Reclamante: Beltrano; ok</p>")
    assert blocks == ["01 Carro VW Gol, cor Prata.", "Situação: Regular. ok"]
    assert M.text_blocks(None) == []
    s = MontenegroScraper(source_id=11, base_url=None, config={})
    # "-" e' o "nao informado" da fonte: nao vira marca nem cor
    attrs = s.vehicle_attrs({"modelo": {"nome": "APACHE RTR 150", "marca": {"nome": "-"}}, "cor": "-",
                             "placa": "ABC1D23", "kilometragem": "0", "funcionando": "Sim"})
    assert "marca" not in attrs and "cor" not in attrs and "km" not in attrs
    assert attrs["modelo"] == "Apache Rtr 150" and attrs["funcionando"] is True
    assert "placa_mascarada" not in attrs  # placa em claro nao entra (RN-009)
    assert s.vehicle_attrs({}) == {}
    s = MontenegroScraper(source_id=11, base_url=None, config={"categoria": ""})
    assert s._api_path("dados-home-lotes") == "/api-publica/stale/dados-home-lotes"
    s = MontenegroScraper(source_id=11, base_url=None, config={})
    assert s._api_path("dados-home-lotes") == "/api-publica/stale/dados-home-lotes/veicular/categorias/veiculos"
    assert s._api_path("dados-home") == "/api-publica/stale/dados-home/veicular/categorias/veiculos"
