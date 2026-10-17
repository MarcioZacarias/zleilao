"""Regras de evidencia da deduplicacao (RN-004 / F4).

O que importa aqui nao e' a pontuacao exata, e' a fronteira: so' placa igual
ou URL oficial igual chegam a 1.0, e carros de frota — iguais em tudo que a
fonte mostra — ficam abaixo disso.
"""
from types import SimpleNamespace

from app.engine.dedup import SIMILARITY_CAP, STRONG, is_strong, similarity


def lote(**kw):
    base = dict(plate_hash=None, official_url=None, title=None, year_model=None, km=None, state=None, attributes={})
    base.update(kw)
    return SimpleNamespace(**base)


FROTA = dict(title="CHEVROLET ONIX 1.0 LT 2022", year_model=2022, state="SP", attributes={"cor": "Branca"})


def test_placa_igual_e_evidencia_forte():
    sim, reasons = similarity(lote(plate_hash="abc", **FROTA), lote(plate_hash="abc", title="Onix LT"))
    assert sim == STRONG and is_strong(reasons)


def test_placas_diferentes_nunca_vinculam():
    sim, reasons = similarity(lote(plate_hash="abc", km=30000, **FROTA), lote(plate_hash="xyz", km=30500, **FROTA))
    assert sim == 0.0 and not is_strong(reasons)


def test_mesma_url_oficial_ignora_www_barra_e_rastreio():
    a = lote(official_url="https://www.leiloeiro.com.br/lote/123/")
    b = lote(official_url="https://leiloeiro.com.br/lote/123?utm=portal")
    sim, reasons = similarity(a, b)
    assert sim == STRONG and reasons["url"] == 1.0


def test_frota_igual_em_tudo_nao_chega_a_fundir():
    sim, reasons = similarity(lote(km=30000, **FROTA), lote(km=30500, **FROTA))
    assert sim <= SIMILARITY_CAP < STRONG
    assert not is_strong(reasons)
    # ...mas e' suspeito o bastante para o admin olhar.
    assert sim >= 0.85
