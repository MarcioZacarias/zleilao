"""Superbid: parser offline sobre a resposta JSON do microservico de ofertas
e a agenda de eventos (fixtures recortadas de respostas reais de 17/10/2026,
ja' sem dono do veiculo, telefones, login de licitante e partes do processo)."""
import json
from decimal import Decimal

import httpx
import pytest

from app.scrapers.superbid import SuperbidScraper, slugify


def _scraper(**config) -> SuperbidScraper:
    return SuperbidScraper(source_id=12, base_url=None, config=config)


@pytest.fixture
def superbid(fixture):
    s = _scraper()
    data = json.loads(fixture("superbid_offers.json"))
    events = s.events_from_json(json.loads(fixture("superbid_events.json")))
    return s, data["offers"], events


def test_slug_e_urls():
    s = _scraper()
    # Mesmos slugs que o site poe nos cards (17/10/2026)
    assert slugify("02 PNEUS 265/45ZR20 CONTINENTAL COM RODA DE ALUMÍNIO MERCEDES-BENZ") == \
        "02-pneus-265-45zr20-continental-com-roda-de-aluminio-mercedes-benz"
    assert s.offer_url("FIAT STRADA FIRE FLEX, 2012/2012, Placa FINAL 1 (PR),  (Ref.: 26919)", 5041304) == \
        "https://www.superbid.net/oferta/fiat-strada-fire-flex-2012-2012-placa-final-1-pr-ref-26919-5041304"
    assert s.offer_url("", 7) == "https://www.superbid.net/oferta/7"
    assert s.event_url("3ª Vara Federal de Maringá", 797614) == "https://www.superbid.net/evento/3a-vara-federal-de-maringa-797614"


def test_category_entries():
    s = _scraper(categorias=[
        "carros-motos", "carros-motos/motos", "https://www.superbid.net/categorias/caminhoes-onibus",
        {"url": "carros-motos", "filter": "auction.subMarketplaces.subMarketplaceId:3", "order_by": "endDate:desc"},
        "", None,
    ])
    entries = s.category_entries()
    assert [e["url"] for e in entries] == [
        "https://www.superbid.net/categorias/carros-motos",
        "https://www.superbid.net/categorias/carros-motos/motos",
        "https://www.superbid.net/categorias/caminhoes-onibus",
        "https://www.superbid.net/categorias/carros-motos",
    ]
    assert entries[0]["order_by"] == "endDate:asc" and entries[0]["filter"] == ""
    assert entries[3]["filter"] == "auction.subMarketplaces.subMarketplaceId:3" and entries[3]["order_by"] == "endDate:desc"
    assert entries[3]["label"] == "carros-motos [auction.subMarketplaces.subMarketplaceId:3]"
    assert [e["label"] for e in _scraper().category_entries()] == ["carros-motos", "caminhoes-onibus", "maquinas-pesadas-agricolas"]


def test_events_from_json(superbid):
    s, _, events = superbid
    assert len({e["id"] for e in events.values()}) == 3
    assert events["797249"]["store"]["name"] == "BEZERRA LEILÕES"
    assert events["797248"]["id"] == 797249  # indexado tambem pelo id de cada praca
    assert events["802215"]["id"] == 802214
    assert s.events_from_json(None) == {} and s.events_from_json({"events": [{"sem_id": 1}, "lixo"]}) == {}


