"""Extracao deterministica de campos de veiculo a partir do titulo, da
descricao curta e dos atributos que a fonte ja' entrega.

Roda SEMPRE (barato, previsivel) e serve de base para o LLM, que so'
preenche/corrige o que as regras nao alcancam. Sem API key configurada, e'
o unico extrator — o item ainda e' publicado, com menos campos.

Versao: mude DET_VERSION quando alterar regras que afetam a saida.
"""
from __future__ import annotations

import re
from typing import Any

from unidecode import unidecode

DET_VERSION = "det-1"

BRANDS = {
    "volkswagen": ["volkswagen", "vw", "vw/", "volks"],
    "chevrolet": ["chevrolet", "gm", "gm/", "chev"],
    "fiat": ["fiat"],
    "ford": ["ford"],
    "toyota": ["toyota"],
    "honda": ["honda"],
    "hyundai": ["hyundai"],
    "renault": ["renault"],
    "nissan": ["nissan"],
    "jeep": ["jeep"],
    "peugeot": ["peugeot"],
    "citroen": ["citroen"],
    "mitsubishi": ["mitsubishi"],
    "kia": ["kia"],
    "bmw": ["bmw"],
    "mercedes-benz": ["mercedes-benz", "mercedes", "m.benz", "m benz", "mb/"],
    "audi": ["audi"],
    "volvo": ["volvo"],
    "scania": ["scania"],
    "iveco": ["iveco"],
    "daf": ["daf"],
    "man": ["man/"],
    "yamaha": ["yamaha"],
    "suzuki": ["suzuki"],
    "kawasaki": ["kawasaki"],
    "bmw motorrad": ["bmw motorrad"],
    "dafra": ["dafra"],
    "shineray": ["shineray"],
    "haojue": ["haojue"],
    "royal enfield": ["royal enfield"],
    "triumph": ["triumph"],
    "harley-davidson": ["harley", "harley-davidson"],
    "land rover": ["land rover", "lr/", "lr "],
    "rontan": ["rontan", "rotan"],
    "troller": ["troller"],
    "jaguar": ["jaguar"],
    "lexus": ["lexus"],
    "effa": ["effa"],
    "foton": ["foton"],
    "caoa": ["caoa"],
    "chery": ["chery", "caoa chery"],
    "jac": ["jac"],
    "byd": ["byd"],
    "gwm": ["gwm", "haval"],
    "ram": ["ram/"],
    "dodge": ["dodge"],
    "subaru": ["subaru"],
    "lifan": ["lifan"],
    "porsche": ["porsche"],
    "mini": ["mini/"],
    "agrale": ["agrale"],
    "marcopolo": ["marcopolo"],
    "randon": ["randon"],
    "facchini": ["facchini"],
    "librelato": ["librelato"],
    "guerra": ["guerra"],
    "noma": ["noma"],
}
BRAND_LABEL = {
    "volkswagen": "Volkswagen", "chevrolet": "Chevrolet", "fiat": "Fiat", "ford": "Ford", "toyota": "Toyota",
    "honda": "Honda", "hyundai": "Hyundai", "renault": "Renault", "nissan": "Nissan", "jeep": "Jeep",
    "peugeot": "Peugeot", "citroen": "Citroën", "mitsubishi": "Mitsubishi", "kia": "Kia", "bmw": "BMW",
    "mercedes-benz": "Mercedes-Benz", "audi": "Audi", "volvo": "Volvo", "scania": "Scania", "iveco": "Iveco",
    "daf": "DAF", "man": "MAN", "yamaha": "Yamaha", "suzuki": "Suzuki", "kawasaki": "Kawasaki",
    "bmw motorrad": "BMW Motorrad", "dafra": "Dafra", "shineray": "Shineray", "haojue": "Haojue",
    "royal enfield": "Royal Enfield", "triumph": "Triumph", "harley-davidson": "Harley-Davidson",
    "land rover": "Land Rover", "rontan": "Rontan", "troller": "Troller", "jaguar": "Jaguar", "lexus": "Lexus",
    "effa": "Effa", "foton": "Foton", "caoa": "CAOA", "chery": "Chery", "jac": "JAC", "byd": "BYD", "gwm": "GWM", "ram": "RAM",
    "dodge": "Dodge", "subaru": "Subaru", "lifan": "Lifan", "porsche": "Porsche", "mini": "MINI",
    "agrale": "Agrale", "marcopolo": "Marcopolo", "randon": "Randon", "facchini": "Facchini",
    "librelato": "Librelato", "guerra": "Guerra", "noma": "Noma",
}

