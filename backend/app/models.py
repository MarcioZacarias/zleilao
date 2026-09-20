"""Modelo de dados do ZConnect Leilao (F1 — MVP Leilao).

Decisoes que diferem da EF v1.1 e o motivo (ver docs/DECISOES.md):

- `auction_sessions` em vez de "1a/2a praca" fixas no pregao: leilao de
  seguradora/financeira tem sessao unica, repasse e lance condicional.
- `item_price_history`: sem historico nao ha' como detectar "queda de lance"
  (RN-006) nem alimentar o comparador (F3).
- `items.plate_hash` (HMAC) em vez de placa parcial: permite deduplicar
  (RN-004) sem guardar a placa em claro (RN-009).
- `items.condition` promovido a coluna: e' o que impede o comparador (F3) de
  chamar um sinistrado de "oportunidade".
- `items.extraction_version`: permite reextrair quando prompt/schema mudam.
- `raw_items` grava payload SO quando o hash muda, com retencao configuravel.
"""
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import relationship

from app.database import Base


from app.timeutil import now_brt


def utcnow() -> datetime:
    """Nome mantido por compatibilidade: devolve agora em Brasilia (naive)."""
    return now_brt()


# ── Fontes ─────────────────────────────────────────────────────────────────

class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    slug = Column(String(80), unique=True, nullable=False)
    # auction | marketplace (marketplace so' entra na F2/F3)
    kind = Column(String(20), nullable=False, default="auction")
    # Chave do registro em scrapers/__init__.py (megaleiloes, freitas, leilo, ...)
    parser_type = Column(String(50), nullable=False)
    base_url = Column(String(500), nullable=True)
    config = Column(JSONB, nullable=True, default=dict)

    # Dois interruptores distintos, como no Promo:
    #   is_active        -> a fonte e' COLETADA
    #   dispatch_enabled -> os itens dela sao PUBLICADOS na vitrine
    is_active = Column(Boolean, default=True, nullable=False)
    dispatch_enabled = Column(Boolean, default=True, nullable=False)

    # RN-009: avaliado no cadastro. False bloqueia a coleta e gera incidente.
    scraping_allowed = Column(Boolean, default=True, nullable=False)
    robots_checked_at = Column(DateTime, nullable=True)
    robots_status = Column(String(20), nullable=True)  # allowed | disallowed | unknown

    scrape_frequency = Column(Integer, default=240, nullable=False)  # minutos
    priority_weight = Column(Integer, default=1, nullable=False)

    # Saude (RN-008)
    last_run_at = Column(DateTime, nullable=True)
    last_run_status = Column(String(20), nullable=True)  # success | failed | suspended | skipped
    last_items_count = Column(Integer, default=0, nullable=False)
    avg_items_count = Column(Float, nullable=True)  # media movel das ultimas coletas boas
    health_status = Column(String(20), default="unknown", nullable=False)  # ok | suspended | unknown
    suspended_reason = Column(Text, nullable=True)

    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    items = relationship("Item", back_populates="source")
    auctions = relationship("Auction", back_populates="source")
    incidents = relationship("ScrapeIncident", back_populates="source")


# ── Categorias e campos dinamicos (RN-002) ────────────────────────────────

