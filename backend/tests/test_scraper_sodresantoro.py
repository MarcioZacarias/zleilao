"""Sodré Santoro: parser offline sobre a resposta de `POST /api/search-lots`
(fixture com 14 lotes reais de 17/10/2026 cobrindo judicial em 1ª e 2ª praça,
sucata, extrajudicial com e sem lance, lance inicial zerado, comitente
"outros" e os quatro patios). Nomes, placas, RENAVAM, chassi e enderecos de
pessoa foram trocados por valores ficticios antes de gravar (RN-009): os
testes verificam que nem esses sobrevivem ao parser.
"""
import json
from decimal import Decimal

import pytest

from app.scrapers.sodresantoro import (
    DEFAULT_INDICES, PRIVATE_KEYS, SEARCH_FILTER, SEARCH_SORT, SodreSantoroScraper, fix_mojibake,
)


def _scraper(**config) -> SodreSantoroScraper:
    return SodreSantoroScraper(source_id=12, base_url=None, config=config)


@pytest.fixture
def lots(fixture):
    return json.loads(fixture("sodre_search.json"))["results"]


@pytest.fixture
def items(lots):
    s = _scraper()
    parsed = s.parse_results(lots)
    assert s.stats.errors == 0
    return {i.external_id: i for i in parsed}


def test_search_body():
    s = _scraper()
    body = s.search_body(100, 100)
    assert body["indices"] == DEFAULT_INDICES
    assert (body["from"], body["size"]) == (100, 100)
    assert body["sort"] == SEARCH_SORT and body["query"] == {"bool": {"filter": SEARCH_FILTER}}
    json.dumps(body)  # tem que ser serializavel como a SPA manda
    assert _scraper(indices="judiciais-veiculos").search_body(0, 50)["indices"] == ["judiciais-veiculos"]
    assert _scraper(indices=["veiculos"]).search_body(0, 50)["indices"] == ["veiculos"]


def test_parse_results_cobertura(items):
    assert len(items) == 14
    for it in items.values():
        assert it.official_url.startswith("https://www.sodresantoro.com.br/leilao/") and "/lote/" in it.official_url
        assert it.auction and it.auction.official_url == f"https://www.sodresantoro.com.br/leilao/{it.auction.external_id}"
        assert it.status_hint == "open"
        assert it.raw_attributes["status_fonte"] == "andamento"


def test_judicial_sucata_primeira_praca(items):
    it = items["2799014"]
    assert it.title == "Sucata Honda CG 125 2000/2000"
    assert it.official_url == "https://www.sodresantoro.com.br/leilao/29043/lote/2799014"
    assert it.category_hint == "sucatas"
    assert it.price == Decimal("500.00") and it.price_kind == "lance_inicial"
    assert it.lot_number == "0001"
    raw = it.raw_attributes
    assert raw["condicao"] == "sucata" and raw["sucata"] is True and raw["sinistro_fonte"] == "sucata desmanche"
    assert raw["origem"] == "judicial" and raw["origem_fonte"] == "seguro"  # a flag judicial manda
    assert raw["vara"] == "1ª Vara Criminal da Comarca de Ribeirão Preto/SP"
    assert raw["comitente"] == raw["vara"]
    assert raw["processo"] == "1503990-47.2024.8.26.0530" and raw["acao_judicial"] == "ação penal"
    assert raw["placa_mascarada"] == "final 3"
    assert raw["comissao_pct"] == 8.0 and "taxas" not in raw
    assert raw["valor_avaliacao"] == "500.00"
    assert raw["cor"] == "Cinza" and raw["categoria_fonte"] == "motos"
    assert "km" not in raw and "combustivel" not in raw and "combustivel_fonte" not in raw  # 0 e "indefinido"
    assert "opcionais" not in raw and "patio" not in raw and "lance_atual" not in raw
    # "outros locais" nao e' cidade; a comarca da vara e'
    assert (it.city, it.state, it.location_text) == ("Ribeirão Preto", "SP", None)
    assert it.image_url == "https://photos.sodresantoro.com.br/veiculos/29043/2799014/1788268760_C1667175N1.JPG"
    assert "SUCATA de uma Honda CG 125" in it.description and "Avaliação: R$ 500,00" in it.description
    assert "Comitente: 1ª Vara Criminal" in it.description and "1ª Praça." in it.description
    a = it.auction
    assert a.external_id == "29043" and a.auction_type == "judicial"
    assert a.title == "(TJ) - 1ª Vara Criminal da Comarca de Ribeirão Preto/SP"
    assert a.auctioneer_name == "Otavio Lauro Sodre Santoro"
    assert a.modality is None
    assert [x.kind for x in a.sessions] == ["1a_praca", "2a_praca"]
    assert a.sessions[0].starts_at.strftime("%Y-%m-%d %H:%M") == "2026-10-19 11:00"
    assert a.sessions[0].ends_at.strftime("%Y-%m-%d %H:%M") == "2026-10-19 11:00"
    assert a.sessions[0].min_bid == Decimal("500.00")
    assert a.sessions[1].starts_at.strftime("%Y-%m-%d %H:%M") == "2026-10-27 11:00"
    assert a.sessions[1].ends_at is None and a.sessions[1].min_bid is None


