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
/** Jobs com histórico em `/dashboard.last_jobs`. Match e dispatch (Onda 2)
 *  aparecem em `/jobs` e no agendador, mas não nesse resumo. */
export type JobType = "scrape" | "normalize" | "lifecycle" | "dedup" | "cleanup";
export type JobRunType =
  | "scrape_tick"
  | "normalize"
  | "lifecycle"
  | "dedup"
  | "cleanup"
  | "match"
  | "dispatch";
export type JobStatus = "running" | "success" | "failed" | "skipped";
export type SortOption =
  | "relevance"
  | "price_asc"
  | "price_desc"
  | "session_asc"
  | "newest"
  /** maior desconto sobre a referência de mercado (RN-010) */
  | "opportunity"
  /** exige os três parâmetros de raio */
  | "distance";
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
  /** RN-010. Nulo quando não há referência confiável — nunca tratar como zero. */
  opportunity_score: number | null;
  opportunity_discount: number | null;
  /** Só vem preenchido na busca por raio. Distância entre municípios. */
  distance_km?: number | null;
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
  opportunity: Opportunity | null;
}

/**
 * Score de oportunidade (RN-010). Só existe quando dá para comparar com
 * honestidade. As `reasons` não são detalhe técnico: são o que torna o número
 * legível, e a interface é obrigada a mostrá-las junto.
 */
export interface Opportunity {
  score: number;
  discount_pct: number;
  reference_value: string;
  total_cost: string;
  reference_label: string | null;
  computed_at: string;
  reasons: {
    lance?: number;
    comissao_pct?: number;
    comissao?: number;
    despesas?: number;
    custo_total?: number;
    referencia?: number;
    referencia_ajustada?: number;
    desconto_pct?: number;
    condicao?: string;
    condicao_presumida?: boolean;
    fator_condicao?: number;
    base_calculo?: string;
    /** Ressalva de que o lance inicial é o piso do pregão. */
    nota_preco?: string;
    /** Aviso de que o estado do bem foi presumido. */
    nota_condicao?: string;
    /** Explicação do ajuste da referência para sinistro/sucata. */
    nota?: string;
    /** Custo acima da referência de mercado. */
    alerta?: string;
  };
}

/** Município para a busca por raio (`GET /portal/cities`). */
export interface CityOption {
  city: string;
  state: string;
  lat: number;
  lng: number;
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
  /** Busca por raio: os três andam juntos ou nenhum vale. */
  near_city?: string;
  near_state?: string;
  radius_km?: number | string;
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

/* ─────────────────────────────────────────────────────────────────────
   Onda 2 — contas, filtros salvos e alertas (RN-006/RN-007)
   ───────────────────────────────────────────────────────────────────── */

export type AlertReason = "new" | "price_drop" | "new_session";
export type AlertStatus = "pending" | "sent" | "failed" | "skipped";
export type AlertChannel = "email" | "whatsapp";
export type Plan = "free" | "pro";
export type PlanStatus = "active" | "canceled" | "expired";
export type UserRole = "user" | "admin";

/** Valores aceitos no `criteria` do filtro salvo (mesmas chaves da busca). */
export type CriteriaValue = string | number;
export type Criteria = Partial<Record<CriteriaKey, CriteriaValue>>;
export type CriteriaKey =
  | "q"
  | "category"
  | "brand"
  | "model"
  | "year_min"
  | "year_max"
  | "price_min"
  | "price_max"
  | "state"
  | "city"
  | "source"
  | "condition"
  | "auction_type"
  | "near_city"
  | "near_state"
  | "radius_km";

/** `GET /me` — a conta do assinante logado. */
export interface AccountMe {
  id: number;
  email: string;
  name: string | null;
  role: string;
  phone: string | null;
  email_opt_in: boolean;
  whatsapp_opt_in: boolean;
  email_verified: boolean;
  quiet_start: string | null;
  quiet_end: string | null;
  plan: Plan;
  plan_status: string;
  plan_expires_at: string | null;
  filters_used: number;
  filters_limit: number;
  whatsapp_channel_available: boolean;
  realtime_alerts: boolean;
}

export interface AccountUpdate {
  name?: string;
  phone?: string | null;
  email_opt_in?: boolean;
  whatsapp_opt_in?: boolean;
  quiet_start?: string | null;
  quiet_end?: string | null;
}

export interface SavedFilter {
  id: number;
  name: string;
  criteria: Criteria;
  channels: AlertChannel[];
  is_active: boolean;
  last_matched_at: string | null;
  matches_count: number;
  created_at: string;
  description: string;
}

export interface SavedFilterInput {
  name?: string | null;
  criteria: Criteria;
  channels: AlertChannel[];
  is_active: boolean;
}

export interface SavedFilterList {
  filters: SavedFilter[];
  limit: number;
  plan: Plan;
}

export interface FilterPreview {
  total: number;
  items: ItemCard[];
}

export interface MyAlert {
  id: number;
  reason: string;
  status: string;
  channel: string | null;
  detail: string | null;
  created_at: string;
  sent_at: string | null;
  saved_filter_id: number | null;
  item: ItemCard | null;
}

export interface AdminAlert {
  id: number;
  reason: string;
  status: string;
  channel: string | null;
  detail: string | null;
  error: string | null;
  created_at: string;
  sent_at: string | null;
  user: { id: number; email: string; name: string | null } | null;
  item: ItemCard | null;
}

export interface UserAdmin {
  id: number;
  email: string;
  name: string | null;
  role: UserRole;
  is_active: boolean;
  phone: string | null;
  email_opt_in: boolean;
  whatsapp_opt_in: boolean;
  email_verified: boolean;
  created_at: string;
  last_login_at: string | null;
  plan: Plan;
  plan_status: string;
  plan_expires_at: string | null;
  plan_note: string | null;
  filters: number;
  alerts_sent: number;
}

export interface UsersPage {
  users: UserAdmin[];
  meta: PageMeta;
}

export interface UsersSummary {
  users_total: number;
  users_verified: number;
  by_plan: Record<string, number>;
  active_filters: number;
  alerts_sent_today: number;
  alerts_pending: number;
  alerts_failed: number;
}

export interface UserAdminUpdate {
  is_active?: boolean;
  role?: UserRole;
  email_verified?: boolean;
}

export interface PlanUpdateInput {
  plan: Plan;
  /** 0 no plano pago = sem vencimento (cortesia). */
  months: number;
  note?: string | null;
}

/** `/users/{id}/filters` não devolve `description` (só a conta do dono devolve). */
export interface AdminSavedFilter {
  id: number;
  name: string;
  criteria: Criteria;
  channels: AlertChannel[];
  is_active: boolean;
  matches_count: number;
  last_matched_at: string | null;
  created_at: string;
}

export interface RegisterResponse {
  status: string;
  verification_required: boolean;
  verification_sent: boolean;
  detail: string;
}

export interface SimpleStatus {
  status: string;
  detail?: string;
}

export interface VerifyEmailResponse {
  status: string;
  email: string;
}

/** `POST /auth/reset-password` já devolve a sessão aberta. */
export interface ResetPasswordResponse extends LoginResponse {
  status: string;
}

export interface TestSendResult {
  ok: boolean;
  detail: string;
}