class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    parent_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    # Caminho materializado: "veiculos/carros". Facilita filtro por subarvore.
    path = Column(String(300), nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    # Palavras-chave para classificacao deterministica do titulo (JSON array).
    keywords = Column(JSONB, nullable=True, default=list)
    # Instrucao extra para o LLM na extracao desta categoria.
    llm_hint = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    parent = relationship("Category", remote_side=[id], backref="children")
    fields = relationship(
        "CategoryField", back_populates="category", order_by="CategoryField.sort_order",
        cascade="all, delete-orphan",
    )
    items = relationship("Item", back_populates="category")


class CategoryField(Base):
    __tablename__ = "category_fields"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    key = Column(String(60), nullable=False)  # chave em items.attributes
    label = Column(String(100), nullable=False)
    # string | int | decimal | bool | enum | date
    field_type = Column(String(20), nullable=False, default="string")
    unit = Column(String(20), nullable=True)
    required = Column(Boolean, default=False, nullable=False)
    options = Column(JSONB, nullable=True)  # valores validos quando enum
    show_in_card = Column(Boolean, default=False, nullable=False)
    filterable = Column(Boolean, default=False, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    description = Column(Text, nullable=True)  # dica para o LLM

    category = relationship("Category", back_populates="fields")

    __table_args__ = (UniqueConstraint("category_id", "key", name="uq_category_field_key"),)


# ── Pregoes ────────────────────────────────────────────────────────────────

class Auction(Base):
    __tablename__ = "auctions"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False)
    external_id = Column(String(200), nullable=False)
    title = Column(Text, nullable=True)
    auctioneer_name = Column(String(200), nullable=True)
    auctioneer_registration = Column(String(200), nullable=True)  # ex.: JUCESP 844
    committer_name = Column(String(200), nullable=True)  # comitente (banco, seguradora, vara)
    modality = Column(String(20), nullable=True)  # online | presencial | hibrido
    auction_type = Column(String(20), nullable=True)  # judicial | extrajudicial
    official_url = Column(Text, nullable=True)
    status = Column(String(20), default="unknown", nullable=False)  # scheduled | open | closed | unknown
    starts_at = Column(DateTime, nullable=True)
    ends_at = Column(DateTime, nullable=True)
    raw = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    source = relationship("Source", back_populates="auctions")
    sessions = relationship(
        "AuctionSession", back_populates="auction", order_by="AuctionSession.sequence",
        cascade="all, delete-orphan",
    )
    items = relationship("Item", back_populates="auction")

    __table_args__ = (UniqueConstraint("source_id", "external_id", name="uq_auction_source_external"),)


class AuctionSession(Base):
    """Uma sessao do pregao: 1a praca, 2a praca, sessao unica, repasse..."""

    __tablename__ = "auction_sessions"

    id = Column(Integer, primary_key=True, index=True)
    auction_id = Column(Integer, ForeignKey("auctions.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String(20), nullable=False)  # 1a_praca | 2a_praca | unica | repasse | condicional
    sequence = Column(Integer, default=1, nullable=False)
    starts_at = Column(DateTime, nullable=True)
    ends_at = Column(DateTime, nullable=True)
    min_bid = Column(Numeric(14, 2), nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    auction = relationship("Auction", back_populates="sessions")

    __table_args__ = (Index("ix_auction_sessions_start", "starts_at"),)


# ── Itens (lote | anuncio) ─────────────────────────────────────────────────

ITEM_STATUSES = (
    "collected",           # coletado, ainda nao publicado
    "review",              # RN-003: falhou 2x na extracao -> fila manual
    "published",           # na vitrine
    "auction_soon",        # RN-005: pregao em D-2
    "closed",              # encerrado
    "withdrawn",           # retirado pela fonte
    "possibly_withdrawn",  # RN-005: nao reencontrado em N coletas
)

EXTRACTION_STATUSES = ("pending", "done", "failed", "review", "skipped")


class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    item_type = Column(String(10), nullable=False, default="lot")  # lot | listing
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False)
    external_id = Column(String(200), nullable=False)
    auction_id = Column(Integer, ForeignKey("auctions.id"), nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)

    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)  # ja' mascarada (RN-009)
    lot_number = Column(String(50), nullable=True)

    # Preco: lance inicial / lance atual / avaliacao (lote) ou preco pedido (anuncio)
    price = Column(Numeric(14, 2), nullable=True)
    price_kind = Column(String(20), nullable=True)  # lance_inicial | lance_atual | avaliacao | preco_pedido
    price_second = Column(Numeric(14, 2), nullable=True)  # valor da 2a praca, quando houver
    currency = Column(String(3), default="BRL", nullable=False)

    # Localizacao
    city = Column(String(120), nullable=True)
    state = Column(String(2), nullable=True)
    location_text = Column(Text, nullable=True)
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)

    official_url = Column(Text, nullable=False)  # RN-001
    image_url = Column(Text, nullable=True)
    images = Column(JSONB, nullable=True, default=list)

    # Campos dinamicos da categoria (RN-002) + colunas promovidas para filtro
    attributes = Column(JSONB, nullable=True, default=dict)
    brand = Column(String(60), nullable=True)
    model = Column(String(120), nullable=True)
    year_model = Column(Integer, nullable=True)
    year_fab = Column(Integer, nullable=True)
    km = Column(Integer, nullable=True)
    # normal | sinistro_recuperavel | sinistro_media_monta | sucata | sem_documento | desconhecido
    condition = Column(String(30), nullable=True)
    # HMAC da placa normalizada — deduplicacao sem placa em claro (RN-004 x RN-009)
    plate_hash = Column(String(64), nullable=True, index=True)

    status = Column(String(20), default="collected", nullable=False)
    status_hint = Column(String(20), nullable=True)  # o que a fonte disse: open | soon | closed | sold

    # Normalizacao (RN-003)
    extraction_status = Column(String(20), default="pending", nullable=False)
    extraction_attempts = Column(Integer, default=0, nullable=False)
    extraction_version = Column(String(40), nullable=True)
    extraction_error = Column(Text, nullable=True)
    extraction_model = Column(String(60), nullable=True)

    # Ciclo de vida (RN-005)
    content_hash = Column(String(64), nullable=True)
    first_seen_at = Column(DateTime, default=utcnow, nullable=False)
    last_seen_at = Column(DateTime, default=utcnow, nullable=False)
    misses = Column(Integer, default=0, nullable=False)
    # Denormalizado: inicio da proxima sessao (ordenacao/contagem regressiva)
    next_session_at = Column(DateTime, nullable=True)
    published_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)

    search_tsv = Column(TSVECTOR, nullable=True)

    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    source = relationship("Source", back_populates="items")
    auction = relationship("Auction", back_populates="items")
    category = relationship("Category", back_populates="items")
    price_history = relationship(
        "ItemPriceHistory", back_populates="item", order_by="ItemPriceHistory.observed_at.desc()",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_item_source_external"),
        Index("ix_items_status", "status"),
        Index("ix_items_extraction_status", "extraction_status"),
        Index("ix_items_category", "category_id"),
        Index("ix_items_brand_model", "brand", "model"),
        Index("ix_items_state", "state"),
        Index("ix_items_price", "price"),
        Index("ix_items_next_session", "next_session_at"),
        Index("ix_items_year", "year_model"),
    )