def test_judicial_com_lance(items):
    it = items["2802588"]
    assert it.title == "Volkswagen Amarok V6 Extr AC4 2018/2019"
    assert it.price == Decimal("96300.00") and it.price_kind == "lance_atual"
    raw = it.raw_attributes
    assert raw["lance_inicial"] == "91285.20" and raw["lance_atual"] == "96300.00"
    assert raw["cambio"] == "automatico" and raw["combustivel"] == "diesel"
    assert raw["opcionais"] == ["ar-condicionado", "direcao-hidraulica", "chave-ignicao"]
    assert raw["condicao"] == "normal" and raw["sinistro_fonte"] == "sem sinistro"
    assert raw["ano_fabricacao"] == 2018 and raw["ano_modelo"] == 2019
    assert it.category_hint == "utilitarios-leves"  # o HINT_MAP do classificador resolve
    assert (it.city, it.state, it.location_text) == ("Ribeirão Preto", "SP", "Ribeirão Preto/SP")
    assert raw["patio"] == "Ribeirão Preto/SP"
    assert raw["comitente"] == "5ª Vara Criminal de Ribeirão Preto/SP"  # a vara, nao o client_name
    assert it.auction.committer_name == raw["comitente"]
    assert "placa final 0" in it.description and "executad" not in it.description.lower()


def test_judicial_segunda_praca(items):
    it = items["2810875"]
    assert it.price == Decimal("15300.00") and it.price_kind == "lance_atual"
    assert it.raw_attributes["praca"] == "2ª Praça"
    s1, s2 = it.auction.sessions
    # `auction_date_2` (30/09) e' a 1a praca ja' passada: a ordem cronologica decide
    assert (s1.kind, s1.starts_at.strftime("%d/%m/%Y")) == ("1a_praca", "30/09/2026")
    assert (s2.kind, s2.starts_at.strftime("%d/%m/%Y %H:%M")) == ("2a_praca", "22/10/2026 11:00")
    assert s2.ends_at.strftime("%d/%m/%Y %H:%M") == "22/10/2026 11:00" and s2.min_bid == Decimal("13756.00")
    assert s1.ends_at is None and s1.min_bid is None
    assert (it.city, it.state) == ("Campo Largo", "PR")
    assert it.auction.auctioneer_name == "Otavio Lauro Sodre Santoro (Jucepar)"
    assert it.auction.title.startswith("(TJ) - Vara e Ofício do Juizado Especial Cível da Comarca de Campo Largo/PR")


