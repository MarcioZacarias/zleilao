"""Regras de alerta (RN-006/RN-007) que dão para testar sem banco."""
from datetime import datetime, time

import pytest

from app.engine.search import CRITERIA_KEYS, describe_criteria, normalize_criteria
from app.notify.dispatcher import in_quiet_window, parse_hhmm
from app.notify.email import is_valid_email
from app.notify.templates import brl, whatsapp_message
from app.notify.whatsapp import normalize_phone


# ── critério do filtro salvo ───────────────────────────────────────

def test_normalize_criteria():
    raw = {"brand": " Fiat ", "year_min": "2015", "price_max": "50000.5", "q": "",
           "state": "sp", "lixo": "x", "year_max": "nao-numero"}
    out = normalize_criteria(raw)
    assert out["brand"] == "Fiat"
    assert out["year_min"] == 2015
    assert out["price_max"] == 50000.5
    assert out["state"] == "sp"          # a query normaliza para maiúsculo
    assert "lixo" not in out             # chave desconhecida é descartada
    assert "q" not in out                # vazio não vira filtro
    assert "year_max" not in out         # valor inválido é descartado
    assert normalize_criteria(None) == {}
    assert set(out).issubset(set(CRITERIA_KEYS))


def test_describe_criteria():
    assert describe_criteria({}) == "todos os lotes"
    d = describe_criteria({"brand": "Fiat", "year_min": 2015})
    assert "marca: Fiat" in d and "ano de: 2015" in d


# ── janela de silêncio (RN-006) ────────────────────────────────────

def test_parse_hhmm():
    assert parse_hhmm("22:00") == time(22, 0)
    assert parse_hhmm("8:30") == time(8, 30)
    assert parse_hhmm("") is None
    assert parse_hhmm("banana") is None
    assert parse_hhmm(None) is None


def test_quiet_window_cruzando_meia_noite():
    """A janela normal (22:00–08:00) cruza a meia-noite: é o caso comum,
    não a exceção."""
    start, end = time(22, 0), time(8, 0)
    assert in_quiet_window(datetime(2026, 9, 20, 23, 30), start, end)
    assert in_quiet_window(datetime(2026, 9, 20, 3, 0), start, end)
    assert in_quiet_window(datetime(2026, 9, 20, 22, 0), start, end)   # início inclusivo
    assert not in_quiet_window(datetime(2026, 9, 20, 8, 0), start, end)  # fim exclusivo
    assert not in_quiet_window(datetime(2026, 9, 20, 12, 0), start, end)


def test_quiet_window_no_mesmo_dia():
    start, end = time(12, 0), time(14, 0)
    assert in_quiet_window(datetime(2026, 9, 20, 13, 0), start, end)
    assert not in_quiet_window(datetime(2026, 9, 20, 15, 0), start, end)


def test_quiet_window_desligada():
    assert not in_quiet_window(datetime(2026, 9, 20, 3, 0), None, None)
    assert not in_quiet_window(datetime(2026, 9, 20, 3, 0), time(8, 0), time(8, 0))


# ── contatos ───────────────────────────────────────────────────────

def test_normalize_phone():
    assert normalize_phone("(11) 98765-4321") == "5511987654321"
    assert normalize_phone("11987654321") == "5511987654321"
    assert normalize_phone("+55 11 98765-4321") == "5511987654321"
    assert normalize_phone("0055 11 3117-1000") == "551131171000"
    assert normalize_phone("123") is None
    assert normalize_phone(None) is None


def test_is_valid_email():
    assert is_valid_email("marcio@radconsult.com.br")
    assert not is_valid_email("sem-arroba")
    assert not is_valid_email("a@b")
    assert not is_valid_email(None)


# ── formatação das mensagens ───────────────────────────────────────

class _FakeItem:
    id = 7
    title = "VW/GOL 1.0"
    brand, model, year_model = "Volkswagen", "Gol", 2011
    price, price_second = 21900, None
    city, state = "Santo André", "SP"
    next_session_at = datetime(2026, 9, 25, 10, 0)
    last_seen_at = datetime(2026, 9, 20, 3, 0)
    image_url = None


def test_brl():
    assert brl(21900) == "R$ 21.900,00"
    assert brl(None) == "sob consulta"


def test_whatsapp_message_traz_fonte_e_link():
    """RN-001 vale fora do portal: fonte, data da coleta e link oficial."""
    msg = whatsapp_message(
        [{"item": _FakeItem(), "source_name": "Mega Leilões", "reason": "new", "detail": None}],
        "https://leilao.zconnect.ia.br",
    )
    assert "VW/GOL 1.0" in msg
    assert "R$ 21.900,00" in msg
    assert "Mega Leilões" in msg
    assert "20/09/2026" in msg              # última coleta
    assert "https://leilao.zconnect.ia.br/lote/7" in msg
    assert "agregador" in msg.lower()       # disclaimer