class ItemPriceHistory(Base):
    __tablename__ = "item_price_history"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    price = Column(Numeric(14, 2), nullable=False)
    price_kind = Column(String(20), nullable=True)
    observed_at = Column(DateTime, default=utcnow, nullable=False)

    item = relationship("Item", back_populates="price_history")

    __table_args__ = (Index("ix_item_price_history_item_date", "item_id", "observed_at"),)


class RawItem(Base):
    """Payload bruto (HTML/JSON) por item. Gravado so' quando o hash muda."""

    __tablename__ = "raw_items"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False)
    external_id = Column(String(200), nullable=False)
    content_hash = Column(String(64), nullable=False)
    payload = Column(Text, nullable=False)
    fetched_at = Column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_raw_items_key", "source_id", "external_id", "fetched_at"),
        Index("ix_raw_items_fetched", "fetched_at"),
    )


class ExtractionCache(Base):
    """Resultado da extracao por hash do conteudo — evita pagar LLM duas vezes."""

    __tablename__ = "extraction_cache"

    id = Column(Integer, primary_key=True, index=True)
    content_hash = Column(String(64), nullable=False)
    category_id = Column(Integer, nullable=True)
    extraction_version = Column(String(40), nullable=False)
    result = Column(JSONB, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("content_hash", "category_id", "extraction_version", name="uq_extraction_cache"),
    )


class ItemDuplicate(Base):
    """RN-004: vinculo conservador. Nunca funde automaticamente."""

    __tablename__ = "item_duplicates"

    id = Column(Integer, primary_key=True, index=True)
    canonical_item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    duplicate_item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    similarity = Column(Float, nullable=False)
    reasons = Column(JSONB, nullable=True)
    status = Column(String(20), default="suspected", nullable=False)  # suspected | confirmed | rejected
    created_at = Column(DateTime, default=utcnow, nullable=False)
    reviewed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("canonical_item_id", "duplicate_item_id", name="uq_item_duplicate_pair"),
        Index("ix_item_duplicates_status", "status"),
    )


# ── Operacao ───────────────────────────────────────────────────────────────

class ScrapeIncident(Base):
    """RN-008: parser com 0 itens ou variacao anormal suspende a fonte."""

    __tablename__ = "scrape_incidents"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False)
    # zero_items | abnormal_variation | parser_error | http_error | robots_disallowed | scraping_not_allowed
    kind = Column(String(40), nullable=False)
    message = Column(Text, nullable=False)
    expected = Column(Float, nullable=True)
    observed = Column(Float, nullable=True)
    status = Column(String(20), default="open", nullable=False)  # open | acknowledged | resolved
    created_at = Column(DateTime, default=utcnow, nullable=False)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(String(200), nullable=True)

    source = relationship("Source", back_populates="incidents")

    __table_args__ = (Index("ix_scrape_incidents_status", "status"),)