def test_dados_pessoais_na_descricao(items):
    # placa, RENAVAM e chassi (ficticios) em claro sao mascarados; a frase do
    # depositario (nome + endereco) sai inteira
    it = items["2803152"]
    d = it.description
    assert "ABC-1234" not in d and "ABC-****" in d
    assert "00000000000" not in d and "renavam ***********" in d
    assert "9XXXXXXXXXXXXXXX1" not in d and "XXX1" in d
    assert "Fulana" not in d
    assert "Rua Exemplo" not in d and "n° 100" not in d
    assert "Comarca de Pindamonhangaba/SP" in d  # a comarca vem do comitente, que e' institucional
    assert "Avaliação: R$ 8.273,00" in d and it.raw_attributes["valor_avaliacao"] == "8273.00"
    assert it.price == Decimal("8788.00") and it.price_kind == "lance_inicial"
    assert (it.city, it.state) == ("Pindamonhangaba", "SP")  # da comarca, nao do endereco

    it = items["2810875"]
    d = it.description
    assert "9A87" not in d and "XYZ-****" in d and "1111111111" not in d
    assert "(i) O bem está sob o depósito" not in d and "Rua Exemplo" not in d
    assert "(ii) Foram localizados débitos" in d  # o resto da observacao fica
    assert it.raw_attributes["valor_avaliacao"] == "27512.00"

    it = items["2814576"]
    assert "Rua Exemplo" not in it.description and "executado" not in it.description
    assert "certidão do oficial de justiça" in it.description
    assert it.raw_attributes["origem"] == "judicial" and "origem_fonte" not in it.raw_attributes
    assert (it.city, it.state) == (None, None)  # "veepem" nao diz a comarca
    assert it.raw_attributes["valor_avaliacao"] == "4000.00"

    # comitente "outros" e' pessoa fisica: contato e endereco da casa saem
    for ext in ("2815700", "2815504"):
        it = items[ext]
        d = it.description
        assert "Fulano" not in d and "fone" not in d.lower() and "whatts" not in d.lower()
        assert "00-00000.0000" not in d and "00000-0000" not in d
        assert "Exemplo" not in d
        assert it.auction.committer_name is None and "comitente" not in it.raw_attributes
        assert (it.city, it.state, it.location_text) == (None, None, None)
        assert "lot_location_address" not in json.loads(it.raw_payload)  # nem no payload bruto
    assert "IPVA 2026 PAGO" in items["2815700"].description and "Blindagem" in items["2815700"].description
    assert items["2815700"].raw_attributes["origem"] == "frota"  # declarada pela fonte: vale
    assert "origem" not in items["2815504"].raw_attributes  # "outros" nao diz de onde veio
    assert "Motor devidamente cadastrado" in items["2815504"].description
    assert items["2814576"].title == "Ford Belina II L 1979/1979"


def test_payload_sem_partes(lots):
    s = _scraper()
    lot = dict(lots[0], lot_judicial_executed="Fulano de Tal", lot_judicial_executor="Justiça Pública",
               lot_judicial_judge="Dra. Beltrana", lot_judicial_defendant="Sicrano", bid_user_nickname="a*p",
               search_terms="fulano de tal honda cg 125", lot_note="Visitação ... (11) 2464-6464")
    it = s.parse_results([lot])[0]
    payload = json.loads(it.raw_payload)
    assert not any(k in payload for k in PRIVATE_KEYS) and "lot_note" not in payload
    assert payload["lot_rate_information"] == "Comissão: 8.00% do valor do lance"  # mojibake desfeito
    dump = it.raw_payload + it.description + json.dumps(it.raw_attributes, ensure_ascii=False)
    assert "Fulano" not in dump and "Beltrana" not in dump and "Sicrano" not in dump and "a*p" not in dump


def test_extrajudicial_allianz(items):
    it = items["2815649"]
    assert it.title == "Jeep Renegade Moab 2020/2021"
    assert it.price == Decimal("22500.00") and it.price_kind == "lance_atual"
    raw = it.raw_attributes
    assert "lance_inicial" not in raw and raw["lance_atual"] == "22500.00"  # 0,00 nao e' lance minimo
    assert raw["origem"] == "seguradora" and "origem_fonte" not in raw  # pelo comitente
    assert raw["condicao"] == "sinistro_media_monta" and raw["sinistro_fonte"] == "média monta"
    assert raw["combustivel"] == "diesel" and raw["km"] == 121527 and raw["cor"] == "Preta"
    assert raw["comissao_pct"] == 5.0
    assert raw["taxas"] == {"Depósito de Bens": "2350.00", "Logística e/ou Despachante": "500.00"}
    assert raw["permite_financiamento"] is False and "Financiável." not in it.description
    assert raw["patio"] == "Curitiba I/PR"
    # o endereco do patio (institucional) vale mais que o nome do patio
    assert (it.city, it.state) == ("São José dos Pinhais", "PR")
    assert it.location_text == "R Vanderlei Moreno, 9850 - São José dos Pinhais/PR"
    assert "R Vanderlei Moreno" in it.description and "Sinistro: média monta." in it.description
    assert "Comissão do leiloeiro: 5%." in it.description
    assert it.category_hint == "carros"
    a = it.auction
    assert a.external_id == "29132" and a.auction_type == "extrajudicial"
    assert a.title == "Banco, Seguradoras, Etc" and a.committer_name == "Allianz Seguros S.A"
    assert a.auctioneer_name == "Luiz Fernando de Abreu Sodre Santoro"
    assert [x.kind for x in a.sessions] == ["unica"]
    assert a.sessions[0].starts_at.strftime("%Y-%m-%d %H:%M") == "2026-10-19 09:30"
    assert a.sessions[0].ends_at.strftime("%Y-%m-%d %H:%M:%S") == "2026-10-19 09:30:45"
    assert a.sessions[0].min_bid is None