COLORS = ["branca", "branco", "preta", "preto", "prata", "cinza", "vermelha", "vermelho", "azul", "verde",
          "amarela", "amarelo", "marrom", "bege", "dourada", "dourado", "laranja", "vinho", "grafite", "roxa", "rosa"]

FUEL_PATTERNS = [
    (r"gasol\w*\s*/\s*alc\w*|alc\w*\s*/\s*gasol\w*|gasol\w*\s+e\s+alc\w*|alc\w*\s+e\s+gasol\w*|\bflex\b|bicombust|total\s*flex", "flex"),
    (r"\bdiesel\b|\bdies\b", "diesel"),
    (r"\bgnv\b", "gnv"),
    (r"eletric|el[eé]trico", "eletrico"),
    (r"h[ií]brid", "hibrido"),
    (r"\b[aá]lcool\b|\betanol\b|\balc\b", "etanol"),
    (r"\bgasolina\b|\bgasol\b", "gasolina"),
]
GEAR_PATTERNS = [
    (r"automatizad", "automatizado"),
    (r"\bcvt\b", "cvt"),
    (r"autom[aá]tic|\baut\b|\bat\b(?![a-z])", "automatico"),
    (r"\bmanual\b|\bmec[aâ]nic[oa]\b|\bmt\b", "manual"),
]
CONDITION_PATTERNS = [
    (r"\bsucata\b|baixad[oa]\b", "sucata"),
    (r"grande monta", "sinistro_grande_monta"),
    (r"m[eé]dia monta", "sinistro_media_monta"),
    (r"pequena monta|recuper[aá]vel|sinistrad[oa]|\bsinistro\b|colis[aã]o|batid[oa]|avariad[oa]", "sinistro_recuperavel"),
]
DOC_PATTERNS = [
    (r"crlv[- ]?e?\s*dispon|documento\s*ok|com documento", "crlv_disponivel"),
    (r"sem documento|sem doc\b|s/\s*doc", "sem_documento"),
    (r"documento pendente|pendente de regulariza|regulariza[cç][aã]o pendente|sem crlv", "documento_pendente"),
]
ORIGEM_PATTERNS = [
    (r"financeira|banco|retomad[oa] de financ|aliena[cç][aã]o fiduci", "financeira"),
    (r"seguradora|sinistro de seguro", "seguradora"),
    (r"judicial|vara\b|execu[cç][aã]o|penhora|processo n", "judicial"),
    (r"locadora|\bloca[cç][aã]o\b|rent a car|localiza|movida|unidas", "locadora"),
    (r"\bfrota\b|frotista", "frota"),
]


def _n(s: str | None) -> str:
    return unidecode(s or "").lower()


def detect_brand(text: str) -> str | None:
    t = " " + _n(text).replace("/", " / ") + " "
    best: tuple[int, str] | None = None
    for key, aliases in BRANDS.items():
        for a in aliases:
            a_n = _n(a).replace("/", " /")
            pattern = r"(?<![a-z0-9])" + re.escape(a_n.strip()) + r"(?![a-z0-9])"
            m = re.search(pattern, t)
            if m and (best is None or m.start() < best[0]):
                best = (m.start(), key)
    return BRAND_LABEL.get(best[1]) if best else None


