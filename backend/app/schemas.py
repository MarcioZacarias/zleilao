from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Source ─────────────────────────────────────────────────────────────────

class SourceBase(BaseModel):
    name: str
    slug: str
    kind: str = "auction"
    parser_type: str
    base_url: Optional[str] = None
    config: Optional[dict] = None
    is_active: bool = True
    dispatch_enabled: bool = True
    scraping_allowed: bool = True
    scrape_frequency: int = 240
    priority_weight: int = 1


class SourceCreate(SourceBase):
    pass


class SourceUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    kind: Optional[str] = None
    parser_type: Optional[str] = None
    base_url: Optional[str] = None
    config: Optional[dict] = None
    is_active: Optional[bool] = None
    dispatch_enabled: Optional[bool] = None
    scraping_allowed: Optional[bool] = None
    scrape_frequency: Optional[int] = None
    priority_weight: Optional[int] = None


class SourceOut(SourceBase):
    id: int
    robots_status: Optional[str] = None
    robots_checked_at: Optional[datetime] = None
    last_run_at: Optional[datetime] = None
    last_run_status: Optional[str] = None
    last_items_count: int = 0
    avg_items_count: Optional[float] = None
    health_status: str = "unknown"
    suspended_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    items_total: int = 0
    items_published: int = 0
    open_incidents: int = 0
    model_config = ConfigDict(from_attributes=True)


# ── Category / fields ──────────────────────────────────────────────────────

class CategoryFieldBase(BaseModel):
    key: str
    label: str
    field_type: str = "string"
    unit: Optional[str] = None
    required: bool = False
    options: Optional[list[str]] = None
    show_in_card: bool = False
    filterable: bool = False
    sort_order: int = 0
    description: Optional[str] = None


class CategoryFieldCreate(CategoryFieldBase):
    pass


class CategoryFieldUpdate(BaseModel):
    key: Optional[str] = None
    label: Optional[str] = None
    field_type: Optional[str] = None
    unit: Optional[str] = None
    required: Optional[bool] = None
    options: Optional[list[str]] = None
    show_in_card: Optional[bool] = None
    filterable: Optional[bool] = None
    sort_order: Optional[int] = None
    description: Optional[str] = None


class CategoryFieldOut(CategoryFieldBase):
    id: int
    category_id: int
    inherited_from: Optional[str] = None  # slug da categoria-mae quando herdado
    model_config = ConfigDict(from_attributes=True)


class CategoryBase(BaseModel):
    name: str
    slug: str
    parent_id: Optional[int] = None
    is_active: bool = True
    sort_order: int = 0
    keywords: Optional[list[str]] = None
    llm_hint: Optional[str] = None


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    parent_id: Optional[int] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None
    keywords: Optional[list[str]] = None
    llm_hint: Optional[str] = None


class CategoryOut(CategoryBase):
    id: int
    path: str
    created_at: datetime
    items_count: int = 0
    fields: list[CategoryFieldOut] = []
    model_config = ConfigDict(from_attributes=True)


class CategoryTreeOut(CategoryOut):
    children: list["CategoryTreeOut"] = []


# ── Auction ────────────────────────────────────────────────────────────────

class AuctionSessionOut(BaseModel):
    id: int
    kind: str
    sequence: int
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    min_bid: Optional[Decimal] = None
    model_config = ConfigDict(from_attributes=True)


class AuctionOut(BaseModel):
    id: int
    source_id: int
    source_name: Optional[str] = None
    external_id: str
    title: Optional[str] = None
    auctioneer_name: Optional[str] = None
    auctioneer_registration: Optional[str] = None
    committer_name: Optional[str] = None
    modality: Optional[str] = None
    auction_type: Optional[str] = None
    official_url: Optional[str] = None
    status: str
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    sessions: list[AuctionSessionOut] = []
    items_count: int = 0
    model_config = ConfigDict(from_attributes=True)


# ── Item ───────────────────────────────────────────────────────────────────

