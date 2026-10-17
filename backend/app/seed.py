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

#: Máquinas e equipamentos: o que identifica o bem é o horímetro, não a
#: quilometragem, e o estado operacional pesa mais que o ano.
MAQUINA_FIELDS = [
    ("marca", "Marca", "string", None, True, None, True, True, "Fabricante (ex.: John Deere, Caterpillar, Valtra)."),
    ("modelo", "Modelo", "string", None, False, None, True, True, "Modelo do equipamento."),
    ("ano_fabricacao", "Ano de fabricação", "int", None, False, None, True, True, "Ano, 4 digitos."),
    ("horimetro", "Horímetro", "int", "h", False, None, True, True, "Horas trabalhadas, apenas numero."),
    ("tipo_equipamento", "Tipo", "string", None, False, None, True, True, "Trator, colheitadeira, retroescavadeira, empilhadeira, gerador..."),
    ("potencia_cv", "Potência", "int", "cv", False, None, False, False, None),
    ("condicao", "Condição", "enum", None, True, ["normal", "necessita_reparo", "sucata", NI], True, True,
     "'necessita_reparo' quando o texto aponta defeito ou falta de peca; 'sucata' quando inservivel."),
    ("funcionando", "Funcionando", "bool", None, False, None, False, False, "O anuncio afirma que liga/opera?"),
    ("implementos", "Implementos", "string", None, False, None, False, False, "Acessorios inclusos (concha, lamina, plataforma...)."),
    ("observacoes", "Observações", "string", None, False, None, False, False, "Avarias e pontos relevantes, ate 300 caracteres."),
]