def detect_model(text: str, brand: str | None) -> str | None:
    if not brand:
        return None
    t = re.sub(r"\s+", " ", text.replace("/", " / "))
    aliases = BRANDS.get(_n(brand).replace("ë", "e"), []) + [brand]
    tn = _n(t)
    pos = None
    for a in aliases:
        a_n = _n(a).replace("/", " /").strip()
        m = re.search(r"(?<![a-z0-9])" + re.escape(a_n) + r"(?![a-z0-9])", tn)
        if m and (pos is None or m.end() > pos):
            pos = m.end()
    if pos is None:
        return None
    rest = t[pos:].lstrip(" /-–:")
    # corta em virgula, ano (4 digitos ou 19/20), "ano", "placa", hifen isolado
    rest = re.split(r",|\(|\s-\s|\bano\b|\bplaca\b|\blote\b|\b(?:19|20)\d{2}\b|\b\d{2}/\d{2}\b|\bkm\b", rest, flags=re.I)[0]
    tokens = [tok for tok in rest.split() if tok]
    if not tokens:
        return None
    # modelo = ate 2 tokens (ex.: "Fox 1.6" -> "Fox"; "Sandero GTL" -> "Sandero GTL"; "Hilux CD" -> "Hilux")
    model_tokens = []
    for tok in tokens[:3]:
        if re.fullmatch(r"\d\.\d|\d{1,2}v|\d{3,4}", tok.lower()):
            break
        model_tokens.append(tok)
        if len(model_tokens) == 2:
            break
    model = " ".join(model_tokens).strip(" .-/")
    return model.title() if model else None


#: Sufixo de portas das bases de referencia de veiculos (Infocar/Molicar):
#: "GOL TRENDLINE (2P/4P)". Nao descreve o bem e atrapalha busca e dedup.
DOORS_SUFFIX_RE = re.compile(r"\s*\(\s*\d\s*P(\s*/\s*\d\s*P)*\s*\)\s*", re.I)


def clean_model(raw: str | None) -> str | None:
    """Normaliza o modelo vindo da fonte. Roda tambem na reextracao, entao
    alcanca o que ja' esta' gravado em `attributes._raw`."""
    if not raw:
        return None
    cleaned = DOORS_SUFFIX_RE.sub(" ", str(raw))
    return re.sub(r"\s{2,}", " ", cleaned).strip(" .-/") or None


def detect_years(text: str) -> tuple[int | None, int | None]:
    """Retorna (ano_fabricacao, ano_modelo)."""
    t = text
    m = re.search(r"\b((?:19|20)\d{2})\s*/\s*((?:19|20)\d{2})\b", t)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"\b(\d{2})\s*/\s*(\d{2})\b(?!\s*/)", t)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        def full(y: int) -> int:
            return 2000 + y if y <= 40 else 1900 + y
        fa, fb = full(a), full(b)
        if fb - fa in (0, 1):
            return fa, fb
    m = re.search(r"\b(?:ano|ano/?modelo|a/m)\s*[:\-]?\s*((?:19|20)\d{2})", t, re.I)
    if m:
        y = int(m.group(1))
        return y, y
    years = [int(y) for y in re.findall(r"\b((?:19|20)\d{2})\b", t)]
    years = [y for y in years if 1960 <= y <= 2035]
    if years:
        return None, years[0]
    return None, None


def detect_km(text: str) -> int | None:
    m = re.search(r"(\d{1,3}(?:\.\d{3})+|\d{4,7})\s*km\b", _n(text))
    if m:
        try:
            return int(m.group(1).replace(".", ""))
        except ValueError:
            return None
    m = re.search(r"\bkm[:\s]*(\d{1,3}(?:\.\d{3})+|\d{3,7})\b", _n(text))
    if m:
        return int(m.group(1).replace(".", ""))
    return None


def _first_match(text: str, patterns: list[tuple[str, str]]) -> str | None:
    t = _n(text)
    for pat, val in patterns:
        if re.search(pat, t):
            return val
    return None


