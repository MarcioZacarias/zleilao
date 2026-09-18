"""Seeds: usuario admin, arvore de categorias com campos dinamicos (RN-002)
e fontes de leilao da F1.

Idempotente: so' insere o que falta. Campos de categoria sao herdados pelos
filhos (Carros herda os campos de Veiculos) — ver `engine/category_fields.py`.
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import hash_password
from app.config import get_settings
from app.models import Category, CategoryField, Source, User

logger = logging.getLogger("zleilao.seed")

NI = "nao_informado"

VEHICLE_FIELDS = [
    # key, label, type, unit, required, options, show_in_card, filterable, description
    ("marca", "Marca", "string", None, True, None, True, True, "Fabricante do veiculo (ex.: Volkswagen, Fiat, Honda)."),
    ("modelo", "Modelo", "string", None, False, None, True, True, "Modelo sem a versao (ex.: Gol, Corolla, CG 160)."),
    ("versao", "Versão", "string", None, False, None, False, False, "Versao/acabamento (ex.: 1.6 MSI Highline, XEi 2.0)."),
    ("ano_fabricacao", "Ano fabricação", "int", None, False, None, False, False, "Ano de fabricacao, 4 digitos."),
    ("ano_modelo", "Ano modelo", "int", None, False, None, True, True, "Ano modelo, 4 digitos. Em '19/20' o segundo e' o ano modelo."),
    ("km", "Quilometragem", "int", "km", False, None, True, True, "Quilometragem em km, apenas numero."),
    ("combustivel", "Combustível", "enum", None, False, ["gasolina", "etanol", "flex", "diesel", "gnv", "eletrico", "hibrido", NI], False, True, "GASOL/ALC = flex."),
    ("cambio", "Câmbio", "enum", None, False, ["manual", "automatico", "automatizado", "cvt", NI], False, True, None),
    ("cor", "Cor", "string", None, False, None, False, False, None),
    ("placa_mascarada", "Placa (mascarada)", "string", None, False, None, False, False, "Placa com os 4 caracteres centrais ocultos (ex.: ABC****). Nunca a placa completa."),
    ("situacao_documento", "Situação do documento", "enum", None, False, ["crlv_disponivel", "sem_documento", "documento_pendente", NI], False, True, "CRLV disponivel, sem documento, pendente de regularizacao."),
    ("condicao", "Condição", "enum", None, True, ["normal", "sinistro_recuperavel", "sinistro_media_monta", "sinistro_grande_monta", "sucata", NI], True, True, "Sinistro/recuperavel/sucata quando o texto indicar; 'normal' so' quando explicitamente sem sinistro (ex.: retomada de financeira ou frota sem mencao a dano)."),
    ("laudo_cautelar", "Laudo cautelar", "enum", None, False, ["aprovado", "reprovado", NI], False, True, None),
    ("ipva_pago", "IPVA pago", "bool", None, False, None, False, False, None),
    ("debitos", "Débitos informados", "decimal", "BRL", False, None, False, False, "Soma dos debitos (IPVA, multas) citados no texto, em reais."),
    ("restricoes", "Restrições", "string", None, False, None, False, False, "Restricoes judiciais/administrativas citadas (Renajud, bloqueio, alienacao)."),
    ("origem", "Origem", "enum", None, False, ["financeira", "seguradora", "judicial", "frota", "locadora", "particular", NI], True, True, "Quem esta' vendendo: banco/financeira, seguradora, vara judicial, frota de empresa, locadora."),
    ("opcionais", "Opcionais", "string", None, False, None, False, False, "Lista separada por virgula (ar condicionado, direcao hidraulica...)."),
    ("observacoes", "Observações", "string", None, False, None, False, False, "Avarias e observacoes relevantes, resumidas em ate 300 caracteres."),
]

MOTO_FIELDS = [
    ("cilindradas", "Cilindradas", "int", "cc", False, None, True, True, "Cilindrada em cc."),
]

CAMINHAO_FIELDS = [
    ("eixos", "Eixos", "int", None, False, None, False, False, None),
    ("carroceria", "Carroceria", "string", None, False, None, False, False, "Bau, grade baixa, bascula, cavalo mecanico, etc."),
    ("tracao", "Tração", "string", None, False, None, False, False, "4x2, 6x2, 6x4..."),
]

CATEGORIES = [
    {"name": "Veículos", "slug": "veiculos", "parent": None, "fields": VEHICLE_FIELDS, "keywords": [],
     "llm_hint": "Lote de veiculo automotor em leilao no Brasil."},
    {"name": "Carros", "slug": "carros", "parent": "veiculos", "fields": [], "keywords": ["carro", "automovel", "hatch", "sedan", "suv", "picape", "pick-up", "camionete"]},
    {"name": "Motos", "slug": "motos", "parent": "veiculos", "fields": MOTO_FIELDS, "keywords": ["moto", "motocicleta", "scooter", "ciclomotor", "cg 160", "biz", "fazer", "xre", "cb 500", "titan", "bros", "pcx", "nmax"]},
    {"name": "Caminhões", "slug": "caminhoes", "parent": "veiculos", "fields": CAMINHAO_FIELDS, "keywords": ["caminhao", "caminhão", "cavalo mecanico", "semirreboque", "semi-reboque", "carreta", "bitrem", "truck", "tector", "constellation", "atego", "accelo", "vm 270", "fh 540", "actros"]},
    {"name": "Utilitários e vans", "slug": "utilitarios", "parent": "veiculos", "fields": [], "keywords": ["van", "furgao", "furgão", "utilitario", "ducato", "sprinter", "master", "transit", "daily", "hr ", "kombi", "fiorino", "partner", "kangoo"]},
    {"name": "Ônibus", "slug": "onibus", "parent": "veiculos", "fields": [], "keywords": ["onibus", "ônibus", "micro-onibus", "microonibus", "micro onibus", "rodoviario"]},
    {"name": "Outros veículos", "slug": "outros-veiculos", "parent": "veiculos", "fields": [], "keywords": ["reboque", "trailer", "quadriciclo", "jet ski", "barco", "lancha", "aeronave", "sucata"]},
    {"name": "Máquinas e equipamentos", "slug": "maquinas-equipamentos", "parent": None, "fields": [], "keywords": ["trator", "colheitadeira", "retroescavadeira", "escavadeira", "empilhadeira", "gerador", "compressor", "pa carregadeira", "motoniveladora"]},
    {"name": "Imóveis", "slug": "imoveis", "parent": None, "fields": [], "keywords": ["apartamento", "casa", "terreno", "imovel", "imóvel", "sala comercial", "galpao", "galpão", "sitio", "fazenda"]},
    {"name": "Diversos", "slug": "diversos", "parent": None, "fields": [], "keywords": []},
]

# Fontes da F1. Config editavel no admin. `dispatch_enabled` comeca True para
# os itens irem para a vitrine assim que a normalizacao concluir.
SOURCES = [
    {
        "name": "Mega Leilões", "slug": "megaleiloes", "parser_type": "megaleiloes",
        "base_url": "https://www.megaleiloes.com.br", "scrape_frequency": 240,
        "config": {"pages": ["/veiculos"], "max_pages": 10, "fetch_details": True, "max_details_per_run": 60},
    },
    {
        "name": "Freitas Leiloeiro", "slug": "freitas", "parser_type": "freitas",
        "base_url": "https://www.freitasleiloeiro.com.br", "scrape_frequency": 240,
        "config": {"categoria": 1, "verify_ssl": False, "top_rows": 12, "max_pages": 30, "fetch_details": True, "max_details_per_run": 60},
    },
    {
        "name": "Leilo", "slug": "leilo", "parser_type": "leilo",
        "base_url": "https://www.leilo.com.br", "scrape_frequency": 240,
        "config": {"path": "/leilao", "max_pages": 10, "fetch_details": False},
    },
]


async def seed_admin_user(db: AsyncSession):
    cfg = get_settings()
    existing = await db.scalar(select(User).where(User.email == cfg.ADMIN_EMAIL))
    if existing:
        return
    db.add(User(email=cfg.ADMIN_EMAIL, hashed_password=hash_password(cfg.ADMIN_PASSWORD), name="Administrador", role="admin"))
    await db.commit()
    logger.info("Admin user created: %s", cfg.ADMIN_EMAIL)


async def seed_categories(db: AsyncSession):
    by_slug: dict[str, Category] = {}
    for spec in CATEGORIES:
        cat = await db.scalar(select(Category).where(Category.slug == spec["slug"]))
        parent = by_slug.get(spec["parent"]) if spec["parent"] else None
        if not cat:
            path = f"{parent.path}/{spec['slug']}" if parent else spec["slug"]
            cat = Category(
                name=spec["name"], slug=spec["slug"], parent_id=parent.id if parent else None,
                path=path, keywords=spec.get("keywords") or [], llm_hint=spec.get("llm_hint"),
                sort_order=len(by_slug),
            )
            db.add(cat)
            await db.flush()
        by_slug[spec["slug"]] = cat

        existing_keys = {f.key for f in (await db.execute(
            select(CategoryField).where(CategoryField.category_id == cat.id)
        )).scalars().all()}
        for order, (key, label, ftype, unit, required, options, in_card, filterable, desc) in enumerate(spec["fields"]):
            if key in existing_keys:
                continue
            db.add(CategoryField(
                category_id=cat.id, key=key, label=label, field_type=ftype, unit=unit,
                required=required, options=options, show_in_card=in_card, filterable=filterable,
                sort_order=order, description=desc,
            ))
    await db.commit()
    logger.info("Categories seeded (%d)", len(by_slug))


async def seed_sources(db: AsyncSession):
    created = 0
    for spec in SOURCES:
        existing = await db.scalar(select(Source).where(Source.slug == spec["slug"]))
        if existing:
            continue
        db.add(Source(kind="auction", is_active=True, dispatch_enabled=True, scraping_allowed=True, **spec))
        created += 1
    await db.commit()
    if created:
        logger.info("Sources seeded (%d)", created)
