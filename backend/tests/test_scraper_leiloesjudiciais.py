import re
from datetime import datetime
from decimal import Decimal

from app.scrapers.leiloesjudiciais import LeiloesJudiciaisScraper, parse_nuxt_payload


def _scraper(**config):
    return LeiloesJudiciaisScraper(source_id=9, base_url=None, config=config)


def test_leiloesjudiciais_payload(fixture):
    root = parse_nuxt_payload(fixture("leiloesjudiciais_listing.html"))
    key = next(k for k in root["data"] if k.startswith("busca_ssr"))
    geral = root["data"][key]["dadosGeral"]
    assert geral["totalItems"] == 1015 and geral["totalPages"] == 25
    assert parse_nuxt_payload("<html></html>") is None


def test_leiloesjudiciais_listing(fixture):
    s = _scraper()
    items = s.parse_listing(fixture("leiloesjudiciais_listing.html"), "/veiculos")
    assert len(items) == 8
    assert s.last_meta["totalPages"] == 25 and s.has_next_page(1) and not s.has_next_page(25)

    vw = next(i for i in items if i.external_id == "219958")
    assert vw.title == "VW/24220 - 10/10 - Vespasiano/MG"
    assert vw.official_url == "https://www.leiloesjudiciais.com.br/lote/100247/219958"
    assert vw.price == Decimal("380000.00") and vw.price_kind == "lance_inicial"
    assert vw.price_second == Decimal("266000.00")
    assert (vw.city, vw.state) == ("Vespasiano", "MG")
    assert vw.status_hint == "open"
    assert vw.lot_number == "1"
    assert vw.image_url and "/640x480/" in vw.image_url and len(vw.images) == 4
    assert vw.category_hint == "caminhoes"
    assert vw.raw_attributes["valor_avaliacao"] == "380000.00"
    assert vw.raw_attributes["lance_2a_praca"] == "266000.00"
    assert (vw.raw_attributes["ano_fabricacao"], vw.raw_attributes["ano_modelo"]) == (2010, 2010)
    assert vw.raw_attributes["parcelas"] == 6 and vw.raw_attributes["entrada_pct"] == 25
    assert vw.raw_attributes["origem"] == "judicial"
    assert vw.raw_attributes["edital_url"].endswith(".pdf")
    assert "Alienação Fiduciária" in vw.description
    assert vw.auction and vw.auction.external_id == "100247"
    assert vw.auction.official_url == "https://www.leiloesjudiciais.com.br/leilao/100247"
    assert vw.auction.auction_type == "judicial" and vw.auction.modality == "online"
    assert vw.auction.auctioneer_name  # leiloeiro oficial: funcao publica, nao e' parte
    assert [x.kind for x in vw.auction.sessions] == ["1a_praca", "2a_praca"]
    assert vw.auction.sessions[0].min_bid == Decimal("380000.00")
    assert vw.auction.sessions[0].ends_at == datetime(2026, 11, 4, 13, 0)
    assert vw.auction.sessions[1].min_bid == Decimal("266000.00")

    # ja' na 2a praca: o lance minimo atual e' o da 2a, sem price_second redundante
    trator = next(i for i in items if i.external_id == "223276")
    assert trator.price == Decimal("534000.00") and trator.price_second is None
    assert [x.kind for x in trator.auction.sessions] == ["2a_praca"]
    assert trator.auction.sessions[0].ends_at == datetime(2026, 10, 28, 16, 0)
    assert trator.category_hint == "maquinas-agricolas"
    assert trator.raw_attributes["valor_avaliacao"] == "890000.00"
    assert (trator.raw_attributes["ano_fabricacao"], trator.raw_attributes["ano_modelo"]) == (2022, 2022)

    # etapa unica, sem foto (placeholder da fonte), partes e CPF fora (RN-009)
    trt = next(i for i in items if i.external_id == "218966")
    assert [x.kind for x in trt.auction.sessions] == ["unica"]
    assert trt.price == Decimal("511000.00") and trt.price_second is None
    assert trt.image_url is None and trt.images == []
    assert "AUTOMÓVEL" in trt.description
    for forbidden in ("EXEQUENTE", "EXECUTADO", "393.868.618-95", "CPF", "HITALO"):
        assert forbidden not in trt.description
    # leilao unificado do TRT: a vara do lote esta' na descricao, nao no titulo do leilao
    assert trt.auction.committer_name == "85ª VT São Paulo/SP"
    assert trt.raw_attributes["ano_modelo"] == 2023
    assert trt.auction.title.startswith("711ª LEILÃO JUDICIAL UNIFICADO DO TRT")

    mustang = next(i for i in items if i.external_id == "222640")
    assert mustang.auction.committer_name == "2ª VARA DE ÓRFÃOS E SUCESSÕES DE BRASÍLIA"
    for forbidden in ("DORNELLES", "Advogado", "Autor", "Réu", "21202DF"):
        assert forbidden not in mustang.description
    assert mustang.description.startswith("Ford Mustang GTS 1966/1966")
    assert mustang.raw_attributes["ano_modelo"] == 1966
    assert mustang.price == Decimal("100000.00") and mustang.price_second == Decimal("85000.00")

    aero = next(i for i in items if i.external_id == "201382")
    assert aero.category_hint == "outros-veiculos"
    assert aero.raw_attributes["ano_fabricacao"] == 1998
    assert aero.state == "AM"

    s10 = next(i for i in items if i.external_id == "221601")
    assert s10.category_hint == "veiculos"  # "Outros" da fonte: o titulo decide
    assert s10.raw_attributes["lance_2a_praca"] == "71250.00" and s10.price_second is None


