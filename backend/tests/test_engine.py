from datetime import datetime

from app.engine.category_fields import coerce_value, json_schema_for, validate_attributes
from app.engine.classifier import classify
from app.engine.dedup import similarity
from app.engine.deterministic import detect_brand, detect_km, detect_model, detect_years, extract_vehicle_fields
from app.engine.masking import mask_text
from app.models import Category, CategoryField, Item


# ── masking (RN-009) ───────────────────────────────────────────────

def test_mask_plate_chassi_renavam():
    txt = ("Um veículo marca VW, modelo Fox 1.6, ano 2005, placa HCM2183, cor preta, chassi 9BWKB05Z85P001329, "
           "renavam 00854415840. Contato (11) 98765-4321, CPF 123.456.789-00, joao@x.com")
    r = mask_text(txt)
    assert "HCM2183" not in r.text and "HCM-****" in r.text
    assert "9BWKB05Z85P001329" not in r.text and "1329" in r.text
    assert "00854415840" not in r.text
    assert "98765" not in r.text and "[telefone removido]" in r.text
    assert "[CPF removido]" in r.text
    assert "[e-mail removido]" in r.text
    assert r.plate_masked == "HCM-****"
    assert r.plate_hash and len(r.plate_hash) == 64
    assert "placa" in r.removed and "chassi" in r.removed


def test_mask_is_idempotent_and_keeps_source_masking():
    t = "RENAULT/SANDERO GTL 10MT, 19/20, PLACA: D__-___6, GASOL/ALC, BRANCA"
    r = mask_text(t)
    assert r.text == t
    assert r.plate_hash is None
    r2 = mask_text(mask_text("placa ABC1D23 ok").text)
    assert r2.text == "placa ABC-**** ok"


def test_mask_mercosul_plate_same_hash_with_or_without_dash():
    a = mask_text("placa ABC1D23").plate_hash
    b = mask_text("placa ABC-1D23").plate_hash
    assert a == b


# ── deterministico ─────────────────────────────────────────────────

def test_detect_brand_model_years_km():
    t = "RENAULT/SANDERO GTL 10MT, 19/20, PLACA: D__-___6, GASOL/ALC, BRANCA"
    assert detect_brand(t) == "Renault"
    assert detect_model(t, "Renault") == "Sandero Gtl"
    assert detect_years(t) == (2019, 2020)
    assert detect_brand("Carro Volkswagen Fox 1.6 - 2005") == "Volkswagen"
    assert detect_model("Carro Volkswagen Fox 1.6 - 2005", "Volkswagen") == "Fox"
    assert detect_years("Carro Volkswagen Fox 1.6 - 2005") == (None, 2005)
    assert detect_years("Caminhao Iveco Tector 170E25 2010/2011") == (2010, 2011)
    assert detect_km("Veiculo com 49.653 km rodados") == 49653
    assert detect_km("KM: 120000") == 120000
    assert detect_brand("I/TOYOTA HILUX CD 4X4 SRV") == "Toyota"
    assert detect_brand("Mini Trailer Rontan (Lote 21)") == "Rontan"
    assert detect_model("Mini Trailer Rontan (Lote 21)", "Rontan") is None  # parenteses nao sao modelo
    assert detect_brand("Carro LR Freelander 2SD4S - 2011") == "Land Rover"


def test_extract_vehicle_fields_freitas_like():
    title = "RENAULT/SANDERO GTL 10MT, 19/20, PLACA: D__-___6, GASOL/ALC, BRANCA"
    desc = "EMBREAGEM DANIFICADA / IPVA 2026 PAGO / CRLV DISPONÍVEL / AR COND."
    out = extract_vehicle_fields(title, desc, {"origem": "financeira", "opcionais": "Ar Condicionado, Direção Hidráulica"})
    assert out["marca"] == "Renault"
    assert out["ano_modelo"] == 2020 and out["ano_fabricacao"] == 2019
    assert out["combustivel"] == "flex"
    assert out["cor"] == "Branca"
    assert out["ipva_pago"] is True
    assert out["situacao_documento"] == "crlv_disponivel"
    assert out["origem"] == "financeira"
    assert "condicao" not in out  # nao inferido sem evidencia explicita


def test_extract_vehicle_fields_judicial_like():
    title = "Carro Volkswagen Fox 1.6 - 2005"
    desc = ("Um veículo marca VW, modelo Fox 1.6, ano 2005, placa HCM-****, cor preta, combustível álcool/gasolina. "
            "Consta débitos vinculados ao veículo no valor total R$ 396,20. Consta Bloqueio Judicial – Renajud.")
    out = extract_vehicle_fields(title, desc, {})
    assert out["marca"] == "Volkswagen" and out["modelo"] == "Fox"
    assert out["ano_modelo"] == 2005
    assert out["debitos"] == 396.2
    assert "Renajud" in out["restricoes"]
    assert out["cor"] == "Preta"


def test_extract_leilo_structured_raw_wins():
    out = extract_vehicle_fields("FORD/TRANSIT 350 FUGAO", "Laudo cautelar: reprovado. Avarias: TETO DANIFICADO",
                                 {"marca": "Ford", "modelo": "Transit 350 Fugao", "ano_modelo": 2025, "ano_fabricacao": 2024, "km": 49653, "origem": "frota", "laudo_cautelar": "reprovado"})
    assert out["km"] == 49653 and out["ano_modelo"] == 2025
    assert "condicao" not in out  # dano descrito nao e' classificacao de sinistro: fica para o LLM