CATEGORIES = [
    {"name": "Veículos", "slug": "veiculos", "parent": None, "fields": VEHICLE_FIELDS, "keywords": [],
     "llm_hint": "Lote de veiculo automotor em leilao no Brasil."},
    {"name": "Carros", "slug": "carros", "parent": "veiculos", "fields": [], "keywords": ["carro", "automovel", "hatch", "sedan", "suv", "picape", "pick-up", "camionete"]},
    {"name": "Motos", "slug": "motos", "parent": "veiculos", "fields": MOTO_FIELDS, "keywords": ["moto", "motocicleta", "scooter", "ciclomotor", "cg 160", "biz", "xre", "cb 500",
                  "titan", "bros", "pcx", "nmax",
                  # marcas que so' fazem moto: a marca ja' identifica o tipo do bem
                  "ducati", "ktm", "aprilia", "mv agusta", "harley", "harley-davidson", "husqvarna",
                  "benelli", "kasinski", "traxx", "sundown", "xinling", "voltz", "royal enfield",
                  "triumph", "dafra", "shineray", "haojue", "vespa"]},
    {"name": "Caminhões", "slug": "caminhoes", "parent": "veiculos", "fields": CAMINHAO_FIELDS, "keywords": ["caminhao", "caminhão", "cavalo mecanico", "semirreboque", "semi-reboque", "carreta", "bitrem", "truck", "tector", "constellation", "atego", "accelo", "vm 270", "fh 540", "actros"]},
    {"name": "Utilitários e vans", "slug": "utilitarios", "parent": "veiculos", "fields": [], "keywords": ["van", "furgao", "furgão", "utilitario", "ducato", "sprinter", "master", "transit", "daily", "kombi", "fiorino", "partner", "kangoo"]},
    {"name": "Ônibus", "slug": "onibus", "parent": "veiculos", "fields": [], "keywords": ["onibus", "ônibus", "micro-onibus", "microonibus", "micro onibus", "rodoviario"]},
    # `marca` volta aqui com required=False sobrescrevendo Veiculos: carcaca,
    # sucata e monobloco sao lotes reais que a fonte publica sem marca, e
    # exigi-la manda o lote para a revisao de onde ele nunca sai.
    {"name": "Outros veículos", "slug": "outros-veiculos", "parent": "veiculos",
     "fields": [("marca", "Marca", "string", None, False, None, True, True,
                 "Fabricante, quando a fonte informa. Carcaca e sucata costumam nao ter.")],
     "keywords": ["reboque", "trailer", "quadriciclo", "jet ski", "barco", "lancha", "aeronave",
                  "sucata", "carcaca", "carcaça", "monobloco", "salvado", "motor ", "cavalo mecanico"]},
    {"name": "Máquinas e equipamentos", "slug": "maquinas-equipamentos", "parent": None, "fields": MAQUINA_FIELDS,
     "keywords": ["trator", "colheitadeira", "retroescavadeira", "escavadeira", "empilhadeira", "gerador",
                  "compressor", "pa carregadeira", "motoniveladora", "plaina agricola", "pulverizador",
                  "semeadeira", "plantadeira", "rolo compactador", "guindaste", "munck", "betoneira"],
     "llm_hint": "Maquina ou equipamento agricola/industrial em leilao. O horimetro faz o papel da quilometragem."},
    {"name": "Máquinas agrícolas", "slug": "maquinas-agricolas", "parent": "maquinas-equipamentos", "fields": [],
     "keywords": ["trator", "colheitadeira", "plantadeira", "semeadeira", "pulverizador", "plaina agricola",
                  "grade aradora", "implemento agricola", "subsolador", "rocadeira", "roçadeira",
                  "ensiladeira", "carreta agricola", "distribuidor de calcario", "arado"]},
    {"name": "Máquinas de construção", "slug": "maquinas-construcao", "parent": "maquinas-equipamentos", "fields": [],
     "keywords": ["retroescavadeira", "escavadeira", "pa carregadeira", "motoniveladora", "rolo compactador", "betoneira", "guindaste", "munck"]},
    {"name": "Equipamentos diversos", "slug": "equipamentos-diversos", "parent": "maquinas-equipamentos", "fields": [],
     "keywords": ["empilhadeira", "gerador", "compressor", "transformador", "torno", "prensa"]},
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
    # F4 (17/10/2026). A fonte nao pagina: cada entrada de `pages` traz a
    # categoria inteira, e `max_pages` limita quantas entradas sao visitadas.
    {
        "name": "Rogério Menezes", "slug": "rogeriomenezes", "parser_type": "rogeriomenezes",
        "base_url": "https://rogeriomenezes.com.br", "scrape_frequency": 240,
        "config": {
            "pages": ["/categorias/carros", "/categorias/motos", "/categorias/caminhoes", "/categorias/sucatas"],
            "max_pages": 10, "fetch_details": True, "max_details_per_run": 60,
        },
    },
    # Judicial do Parana. Categorias da fonte: 2 = veiculos, 3 = maquinas
    # (5 traria tudo, inclusive imoveis). O detalhe custa duas requisicoes
    # por lote (casca + JSON na sessao PHP).
    {
        "name": "Nakakogue Leilões", "slug": "nakakogue", "parser_type": "nakakogue",
        "base_url": "https://www.nakakogueleiloes.com.br", "scrape_frequency": 240,
        "config": {"categorias": [2, 3], "index_home": True, "fetch_details": True, "max_details_per_run": 60},
    },
    # Brasilia/DF; extrajudicial (bancos) e judicial em listas separadas. O
    # preco so existe no detalhe, por isso `fetch_details` e um teto alto:
    # um pregao de banco tem ~100 lotes e precisa caber numa rodada.
    {
        "name": "Parque dos Leilões", "slug": "parquedosleiloes", "parser_type": "parquedosleiloes",
        "base_url": "https://www.parquedosleiloes.com.br", "scrape_frequency": 240,
        "config": {
            "auction_lists": ["/leiloes?searchMode=normal&type_id=1", "/leiloes-judiciais?searchMode=judicial&type_id=1"],
            "include_closed": False, "max_list_pages": 5, "max_auctions": 10, "max_pages": 10,
            "fetch_details": True, "max_details_per_run": 150,
            "default_city": "Brasília", "default_state": "DF",
        },
    },
    # Entra DESATIVADA e sem permissao de coleta: o robots.txt libera tudo,
    # mas os termos de uso (pdf/termo-uso.pdf, clausula d) vedam "robos para
    # navegacao ... da plataforma". Ligar e' decisao do operador (RN-009).
    {
        "name": "Pestana Leilões", "slug": "pestana", "parser_type": "pestana",
        "base_url": "https://www.pestanaleiloes.com.br", "scrape_frequency": 240,
        "is_active": False, "scraping_allowed": False,
        "config": {"tipo_bem": 421, "max_auctions": 10, "include_private": False, "fetch_details": False, "max_details_per_run": 0},
    },
    # Campo Grande/MS (DETRAN, prefeitura, varas), no parser generico: capa
    # lista pregoes, cada pregao traz todos os lotes numa pagina. A capa so
    # da "Encerra dd/mm" sem ano; abertura e encerramento completos vem do
    # cabecalho do pregao (`page_fields`). Tipo judicial/extrajudicial sai do
    # titulo do pregao (`auction_type: auto`).
    {
        "name": "Casa de Leilões", "slug": "casadeleiloes", "parser_type": "generic_html",
        "base_url": "https://www.casadeleiloes.com.br", "scrape_frequency": 240,
        "config": {
            "auction_list": {
                "url": "/", "item_selector": "a[href^='/leilao/']:not([href$='/1'])",
                "link": {"attr": "href"}, "id_regex": "/leilao/[^/]+/(\\d+)$",
                "title": {"selector": ".box-titulo"}, "end_date": {"selector": ".box-subtitulo strong"},
                "max_auctions": 20,
            },
            "page_fields": {
                "title": {"selector": "h3"},
                "date": {"selector": ".leilao-dados", "regex": "Abertura\\s*(\\d{2}/\\d{2}/\\d{4}\\s*\\d{1,2}:\\d{2})"},
                "end_date": {"selector": ".leilao-dados", "regex": "Encerra[^:]*:\\s*(\\d{2}/\\d{2}/\\d{4}\\s*\\d{1,2}:\\d{2})"},
                "modality": {"selector": ".leilao-dados", "regex": "Modalidade\\s*([A-Za-z]+)"},
            },
            "item_selector": "a.lote-lista",
            "fields": {
                "external_id": {"attr": "href", "regex": "/(\\d+)$"},
                "title": {"selector": "blockquote"},
                "url": {"attr": "href"},
                "price": {"selector": ".lote-lista-direita span.botao-azul[style*='display: block']"},
                "image": {"selector": ".lazy", "attr": "data-src", "sub": ["p\\.(jpe?g|png)$", ".\\1"]},
                "location": {"selector": ".col-md-6 b"},
                "lot_number": {"selector": ".col-md-6", "regex": "Lote:\\s*(\\d+)"},
                "status": {"selector": ".circulo-item-grande", "map": {"em leilao": "open"}},
                "category": {
                    "selector": ".col-md-6", "regex": "^(.*?)\\s*»",
                    "map": {"veiculo": "veiculos", "motocicleta": "motos", "caminhao": "caminhoes", "sucata": "sucatas", "imovel": "imoveis"},
                },
            },
            "category_hint": "diversos", "auction_type": "auto", "default_state": "MS", "fetch_details": False,
            "detail": {"images_regex": "/envios/leilao_lote_imagem\\d+\\.jpe?g"},
        },
    },
    # Portal judicial (Serrano), ~1.000 veiculos. O robots.txt veda robos na
    # paginacao (`?pagina=`), por isso `max_pages` fica em 1 e a cobertura
    # vem de fatiar o catalogo (subcategoria x ordenacao x faixa de valor x
    # UF em `pages`) e de colher os lotes irmaos na pagina de cada leilao.
    # `max_details_per_run` conta leiloes (paginas de ~1,2 MB), nao lotes.
    {
        "name": "Leilões Judiciais", "slug": "leiloesjudiciais", "parser_type": "leiloesjudiciais",
        "base_url": "https://www.leiloesjudiciais.com.br", "scrape_frequency": 240,
        "config": {
            "pages": [
                "/veiculos/carros?ordenacao=min", "/veiculos/carros?ordenacao=max",
                "/veiculos/motos?ordenacao=min", "/veiculos/caminhoes?ordenacao=min",
                "/veiculos/onibus", "/veiculos/veiculos-pesados",
                "/maquinas-e-equipamentos/tratores-e-colheitadeiras",
            ],
            "states": [], "max_pages": 1, "fetch_details": True, "max_details_per_run": 40,
            "harvest_auction_lots": True, "segments": ["veiculos"],
        },
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
        # A spec pode desligar a fonte ao nascer (fonte com termos restritivos).
        params = {"kind": "auction", "is_active": True, "dispatch_enabled": True, "scraping_allowed": True, **spec}
        db.add(Source(**params))
        created += 1
    await db.commit()
    if created:
        logger.info("Sources seeded (%d)", created)
