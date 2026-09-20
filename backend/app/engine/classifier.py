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


def _leaves(categories: list[Category]) -> list[Category]:
    """Folhas antes das raizes, na ordem de exibicao."""
    out = [c for c in categories if c.is_active and c.keywords]
    out.sort(key=lambda c: (c.path.count("/") == 0, c.sort_order))
    return out


def _matches(title: str, categories: list[Category]) -> list[tuple[int, int, Category]]:
    """(posicao, tamanho, categoria) de cada palavra-chave achada no titulo.

    A posicao importa porque nos leiloes o titulo abre pelo tipo do bem
    ("Trator John Deere", "Plaina agricola Baldan"); o tamanho importa para
    "plaina agricola" ganhar de "plaina".
    """
    t = " " + _norm(title) + " "
    found: list[tuple[int, int, Category]] = []
    for cat in _leaves(categories):
        for kw in cat.keywords or []:
            k = _norm(kw)
            if not k:
                continue
            m = re.search(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", t)
            if m:
                found.append((m.start(), len(k), cat))
    found.sort(key=lambda x: (x[0], -x[1]))
    return found


def classify(title: str, hint: str | None, categories: list[Category]) -> Category | None:
    by_slug = {c.slug: c for c in categories if c.is_active}
    found = _matches(title, categories)

    parent_slug = None
    if hint:
        h = _norm(hint).replace(" ", "-")
        slug = HINT_MAP.get(h) or (h if h in by_slug else None)
        if slug and slug in by_slug and by_slug[slug].parent_id is not None:
            # A dica ja' aponta uma folha, mas ela e' grossa: muitos leiloeiros
            # so' tem "leves" e "pesados" e jogam trator, implemento e carcaca
            # no balde mais proximo. Havendo palavra-chave no titulo, o titulo
            # manda; e a primeira delas e' o bem ("Carcaca de Carro" e' carcaca,
            # "Caminhao com munck" e' caminhao).
            return found[0][2] if found else by_slug[slug]
        parent_slug = slug

    for _, _, cat in found:
        if parent_slug and cat.path.split("/")[0] != parent_slug and parent_slug in by_slug:
            # dica de pai diverge do keyword: a dica da fonte manda
            continue
        return cat
    if found:
        return found[0][2]
    if parent_slug and parent_slug in by_slug:
        # Veiculo sem folha identificada: assume carros quando a fonte e' de veiculos
        if parent_slug == "veiculos" and "carros" in by_slug:
            return by_slug["carros"]
        return by_slug[parent_slug]
    return by_slug.get("diversos")