# ── campos dinamicos (RN-002) ─────────────────────────────────────

def _fields():
    return [
        CategoryField(id=1, category_id=1, key="marca", label="Marca", field_type="string", required=True),
        CategoryField(id=2, category_id=1, key="ano_modelo", label="Ano", field_type="int"),
        CategoryField(id=3, category_id=1, key="km", label="KM", field_type="int", unit="km"),
        CategoryField(id=4, category_id=1, key="combustivel", label="Comb.", field_type="enum", options=["flex", "diesel", "nao_informado"]),
        CategoryField(id=5, category_id=1, key="ipva_pago", label="IPVA", field_type="bool"),
        CategoryField(id=6, category_id=1, key="debitos", label="Débitos", field_type="decimal"),
    ]


def test_coerce_and_validate():
    f = _fields()
    assert coerce_value(f[1], "2.019") == (2019, None)
    assert coerce_value(f[2], "49.653") == (49653, None)
    assert coerce_value(f[3], "FLEX") == ("flex", None)
    assert coerce_value(f[3], "gasolina")[0] is None
    assert coerce_value(f[4], "sim") == (True, None)
    assert coerce_value(f[5], "R$ 396,20") == (396.2, None)
    clean, errors = validate_attributes(f, {"marca": "Fiat", "ano_modelo": "2019", "combustivel": "gasolina", "extra": 1})
    assert clean["marca"] == "Fiat" and clean["ano_modelo"] == 2019
    assert clean["combustivel"] == "nao_informado"  # invalido -> nao informado, nunca inferido
    assert "extra" not in clean
    assert clean["km"] is None
    assert any("fora das opcoes" in e for e in errors)
    clean2, errors2 = validate_attributes(f, {"ano_modelo": 2019})
    assert any(e.startswith("campo obrigatorio") for e in errors2)


def test_json_schema():
    schema = json_schema_for(_fields())
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"marca", "ano_modelo", "km", "combustivel", "ipva_pago", "debitos"}
    assert None in schema["properties"]["combustivel"]["enum"]


# ── classificador ──────────────────────────────────────────────────

def _cats():
    v = Category(id=1, slug="veiculos", name="Veículos", path="veiculos", is_active=True, keywords=[], sort_order=0)
    return [
        v,
        Category(id=2, slug="carros", name="Carros", path="veiculos/carros", parent_id=1, is_active=True, keywords=["carro", "sedan", "hatch"], sort_order=1),
        Category(id=3, slug="motos", name="Motos", path="veiculos/motos", parent_id=1, is_active=True, keywords=["moto", "cg 160", "biz"], sort_order=2),
        Category(id=4, slug="caminhoes", name="Caminhões", path="veiculos/caminhoes", parent_id=1, is_active=True, keywords=["caminhao", "tector", "semirreboque"], sort_order=3),
        Category(id=9, slug="diversos", name="Diversos", path="diversos", is_active=True, keywords=[], sort_order=9),
    ]


def test_classify():
    cats = _cats()
    assert classify("Caminhão Iveco Tector 170E25 2010", None, cats).slug == "caminhoes"
    assert classify("HONDA/CG 160 FAN 2020", "veiculos", cats).slug == "motos"
    assert classify("Carro Volkswagen Fox 1.6 - 2005", "carros", cats).slug == "carros"
    assert classify("RENAULT/SANDERO GTL", "veiculos", cats).slug == "carros"  # fallback veiculo -> carros
    assert classify("FORD/TRANSIT 350", "pesados", cats).slug == "caminhoes"  # dica da fonte
    assert classify("Lote de cadeiras", None, cats).slug == "diversos"


# ── dedup (RN-004) ─────────────────────────────────────────────────

def test_similarity():
    now = datetime.utcnow()
    a = Item(id=1, source_id=1, external_id="a", title="Toyota Hilux CD SRV 2019", official_url="u", brand="Toyota", model="Hilux", year_model=2019, km=80000, state="SP", attributes={"cor": "Prata"}, first_seen_at=now, last_seen_at=now)
    b = Item(id=2, source_id=2, external_id="b", title="TOYOTA/HILUX CD SRV 4X4 2019", official_url="u", brand="Toyota", model="Hilux", year_model=2019, km=82000, state="SP", attributes={"cor": "prata"}, first_seen_at=now, last_seen_at=now)
    c = Item(id=3, source_id=2, external_id="c", title="Fiat Uno 2010", official_url="u", brand="Fiat", model="Uno", year_model=2010, km=None, state="RJ", attributes={}, first_seen_at=now, last_seen_at=now)
    sim_ab, reasons = similarity(a, b)
    assert sim_ab >= 0.85 and reasons["ano"] == 1.0 and reasons["km"] == 1.0
    sim_ac, _ = similarity(a, c)
    assert sim_ac < 0.3
    a.plate_hash = b.plate_hash = "x" * 64
    assert similarity(a, b) == (1.0, {"placa": 1.0})
