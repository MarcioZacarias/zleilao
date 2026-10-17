"""Palácio dos Leilões — fixtures capturadas em 17/10/2026: recorte de 13 cards
do POST `listar_lote` (categoria 1, modo lista, "Exibir todos") cobrindo os
quatro patios, os quatro textos de condicao, "Sequencia N" / "Lote N" / vazio,
comitente vazio, titulo colado sem anos e preco "0,00"; e o fragmento
`exibir_lote_2` do lote 1578438 (Fiat Toro 0 km, Mapfre, 93 lances).
"""
from datetime import datetime
from decimal import Decimal

import httpx
import pytest

from app.scrapers.palacio import PalacioScraper


def _scraper(**config) -> PalacioScraper:
    return PalacioScraper(source_id=11, base_url=None, config=config)


def test_palacio_helpers():
    P = PalacioScraper
    assert P.parse_date_short("17/10/26") == datetime(2026, 10, 17)
    assert P.parse_date_short("Data 19/10/2026") == datetime(2026, 10, 19)
    assert P.parse_date_short("") is None and P.parse_date_short("31/02/26") is None

    title, attrs = P.split_title(" FIAT/TORO VOLC TD450 AT 2026 2026")
    assert title == "FIAT/TORO VOLC TD450 AT 2026/2026"
    assert attrs == {"ano_fabricacao": 2026, "ano_modelo": 2026, "marca": "Fiat", "modelo": "Toro Volc Td450 At"}
    # titulo colado sem anos fica como esta': separar marca de modelo seria chute
    assert P.split_title("GMMONTANA") == ("GMMONTANA", {})
    assert P.split_title("MERCEDES-BENZACTROS 2651") == ("MERCEDES-BENZACTROS 2651", {})
    # "I/" e' prefixo de importado, nao marca
    imp = P.split_title("I/JINCHENG AVELLOZ AZ125 2025 2025")[1]
    assert (imp["marca"], imp["modelo"], imp["importado"]) == ("Jincheng", "Avelloz Az125", True)
    assert P.split_title("REB/RANDON SR GR TR 1992 1992")[1]["marca"] == "Reb"

    assert P.origem_from_committer("BRADESCO SEGUROS") == "seguradora"
    assert P.origem_from_committer("BANCO BRADESCO") == "financeira"
    assert P.origem_from_committer("PAN") == "financeira"
    assert P.origem_from_committer("HONDA") == "financeira"
    assert P.origem_from_committer("LOCALIZA DIGITAL") == "locadora"
    assert P.origem_from_committer("UNIDAS ATACADO") == "locadora"
    assert P.origem_from_committer("VALE") == "frota"
    assert P.origem_from_committer("BEM PROTEGE") == "seguradora"
    assert P.origem_from_committer("PROAUTO") is None
    assert P.origem_from_committer("") is None

    assert P.condition_from_text("no estado que se encontra") is None
    assert P.condition_from_text("sinistrado (media monta)") == "sinistro_media_monta"
    assert P.condition_from_text("pequena monta") == "sinistro_recuperavel"
    assert P.condition_from_text("sucata (grande monta)") == "sucata"

    form = P.listing_form(1)
    assert (form["opcao"], form["categoria_pesquisa"], form["tipo_exibicao"], form["paginacao"]) == ("listar_lote", "1", "lista", "-1")