def detect_color(text: str) -> str | None:
    t = _n(text)
    for c in COLORS:
        if re.search(r"(?<![a-z])" + _n(c) + r"(?![a-z])", t):
            return c.capitalize()
    return None


def detect_debitos(text: str) -> float | None:
    t = text
    m = re.search(r"d[eé]bitos?.{0,80}?R\$\s*([\d\.]+(?:,\d{2})?)", t, re.I | re.S)
    if m:
        try:
            return float(m.group(1).replace(".", "").replace(",", "."))
        except ValueError:
            return None
    return None


def detect_restricoes(text: str) -> str | None:
    t = _n(text)
    found = []
    for pat, label in [
        (r"renajud", "Renajud"), (r"bloqueio judicial", "Bloqueio judicial"),
        (r"alienacao fiduciaria", "Alienação fiduciária"), (r"restricao judic", "Restrição judiciária"),
        (r"restricao administrativa", "Restrição administrativa"), (r"gravame", "Gravame"),
        (r"roubo\s*/?\s*furto|furto\s*/?\s*roubo", "Ocorrência de roubo/furto"),
    ]:
        if re.search(pat, t) and label not in found:
            found.append(label)
    return ", ".join(found) if found else None


#: Tipos de maquina reconhecidos no titulo, do mais especifico para o generico.
MACHINE_TYPES = [
    ("retroescavadeira", "Retroescavadeira"), ("escavadeira", "Escavadeira"),
    ("pa carregadeira", "Pá carregadeira"), ("motoniveladora", "Motoniveladora"),
    ("rolo compactador", "Rolo compactador"), ("colheitadeira", "Colheitadeira"),
    ("empilhadeira", "Empilhadeira"), ("plantadeira", "Plantadeira"),
    ("semeadeira", "Semeadeira"), ("pulverizador", "Pulverizador"),
    ("plaina agricola", "Plaina agrícola"), ("grade aradora", "Grade aradora"),
    ("betoneira", "Betoneira"), ("guindaste", "Guindaste"), ("gerador", "Gerador"),
    ("compressor", "Compressor"), ("transformador", "Transformador"),
    ("munck", "Munck"), ("trator", "Trator"),
]

MACHINE_CONDITION_PATTERNS = [
    (r"\bsucata\b|inserviv|imprest", "sucata"),
    (r"nao funciona|nao liga|necessita (de )?reparo|para reparo|com defeito|danificad|quebrad|faltando pec", "necessita_reparo"),
]


def detect_horimeter(text: str | None) -> int | None:
    """Horimetro faz, para maquina, o papel da quilometragem no veiculo."""
    if not text:
        return None
    t = _n(text)
    m = re.search(r"(\d{1,3}(?:\.\d{3})+|\d{2,7})\s*(?:horas|hrs|hs|h)\b", t)
    if not m:
        m = re.search(r"horimetro[:\s]*(\d{1,3}(?:\.\d{3})+|\d{2,7})", t)
    if not m:
        return None
    try:
        value = int(m.group(1).replace(".", ""))
    except ValueError:
        return None
    # Horimetro plausivel: acima de 200.000 h e' quase certo erro de leitura.
    return value if 0 < value <= 200_000 else None


def detect_machine_type(text: str | None) -> str | None:
    t = _n(text)
    for needle, label in MACHINE_TYPES:
        if needle in t:
            return label
    return None


def extract_machine_fields(title: str, short_text: str | None, raw: dict[str, Any] | None) -> dict[str, Any]:
    """Campos de maquina/equipamento. Mesma regra do veiculo: nunca inventa."""
    raw = raw or {}
    text = f"{title}\n{short_text or ''}"
    out: dict[str, Any] = {
        "marca": raw.get("marca") or detect_brand(title) or detect_brand(text),
        "modelo": clean_model(raw.get("modelo")),
        "ano_fabricacao": raw.get("ano_fabricacao") or detect_years(title)[0] or detect_years(title)[1],
        "horimetro": raw.get("horimetro") or detect_horimeter(text),
        "tipo_equipamento": raw.get("tipo_equipamento") or detect_machine_type(text),
        "condicao": raw.get("condicao") or _first_match(text, MACHINE_CONDITION_PATTERNS),
        "observacoes": raw.get("observacoes") or None,
        "implementos": raw.get("implementos") or None,
    }
    if raw.get("potencia_cv"):
        out["potencia_cv"] = raw["potencia_cv"]
    else:
        m = re.search(r"(\d{2,4})\s*(?:cv|hp)\b", _n(text))
        if m:
            out["potencia_cv"] = int(m.group(1))
    return {k: v for k, v in out.items() if v is not None}