def test_demais_extrajudiciais(items):
    sem_lance = items["2815748"]
    assert sem_lance.price is None and sem_lance.price_kind == "lance_inicial"
    assert "lance_inicial" not in sem_lance.raw_attributes and "lance_atual" not in sem_lance.raw_attributes

    amg = items["2815700"]
    assert amg.price == Decimal("220000.00") and amg.price_kind == "lance_inicial"
    assert amg.raw_attributes["condicao"] == "sinistro_recuperavel"

    pan = items["2816112"]
    assert pan.raw_attributes["origem"] == "financeira"
    assert pan.raw_attributes["permite_financiamento"] is True and "Financiável." in pan.description
    assert pan.category_hint == "carros"

    scania = items["2815938"]
    assert scania.title == "Scania R540 A6X4 2021/2021"
    assert scania.category_hint == "caminhoes"
    assert (scania.city, scania.state) == ("Monte Mor", "SP")

    assert items["2815662"].category_hint == "utilitarios"  # "van leve"
    assert items["2815651"].raw_attributes["combustivel"] == "hibrido"
    assert items["2815651"].raw_attributes["condicao"] == "sinistro_recuperavel"

    suhai = items["2816155"]
    assert suhai.raw_attributes["origem"] == "seguradora"
    # endereco sem UF: a cidade vem do nome do patio
    assert (suhai.city, suhai.state) == ("Guarulhos", "SP")
    assert suhai.location_text == "Rod. Pres. Dutra, Km 223,5 Pista Lateral Guarulhos"


def test_fallbacks(lots):
    s = _scraper()
    base = lots[5]  # Allianz
    # sem id de lote ou de leilao nao entra; sem marca/modelo usa o lot_title
    assert s.parse_results([dict(base, lot_id=None), dict(base, auction_id=None)]) == []
    it = s.parse_results([dict(base, lot_brand=None, lot_model="", lot_title="jeep - renegade moab")])[0]
    assert it.title == "Jeep Renegade Moab 2020/2021"
    assert "marca" not in it.raw_attributes
    # status desconhecido: texto, depois status do leilao
    assert s.parse_results([dict(base, lot_status="Arrematado")])[0].status_hint == "sold"
    assert s.parse_results([dict(base, lot_status="Não vendido")])[0].status_hint == "closed"
    assert s.parse_results([dict(base, lot_status="xpto", auction_status="encerrado")])[0].status_hint == "closed"
    assert s.parse_results([dict(base, lot_status="xpto", auction_status="online")])[0].status_hint == "open"
    # placa em claro vinda da fonte nunca entra
    assert "placa_mascarada" not in s.parse_results([dict(base, lot_plate="ABC1D23")])[0].raw_attributes
    # combustivel fora do mapa fica so' como texto da fonte
    raw = s.parse_results([dict(base, lot_fuel="Querosene")])[0].raw_attributes
    assert "combustivel" not in raw and raw["combustivel_fonte"] == "querosene"
    # praca so' pelo rotulo (sem lot_praca_status) e desconto da 2a praca
    jud = dict(lots[0], lot_praca_status=None, lot_praca_label="2ª Praça", tj_praca_value="300.00", tj_praca_discount="40")
    it = s.parse_results([jud])[0]
    assert it.auction.sessions[1].ends_at is not None and it.auction.sessions[1].min_bid == Decimal("500.00")
    assert it.price_second == Decimal("300.00") and it.raw_attributes["desconto_2a_praca_pct"] == "40.00"
    # sem datas de 2a praca e sem rotulo: sessao unica
    uni = dict(lots[0], auction_date_2=None, lot_praca_status=None, lot_praca_label=None)
    assert [x.kind for x in s.parse_results([uni])[0].auction.sessions] == ["unica"]
    assert s.stats.errors == 0