def test_palacio_listing(fixture):
    s = _scraper()
    html = fixture("palacio_listing.html")
    assert s.total_from_listing(html) == 13
    items = s.parse_listing(html, 1)
    assert len(items) == 13
    assert s.stats.errors == 0
    assert len({i.external_id for i in items}) == 13
    by_id = {i.external_id: i for i in items}

    toro = by_id["1578438"]
    assert toro.title == "FIAT/TORO VOLC TD450 AT 2026/2026"
    assert toro.official_url == "https://www.palaciodosleiloes.com.br/site/lotem.php?cl=1578438"
    assert toro.price == Decimal("137000.00") and toro.price_kind == "lance_atual"
    assert toro.image_url == "https://www.palaciodosleiloes.com.br/site/imagens_lote/500375/012_863b0e12096181ff624cf455ca8fe01f.webp"
    assert (toro.city, toro.state) == ("Juatuba", "MG")
    assert toro.location_text == "Pátio Juatuba — Juatuba/MG"
    assert toro.lot_number is None  # o card so' traz a sequencia; o numero vem do detalhe
    assert toro.raw_attributes["sequencia"] == 7
    assert toro.raw_attributes["comitente"] == "MAPFRE"
    assert toro.raw_attributes["origem"] == "seguradora"
    assert toro.raw_attributes["cod_leilao"] == "8827"
    assert "condicao" not in toro.raw_attributes  # "no estado que se encontra" nao e' condicao
    assert toro.raw_attributes["condicao_fonte"] == "no estado que se encontra"
    assert (toro.raw_attributes["marca"], toro.raw_attributes["modelo"]) == ("Fiat", "Toro Volc Td450 At")
    assert (toro.raw_attributes["ano_fabricacao"], toro.raw_attributes["ano_modelo"]) == (2026, 2026)
    assert toro.category_hint == "veiculos" and toro.status_hint == "open"
    assert toro.auction.external_id == "8827"
    assert toro.auction.auction_type == "extrajudicial"
    assert toro.auction.committer_name == "MAPFRE"
    assert toro.auction.auctioneer_name == "Palácio dos Leilões"
    assert toro.auction.official_url == "https://www.palaciodosleiloes.com.br/site/leilao.php?cl=8827"
    assert [x.kind for x in toro.auction.sessions] == ["unica"]
    assert toro.auction.sessions[0].starts_at == datetime(2026, 10, 17)  # "17/10/26" na fonte
    assert "exibir_lote(1578438,8827)" in toro.raw_payload

    # patio Salvador, icone do YouTube dentro do titulo, pequena monta
    byd = by_id["1577901"]
    assert byd.title == "BYD/SONG PRO GL DM 2026/2027"
    assert (byd.city, byd.state) == ("Salvador", "BA")
    assert byd.raw_attributes["condicao"] == "sinistro_recuperavel"
    assert byd.raw_attributes["origem"] == "seguradora"  # SOMPO
    assert byd.raw_attributes["sequencia"] == 109

    cb = by_id["1579853"]
    assert (cb.city, cb.state) == ("Cajamar", "SP")
    assert cb.raw_attributes["origem"] == "financeira"  # HONDA = Banco Honda

    # bem externo: sem cidade, "Lote 340" vira numero do lote
    reb = by_id["1580827"]
    assert (reb.city, reb.state) == (None, None)
    assert reb.location_text == "Externo"
    assert reb.lot_number == "340" and "sequencia" not in reb.raw_attributes
    assert reb.raw_attributes["origem"] == "locadora"
    assert reb.raw_attributes["marca"] == "Reb"
    assert reb.auction.sessions[0].starts_at == datetime(2026, 10, 21)

    # comitente vazio, sem sequencia, titulo colado
    volvo = by_id["1581608"]
    assert volvo.title == "VOLVOFM 370"
    assert "comitente" not in volvo.raw_attributes and "marca" not in volvo.raw_attributes
    assert volvo.auction.committer_name is None
    assert volvo.lot_number is None
    assert volvo.price == Decimal("162000.00") and volvo.price_kind == "lance_inicial"

    assert by_id["1578395"].raw_attributes["condicao"] == "sinistro_media_monta"

    # sucata e' veiculo baixado
    shi = by_id["1581622"]
    assert shi.raw_attributes["condicao"] == "sucata" and shi.category_hint == "sucatas"
    assert shi.auction.external_id == "8852" and shi.auction.sessions[0].starts_at == datetime(2026, 10, 20)

    # "0,00 lance inicial" e' lance livre: zero nao vira preco
    corolla = by_id["1581100"]
    assert corolla.price is None and corolla.price_kind == "lance_inicial"
    assert corolla.raw_attributes["sem_lance_minimo"] is True
    assert corolla.lot_number == "800"
    assert corolla.raw_attributes["origem"] == "seguradora"  # BEM PROTEGE

    assert by_id["1576790"].raw_attributes["origem"] == "frota"  # VALE
    assert by_id["1576790"].title == "KARCHERKMR 1700 D"
    up = by_id["1581448"]
    assert "origem" not in up.raw_attributes  # PROAUTO e' revenda: sem enum, sem chute
    assert up.auction.sessions[0].starts_at == datetime(2026, 10, 22)
    mobi = by_id["1581716"]
    assert (mobi.city, mobi.state, mobi.lot_number) == ("Cajamar", "SP", "320")

    # nada de placa/chassi nos campos estruturados (RN-009)
    for it in items:
        assert not any("placa" in k or "chassi" in k for k in it.raw_attributes)


def test_palacio_listing_patio_configuravel(fixture):
    s = _scraper(patios={"Juatuba": ["Juatuba", "MG"], "Salvador": ["Simões Filho", "BA"]})
    items = s.parse_listing(fixture("palacio_listing.html"), 1)
    by_id = {i.external_id: i for i in items}
    assert (by_id["1577901"].city, by_id["1577901"].state) == ("Simões Filho", "BA")
    # patio fora do mapa fica sem cidade, com o rotulo preservado
    assert (by_id["1579853"].city, by_id["1579853"].state) == (None, None)
    assert by_id["1579853"].location_text == "Cajamar"