def has_damage_words(text: str | None) -> bool:
    """O texto menciona dano, sinistro, sucata ou avaria?

    Usado pelo comparador para decidir se pode presumir um bem intacto. Vale
    tanto para o vocabulario de sinistro quanto para avarias pontuais
    ("embreagem danificada"), porque qualquer um deles derruba a premissa.
    """
    if not text:
        return False
    t = _n(text)
    if any(re.search(pat, t) for pat, _ in CONDITION_PATTERNS):
        return True
    return bool(re.search(r"danificad|avaria|amassad|quebrad|faltando|ausencia de|nao funciona|sem motor|incendi|enchente|alagad", t))


def extract_vehicle_fields(title: str, short_text: str | None, raw: dict[str, Any] | None) -> dict[str, Any]:
    """Campos que as regras conseguem extrair. Nunca inventa: ausente = None."""
    raw = raw or {}
    text = f"{title}\n{short_text or ''}"
    brand = raw.get("marca") or detect_brand(title) or detect_brand(text)
    model = clean_model(raw.get("modelo")) or detect_model(title, brand)
    fab, mod = detect_years(title)
    if fab is None and mod is None:
        fab, mod = detect_years(text)
    out: dict[str, Any] = {
        "marca": brand,
        "modelo": model,
        "ano_fabricacao": raw.get("ano_fabricacao") or fab,
        "ano_modelo": raw.get("ano_modelo") or mod or fab,
        "km": raw.get("km") if raw.get("km") not in (None, "", 0) else detect_km(text),
        "combustivel": raw.get("combustivel") or _first_match(text, FUEL_PATTERNS),
        "cambio": raw.get("cambio") or _first_match(text, GEAR_PATTERNS),
        "cor": raw.get("cor") or detect_color(title) or detect_color(short_text or ""),
        "condicao": raw.get("condicao") or _first_match(text, CONDITION_PATTERNS),
        "situacao_documento": raw.get("situacao_documento") or _first_match(text, DOC_PATTERNS),
        "ipva_pago": raw.get("ipva_pago") if raw.get("ipva_pago") is not None else (True if re.search(r"ipva\s*(?:\d{4})?\s*pago", _n(text)) else None),
        "laudo_cautelar": raw.get("laudo_cautelar"),
        "debitos": raw.get("debitos") or detect_debitos(text),
        "restricoes": raw.get("restricoes") or detect_restricoes(text),
        "origem": raw.get("origem") or _first_match(text, ORIGEM_PATTERNS),
        "opcionais": raw.get("opcionais") or None,
        "observacoes": raw.get("observacoes") or None,
        "placa_mascarada": raw.get("placa_mascarada"),
        "chassi_mascarado": raw.get("chassi_mascarado"),
    }
    if raw.get("cilindradas"):
        out["cilindradas"] = raw["cilindradas"]
    else:
        m = re.search(r"\b(\d{2,4})\s*(?:cc|cilindradas)\b", _n(text))
        if m:
            out["cilindradas"] = int(m.group(1))
    # Retomada de frota/financeira sem mencao a dano -> normal (regra explicita, nao inferencia)
    if out["condicao"] is None and out["origem"] in ("financeira", "frota", "locadora") and raw.get("laudo_cautelar") == "aprovado":
        out["condicao"] = "normal"
    return {k: v for k, v in out.items() if v is not None}
