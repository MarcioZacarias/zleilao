"""Classificacao de categoria: dica da fonte primeiro, depois palavras-chave
do titulo (folhas antes dos pais). Fallback: 'veiculos' para fontes de
leilao de veiculos, senao 'diversos'.
"""
from __future__ import annotations

import re

from unidecode import unidecode

from app.models import Category

# Dicas conhecidas das fontes -> slug
HINT_MAP = {
    "carros": "carros", "carro": "carros", "leves": "carros", "automoveis": "carros", "utilitarios-leves": "carros",
    "motos": "motos", "moto": "motos", "motocicletas": "motos",
    "caminhoes": "caminhoes", "caminhao": "caminhoes", "pesados": "caminhoes", "carretas": "caminhoes",
    "utilitarios": "utilitarios", "vans": "utilitarios", "utilitario": "utilitarios",
    "onibus": "onibus", "micro-onibus": "onibus",
    "barcos": "outros-veiculos", "aeronaves": "outros-veiculos", "reboques": "outros-veiculos", "sucatas": "outros-veiculos",
    "maquinas": "maquinas-equipamentos", "agro": "maquinas-equipamentos", "equipamentos": "maquinas-equipamentos",
    "imoveis": "imoveis", "veiculos": "veiculos",
}


def _norm(s: str | None) -> str:
    return unidecode(s or "").lower().strip()


def classify(title: str, hint: str | None, categories: list[Category]) -> Category | None:
    by_slug = {c.slug: c for c in categories if c.is_active}
    if hint:
        h = _norm(hint).replace(" ", "-")
        slug = HINT_MAP.get(h) or (h if h in by_slug else None)
        if slug and slug in by_slug and by_slug[slug].parent_id is not None:
            return by_slug[slug]  # dica ja' aponta para uma folha
        parent_slug = slug

    else:
        parent_slug = None

    t = " " + _norm(title) + " "
    leaves = [c for c in categories if c.is_active and c.keywords]
    # folhas (path com "/") primeiro, depois raizes
    leaves.sort(key=lambda c: (c.path.count("/") == 0, c.sort_order))
    for cat in leaves:
        for kw in cat.keywords or []:
            k = _norm(kw)
            if not k:
                continue
            if re.search(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", t):
                if parent_slug and cat.path.split("/")[0] != parent_slug and parent_slug in by_slug:
                    # dica de pai diverge do keyword: a dica da fonte manda
                    continue
                return cat
    if parent_slug and parent_slug in by_slug:
        # Veiculo sem folha identificada: assume carros quando a fonte e' de veiculos
        if parent_slug == "veiculos" and "carros" in by_slug:
            return by_slug["carros"]
        return by_slug[parent_slug]
    return by_slug.get("diversos")
