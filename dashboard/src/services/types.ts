// Contrato do backend — ver docs/API.md. Datas em ISO 8601 sem timezone
// (horário de Brasília); valores monetários como string decimal em BRL.

export type ItemStatus =
  | "collected"
  | "review"
  | "published"
  | "auction_soon"
  | "closed"
  | "withdrawn"
  | "possibly_withdrawn";

export type ExtractionStatus = "pending" | "done" | "failed" | "review" | "skipped";
export type PriceKind = "lance_inicial" | "lance_atual" | "avaliacao" | "preco_pedido";
export type Condition =
  | "normal"
  | "sinistro_recuperavel"
  | "sinistro_media_monta"
  | "sinistro_grande_monta"
  | "sucata"
  | "nao_informado";
export type SessionKind = "1a_praca" | "2a_praca" | "unica" | "repasse" | "condicional";
export type AuctionType = "judicial" | "extrajudicial";
export type Modality = "online" | "presencial" | "hibrido";
export type HealthStatus = "ok" | "suspended" | "unknown";
export type IncidentKind =
  | "zero_items"
  | "abnormal_variation"
  | "parser_error"
  | "http_error"
  | "robots_disallowed"
  | "scraping_not_allowed";
export type IncidentStatus = "open" | "acknowledged" | "resolved";
export type DuplicateStatus = "suspected" | "confirmed" | "rejected";
export type FieldType = "string" | "int" | "decimal" | "bool" | "enum" | "date";
export type JobType = "scrape" | "normalize" | "lifecycle" | "dedup" | "cleanup";
export type JobRunType = "scrape_tick" | "normalize" | "lifecycle" | "dedup" | "cleanup";
export type JobStatus = "running" | "success" | "failed" | "skipped";
export type SortOption = "relevance" | "price_asc" | "price_desc" | "session_asc" | "newest";
export type AdminSortOption = "updated_desc" | "first_seen_desc" | "session_asc" | "price_desc";

export interface ItemCard {
  id: number;
  item_type: "lot" | "listing";
  title: string;
  lot_number: string | null;
  price: string | null;
  price_kind: string | null;
  price_second: string | null;
  image_url: string | null;
  city: string | null;
  state: string | null;
  brand: string | null;
  model: string | null;
  year_model: number | null;
  km: number | null;
  condition: string | null;
  status: string;
  next_session_at: string | null;
  last_seen_at: string;
  source_id: number;
  source_name: string | null;
  source_slug: string | null;
  category_id: number | null;
  category_slug: string | null;
  category_name: string | null;
  auction_id: number | null;
  auction_type: string | null;
  card_fields: Record<string, unknown>;
  possible_duplicate: boolean;
}

export interface CategoryField {
  id: number;
  category_id: number;
  key: string;
  label: string;
  field_type: string;
  unit: string | null;
  required: boolean;
  options: string[] | null;
  show_in_card: boolean;
  filterable: boolean;
  sort_order: number;
  description: string | null;
  inherited_from: string | null;
}

export type CategoryFieldInput = Omit<CategoryField, "id" | "category_id" | "inherited_from">;

export interface AuctionSession {
  id: number;
  kind: string;
  sequence: number;
  starts_at: string | null;
  ends_at: string | null;
  min_bid: string | null;
}

export interface Auction {
  id: number;
  source_id: number;
  source_name: string | null;
  external_id: string;
  title: string | null;
  auctioneer_name: string | null;
  auctioneer_registration: string | null;
  committer_name: string | null;
  modality: string | null;
  auction_type: string | null;
  official_url: string | null;
  status: string;
  starts_at: string | null;
  ends_at: string | null;
  sessions: AuctionSession[];
  items_count: number;
}

export interface PriceHistoryEntry {
  price: string;
  price_kind: string | null;
  observed_at: string;
}

export interface DuplicateRef {
  item_id: number;
  title: string;
  source_name: string | null;
  official_url: string;
  similarity: number;
  status: string;
}

export interface ItemDetail extends ItemCard {
  description: string | null;
  images: string[];
  attributes: Record<string, unknown>;
  field_defs: CategoryField[];
  official_url: string;
  location_text: string | null;
  auction: Auction | null;
  price_history: PriceHistoryEntry[];
  duplicates: DuplicateRef[];
  first_seen_at: string;
  disclaimer: string | null;
  extraction_status: string | null;
  extraction_version: string | null;
}

export interface FacetValue {
  value: string;
  label: string | null;
  count: number;
}

export interface PageMeta {
  page: number;
  page_size: number;
  total: number;
  pages: number;
}

export type FacetKey = "states" | "sources" | "categories" | "brands" | "conditions" | "auction_types";

export interface ItemPage {
  items: ItemCard[];
  meta: PageMeta;
  facets: Partial<Record<FacetKey, FacetValue[]>>;
}

export interface Category {
  id: number;
  name: string;
  slug: string;
  parent_id: number | null;
  is_active: boolean;
  sort_order: number;
  keywords: string[] | null;
  llm_hint: string | null;
  path: string;
  created_at: string;
  items_count: number;
  fields: CategoryField[];
  children: Category[];
}

export interface CategoryInput {
  name: string;
  slug: string;
  parent_id: number | null;
  is_active: boolean;
  sort_order: number;
  keywords: string[];
  llm_hint: string | null;
}

