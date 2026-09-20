"""Comparador leilão × mercado (RN-010).

Cada teste aqui corresponde a uma forma de o score enganar o usuário.
"""
from decimal import Decimal

from app.engine.fipe import model_similarity, norm, parse_brl, vehicle_type_for
from app.engine.opportunity import compute, total_cost


# ── casamento com a tabela FIPE ────────────────────────────────────

def test_model_similarity_aceita_versao_mais_longa():
    """O lote diz "Uno"; a FIPE diz "Uno Mille Way Economy 1.0". É o mesmo bem."""
    assert model_similarity("Uno", "Uno Mille Way Economy 1.0 Flex 8V") >= 0.66
    assert model_similarity("Corolla", "Corolla XEi 2.0 Flex 16V Aut.") >= 0.66
    assert model_similarity("Sandero Gtl", "Sandero GT Line 1.0 Flex") >= 0.66


def test_model_similarity_recusa_modelo_parecido_mas_diferente():
    """Gol e Golf são carros diferentes. Casar os dois daria referência errada
    e, pior, um desconto convincente."""
    assert model_similarity("Gol", "Golf 1.4 TSI") == 0.0
    assert model_similarity("Uno", "Punto 1.4 Attractive") == 0.0
    assert model_similarity("Ka", "Ranger 3.2 XLS") == 0.0
    assert model_similarity("Palio", "Pulse Drive 1.3") == 0.0


def test_model_similarity_vazio():
    assert model_similarity("", "Uno") == 0.0
    assert model_similarity("Uno", "") == 0.0


def test_norm_e_parse_brl():
    assert norm("Citroën C3 GLX") == "citroen c3 glx"
    assert parse_brl("R$ 25.932,00") == Decimal("25932.00")
    assert parse_brl("R$ 1.234.567,89") == Decimal("1234567.89")
    assert parse_brl(None) is None


def test_vehicle_type_for():
    assert vehicle_type_for("veiculos/carros") == "carros"
    assert vehicle_type_for("veiculos/motos") == "motos"
    assert vehicle_type_for("veiculos/caminhoes") == "caminhoes"
    assert vehicle_type_for("veiculos/utilitarios") == "carros"
    assert vehicle_type_for("imoveis") is None
    assert vehicle_type_for(None) is None


# ── custo total, não o lance ───────────────────────────────────────

def test_total_cost_soma_comissao_e_despesas():
    """O arrematante paga lance + comissão + despesas. Comparar o lance cru
    com a FIPE infla o desconto."""
    cost, detail = total_cost(30000, {"comissao_pct": "5", "total_despesas": "2350"})
    assert cost == Decimal("33850.00")
    assert detail["comissao"] == 1500.0
    assert detail["despesas"] == 2350.0


def test_total_cost_usa_comissao_padrao_quando_a_fonte_nao_informa():
    cost, detail = total_cost(30000, {})
    assert cost == Decimal("31500.00")     # 5% padrão
    assert detail["comissao_pct"] == 5.0


def test_total_cost_ignora_valores_implausiveis():
    """Fonte com despesa maior que o próprio lance é erro de parser, não dado."""
    cost, _ = total_cost(30000, {"total_despesas": "999999"})
    assert cost == Decimal("31500.00")
    cost, detail = total_cost(30000, {"comissao_pct": "90"})
    assert detail["comissao_pct"] == 5.0


def test_total_cost_sem_preco():
    assert total_cost(None, {})[0] is None
    assert total_cost(0, {})[0] is None


# ── score ──────────────────────────────────────────────────────────

def test_sem_condicao_conhecida_nao_ha_score():
    """A correção central: um sinistrado a 60% da FIPE não é oportunidade, é o
    preço dele. Sem saber a condição, o comparador recomendaria justamente os
    piores lotes, que são os de maior 'desconto'."""
    assert compute(price=30000, reference_value=60000, condition=None) is None
    assert compute(price=30000, reference_value=60000, condition="nao_informado") is None
    assert compute(price=30000, reference_value=60000, condition="qualquer_coisa") is None


def test_score_de_lote_integro():
    r = compute(price=30000, reference_value=50000, condition="normal", raw_attributes={})
    assert r is not None
    # custo 31.500 contra 50.000 -> 37% de desconto
    assert 36 <= r["discount_pct"] <= 38
    assert 90 <= r["score"] <= 95
    assert r["reasons"]["fator_condicao"] == 1.0


def test_sinistrado_tem_referencia_ajustada():
    """Mesmo lance e mesma FIPE: o sinistrado não pode aparecer como
    oportunidade melhor que o íntegro."""
    integro = compute(price=30000, reference_value=60000, condition="normal")
    sinistro = compute(price=30000, reference_value=60000, condition="sinistro_recuperavel")
    assert integro["discount_pct"] > sinistro["discount_pct"]
    assert sinistro["reasons"]["referencia_ajustada"] == 37200.0   # 62% de 60.000
    assert "Referência ajustada" in sinistro["reasons"]["nota"]