def test_parse_offers(superbid):
    s, offers, _ = superbid
    items = s.parse_offers(offers)
    assert len(items) == 14
    assert s.stats.errors == 0
    by_id = {i.external_id: i for i in items}

    hasta = by_id["5013183"]
    assert hasta.title == "FIAT SIENA FIRE FLEX 2009 2010 PRATA"
    assert hasta.official_url == "https://www.superbid.net/oferta/fiat-siena-fire-flex-2009-2010-prata-5013183"
    assert hasta.price == Decimal("8958.30") and hasta.price_kind == "lance_atual"  # 1 lance
    assert hasta.price_second is None
    assert hasta.lot_number == "1"
    assert (hasta.city, hasta.state, hasta.location_text) == ("Casa Branca", "SP", "Casa Branca - SP")
    assert hasta.image_url.startswith("https://ms.sbwebservices.net/photos/") and len(hasta.images) == 3
    assert hasta.category_hint == "carros" and hasta.status_hint == "open"
    raw = hasta.raw_attributes
    assert (raw["marca"], raw["modelo"], raw["cor"]) == ("Fiat", "Siena Fire Flex", "Prata")
    assert (raw["ano_fabricacao"], raw["ano_modelo"]) == (2009, 2010)
    assert raw["valor_fipe"] == "27564.00"
    assert "placa" not in raw and "placa_final" not in raw
    assert raw["lance_inicial"] == "8958.30" and raw["lance_atual"] == "8958.30"
    assert raw["incremento"] == "413.46" and raw["n_lances"] == 1 and raw["n_licitantes"] == 1
    assert raw["visitas"] == 350 and raw["fotos"] == 6
    assert raw["loja"] == "HASTA SP" and raw["leiloeiro"] == "Marcia Anny Mardirosian Nazar"
    assert raw["comitente"] == "PREFEITURA MUNICIPAL DE SÃO BERNARDO DO CAMPO"
    assert raw["sub_marketplace"] == "gov" and raw["modalidade"] == "Leilão"
    assert raw["categoria_fonte"] == "Carros / Hatches"
    assert "praca" not in raw and "origem" not in raw and "sucata" not in raw
    assert "Comitente: PREFEITURA MUNICIPAL DE SÃO BERNARDO DO CAMPO." in hasta.description
    assert "Loja: HASTA SP." in hasta.description and "Leilão: LEILÃO DE VEÍCULOS CONSERVADOS 19/2026 SBC." in hasta.description
    assert "Agendamento e Retirada" in hasta.description  # texto da fonte, sem HTML
    assert "<" not in hasta.description
    assert hasta.description.count("FIAT SIENA FIRE FLEX 2009 2010 PRATA") == 1  # a fonte repete o titulo no texto
    a = hasta.auction
    assert a.external_id == "801204" and a.title == "LEILÃO DE VEÍCULOS CONSERVADOS 19/2026 SBC"
    assert a.auction_type == "extrajudicial" and a.modality == "online"
    assert a.auctioneer_name == "Marcia Anny Mardirosian Nazar" and a.auctioneer_registration is None
    assert a.committer_name == "PREFEITURA MUNICIPAL DE SÃO BERNARDO DO CAMPO"
    assert a.official_url == "https://www.superbid.net/evento/leilao-de-veiculos-conservados-19-2026-sbc-801204"
    assert [x.kind for x in a.sessions] == ["unica"]
    assert a.sessions[0].starts_at.strftime("%Y-%m-%d %H:%M") == "2026-10-04 09:00"
    assert a.sessions[0].ends_at.strftime("%Y-%m-%d %H:%M") == "2026-10-19 09:00"
    assert a.sessions[0].min_bid == Decimal("8958.30")
    payload = json.loads(hasta.raw_payload)
    assert payload["seller"] == {"id": 1845410, "name": "PREFEITURA MUNICIPAL DE SÃO BERNARDO DO CAMPO"}
    assert "winnerBid" not in payload and "detailedDescription" not in payload["product"]
    assert "translation" not in payload["product"]["productType"] and "address" not in payload["auction"]
    assert "phone" not in hasta.raw_payload and "vehicleOwner" not in hasta.raw_payload

    sem_lance = by_id["5013180"]
    assert sem_lance.price == Decimal("4741.62") and sem_lance.price_kind == "lance_inicial"
    assert "lance_atual" not in sem_lance.raw_attributes and sem_lance.raw_attributes["n_lances"] == 0
    assert "marca" not in sem_lance.raw_attributes  # "IMP." e' o prefixo de importado, nao marca
    assert sem_lance.raw_attributes["modelo"] == "Vw Polo Clas. 1.8 Mi"

    moto = by_id["4858399"]
    assert moto.title == "Honda CG 150 Titan" and moto.category_hint == "motos"
    assert moto.price == Decimal("8286.53") and moto.price_kind == "lance_inicial"
    assert moto.price_second == Decimal("8286.53")  # 2ª praca com o mesmo valor
    assert moto.images == [] and moto.image_url is None  # sem foto nao se inventa imagem
    assert (moto.city, moto.state) == ("Brusque", "SC")
    raw = moto.raw_attributes
    assert raw["processo"] == "5003166-73.2023.8.24.0011" and raw["praca"] == "1º Praça"
    assert raw["origem"] == "judicial" and raw["sub_marketplace"] == "judicial"
    assert raw["comitente"] == "TRIBUNAL DE JUSTICA DE SANTA CATARINA" and raw["loja"] == "CENTRO DOS LEILÕES"
    assert raw["matricula_leiloeiro"] == "AARC/429" and "vara" not in raw
    assert "Praça: 1º Praça." in moto.description and "Processo: 5003166-73.2023.8.24.0011." in moto.description
    a = moto.auction
    assert a.auction_type == "judicial" and a.auctioneer_registration == "AARC/429"
    assert [x.kind for x in a.sessions] == ["1a_praca", "2a_praca"]
    assert a.sessions[0].starts_at.strftime("%d/%m/%Y %H:%M") == "28/07/2026 00:00"
    assert a.sessions[0].ends_at.strftime("%d/%m/%Y %H:%M") == "03/11/2026 14:30"
    assert a.sessions[1].starts_at.strftime("%d/%m/%Y %H:%M") == "03/11/2026 15:30"
    assert a.sessions[1].min_bid == Decimal("8286.53")

    ka = by_id["5026455"]
    assert ka.title == "Ford/KA, 11/11, flex, branco"
    raw = ka.raw_attributes
    assert raw["vara"] == "2ª Vara Cível da Comarca de Votuporanga/SP"
    assert raw["foro"] == "Tribunal de Justiça de São Paulo"
    assert raw["processo_tipo"] == "Cumprimento de sentença - Acidente de Trânsito"
    assert set(json.loads(ka.raw_payload)["product"]["judicial"]) <= {
        "processNumber", "processYear", "processType", "nature", "foro", "district", "vara"}

    sinistrada = by_id["5053037"]
    assert sinistrada.title == "HONDA NXR160 BROS ESDD 2020/2020, Placa FINAL 5"  # "(ID.: 51690)" sai
    assert sinistrada.raw_attributes["ref_fonte"] == "51690"
    assert sinistrada.category_hint == "motos"
    assert sinistrada.raw_attributes["comitente"] == "Companhia Piratininga de Força e Luz"
    assert "marca" not in sinistrada.raw_attributes  # template com valores vazios

    picape = by_id["5042618"]
    assert picape.price == Decimal("53000.00") and picape.price_kind == "lance_atual"
    assert picape.raw_attributes["n_lances"] == 9
    assert (picape.raw_attributes["ano_fabricacao"], picape.raw_attributes["ano_modelo"]) == (2021, 2022)
    assert picape.category_hint == "carros" and (picape.city, picape.state) == ("Goiânia", "GO")

    particular = by_id["5059645"]
    assert particular.auction.committer_name is None and "comitente" not in particular.raw_attributes
    assert particular.raw_attributes["origem"] == "particular"
    assert json.loads(particular.raw_payload)["seller"] == {"pessoa_fisica": True}
    assert "PESSOA FISICA EXEMPLO" not in particular.description and "PESSOA FISICA EXEMPLO" not in particular.raw_payload
    assert particular.auction.auction_type == "extrajudicial"
    assert particular.raw_attributes["marca"] == "Ford" and particular.raw_attributes["modelo"] == "F250"

    carreta = by_id["5052311"]
    assert carreta.category_hint == "outros-veiculos"  # "Reboque"
    assert carreta.auction.auction_type == "judicial"
    assert [x.kind for x in carreta.auction.sessions] == ["1a_praca", "2a_praca"]
    assert carreta.auction.sessions[1].min_bid == Decimal("20000.00") and carreta.price_second == Decimal("20000.00")
    assert carreta.price == Decimal("40000.00")
    assert carreta.raw_attributes["vara"] == "3ª Vara Federal de Maringá"  # nome do leilao
    assert carreta.auction.auctioneer_name == "Luciano Marangoni" and carreta.auction.auctioneer_registration == "19/308-L"
    assert "Renavam (omitido)" in carreta.description and "0053.746.504-9" not in carreta.description
    assert "Placa FINAL 9/SP" in carreta.description

    basculante = by_id["5026511"]
    assert basculante.category_hint == "caminhoes"
    assert basculante.price == Decimal("53916.67") and basculante.price_kind == "lance_atual"
    assert basculante.raw_attributes["lance_inicial"] == "33916.67" and basculante.raw_attributes["n_lances"] == 20
    assert basculante.raw_attributes["marca"] == "Ford" and basculante.raw_attributes["ano_fabricacao"] == 2005
    assert "grade" not in basculante.raw_attributes  # checklist de avarias fica de fora
    assert basculante.auction.external_id == "801772" and basculante.auction.title == "Município de Rio Azul/PR"

    onibus = by_id["5026516"]
    assert onibus.category_hint == "onibus" and onibus.raw_attributes["n_lances"] == 91
    assert onibus.price == Decimal("60250.00")

    van = by_id["5029779"]
    assert van.category_hint == "utilitarios"
    assert van.title == "I/Ford Transit Jaedi Tur - 2012/2012 - Placa FINAL: 2D16"
    assert "placa" not in van.raw_attributes

    sucata = by_id["5033689"]
    assert sucata.category_hint == "outros-veiculos" and sucata.raw_attributes["sucata"] is True
    assert sucata.title == "SUCATA DE CAMINHÃO MERCEDES-BENZ 2423 K, 2006/2006, Placa FINAL 3 (SP)"
    assert sucata.raw_attributes["ref_fonte"] == "1239"
    assert sucata.raw_attributes["restricoes"] == "ADMINISTRATIVA" and sucata.raw_attributes["debitos_veiculo"] == "174.08"
    assert sucata.raw_attributes["categoria_fonte"] == "Caminhões / Sucata de Caminhões"
    assert "Lote de sucata." in sucata.description

    maquina = by_id["4380387"]
    assert maquina.title == "Komatsu PC130 2014" and maquina.category_hint == "maquinas-construcao"
    assert maquina.price == Decimal("262500.00") and maquina.price_kind == "lance_inicial"  # tomada de preco
    raw = maquina.raw_attributes
    assert raw["modalidade"] == "Tomada de preço" and raw["oferta_tipo_id"] == 9
    assert (raw["horimetro"], raw["potencia_cv"], raw["ano_fabricacao"]) == (11654, 97, 2014)
    assert raw["combustivel"] == "diesel" and raw["tipo_equipamento"] == "Máquinas Pesadas"
    assert raw["condicao_fonte"] == "operacional"
    assert raw["comitente"] == "Arremaq Arremaq"  # revendedor que vende na propria loja
    assert maquina.status_hint == "open"
    assert [x.kind for x in maquina.auction.sessions] == ["unica"]
    assert maquina.auction.sessions[0].ends_at.strftime("%Y-%m-%d %H:%M") == "2026-10-19 10:00"
    assert (maquina.city, maquina.state) == ("Mathias Lobato", "MG")

    gov = by_id["5026512"]
    assert gov.category_hint == "maquinas-construcao" and gov.price == Decimal("52400.00")
    assert gov.raw_attributes["matricula_leiloeiro"] == "20/322-L"


