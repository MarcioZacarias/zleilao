"""Extracao do `__INITIAL_STATE__` do Leilo.

Em 14/10/2026 o site passou a embutir valores `undefined` (JavaScript, nao
JSON) e a fonte ficou tres dias suspensa por erro de parser. O teste fixa o
caso para o proximo que aparecer nao passar despercebido.
"""
from app.scrapers.leilo import parse_initial_state


def test_undefined_e_new_date_viram_json():
    html = ('<script>window.__INITIAL_STATE__={"hotsite":{"elasticIndex":undefined,"nome":"Leilo",'
            '"updatedAt":new Date("2026-09-09T22:47:30.000Z"),"createdAt":new Date(),"nota":NaN},'
            '"lista":[undefined,1,-Infinity]};document.currentScript.remove()</script>')
    estado = parse_initial_state(html)
    assert estado["hotsite"]["elasticIndex"] is None
    assert estado["hotsite"]["nome"] == "Leilo"
    assert estado["hotsite"]["updatedAt"] == "2026-09-09T22:47:30.000Z"
    assert estado["hotsite"]["createdAt"] is None
    assert estado["hotsite"]["nota"] is None
    assert estado["lista"] == [None, 1, None]


def test_json_normal_continua_igual():
    html = 'x;window.__INITIAL_STATE__ = {"a": {"b": "}{"}, "c": [1, 2]};'
    assert parse_initial_state(html) == {"a": {"b": "}{"}, "c": [1, 2]}