class ItemCardOut(BaseModel):
    """Card da vitrine / listagens."""

    id: int
    item_type: str
    title: str
    lot_number: Optional[str] = None
    price: Optional[Decimal] = None
    price_kind: Optional[str] = None
    price_second: Optional[Decimal] = None
    image_url: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    year_model: Optional[int] = None
    km: Optional[int] = None
    condition: Optional[str] = None
    status: str
    next_session_at: Optional[datetime] = None
    last_seen_at: datetime
    source_id: int
    source_name: Optional[str] = None
    source_slug: Optional[str] = None
    category_id: Optional[int] = None
    category_slug: Optional[str] = None
    category_name: Optional[str] = None
    auction_id: Optional[int] = None
    auction_type: Optional[str] = None
    card_fields: dict[str, Any] = {}  # campos show_in_card da categoria
    possible_duplicate: bool = False
    opportunity_score: Optional[int] = None      # RN-010; ausente = sem referência confiável
    opportunity_discount: Optional[float] = None
    distance_km: Optional[float] = None          # só na busca por raio, a partir da cidade do lote
    model_config = ConfigDict(from_attributes=True)


class ItemPriceHistoryOut(BaseModel):
    price: Decimal
    price_kind: Optional[str] = None
    observed_at: datetime
    model_config = ConfigDict(from_attributes=True)


class DuplicateRefOut(BaseModel):
    item_id: int
    title: str
    source_name: Optional[str] = None
    official_url: str
    similarity: float
    status: str


class OpportunityOut(BaseModel):
    """RN-010 — só existe quando dá para comparar com honestidade."""
    score: int
    discount_pct: float
    reference_value: Decimal
    total_cost: Decimal
    reasons: dict[str, Any] = {}
    reference_label: Optional[str] = None   # ex.: "FIPE set/2026 — Uno Mille Way 1.0"
    computed_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ItemDetailOut(ItemCardOut):
    description: Optional[str] = None
    images: list[str] = []
    attributes: dict[str, Any] = {}
    field_defs: list[CategoryFieldOut] = []
    official_url: str
    location_text: Optional[str] = None
    auction: Optional[AuctionOut] = None
    price_history: list[ItemPriceHistoryOut] = []
    duplicates: list[DuplicateRefOut] = []
    first_seen_at: datetime
    disclaimer: Optional[str] = None
    extraction_status: Optional[str] = None
    extraction_version: Optional[str] = None
    opportunity: Optional[OpportunityOut] = None


class ItemAdminOut(ItemCardOut):
    external_id: str
    official_url: str
    extraction_status: str
    extraction_attempts: int
    extraction_version: Optional[str] = None
    extraction_error: Optional[str] = None
    extraction_model: Optional[str] = None
    status_hint: Optional[str] = None
    misses: int
    first_seen_at: datetime
    created_at: datetime
    updated_at: datetime
    description: Optional[str] = None
    attributes: dict[str, Any] = {}
    images: list[str] = []


class ItemUpdate(BaseModel):
    title: Optional[str] = None
    category_id: Optional[int] = None
    attributes: Optional[dict[str, Any]] = None
    status: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    year_model: Optional[int] = None
    year_fab: Optional[int] = None
    km: Optional[int] = None
    condition: Optional[str] = None
    description: Optional[str] = None


class FacetValue(BaseModel):
    value: str
    label: Optional[str] = None
    count: int


class PageMeta(BaseModel):
    page: int
    page_size: int
    total: int
    pages: int


class ItemPage(BaseModel):
    items: list[ItemCardOut]
    meta: PageMeta
    facets: dict[str, list[FacetValue]] = {}


class ItemAdminPage(BaseModel):
    items: list[ItemAdminOut]
    meta: PageMeta


# ── Operacao ───────────────────────────────────────────────────────────────

class IncidentOut(BaseModel):
    id: int
    source_id: int
    source_name: Optional[str] = None
    kind: str
    message: str
    expected: Optional[float] = None
    observed: Optional[float] = None
    status: str
    created_at: datetime
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class IncidentUpdate(BaseModel):
    status: str  # acknowledged | resolved
    reactivate_source: bool = True


class JobExecutionOut(BaseModel):
    id: int
    job_type: str
    source_id: Optional[int] = None
    source_name: Optional[str] = None
    status: str
    items_processed: int
    details: Optional[dict] = None
    error: Optional[str] = None
    started_at: datetime
    finished_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class DuplicateOut(BaseModel):
    id: int
    canonical: ItemCardOut
    duplicate: ItemCardOut
    similarity: float
    reasons: Optional[dict] = None
    status: str
    created_at: datetime


class DuplicateUpdate(BaseModel):
    status: str  # confirmed | rejected


class SourceTestOut(BaseModel):
    ok: bool
    items_found: int
    sample: list[dict] = []
    error: Optional[str] = None
    duration_ms: int = 0


class SettingsUpdateRequest(BaseModel):
    settings: dict[str, str] = Field(default_factory=dict)