def test_dados_pessoais_nao_passam(superbid):
    """RN-009 com valores inventados: dono do veiculo, partes, advogado, juiz,
    endereco, telefone e login do licitante nao chegam a lugar nenhum."""
    s, offers, _ = superbid
    o = json.loads(json.dumps(offers[0]))
    o["product"]["productCustomJson"] = json.dumps({"vehicleOwner": "Fulano Proprietario", "vehicleRestrictions": "NENHUMA", "vehicleDebts": 12.5})
    o["product"]["judicial"] = {
        "processNumber": "0001234-56.2024.8.26.0100", "vara": "1ª Vara Cível", "judge": "Juiz Beltrano",
        "lawyer": "Dr. Sicrano Advogado", "defendant": "Fulano Executado", "author": "Beltrana Autora",
        "depositary": "Fulano Depositario", "local": "Rua das Flores, 10 - Centro",
    }
    o["product"]["detailedDescription"] = (
        "<p>Veiculo em bom estado.</p><p>Executado: Fulano Executado.</p><p>Depositário: Fulano Depositario; "
        "chassi 9BWZZZ377VT004251, placa ABC1D23, Renavam 00123456789.</p>"
    )
    o["seller"] = {"id": 1, "name": "Fulano Vendedor", "phone": [{"ddd": "11", "number": "999999999"}], "company": [{}]}
    o["winnerBid"] = {"currentWinner": 1, "currentWinnerLogin": "F*****no"}
    item = s.parse_offers([o])[0]
    tudo = item.description + item.raw_payload + json.dumps(item.raw_attributes, ensure_ascii=False)
    for proibido in ("Fulano Proprietario", "Beltrano", "Sicrano", "Fulano Executado", "Beltrana", "Depositario",
                     "Rua das Flores", "999999999", "F*****no", "Fulano Vendedor", "9BWZZZ377VT004251", "ABC1D23", "00123456789"):
        assert proibido not in tudo, proibido
    assert item.raw_attributes["processo"] == "0001234-56.2024.8.26.0100" and item.raw_attributes["vara"] == "1ª Vara Cível"
    assert item.raw_attributes["restricoes"] == "NENHUMA" and item.raw_attributes["debitos_veiculo"] == "12.50"
    assert item.raw_attributes["origem"] == "judicial"  # `product.judicial` basta
    assert "Veiculo em bom estado" in item.description and "chassi (omitido)" in item.description
    assert "placa *******" in item.description and "Renavam (omitido)" in item.description
    assert json.loads(item.raw_payload)["seller"] == {"pessoa_fisica": True}