def test_whatsapp_message_agrupa():
    entries = [{"item": _FakeItem(), "source_name": "Mega", "reason": "new", "detail": None},
               {"item": _FakeItem(), "source_name": "Leilo", "reason": "price_drop", "detail": "lance caiu 20%"}]
    msg = whatsapp_message(entries, "https://x.com")
    assert "2 lotes" in msg
    assert "lance caiu 20%" in msg


# ── busca por raio (Onda 4) ────────────────────────────────────────

from app.engine.geo import bounding_box, coords_for, haversine_km, normalize_city, search_cities
from app.engine.search import radius_center


def test_coords_for_municipios_reais():
    assert coords_for("São Paulo", "SP") == (-23.5329, -46.6395)
    assert coords_for("santo andre", "SP") is not None     # sem acento
    assert coords_for("Guaratinguetá", "SP") is not None
    # cidade desconhecida fica sem coordenada: some da busca por raio em vez
    # de aparecer no lugar errado
    assert coords_for("Cidade Inexistente", "SP") is None
    assert coords_for("São Paulo", None) is None
    assert coords_for(None, "SP") is None


def test_normalize_city_tira_uf_colada():
    assert normalize_city("Santo André/SP") == "santo andre"
    assert normalize_city("SÃO PAULO") == "sao paulo"


def test_haversine_bate_com_a_realidade():
    sp, rj = coords_for("São Paulo", "SP"), coords_for("Rio de Janeiro", "RJ")
    assert 340 <= haversine_km(*sp, *rj) <= 380      # ~360 km
    sa = coords_for("Santo André", "SP")
    assert haversine_km(*sp, *sa) < 25               # ~18 km


def test_bounding_box_contem_o_circulo():
    lat, lng = coords_for("São Paulo", "SP")
    lat_min, lat_max, lng_min, lng_max = bounding_box(lat, lng, 100)
    assert lat_min < lat < lat_max and lng_min < lng < lng_max
    # o ponto a 100 km ao norte precisa caber na caixa
    assert lat_max >= lat + (100 / 111.045) - 0.01


def test_radius_center_valida_a_entrada():
    assert radius_center({"near_city": "São Paulo", "near_state": "SP", "radius_km": 50}) is not None
    assert radius_center({"near_city": "São Paulo", "near_state": "SP"}) is None      # sem raio
    assert radius_center({"radius_km": 50}) is None                                   # sem cidade
    assert radius_center({"near_city": "X", "near_state": "SP", "radius_km": 50}) is None  # cidade desconhecida
    assert radius_center({"near_city": "São Paulo", "near_state": "SP", "radius_km": -5}) is None
    assert radius_center({"near_city": "São Paulo", "near_state": "SP", "radius_km": 99999}) is None


def test_search_cities_autocomplete():
    r = search_cities("campin", 5)
    assert any(c["city"].lower().startswith("campinas") for c in r)
    assert all("lat" in c and "state" in c for c in r)
    assert search_cities("x", 5) == []    # termo curto demais


def test_normalize_city_nao_corta_nome_composto():
    """A UF só sai quando é sigla real: senão "Campo Grande" viraria "Campo"."""
    assert normalize_city("Campo Grande") == "campo grande"
    assert normalize_city("Rio Verde") == "rio verde"
    assert normalize_city("Bauru, SP") == "bauru"
    assert normalize_city("Guaratinguetá (SP)") == "guaratingueta"
    assert coords_for("Campo Grande", "MS") is not None
    assert coords_for("Rio Verde", "GO") is not None


def test_search_cities_ordena_por_populacao():
    """Quem digita "camp" quer Campinas, não Campanha: o peso é a população."""
    nomes = [c["city"] for c in search_cities("camp", 5)]
    assert nomes[0] == "Campinas"
    assert "Campo Grande" in nomes
    # nome de exibição vem acentuado, não do índice normalizado
    assert search_cities("sao p", 1)[0]["city"] == "São Paulo"
    assert search_cities("ribeirao p", 1)[0]["city"] == "Ribeirão Preto"


def test_search_cities_nao_repete_apelido_sem_apostrofo():
    """A base indexa "santa barbara doeste" como apelido de "d'oeste";
    o apelido serve para casar o que as fontes escrevem, não para virar
    uma segunda opção na lista."""
    r = search_cities("santa b", 8)
    assert len([c for c in r if c["city"] == "Santa Bárbara d'Oeste"]) == 1
    # o apelido continua resolvendo coordenada
    assert coords_for("Sta Barbara Doeste", "SP") is not None


def test_wants_radius():
    from app.engine.search import wants_radius
    assert wants_radius({"near_city": "Campinas", "radius_km": 100})
    assert not wants_radius({"near_city": "Campinas"})
    assert not wants_radius({"radius_km": 100})
    assert not wants_radius({})
