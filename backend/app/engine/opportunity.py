"""RN-010 — score de oportunidade do lote contra a referência de mercado.

Três correções deliberadas em relação ao texto da EF, todas pelo mesmo motivo:
um score alto que engana é pior que nenhum score.

1. **Custo total, não o lance.** O arrematante paga lance + comissão do
   leiloeiro (5% é o usual) + despesas do pátio. Um lote a R$ 30.000 com 5% de
   comissão e R$ 2.350 de despesas custa R$ 33.850. Comparar o lance cru com o
   preço de mercado infla o desconto em dez pontos ou mais.

2. **Condição desconhecida não gera score.** Um sinistrado a 60% da FIPE não é
   oportunidade, é o preço dele. A EF exigia só amostra mínima; sem olhar a
   condição, o comparador recomendaria justamente os piores lotes, que são os
   que têm o maior "desconto".

3. **Sinistro e sucata entram com referência ajustada**, não excluídos: o
   usuário que procura recuperável precisa comparar. O ajuste é explícito e
   aparece nas razões do score.
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any

logger = logging.getLogger("zleilao.opportunity")

#: Quanto o mercado paga por um bem nessa condição, como fração da referência.
#: Faixas conservadoras: na dúvida, o desconto aparece menor, nunca maior.
CONDITION_FACTOR = {
    "normal": 1.00,
    "sinistro_recuperavel": 0.62,
    "sinistro_media_monta": 0.45,
    "sinistro_grande_monta": 0.28,
    "sucata": 0.18,
}
#: Condições sem score: não dá para comparar sem saber o que se está comparando.
UNKNOWN_CONDITIONS = {None, "", "nao_informado"}

DEFAULT_COMMISSION_PCT = 5.0

#: Origens em que a ausência de menção a avaria é informativa. Leilão de
#: financeira, frota e locadora destaca sinistro quando há; o silêncio aponta
#: para bem íntegro. NÃO vale para seguradora (onde sinistro é a regra) nem
#: para judicial (onde a descrição raramente fala do estado do bem).
ORIGINS_PRESUMED_INTACT = {"financeira", "frota", "locadora"}
#: Desconto de confiança quando a condição foi presumida, não informada. O
#: score sai menor de propósito: a premissa pode estar errada.
PRESUMED_PENALTY = 0.85


def _dec(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def total_cost(price: Any, raw_attributes: dict | None, default_commission: float = DEFAULT_COMMISSION_PCT) -> tuple[Decimal | None, dict]:
    """Lance + comissão + despesas conhecidas. Devolve (custo, detalhamento)."""
    base = _dec(price)
    if base is None or base <= 0:
        return None, {}
    raw = raw_attributes or {}
    pct = _dec(raw.get("comissao_pct"))
    if pct is None or pct < 0 or pct > 30:
        pct = Decimal(str(default_commission))
    commission = (base * pct / Decimal(100)).quantize(Decimal("0.01"))
    fees = _dec(raw.get("total_despesas")) or Decimal(0)
    if fees < 0 or fees > base:   # valor implausível da fonte: ignora
        fees = Decimal(0)
    total = (base + commission + fees).quantize(Decimal("0.01"))
    return total, {
        "lance": float(base),
        "comissao_pct": float(pct),
        "comissao": float(commission),
        "despesas": float(fees),
        "custo_total": float(total),
    }


def presume_condition(origin: str | None, has_damage_words: bool) -> str | None:
    """Condição presumida quando a fonte não informou.

    A RN-002 proíbe **inferir o campo** — e `items.condition` continua
    "não informado" na ficha. Isto aqui é outra coisa: uma premissa explícita
    do comparador, que aparece nas razões do score e é penalizada. Sem ela o
    comparador fica inerte enquanto o LLM não estiver configurado, já que a
    maioria dos lotes não declara o estado do bem.
    """
    if has_damage_words:
        return None
    return "normal" if origin in ORIGINS_PRESUMED_INTACT else None


def compute(
    *,
    price: Any,
    reference_value: Any,
    condition: str | None,
    raw_attributes: dict | None = None,
    default_commission: float = DEFAULT_COMMISSION_PCT,
    presumed_condition: str | None = None,
    price_kind: str | None = None,
) -> dict | None:
    """Score 0-100 e desconto sobre a referência ajustada.

    Devolve None quando não é honesto pontuar: sem preço, sem referência, ou
    com condição desconhecida e sem premissa aceitável.
    """
    presumed = False
    if condition in UNKNOWN_CONDITIONS:
        if not presumed_condition:
            return None
        condition, presumed = presumed_condition, True
    factor = CONDITION_FACTOR.get(condition)
    if factor is None:
        return None
    ref = _dec(reference_value)
    if ref is None or ref <= 0:
        return None

    cost, breakdown = total_cost(price, raw_attributes, default_commission)
    if cost is None:
        return None

    adjusted = (ref * Decimal(str(factor))).quantize(Decimal("0.01"))
    if adjusted <= 0:
        return None
    discount = float((adjusted - cost) / adjusted * Decimal(100))

    # Faixa de score: 0% de desconto -> 0; 40% ou mais -> 100. Acima de 40% o
    # ganho satura de propósito: desconto muito alto costuma ser sinal de
    # problema no bem, não de oportunidade melhor.
    score = max(0, min(100, round(discount / 40 * 100)))
    if presumed:
        score = round(score * PRESUMED_PENALTY)

    reasons = {
        **breakdown,
        "referencia": float(ref),
        "condicao": condition,
        "condicao_presumida": presumed,
        "fator_condicao": factor,
        "referencia_ajustada": float(adjusted),
        "desconto_pct": round(discount, 1),
    }
    # O lance inicial é o piso do leilão, não o preço de arremate: o lote será
    # disputado e o valor sobe. Sem esta ressalva o usuário lê o desconto como
    # garantido, e ele é apenas o teto do que dá para ganhar.
    if price_kind in (None, "lance_inicial"):
        reasons["base_calculo"] = "lance_inicial"
        reasons["nota_preco"] = (
            "Cálculo sobre o lance inicial, que é o piso do pregão. O valor de "
            "arremate costuma ser maior, então este é o desconto máximo possível, "
            "não o provável."
        )
    else:
        reasons["base_calculo"] = price_kind

    if presumed:
        reasons["nota_condicao"] = (
            "A fonte não informou o estado do bem. Assumimos íntegro por ser "
            "retomada de financeira, frota ou locadora sem menção a avaria, e "
            "reduzimos o score por essa incerteza. Confirme na fonte oficial."
        )
    if factor < 1.0:
        reasons["nota"] = (
            f"Referência ajustada para a condição '{condition}': o mercado paga "
            f"cerca de {int(factor * 100)}% do valor de um exemplar íntegro."
        )
    if discount <= 0:
        reasons["alerta"] = "O custo total está acima da referência de mercado."

    return {"score": score, "discount_pct": round(discount, 2),
            "total_cost": cost, "reference_adjusted": adjusted, "reasons": reasons}