def test_mascara_e_comitente():
    s = _scraper()
    m = s.mask_identifiers
    assert m("FIAT UNO 1000 e GOL 1000, placa ABC-1234") == "FIAT UNO 1000 e GOL 1000, placa ***-****"
    assert m("Placa: ABC 1234 e NXR160") == "Placa: *** **** e NXR160"
    assert m("placa ABC1D23 e modelo HB20 1.0") == "placa ******* e modelo HB20 1.0"
    assert m("CARGO 2422T FLEX 2009 ESDD 2020 PC130 2014") == "CARGO 2422T FLEX 2009 ESDD 2020 PC130 2014"
    assert m("Chassi: 9BWZZZ377VT004251. Renavam: 00123456789") == "Chassi (omitido). Renavam (omitido)"
    inst = s.institutional_name
    assert inst({"name": "ADEMIR BARBOSA", "company": [{}]}) is None
    assert inst({"name": "MARIA DA LUZ SILVA"}) is None
    assert inst({"name": "Neoenergia Brasília", "company": [{"fantasyName": "NEOENERGIA BRASILIA"}]}) == "Neoenergia Brasília"
    assert inst({"name": "5 Vara Federal de Maringá PR", "courtId": 59}) == "5 Vara Federal de Maringá PR"
    assert inst({"name": "Arremaq Arremaq", "company": [{}]}, {"name": "ARREMAQ"}) == "Arremaq Arremaq"
    assert inst({"name": "SAO LUIZ AGROINDUSTRIA SA"}) == "SAO LUIZ AGROINDUSTRIA SA"
    assert inst({"name": "Jose & Filhos"}) == "Jose & Filhos"
    assert inst("texto") is None and inst({"name": ""}) is None