def test_leiloesjudiciais_cards_fallback(fixture):
    html = re.sub(r'<script[^>]+id="__NUXT_DATA__".*?</script>', "", fixture("leiloesjudiciais_listing.html"), flags=re.S)
    s = _scraper()
    items = s.parse_listing(html, "/veiculos")
    assert len(items) == 8
    assert s.last_meta["totalPages"] == 25 and s.last_meta["totalItems"] == 1015
    vw = next(i for i in items if i.external_id == "219958")
    assert vw.title == "VW/24220 - 10/10 - Vespasiano/MG"
    # o card rotula "Lance mínimo" o menor valor possivel (o da 2a praca); sem o
    # JSON nao da' para separar as etapas, entao fica o que a fonte mostra
    assert vw.price == Decimal("266000.00") and vw.price_second is None
    assert vw.raw_attributes["valor_avaliacao"] == "380000.00"
    assert (vw.city, vw.state) == ("Vespasiano", "MG") and vw.status_hint == "open"
    assert vw.image_url and vw.image_url.endswith(".webp")
    assert vw.raw_attributes["ano_modelo"] == 2010
    trt = next(i for i in items if i.external_id == "218966")
    assert trt.image_url is None


def test_leiloesjudiciais_auction_detail(fixture):
    s = _scraper()
    items = s.parse_listing(fixture("leiloesjudiciais_listing.html"), "/veiculos")
    vw = next(i for i in items if i.external_id == "219958")
    record, lots = s.parse_auction_page(fixture("leiloesjudiciais_detail.html"))
    assert record["id"] == 100247 and [l["lote_id"] for l in lots] == [219958, 219959, 219960, 219961]
    s.apply_auction(vw, record)
    assert vw.auction.title == "Vespasiano/MG - Caminhões - Reboque"
    assert vw.auction.committer_name == "2ª Vara Cível de Vespasiano/MG"
    assert vw.auction.modality == "online" and vw.auction.auction_type == "judicial"
    assert vw.raw_attributes["tipo_leilao"] == "Judicial Online"
    assert vw.raw_attributes["ufs_leilao"] == "MG"
    first, second = vw.auction.sessions
    assert (first.kind, first.starts_at, first.min_bid) == ("1a_praca", datetime(2026, 11, 4, 13, 0), Decimal("380000.00"))
    assert first.ends_at == datetime(2026, 11, 4, 13, 0)
    assert (second.kind, second.starts_at, second.min_bid) == ("2a_praca", datetime(2026, 11, 4, 14, 0), Decimal("266000.00"))

    # lotes irmaos que a listagem nao mostrou viram itens com as mesmas datas
    extras = [s.item_from_lot(l) for l in lots if str(l["lote_id"]) != "219958"]
    for e in extras:
        s.apply_auction(e, record)
    assert [e.external_id for e in extras] == ["219959", "219960", "219961"]
    reboque = extras[-1]
    assert reboque.title.startswith("Reboque - FNV - FRUEHAUF")
    assert reboque.category_hint == "caminhoes"  # "Veículos Pesados" da fonte
    assert reboque.price == Decimal("60000.00") and reboque.price_second == Decimal("42000.00")
    assert reboque.auction.sessions[1].starts_at == datetime(2026, 11, 4, 14, 0)
    assert reboque.raw_attributes["ano_modelo"] == 1982

    # comitente da descricao (Vara) nao e' trocado pelo cadastro do leilao
    mustang = next(i for i in items if i.external_id == "222640")
    s.apply_auction(mustang, dict(record, comitente=[{"nm": "Palladium ALTERAR"}]))
    assert mustang.auction.committer_name == "2ª VARA DE ÓRFÃOS E SUCESSÕES DE BRASÍLIA"
    trt = next(i for i in items if i.external_id == "218966")
    s.apply_auction(trt, dict(record, comitente=[{"nm": "11ª VARA DO TRABALHO de São Paulo/SP"}, {"nm": "2ª Vara do Trabalho de Cotia/SP"}]))
    assert trt.auction.committer_name == "85ª VT São Paulo/SP"
    # titulo do leilao e' reserva fraca: o cadastro com uma unica Vara ganha dele
    onibus = next(i for i in items if i.external_id == "220094")
    assert onibus.auction.committer_name == "JUSTIÇA FEDERAL DE PORTO ALEGRE/RS - 16ª VARA"
    s.apply_auction(onibus, dict(record, comitente={"nm": "16ª Vara Federal de Porto Alegre/RS"}))
    assert onibus.auction.committer_name == "16ª Vara Federal de Porto Alegre/RS"
    # fechamento estagnado na fonte: fim nunca antes do inicio
    s.apply_auction(trt, dict(record, dt_formatada="05/11/2026", hr_formatada="10:00", dt_segundoleilao_data=None, dt_segundoleilao_hora=None))
    assert [x.kind for x in trt.auction.sessions] == ["unica"]
    assert trt.auction.sessions[0].starts_at == datetime(2026, 11, 5, 10, 0) and trt.auction.sessions[0].ends_at is None