def test_palacio_detail(fixture):
    s = _scraper()
    items = s.parse_listing(fixture("palacio_listing.html"), 1)
    toro = next(i for i in items if i.external_id == "1578438")
    s.enrich_from_detail(toro, fixture("palacio_detail.html"))
    a = toro.raw_attributes

    assert toro.lot_number == "363"  # "LOTE 0363" na fonte
    assert a["sequencia"] == 7
    assert toro.description == "veículo 0km! ipva 2026 pago / colisão"
    assert a["observacoes"] == toro.description
    assert a["combustivel"] == "Diesel"
    assert a["origem"] == "seguradora"
    assert a["condicao_fonte"] == "no estado que se encontra" and "condicao" not in a
    assert a["km"] == 15
    assert (a["ano_fabricacao"], a["ano_modelo"]) == (2026, 2026)
    assert a["potencia_cv"] == 200 and a["cilindradas"] == 2184
    assert a["acessorios"] == "manual"
    assert a["valor_mercado_fonte"] == "172127.00"
    assert a["lances"] == 93 and a["visualizacoes"] == 644
    assert a["comissao_pct"] == "5"
    assert a["despesas_fixas"] == "3140.00"
    assert a["origem_fonte"] == "seguradora"
    assert a["visitacao"] == "2026-10-16"
    assert a["local_leilao"] == "Br-262, Km 375 Juatuba-MG"
    # "Local lote: -" e' marcador de ausencia; a cidade do patio fica
    assert (toro.city, toro.state) == ("Juatuba", "MG")
    assert toro.location_text == "Pátio Juatuba — Juatuba/MG"
    # "Final Placa" existe na fonte e fica de fora de proposito (RN-009)
    assert not any("placa" in k for k in a)
    assert toro.price == Decimal("137000.00") and toro.price_kind == "lance_atual"
    assert len(toro.images) == 12  # 13 fotos na fonte, teto de 12
    assert toro.images[0] == "https://www.palaciodosleiloes.com.br/site/imagens_lote/500375/012_863b0e12096181ff624cf455ca8fe01f.jpg"
    assert toro.image_url.endswith(".webp")  # a miniatura da listagem continua a capa
    assert "<!-- detail -->" in toro.raw_payload


def test_palacio_detail_corrige_titulo_colado(fixture):
    """Lote cuja listagem veio colada ("VOLVOFM 370"): o detalhe traz
    "marca/modelo" e repoe titulo, marca e modelo."""
    s = _scraper()
    items = s.parse_listing(fixture("palacio_listing.html"), 1)
    volvo = next(i for i in items if i.external_id == "1581608")
    html = (fixture("palacio_detail.html")
            .replace("fiat/toro volc td450 at", "volvo/fm 370 6x4")
            .replace("Origem<br />seguradora", "Origem<br />empresa"))
    s.enrich_from_detail(volvo, html)
    assert volvo.title == "VOLVO/FM 370 6X4 2026/2026"
    assert (volvo.raw_attributes["marca"], volvo.raw_attributes["modelo"]) == ("Volvo", "Fm 370 6X4")
    # "empresa" na ficha e' o bem da propria comitente: frota no nosso enum
    assert volvo.raw_attributes["origem"] == "frota" and volvo.raw_attributes["origem_fonte"] == "empresa"

    # palavra de origem fora do mapa nao vira enum
    outro = next(i for i in items if i.external_id == "1581448")
    s.enrich_from_detail(outro, fixture("palacio_detail.html").replace("Origem<br />seguradora", "Origem<br />particular"))
    assert "origem" not in outro.raw_attributes and outro.raw_attributes["origem_fonte"] == "particular"


@pytest.mark.asyncio
async def test_palacio_scrape_parcial(fixture, monkeypatch):
    """Fluxo completo com o transporte simulado: categoria que falha marca a
    coleta como parcial, total anunciado maior que o lido idem, e o limite de
    detalhes e' respeitado."""
    s = _scraper(categorias=[1, 15], fetch_details=True, max_details_per_run=1)
    listing = fixture("palacio_listing.html").replace("value='13'", "value='40'")
    calls: list[tuple[str, str, str]] = []

    async def fake_post(url: str, data: dict) -> str:
        calls.append((url.rsplit("/", 1)[-1], data["opcao"], data.get("categoria_pesquisa") or data.get("cod_lote")))
        if data["opcao"] == "listar_lote":
            if data["categoria_pesquisa"] == "15":
                raise httpx.ConnectError("sem rede")
            return listing
        return fixture("palacio_detail.html")

    async def no_delay() -> None:
        return None

    monkeypatch.setattr(s, "post_form", fake_post)
    monkeypatch.setattr(s, "delay", no_delay)
    items = await s.run()

    assert len(items) == 13
    assert (s.stats.pages, s.stats.errors, s.stats.details) == (1, 1, 1)
    assert s.stats.complete is False
    assert any("categoria 15 falhou" in n for n in s.stats.notes)
    assert any("categoria 1: 13 de 40 lotes lidos" in n for n in s.stats.notes)
    assert any("limite de 1 detalhes" in n for n in s.stats.notes)
    assert calls[0] == ("coluna_esquerda_m.php", "listar_lote", "1")
    assert calls[1] == ("coluna_esquerda_m.php", "listar_lote", "15")
    assert calls[2] == ("lote.php", "exibir_lote_2", "1578438")
    assert len(calls) == 3
    assert items[0].lot_number == "363"  # o unico detalhe buscado enriqueceu o primeiro item