def test_categoria_status_e_localizacao(superbid):
    s, offers, _ = superbid
    base = offers[0]

    def with_product(**kw):
        o = json.loads(json.dumps(base))
        o["product"].update(kw)
        return o

    def sub(cat, desc):
        return {"description": desc, "category": {"description": cat}}

    pecas = with_product(subCategory=sub("Partes e peças - Carros e motos", "Motores"))
    assert s.parse_offers([pecas]) == []  # peca nao e' bem inteiro
    assert _scraper(include_parts=True).parse_offers([pecas])[0].category_hint == "veiculos"
    assert s.parse_offers([with_product(subCategory=sub("Carros", "Utilitários & Furgões"))])[0].category_hint == "utilitarios"
    assert s.parse_offers([with_product(subCategory=sub("Motos", "Motos Sinistradas"))])[0].category_hint == "motos"
    assert s.parse_offers([with_product(subCategory=sub("Impl. Rod. e carrocerias", "Sucata de Carrocerias & Impl. Rodov."))])[0].raw_attributes["sucata"] is True
    assert s.parse_offers([with_product(subCategory=sub("Máquinas agrícolas", "Colheitadeiras"))])[0].category_hint == "maquinas-agricolas"
    assert s.parse_offers([with_product(subCategory=sub("Implementos agrícolas", "Pulverizadores"))])[0].category_hint == "maquinas-agricolas"
    assert s.parse_offers([with_product(subCategory=sub("Vans", "Vans de Carga"))])[0].category_hint == "utilitarios"
    # categoria desconhecida cai no tipo de produto
    assert s.parse_offers([with_product(subCategory=sub("Novidade", "X"), productType={"id": 15})])[0].category_hint == "maquinas-equipamentos"
    assert s.parse_offers([with_product(subCategory=None, productType={"id": 11})])[0].category_hint == "veiculos"

    # status pelos flags, depois pelo codigo
    def status(**flags):
        o = json.loads(json.dumps(base))
        o["offerStatus"] = {**{k: False for k in o["offerStatus"]}, **flags}
        o["statusId"] = flags.pop("statusId", o["statusId"]) if "statusId" in flags else o["statusId"]
        return s.status_hint(o)
    assert status(sold=True) == "sold" and status(removed=True) == "withdrawn"
    assert status(closedToBids=True) == "closed" and status(closed=True) == "closed"
    assert status(makeYourProposal=True) == "open"
    assert s.status_hint({"statusId": 6, "offerStatus": {}}) == "closed"
    assert s.status_hint({"statusId": 3}) == "closed" and s.status_hint({"statusId": "x"}) == "open"

    # localizacao: cidade com UF, so' cidade, UF por extenso
    assert s.location({"city": "Jaguapitã - PR", "state": "Paraná"}) == ("Jaguapitã", "PR", "Jaguapitã - PR")
    assert s.location({"city": "Uberlândia"}) == ("Uberlândia", None, "Uberlândia")
    assert s.location({"city": "Contagem", "state": "Minas Gerais"}) == ("Contagem", "MG", "Contagem")
    assert s.location({"city": "Não informado", "state": "x"}) == (None, None, "Não informado")
    assert s.location(None) == (None, None, None)

    # oferta sem id ou sem titulo nao entra; sem offerDetail usa `price`
    assert s.parse_offers([dict(base, id=None), with_product(shortDesc="")]) == []
    sem_detalhe = dict(base, offerDetail=None, totalBids=0, price=1234.5)
    item = s.parse_offers([sem_detalhe])[0]
    assert item.price == Decimal("1234.50") and item.price_kind == "lance_inicial"