def test_sucata_cara_recebe_alerta_e_score_zero():
    r = compute(price=30000, reference_value=60000, condition="sucata")
    assert r["score"] == 0
    assert r["discount_pct"] < 0
    assert "acima da referência" in r["reasons"]["alerta"]


def test_score_satura_em_desconto_muito_alto():
    """Desconto altíssimo costuma ser sinal de problema no bem, não de
    oportunidade melhor: o score satura em 100."""
    a = compute(price=10000, reference_value=100000, condition="normal")
    b = compute(price=1000, reference_value=100000, condition="normal")
    assert a["score"] == 100 and b["score"] == 100


def test_sem_referencia_nao_ha_score():
    assert compute(price=30000, reference_value=None, condition="normal") is None
    assert compute(price=30000, reference_value=0, condition="normal") is None
    assert compute(price=None, reference_value=50000, condition="normal") is None


def test_model_similarity_casos_reais_das_fontes():
    """Casos extraídos dos lotes já coletados: o que precisa casar e o que
    não pode casar de jeito nenhum."""
    from app.engine.fipe import MIN_MODEL_RATIO as T

    deve_casar = [
        ("Onix Plus", "Onix Plus 1.0 Turbo LT"),
        ("Gol", "Gol 1.0 Flex"),
        ("Hilux", "Hilux CD 4x4 SRV 2.8"),
        ("Fox", "Fox 1.6 Highline"),
        ("Civic Lxs", "Civic LXS 1.8 Aut"),
        ("Mobi Like", "Mobi Like 1.0 Fire Flex"),
    ]
    nao_pode = [
        ("Gol", "Golf 1.4 TSI"),
        ("Palio", "Pulse Drive 1.3"),
        ("Ka", "Ranger 3.2 XLS"),
        ("Uno", "Punto 1.4 Attractive"),
        ("Fox", "Fusca 1300"),
    ]
    for m, f in deve_casar:
        assert model_similarity(m, f) >= T, f"deveria casar: {m} x {f}"
    for m, f in nao_pode:
        assert model_similarity(m, f) < T, f"nao deveria casar: {m} x {f}"


# ── condição presumida ─────────────────────────────────────────────

def test_presume_condition():
    """Em leilão de financeira, frota e locadora, o silêncio sobre avaria é
    informativo: esses leilões destacam sinistro quando há. Em seguradora e
    judicial, não é."""
    from app.engine.opportunity import presume_condition

    assert presume_condition("financeira", False) == "normal"
    assert presume_condition("frota", False) == "normal"
    assert presume_condition("locadora", False) == "normal"
    # menção a avaria derruba a premissa
    assert presume_condition("financeira", True) is None
    # onde sinistro é a regra, não se presume nada
    assert presume_condition("seguradora", False) is None
    assert presume_condition("judicial", False) is None
    assert presume_condition(None, False) is None


def test_score_presumido_e_penalizado_e_declarado():
    """Quem lê o score precisa saber que a condição foi presumida."""
    certo = compute(price=30000, reference_value=50000, condition="normal")
    presumido = compute(price=30000, reference_value=50000, condition="nao_informado",
                        presumed_condition="normal")
    assert presumido is not None
    assert presumido["score"] < certo["score"]          # penalizado pela incerteza
    assert presumido["discount_pct"] == certo["discount_pct"]   # o desconto é o mesmo
    assert presumido["reasons"]["condicao_presumida"] is True
    assert "não informou" in presumido["reasons"]["nota_condicao"]
    assert certo["reasons"]["condicao_presumida"] is False


def test_sem_premissa_continua_sem_score():
    assert compute(price=30000, reference_value=50000, condition="nao_informado",
                   presumed_condition=None) is None


def test_score_declara_que_o_lance_inicial_e_o_piso():
    """O lance inicial não é o preço de arremate: o lote será disputado.
    Sem essa ressalva o usuário lê o desconto como garantido."""
    r = compute(price=21500, reference_value=44281, condition="normal", price_kind="lance_inicial")
    assert r["reasons"]["base_calculo"] == "lance_inicial"
    assert "piso do pregão" in r["reasons"]["nota_preco"]
    # lance atual já reflete disputa: a ressalva não se aplica
    r2 = compute(price=21500, reference_value=44281, condition="normal", price_kind="lance_atual")
    assert r2["reasons"]["base_calculo"] == "lance_atual"
    assert "nota_preco" not in r2["reasons"]
