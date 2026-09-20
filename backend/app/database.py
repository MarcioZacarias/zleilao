from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=1800,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# Indices que o create_all nao expressa bem (GIN em JSONB, busca textual).
# Idempotentes: rodam a cada boot sem efeito se ja existirem.
EXTRA_DDL = [
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    "CREATE EXTENSION IF NOT EXISTS unaccent",
    "CREATE INDEX IF NOT EXISTS ix_items_attributes_gin ON items USING GIN (attributes jsonb_path_ops)",
    "CREATE INDEX IF NOT EXISTS ix_items_title_trgm ON items USING GIN (title gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS ix_items_search_tsv ON items USING GIN (search_tsv)",
    # ── F2: colunas novas em `users` ───────────────────────────────────
    # `create_all` cria TABELA nova, mas nunca altera tabela existente. Toda
    # coluna acrescentada depois do primeiro deploy precisa de um ALTER
    # idempotente aqui, senão o boot quebra num banco que já rodou.
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(20)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS whatsapp_opt_in BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_opt_in BOOLEAN NOT NULL DEFAULT TRUE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMP",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS quiet_start VARCHAR(5)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS quiet_end VARCHAR(5)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP",
    # O admin semeado na F1 nasceu com role='admin'; contas novas nascem
    # 'user'. O default da coluna precisa acompanhar o modelo.
    "ALTER TABLE users ALTER COLUMN role SET DEFAULT 'user'",
]


async def init_db():
    async with engine.begin() as conn:
        # Import tardio para registrar todos os modelos no metadata.
        from app import models  # noqa: F401

        await conn.run_sync(Base.metadata.create_all)
        for ddl in EXTRA_DDL:
            try:
                await conn.execute(text(ddl))
            except Exception as exc:  # pragma: no cover - depende do servidor
                # Extensoes podem exigir superuser em bancos gerenciados; a
                # aplicacao funciona sem elas (busca cai no ILIKE).
                import logging

                logging.getLogger("zleilao.db").warning("DDL extra falhou (%s): %s", ddl[:60], exc)