def test_helpers():
    S = SodreSantoroScraper
    assert S.nice_name("(tj) - 1ª vara criminal da comarca de ribeirão preto/sp") == "(TJ) - 1ª Vara Criminal da Comarca de Ribeirão Preto/SP"
    assert S.nice_name("allianz seguros s.a") == "Allianz Seguros S.A"
    assert S.nice_name("BANCO, SEGURADORAS, ETC") == "Banco, Seguradoras, Etc"
    assert S.nice_name("otavio\xa0lauro sodre santoro (jucepar)") == "Otavio Lauro Sodre Santoro (Jucepar)"
    assert S.nice_name("curitiba i/pr") == "Curitiba I/PR"
    assert S.nice_name("  ") is None and S.nice_name(None) is None

    assert S.model_case("cg 160 fan esdi") == "CG 160 Fan ESDI"
    assert S.model_case("r540 a6x4") == "R540 A6X4"
    assert S.model_case("mercedes-benz") == "Mercedes-Benz"
    assert S.model_case("bmw") == "BMW" and S.model_case("kia") == "Kia"
    assert S.model_case("xy125-6a") == "XY125-6A"
    assert S.model_case("belina ii l") == "Belina II L"
    assert S.model_case("xre 300 abs") == "XRE 300 ABS" and S.model_case("gol 1.0") == "Gol 1.0"
    assert S.model_case("") is None

    assert S.city_state_from_location("curitiba i/pr") == ("Curitiba", "PR")
    assert S.city_state_from_location("guarulhos i/sp") == ("Guarulhos", "SP")
    assert S.city_state_from_location("ribeirão preto/sp") == ("Ribeirão Preto", "SP")
    assert S.city_state_from_location("outros locais") == (None, None)
    assert S.city_state_from_location(None) == (None, None)
    assert S.city_state_from_address("r vanderlei moreno, 9850 - são josé dos pinhais/pr") == ("São José dos Pinhais", "PR")
    assert S.city_state_from_address("rua x 184, cambuci, são paulo # sp") == ("São Paulo", "SP")
    assert S.city_state_from_address("rod. pres. dutra, km 223,5 pista lateral guarulhos") == (None, None)
    assert S.city_state_from_court("5ª vara criminal de ribeirão preto/sp") == ("Ribeirão Preto", "SP")
    assert S.city_state_from_court("vara de execuções fiscais de são paulo/sp") == ("São Paulo", "SP")
    assert S.city_state_from_court("vara estadual da execução da pena de multa - veepem") == (None, None)
    assert S.city_state_from_court(None) == (None, None)

    assert fix_mojibake("ComissÃ£o: 5.00%, LogÃ\xadstica") == "Comissão: 5.00%, Logística"
    assert fix_mojibake("Comissão: 5%") == "Comissão: 5%"
    assert fix_mojibake(None) is None
    pct, taxas = S.parse_rate("Comissão: 6.00% do valor do lance, Outros Débitos: 1.330,00, Sedex: Valores na condição de venda")
    assert pct == 6.0 and taxas == {"Outros Débitos": "1330.00"}
    assert S.parse_rate(None) == (None, {})

    assert S.condition_from_sinister("sucata desmanche") == "sucata"
    assert S.condition_from_sinister("Média Monta") == "sinistro_media_monta"
    assert S.condition_from_sinister("grande monta") == "sinistro_grande_monta"
    assert S.condition_from_sinister("pequena monta") == "sinistro_recuperavel"
    assert S.condition_from_sinister("sem sinistro") == "normal"
    assert S.condition_from_sinister("xpto") is None and S.condition_from_sinister(None) is None

    assert S.origin_from_client("Bradesco Seguros") == "seguradora"
    assert S.origin_from_client("Banco Bradesco") == "financeira"
    assert S.origin_from_client("Suhai Seguradora S.A") == "seguradora"
    assert S.origin_from_client("Banco Pan S.A") == "financeira"
    assert S.origin_from_client("Localiza Digital") == "locadora"
    assert S.origin_from_client("Fbc Links Brindes Ltda") is None and S.origin_from_client(None) is None

    assert S.category_hint("caminhões") == "caminhoes" and S.category_hint("utilitarios leves") == "utilitarios-leves"
    assert S.category_hint("van leve") == "utilitarios" and S.category_hint("Ônibus") == "onibus"
    assert S.category_hint("bens diversos") == "bens-diversos" and S.category_hint("") is None

    desc, aval = S.scrub_description("Fiat Uno, placa final 2. Avaliação: R$ 1.000,00 (jan/2026). Bem em poder do executado "
                                     "Fulano, Rua X, 1. - Visitas com o Sr. Beltrano, fone (11) 99999-0000 - IPVA pago.")
    assert desc == "Fiat Uno, placa final 2. Avaliação: R$ 1.000,00 (jan/2026). - IPVA pago." and aval == "1000.00"
    desc, _ = S.scrub_description("Bem encontra-se: R Vanderlei Moreno, 9850 - Cambio: Manual.", strict=True)
    assert desc == "Cambio: Manual."
    desc, _ = S.scrub_description("Bem encontra-se: R Vanderlei Moreno, 9850 - Cambio: Manual.")
    assert desc == "Bem encontra-se: R Vanderlei Moreno, 9850 - Cambio: Manual."
    assert S.scrub_description("") == (None, None)
    assert S.scrub_description("Visitas com o Sr. Fulano.") == (None, None)