class JobExecution(Base):
    __tablename__ = "job_executions"

    id = Column(Integer, primary_key=True, index=True)
    job_type = Column(String(50), nullable=False)  # scrape | normalize | lifecycle | dedup | cleanup
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=True)
    status = Column(String(20), nullable=False)  # running | success | failed | skipped
    items_processed = Column(Integer, default=0, nullable=False)
    details = Column(JSONB, nullable=True)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, default=utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)

    __table_args__ = (Index("ix_job_executions_type_started", "job_type", "started_at"),)


class ClickEvent(Base):
    """Clique 'Ver no leilao oficial' — metrica de CTR por fonte (EF 8.4)."""

    __tablename__ = "click_events"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="SET NULL"), nullable=True)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=True)
    clicked_at = Column(DateTime, default=utcnow, nullable=False)
    referer = Column(String(500), nullable=True)

    __table_args__ = (Index("ix_click_events_source_date", "source_id", "clicked_at"),)


# ── Conta, configuracao, branding ─────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(200), unique=True, nullable=False)
    hashed_password = Column(String(200), nullable=False)
    name = Column(String(100), nullable=True)
    role = Column(String(20), default="user", nullable=False)  # admin | user
    is_active = Column(Boolean, default=True, nullable=False)

    # Contato e consentimento (F2). O telefone so' e' usado se o usuario optar.
    phone = Column(String(20), nullable=True)
    whatsapp_opt_in = Column(Boolean, default=False, nullable=False)
    email_opt_in = Column(Boolean, default=True, nullable=False)
    email_verified_at = Column(DateTime, nullable=True)

    # Janela de silencio pessoal (RN-006). Vazio = usa a global das settings.
    quiet_start = Column(String(5), nullable=True)  # "22:00"
    quiet_end = Column(String(5), nullable=True)    # "08:00"

    created_at = Column(DateTime, default=utcnow, nullable=False)
    last_login_at = Column(DateTime, nullable=True)

    subscription = relationship("Subscription", back_populates="user", uselist=False, cascade="all, delete-orphan")
    saved_filters = relationship("SavedFilter", back_populates="user", cascade="all, delete-orphan")


# ── Assinatura e planos (RN-007) ──────────────────────────────────────────

PLAN_FREE = "free"
PLAN_PRO = "pro"


class Subscription(Base):
    """Plano do usuario. Na F2 a ativacao e' manual pelo admin: a estrutura
    esta' pronta para um gateway (provider/provider_ref), mas cobranca
    automatica exige credenciais que ainda nao existem."""

    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    plan = Column(String(20), default=PLAN_FREE, nullable=False)
    status = Column(String(20), default="active", nullable=False)  # active | canceled | expired
    started_at = Column(DateTime, default=utcnow, nullable=False)
    current_period_end = Column(DateTime, nullable=True)  # nulo no free
    provider = Column(String(30), nullable=True)          # manual | <gateway futuro>
    provider_ref = Column(String(120), nullable=True)
    activated_by = Column(String(200), nullable=True)     # e-mail do admin, quando manual
    note = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    user = relationship("User", back_populates="subscription")


# ── Filtros salvos e alertas (RN-006/RN-007) ──────────────────────────────

ALERT_REASONS = ("new", "price_drop", "new_session")


class SavedFilter(Base):
    """Criterios persistidos do usuario. `criteria` usa exatamente as chaves da
    busca publica (`GET /portal/items`), entao "criar alerta desta busca" e o
    matching reaproveitam o mesmo codigo de filtro."""

    __tablename__ = "saved_filters"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(120), nullable=False)
    criteria = Column(JSONB, nullable=False, default=dict)
    channels = Column(JSONB, nullable=False, default=list)  # ["email", "whatsapp"]
    is_active = Column(Boolean, default=True, nullable=False)
    #: ultima vez que o matcher avaliou este filtro — evita reavaliar o acervo inteiro
    last_checked_at = Column(DateTime, nullable=True)
    last_matched_at = Column(DateTime, nullable=True)
    matches_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    user = relationship("User", back_populates="saved_filters")

    __table_args__ = (Index("ix_saved_filters_user_active", "user_id", "is_active"),)