export interface Source {
  id: number;
  name: string;
  slug: string;
  kind: "auction" | "marketplace";
  parser_type: string;
  base_url: string | null;
  config: Record<string, unknown> | null;
  is_active: boolean;
  dispatch_enabled: boolean;
  scraping_allowed: boolean;
  scrape_frequency: number;
  priority_weight: number;
  robots_status: string | null;
  robots_checked_at: string | null;
  last_run_at: string | null;
  last_run_status: string | null;
  last_items_count: number;
  avg_items_count: number | null;
  health_status: string;
  suspended_reason: string | null;
  created_at: string;
  updated_at: string;
  items_total: number;
  items_published: number;
  open_incidents: number;
}

export interface SourceInput {
  name: string;
  slug: string;
  kind: "auction" | "marketplace";
  parser_type: string;
  base_url: string | null;
  config: Record<string, unknown> | null;
  is_active: boolean;
  dispatch_enabled: boolean;
  scraping_allowed: boolean;
  scrape_frequency: number;
  priority_weight: number;
}

export interface ParserInfo {
  key: string;
  name: string;
  default_config: Record<string, unknown>;
}

export interface SourceTestResult {
  ok: boolean;
  items_found: number;
  sample: Record<string, unknown>[];
  error: string | null;
  duration_ms: number;
}

export interface ItemAdmin extends ItemCard {
  external_id: string;
  official_url: string;
  extraction_status: string;
  extraction_attempts: number;
  extraction_version: string | null;
  extraction_error: string | null;
  extraction_model: string | null;
  status_hint: string | null;
  misses: number;
  first_seen_at: string;
  created_at: string;
  updated_at: string;
  description: string | null;
  attributes: Record<string, unknown>;
  images: string[];
}

export interface ItemAdminPage {
  items: ItemAdmin[];
  meta: PageMeta;
}

export interface ItemUpdate {
  title?: string;
  category_id?: number | null;
  attributes?: Record<string, unknown>;
  status?: string;
  brand?: string | null;
  model?: string | null;
  year_model?: number | null;
  year_fab?: number | null;
  km?: number | null;
  condition?: string | null;
  description?: string | null;
}

export interface ItemsSummary {
  by_status: Record<string, number>;
  by_extraction: Record<string, number>;
}

export interface Incident {
  id: number;
  source_id: number;
  source_name: string | null;
  kind: string;
  message: string;
  expected: number | null;
  observed: number | null;
  status: string;
  created_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
}

export interface JobExecution {
  id: number;
  job_type: string;
  source_id: number | null;
  source_name: string | null;
  status: JobStatus;
  items_processed: number;
  details: Record<string, unknown> | null;
  error: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface SchedulerJob {
  id: string;
  next_run_at: string | null;
  running: boolean;
}

export interface Duplicate {
  id: number;
  canonical: ItemCard;
  duplicate: ItemCard;
  similarity: number;
  reasons: Record<string, unknown> | null;
  status: string;
  created_at: string;
}

export interface DashboardSource {
  id: number;
  name: string;
  slug: string;
  is_active: boolean;
  dispatch_enabled: boolean;
  health_status: string;
  last_run_at: string | null;
  last_run_status: string | null;
  last_items_count: number;
  avg_items_count: number | null;
  items_total: number;
  items_published: number;
  clicks_7d: number;
  ctr_7d: number | null;
}

export interface DashboardData {
  items_total: number;
  items_by_status: Record<string, number>;
  items_by_extraction: Record<string, number>;
  extraction_rate: number | null;
  items_new_24h: number;
  auctions_upcoming_7d: number;
  open_incidents: number;
  suspected_duplicates: number;
  sources: DashboardSource[];
  last_jobs: Record<JobType, JobExecution | null>;
  daily_collected: { day: string; count: number }[];
}

export interface PortalStats {
  items_published: number;
  sources_active: number;
  auctions_upcoming_7d: number;
  next_session_at: string | null;
  last_collected_at: string | null;
  by_category: { slug: string; name: string; count: number }[];
}

export interface BrandingResponse {
  logo_dark: string | null;
  logo_light: string | null;
  favicon: string | null;
  site_title: string | null;
  tagline: string | null;
  disclaimer: string | null;
}

export interface SettingItem {
  key: string;
  value: string;
  label: string;
  is_secret: boolean;
}

export interface SettingsGroup {
  label: string;
  items: SettingItem[];
}

export type SettingsResponse = Record<string, SettingsGroup>;

export interface LlmTestResult {
  ok: boolean;
  detail: string;
  model?: string;
  reply?: string;
  usage?: { input: number | null; output: number | null };
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user_name: string | null;
  user_email: string;
  role: string;
}

export interface MeResponse {
  id: number;
  email: string;
  name: string | null;
  role: string;
  is_active: boolean;
}

export interface PortalSearchParams {
  q?: string;
  category?: string;
  brand?: string;
  model?: string;
  year_min?: number;
  year_max?: number;
  price_min?: number;
  price_max?: number;
  state?: string;
  city?: string;
  source?: string;
  condition?: string;
  auction_type?: string;
  session_from?: string;
  session_to?: string;
  status?: string;
  sort?: SortOption;
  page?: number;
  page_size?: number;
  facets?: boolean;
}

export interface AdminItemsParams {
  q?: string;
  status?: string;
  extraction_status?: string;
  source_id?: number;
  category_id?: number;
  page?: number;
  page_size?: number;
  sort?: AdminSortOption;
}
