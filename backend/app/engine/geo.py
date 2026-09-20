"""Geolocalização por município, para a busca por raio (RN da F4).

**Sem PostGIS e sem API externa.** A EF admitia PostGIS ou `earthdistance`;
os dois adicionam dependência ao servidor compartilhado, e uma API de
geocodificação adicionaria latência e limite de uso a cada coleta. Em vez
disso, a base oficial de 5.571 municípios brasileiros (código IBGE, nome, UF,
coordenadas, população IBGE 2021) mora no repositório: 230 KB, resolução
instantânea, offline e determinística. A população não entra no cálculo de
distância — serve só para ordenar o autocomplete de cidade.

A precisão é a do centroide do município, que é o suficiente: o usuário quer
"lotes até 150 km de mim", não a distância exata até o pátio.
"""
from __future__ import annotations

import json
import logging
import math
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Optional

logger = logging.getLogger("zleilao.geo")

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "municipios.json"
EARTH_RADIUS_KM = 6371.0


UFS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA",
    "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}


def normalize_city(name: str | None) -> str:
    """"São Paulo" -> "sao paulo". Tira o sufixo de UF em qualquer separador.

    A UF só é removida se for uma sigla real: senão "Campo Grande" viraria
    "Campo" e "Rio Verde" viraria "Rio".
    """
    if not name:
        return ""
    s = unicodedata.normalize("NFD", name)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    # Antes de limpar a pontuação: "Santo André/SP", "Osasco - SP", "Bauru (SP)"
    s = re.sub(r"\s*[-/(,]\s*([A-Za-z]{2})\s*\)?\s*$",
               lambda m: "" if m.group(1).upper() in UFS else m.group(0), s)
    s = re.sub(r"[^a-zA-Z0-9\s'-]", " ", s).lower()
    # Sobrou a sigla solta no fim ("santo andre sp")
    parts = s.split()
    if len(parts) > 1 and parts[-1].upper() in UFS:
        parts = parts[:-1]
    return " ".join(parts)


#: Abreviações que as fontes usam no nome do município.
ABBREVIATIONS = {
    "sta": "santa", "sto": "santo", "s": "sao", "sao": "sao",
    "pres": "presidente", "gov": "governador", "eng": "engenheiro",
    "gal": "general", "mal": "marechal", "cel": "coronel", "dr": "doutor",
    "n": "nova", "nsa": "nossa", "srta": "senhorita",
}

#: No Distrito Federal só existe um município: Brasília. Tudo o que as fontes
#: escrevem ali (Taguatinga, Ceilândia, Gama...) são regiões administrativas.
DF_FALLBACK = "brasilia"


@lru_cache(maxsize=1)
def _table() -> dict[str, list[float]]:
    """Base de municípios, com um índice extra sem apóstrofo.

    A base traz "santa barbara d'oeste"; as fontes escrevem "Sta Barbara
    Doeste". Indexar as duas formas resolve sem regex frágil de apóstrofo.
    """
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.error("base de municipios indisponivel (%s): busca por raio desligada", exc)
        return {}
    for key, row in list(data.items()):
        if "'" in key:
            # O 5o elemento marca "esta linha e apelido": o autocomplete pula,
            # para nao listar "Santa Barbara d'Oeste" duas vezes.
            data.setdefault(key.replace("'", ""), list(row) + [True])
    return data


@lru_cache(maxsize=4096)
def coords_for(city: str | None, state: str | None) -> Optional[tuple[float, float]]:
    """(lat, lng) do município. None quando não reconhece — e aí o item
    simplesmente não entra na busca por raio, em vez de entrar no lugar errado."""
    if not city or not state:
        return None
    uf = state.strip().upper()
    table = _table()
    name = normalize_city(city)

    for candidate in (name, _expand_abbreviations(name)):
        found = table.get(f"{uf}|{candidate}")
        if found:
            return found[0], found[1]

    # "Sao Paulo - Capital", "Guaratingueta (SP)": tenta sem o complemento
    base = normalize_city(re.split(r"[(\-–,]", city)[0])
    found = table.get(f"{uf}|{base}") or table.get(f"{uf}|{_expand_abbreviations(base)}")
    if found:
        return found[0], found[1]

    # Regiões administrativas do DF caem em Brasília, o único município de lá.
    if uf == "DF":
        found = table.get(f"DF|{DF_FALLBACK}")
        if found:
            return found[0], found[1]
    return None


def _expand_abbreviations(name: str) -> str:
    """"sta barbara doeste" -> "santa barbara doeste"; "sto andre" -> "santo andre".

    O apóstrofo não precisa ser reconstruído: a tabela também é indexada sem
    ele (ver `_table`).
    """
    parts = [ABBREVIATIONS.get(p.rstrip("."), p) for p in name.split()]
    return " ".join(parts)


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distância em km entre dois pontos na superfície da Terra."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def bounding_box(lat: float, lng: float, radius_km: float) -> tuple[float, float, float, float]:
    """Retângulo que contém o círculo, para o banco filtrar por índice antes de
    calcular a distância exata. Sem isso, um raio de 100 km leria a tabela toda."""
    dlat = radius_km / 111.045
    cos_lat = math.cos(math.radians(lat))
    dlng = radius_km / (111.045 * cos_lat) if abs(cos_lat) > 1e-6 else 180.0
    return (lat - dlat, lat + dlat, max(-180.0, lng - dlng), min(180.0, lng + dlng))


def search_cities(term: str, limit: int = 8) -> list[dict]:
    """Autocomplete de cidade para a interface de busca por raio.

    Ordena por populacao, nao por ordem alfabetica nem por tamanho do nome:
    quem digita "camp" quer Campinas e Campo Grande, nao Campanha. A varredura
    percorre a base inteira — parar nos primeiros achados ordenaria um recorte
    arbitrario da tabela.
    """
    t = normalize_city(term)
    if len(t) < 2:
        return []
    out = []
    for key, row in _table().items():
        uf, name = key.split("|", 1)
        pos = name.find(t)
        if pos < 0 or len(row) > 4:  # len > 4 = apelido sem apostrofo
            continue
        pop = row[2] if len(row) > 2 else 0
        display = row[3] if len(row) > 3 else name.title()
        out.append({"city": display, "state": uf, "lat": row[0], "lng": row[1],
                    "_rank": (pos != 0, -pop, len(name))})
    out.sort(key=lambda x: x["_rank"])
    for o in out:
        o.pop("_rank", None)
    return out[:limit]