def test_agenda_completa_a_oferta(superbid):
    """Oferta sem `eventPipeline`: a agenda (`fetch_events`) traz as pracas e
    o sub-marketplace pelo id do leilao."""
    s, offers, events = superbid
    o = json.loads(json.dumps(offers[0]))
    o["auction"]["id"] = 802215  # 2ª praca do evento 802214 (2ª Vara Civel de Cianorte)
    o["auction"]["subMarketplaces"] = []
    o["auction"]["eventPipeline"] = None
    item = s.parse_offers([o], events)[0]
    assert item.auction.auction_type == "judicial" and item.raw_attributes["sub_marketplace"] == "judicial"
    assert [x.kind for x in item.auction.sessions] == ["1a_praca", "2a_praca"]
    assert item.auction.sessions[0].min_bid == Decimal("95000.00") and item.auction.sessions[1].min_bid == Decimal("47500.00")
    assert item.price_second == Decimal("47500.00")
    # sem agenda continua extrajudicial e com sessao unica
    item = s.parse_offers([o])[0]
    assert item.auction.auction_type == "extrajudicial" and [x.kind for x in item.auction.sessions] == ["unica"]


@pytest.mark.asyncio
async def test_scrape_paginacao(fixture, monkeypatch):
    """Fluxo completo com o transporte simulado: categoria que para no limite
    de paginas marca a coleta como parcial, categoria menor que a pagina e'
    completa, categoria bloqueada conta erro, e a agenda so' e' lida quando
    `fetch_events` esta' ligado."""
    s = _scraper(
        categorias=["carros-motos", {"url": "caminhoes-onibus", "filter": "auction.subMarketplaces.subMarketplaceId:3"},
                    "maquinas-pesadas-agricolas"],
        page_size=5, max_pages=2, fetch_events=True, events_pages=1,
    )
    offers = json.loads(fixture("superbid_offers.json"))["offers"]
    calls: list[tuple[str, dict]] = []

    async def fake_fetch_json(url: str, params: dict | None = None, headers: dict | None = None):
        calls.append((url, dict(params or {})))
        assert headers["Origin"] == "https://www.superbid.net"
        if "event-query" in url:
            return json.loads(fixture("superbid_events.json"))
        url_seo = params["urlSeo"]
        if "maquinas" in url_seo:
            req = httpx.Request("GET", url)
            raise httpx.HTTPStatusError("403", request=req, response=httpx.Response(403, request=req))
        if "caminhoes" in url_seo:
            return {"total": 3, "start": 0, "limit": 5, "offers": offers[10:13]}
        start = (params["pageNumber"] - 1) * params["pageSize"]
        return {"total": 14, "start": start, "limit": 5, "offers": offers[start:start + params["pageSize"]]}

    async def no_delay() -> None:
        return None

    monkeypatch.setattr(s, "fetch_json", fake_fetch_json)
    monkeypatch.setattr(s, "delay", no_delay)
    items = await s.run()

    assert len(items) == 13  # 10 de carros (2 paginas de 5) + 3 de caminhoes
    assert (s.stats.pages, s.stats.errors, s.stats.complete) == (4, 1, False)
    assert any("carros-motos: parou em 2 paginas (10 de 14 ofertas)" in n for n in s.stats.notes)
    assert any("maquinas-pesadas-agricolas: pagina 1 falhou" in n for n in s.stats.notes)
    assert not any("caminhoes" in n for n in s.stats.notes)
    assert calls[0][0].startswith("https://event-query.superbid.net/events/v2/")
    assert calls[0][1]["filter"] == "modalityId:[1,4,5,7]" and calls[0][1]["pageSize"] == 50
    p = calls[1][1]
    assert calls[1][0] == "https://offer-query.superbid.net/seo/offers/"
    assert (p["urlSeo"], p["searchType"], p["orderBy"], p["pageNumber"], p["pageSize"], p["filter"]) == \
        ("https://www.superbid.net/categorias/carros-motos", "opened", "endDate:asc", 1, 5, "")
    assert p["portalId"] == "[2,15]" and p["timeZoneId"] == "America/Sao_Paulo"
    assert calls[2][1]["pageNumber"] == 2
    assert calls[3][1]["filter"] == "auction.subMarketplaces.subMarketplaceId:3"
    assert len(calls) == 5  # agenda + 2 + 1 + 1 (o 403 nao e' repetido)

    # Sem agenda nem erro, varredura que cabe nas paginas e' completa
    s2 = _scraper(categorias=["carros-motos"], page_size=5, max_pages=3)
    monkeypatch.setattr(s2, "fetch_json", fake_fetch_json)
    monkeypatch.setattr(s2, "delay", no_delay)
    calls.clear()
    items = await s2.run()
    assert len(items) == 14 and s2.stats.complete is True and s2.stats.pages == 3
    assert all("offer-query" in c[0] for c in calls)