@pytest.mark.asyncio
async def test_scrape_pagina_e_marca_parcial(lots, monkeypatch):
    calls: list = []

    async def fake_fetch(url, params=None, headers=None):
        calls.append(("GET", url))
        return "<html>"

    async def fake_search(offset, size):
        calls.append(("POST", offset, size))
        return {"results": lots[offset:offset + size], "total": len(lots), "page": offset // size + 1, "perPage": size}

    async def no_delay():
        pass

    s = _scraper(page_size=5, max_pages=2)
    monkeypatch.setattr(s, "fetch", fake_fetch)
    monkeypatch.setattr(s, "search", fake_search)
    monkeypatch.setattr(s, "delay", no_delay)
    items = await s.run()
    assert calls == [("GET", "https://www.sodresantoro.com.br/lotes"), ("POST", 0, 5), ("POST", 5, 5)]
    assert len(items) == 10 and s.stats.pages == 2 and s.stats.errors == 0
    assert s.stats.complete is False and s.stats.notes == ["parou em 2 paginas: 10 de 14 lotes"]

    # varredura completa: para no total informado, sem pedir pagina vazia
    calls.clear()
    s = _scraper(page_size=5, max_pages=12)
    monkeypatch.setattr(s, "fetch", fake_fetch)
    monkeypatch.setattr(s, "search", fake_search)
    monkeypatch.setattr(s, "delay", no_delay)
    items = await s.run()
    assert len(items) == 14 and s.stats.pages == 3 and s.stats.complete is True
    assert [c for c in calls if c[0] == "POST"] == [("POST", 0, 5), ("POST", 5, 5), ("POST", 10, 5)]

    # capa falhando nao impede a busca; busca falhando marca parcial
    async def bad_fetch(url, params=None, headers=None):
        raise RuntimeError("403 em /lotes")

    async def bad_search(offset, size):
        raise RuntimeError("403 em /api/search-lots")

    s = _scraper()
    monkeypatch.setattr(s, "fetch", bad_fetch)
    monkeypatch.setattr(s, "search", fake_search)
    monkeypatch.setattr(s, "delay", no_delay)
    assert len(await s.run()) == 14 and s.stats.complete is True
    assert s.stats.errors == 1 and s.stats.notes[0].startswith("capa https://www.sodresantoro.com.br/lotes falhou")

    s = _scraper()
    monkeypatch.setattr(s, "fetch", fake_fetch)
    monkeypatch.setattr(s, "search", bad_search)
    monkeypatch.setattr(s, "delay", no_delay)
    assert await s.run() == []
    assert s.stats.complete is False and s.stats.notes == ["pagina 1 da busca falhou: 403 em /api/search-lots"]