def test_leiloesjudiciais_status():
    s = _scraper()
    lot = {"lote_id": 1, "leilao_id": 2, "nm_titulo_lote": "Lote de teste", "statuslote_id": 15, "nm_statuslote": "Excluido"}
    assert s.item_from_lot(lot).status_hint == "withdrawn"
    assert s.item_from_lot(dict(lot, statuslote_id=19, nm_statuslote="Aguardando")).status_hint == "soon"
    assert s.item_from_lot(dict(lot, statuslote_id=1, nm_statuslote="Aberto para Lance")).status_hint == "open"
    assert s.item_from_lot(dict(lot, statuslote_id=None, nm_statuslote="Encerrado")).status_hint == "closed"
    assert s.item_from_lot(dict(lot, statuslote_id=1, vl_venda="12000.00")).status_hint == "sold"
    assert s.item_from_lot({"lote_id": None, "leilao_id": 2}) is None
    assert s.item_from_lot(dict(lot, nm_titulo_leilao="LEILÃO SIMULAÇÃO - TESTE TRANSMISSÃO")) is None


def test_leiloesjudiciais_auction_type():
    """O portal e' judicial, mas abriga vendas administrativas (PRF): sem Vara
    nem CNJ o tipo fica aberto ate' o cadastro do leilao decidir."""
    s = _scraper()
    prf = {"lote_id": 224214, "leilao_id": 101323, "nm_titulo_lote": "FIAT/UNO MILLE SMART – 00/00 – Dourados/MS",
           "nm_titulo_leilao": "VENDA DIRETA DA SUPERINTENDÊNCIA DA POLÍCIA RODOVIÁRIA FEDERAL DE MATO GROSSO DO SUL - SUCATA INSERVÍVEL",
           "nm_descricao": "AUTOMÓVEL FIAT/UNO MILLE SMART, Ano/Modelo 2000. Processos 08669.002918/2026-99; Classificação SUCATA INSERVÍVEL"}
    item = s.item_from_lot(prf)
    assert item.auction.auction_type is None and "origem" not in item.raw_attributes
    assert item.raw_attributes["ano_modelo"] == 2000
    s.apply_auction(item, {"id": 101323, "nm": prf["nm_titulo_leilao"], "tp_judicial_extrajudicial": 1, "nm_statusleilao": "Venda Direta",
                           "comitente": {"nm": "SUPERINTENDÊNCIA DE POLÍCIA RODOVIÁRIA FEDERAL NO ESTADO DE MATO GROSSO DO SUL - PRF/MS"}})
    assert item.auction.auction_type == "extrajudicial" and "origem" not in item.raw_attributes
    assert item.auction.committer_name.startswith("SUPERINTENDÊNCIA")
    judicial = dict(prf, nm_titulo_leilao="Leilão de bens", nm_descricao="Veículo penhorado. (Proc. 5002993-38.2016.8.13.0290).")
    item = s.item_from_lot(judicial)
    assert item.auction.auction_type == "judicial" and item.raw_attributes["origem"] == "judicial"
    s.apply_auction(item, {"id": 1, "nm": "Leilão de bens", "tp_judicial_extrajudicial": 2})
    assert item.auction.auction_type == "judicial" and item.raw_attributes["origem"] == "judicial"


def test_leiloesjudiciais_paths_and_helpers():
    s = _scraper(pages=["/veiculos/carros?ordenacao=min"], states=["sp", "MG"])
    assert s._listing_paths() == ["/veiculos/carros/estado/SP?ordenacao=min", "/veiculos/carros/estado/MG?ordenacao=min"]
    assert s._page_url("/veiculos", 1) == "https://www.leiloesjudiciais.com.br/veiculos"
    assert s._page_url("/veiculos?ordenacao=min", 2) == "https://www.leiloesjudiciais.com.br/veiculos?ordenacao=min&pagina=2"
    assert LeiloesJudiciaisScraper._dec("182003.45") == Decimal("182003.45")
    assert LeiloesJudiciaisScraper._dec("R$ 182.003,45") == Decimal("182003.45")
    assert LeiloesJudiciaisScraper._dec(None) is None
    assert LeiloesJudiciaisScraper._years("Volvo/VM 270 6x4R - 22/22 - Tocantinópolis/TO") == (2022, 2022)
    assert LeiloesJudiciaisScraper._years("Mercedes-Benz/L-2013 - 79/79 - Novo Horizonte") == (1979, 1979)
    assert LeiloesJudiciaisScraper._years("Lote 1/2 - Sucata") == (None, None)
    assert LeiloesJudiciaisScraper._years("Fiat Uno", "ano fabricação/modelo 2011/2012, cor prata") == (2011, 2012)
