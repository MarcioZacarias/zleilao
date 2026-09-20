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