class Alert(Base):
    """Um casamento item x filtro. Nasce `pending` e o dispatcher envia.

    RN-006: `(user_id, item_id, reason)` e' unico — o mesmo lote nunca e'
    reenviado ao mesmo usuario pelo mesmo motivo, mesmo que case com varios
    filtros. Uma queda de preco depois e' outro motivo, logo outro alerta.
    """

    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    saved_filter_id = Column(Integer, ForeignKey("saved_filters.id", ondelete="SET NULL"), nullable=True)
    reason = Column(String(20), default="new", nullable=False)  # ALERT_REASONS
    channel = Column(String(20), nullable=True)                 # email | whatsapp (definido no envio)
    status = Column(String(20), default="pending", nullable=False)  # pending | sent | failed | skipped
    detail = Column(Text, nullable=True)   # ex.: "lance caiu de R$ 30.000 para R$ 24.000"
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    sent_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "item_id", "reason", name="uq_alert_user_item_reason"),
        Index("ix_alerts_status_created", "status", "created_at"),
        Index("ix_alerts_user_created", "user_id", "created_at"),
    )


# ── Comparador: referência de preço e score (RN-010) ──────────────────────

class PriceReference(Base):
    """Preço de mercado de um bem (marca/modelo/ano), com a origem declarada.

    `source_kind='fipe'` é a referência primária. `median_listings` fica
    reservado para quando houver anúncios de marketplace autorizados.
    """

    __tablename__ = "price_references"

    id = Column(Integer, primary_key=True, index=True)
    vehicle_type = Column(String(20), nullable=False)   # carros | motos | caminhoes
    brand = Column(String(60), nullable=False)
    model = Column(String(120), nullable=False)
    year = Column(Integer, nullable=False)
    fuel = Column(String(30), nullable=True)

    source_kind = Column(String(20), default="fipe", nullable=False)  # fipe | listings
    value = Column(Numeric(14, 2), nullable=False)
    sample_size = Column(Integer, default=1, nullable=False)   # 1 na FIPE; N em anúncios
    min_value = Column(Numeric(14, 2), nullable=True)
    max_value = Column(Numeric(14, 2), nullable=True)

    fipe_code = Column(String(20), nullable=True)
    fipe_model_label = Column(String(200), nullable=True)
    reference_month = Column(String(40), nullable=True)
    match_ratio = Column(Float, nullable=True)   # confiança do casamento de modelo

    computed_at = Column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("vehicle_type", "brand", "model", "year", "fuel", "source_kind",
                         name="uq_price_reference_key"),
        Index("ix_price_reference_lookup", "brand", "model", "year"),
    )


class ItemOpportunity(Base):
    """RN-010 — score de oportunidade de um lote contra a referência de mercado.

    Só existe quando dá para comparar com honestidade: sem referência, ou com
    condição do bem desconhecida, não há score (ver `engine/opportunity.py`).
    """

    __tablename__ = "item_opportunities"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), unique=True, nullable=False)
    price_reference_id = Column(Integer, ForeignKey("price_references.id", ondelete="SET NULL"), nullable=True)

    reference_value = Column(Numeric(14, 2), nullable=False)
    #: lance + comissão do leiloeiro + despesas conhecidas — o que o
    #: arrematante realmente desembolsa. Comparar só o lance infla o desconto.
    total_cost = Column(Numeric(14, 2), nullable=False)
    discount_pct = Column(Float, nullable=False)
    score = Column(Integer, nullable=False)      # 0-100
    reasons = Column(JSONB, nullable=True)
    computed_at = Column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (Index("ix_item_opportunity_score", "score"),)


class AuthToken(Base):
    """Token de uso unico para verificar e-mail ou redefinir senha.
    Guarda o hash, nunca o token em claro."""

    __tablename__ = "auth_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String(20), nullable=False)  # verify_email | reset_password
    token_hash = Column(String(64), unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (Index("ix_auth_tokens_user_kind", "user_id", "kind"),)


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=False, default="")
    label = Column(String(200), nullable=False)
    group = Column(String(50), nullable=False)
    is_secret = Column(Boolean, default=False, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class BrandingAsset(Base):
    __tablename__ = "branding_assets"

    key = Column(String(50), primary_key=True)  # logo_dark | logo_light | favicon
    mimetype = Column(String(80), nullable=False)
    data = Column(LargeBinary, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


# Mantem `JSON` importado para compatibilidade com scripts antigos.
__all__ = [
    "JSON", "Source", "Category", "CategoryField", "Auction", "AuctionSession", "Item",
    "ItemPriceHistory", "RawItem", "ExtractionCache", "ItemDuplicate", "ScrapeIncident",
    "JobExecution", "ClickEvent", "User", "SystemSetting", "BrandingAsset",
    "Subscription", "SavedFilter", "Alert", "AuthToken",
    "ITEM_STATUSES", "EXTRACTION_STATUSES", "ALERT_REASONS", "PLAN_FREE", "PLAN_PRO",
]
