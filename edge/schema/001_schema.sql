-- =====================================================================
-- ZConnect Leilão — esquema D1 (SQLite)
-- ---------------------------------------------------------------------
-- Tradução do esquema PostgreSQL. Quatro decisões valem leitura antes de
-- mexer aqui, porque mudam o significado das colunas:
--
-- 1. DINHEIRO É INTEIRO, EM CENTAVOS. SQLite não tem NUMERIC exato: todo
--    valor decimal vira float64 e 0,1 + 0,2 deixa de ser 0,3. Lance de
--    leilão e referência FIPE não admitem isso, então toda coluna de
--    dinheiro termina em `_cents` e guarda inteiro. A conversão para reais
--    acontece na borda, ao serializar.
--
-- 2. DATA E HORA SÃO TEXTO ISO 'YYYY-MM-DD HH:MM:SS', em horário de
--    Brasília, sem fuso — a mesma convenção do backend em Python
--    (`app/timeutil.now_brt`). Nesse formato a ordenação lexicográfica é a
--    ordenação cronológica, então ORDER BY e BETWEEN funcionam direto.
--
-- 3. BUSCA TEXTUAL É FTS5, não `tsvector`. O tokenizador usa
--    `remove_diacritics 2`, então "caminhao" acha "Caminhão" e "carcaca"
--    acha "CARCAÇA" sem precisar da extensão `unaccent`. Não há stemming
--    de português: "carros" não acha "carro" sozinho, e por isso o termo
--    do usuário também é casado por prefixo na consulta.
--
-- 4. JSON É TEXT. Sem JSONB e sem índice GIN; o que precisa de filtro
--    rápido já está promovido a coluna própria (marca, modelo, ano, km).
--
-- Verificado no D1: acos/radians/cos/sin/sqrt existem, então a busca por
-- raio é o mesmo Haversine em SQL do Postgres.
-- =====================================================================

PRAGMA foreign_keys = ON;

-- ── Fontes ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sources (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  name              TEXT    NOT NULL,
  slug              TEXT    NOT NULL UNIQUE,
  kind              TEXT    NOT NULL DEFAULT 'auction',   -- auction | marketplace
  parser_type       TEXT    NOT NULL,
  base_url          TEXT,
  config            TEXT,                                  -- JSON
  is_active         INTEGER NOT NULL DEFAULT 1,
  dispatch_enabled  INTEGER NOT NULL DEFAULT 1,
  scraping_allowed  INTEGER NOT NULL DEFAULT 1,
  robots_checked_at TEXT,
  robots_status     TEXT,
  scrape_frequency  INTEGER NOT NULL DEFAULT 240,          -- minutos
  priority_weight   INTEGER NOT NULL DEFAULT 10,
  last_run_at       TEXT,
  last_run_status   TEXT,
  last_items_count  INTEGER NOT NULL DEFAULT 0,
  avg_items_count   REAL,
  health_status     TEXT    NOT NULL DEFAULT 'unknown',
  suspended_reason  TEXT,
  created_at        TEXT    NOT NULL,
  updated_at        TEXT    NOT NULL
);

-- ── Categorias e campos dinâmicos (RN-002) ───────────────────────────
CREATE TABLE IF NOT EXISTS categories (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  parent_id  INTEGER REFERENCES categories(id) ON DELETE SET NULL,
  name       TEXT    NOT NULL,
  slug       TEXT    NOT NULL UNIQUE,
  path       TEXT    NOT NULL,                             -- 'veiculos/carros'
  is_active  INTEGER NOT NULL DEFAULT 1,
  sort_order INTEGER NOT NULL DEFAULT 0,
  keywords   TEXT,                                          -- JSON array
  llm_hint   TEXT,
  created_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_categories_path ON categories(path);

CREATE TABLE IF NOT EXISTS category_fields (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  category_id  INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
  key          TEXT    NOT NULL,
  label        TEXT    NOT NULL,
  field_type   TEXT    NOT NULL,                            -- string|int|decimal|bool|enum|date
  unit         TEXT,
  required     INTEGER NOT NULL DEFAULT 0,
  options      TEXT,                                        -- JSON array
  show_in_card INTEGER NOT NULL DEFAULT 0,
  filterable   INTEGER NOT NULL DEFAULT 0,
  sort_order   INTEGER NOT NULL DEFAULT 0,
  description  TEXT,
  UNIQUE (category_id, key)
);

-- ── Pregões ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS auctions (
  id                      INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id               INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  external_id             TEXT    NOT NULL,
  title                   TEXT,
  auctioneer_name         TEXT,
  auctioneer_registration TEXT,
  committer_name          TEXT,
  modality                TEXT,
  auction_type            TEXT,
  official_url            TEXT,
  status                  TEXT    NOT NULL DEFAULT 'open',
  starts_at               TEXT,
  ends_at                 TEXT,
  raw                     TEXT,                             -- JSON
  created_at              TEXT    NOT NULL,
  updated_at              TEXT    NOT NULL,
  UNIQUE (source_id, external_id)
);
CREATE INDEX IF NOT EXISTS ix_auctions_starts ON auctions(starts_at);

CREATE TABLE IF NOT EXISTS auction_sessions (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  auction_id   INTEGER NOT NULL REFERENCES auctions(id) ON DELETE CASCADE,
  kind         TEXT    NOT NULL,                            -- 1a_praca|2a_praca|unica|repasse|condicional
  sequence     INTEGER NOT NULL DEFAULT 1,
  starts_at    TEXT,
  ends_at      TEXT,
  min_bid_cents INTEGER,
  created_at   TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sessions_auction ON auction_sessions(auction_id);

-- ── Itens ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS items (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  item_type          TEXT    NOT NULL DEFAULT 'lot',        -- lot | listing
  source_id          INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  external_id        TEXT    NOT NULL,
  auction_id         INTEGER REFERENCES auctions(id) ON DELETE SET NULL,
  category_id        INTEGER REFERENCES categories(id) ON DELETE SET NULL,
  title              TEXT    NOT NULL,
  description        TEXT,
  lot_number         TEXT,
  price_cents        INTEGER,
  price_kind         TEXT,                                  -- lance_inicial|lance_atual|avaliacao|preco_pedido
  price_second_cents INTEGER,
  currency           TEXT    NOT NULL DEFAULT 'BRL',
  city               TEXT,
  state              TEXT,
  location_text      TEXT,
  lat                REAL,
  lng                REAL,
  official_url       TEXT    NOT NULL,
  image_url          TEXT,
  images             TEXT,                                  -- JSON array
  attributes         TEXT,                                  -- JSON (RN-002)
  brand              TEXT,
  model              TEXT,
  year_model         INTEGER,
  year_fab           INTEGER,
  km                 INTEGER,
  condition          TEXT,
  plate_hash         TEXT,
  status             TEXT    NOT NULL DEFAULT 'collected',
  status_hint        TEXT,
  extraction_status  TEXT    NOT NULL DEFAULT 'pending',
  extraction_attempts INTEGER NOT NULL DEFAULT 0,
  extraction_version TEXT,
  extraction_error   TEXT,
  extraction_model   TEXT,
  content_hash       TEXT,
  first_seen_at      TEXT    NOT NULL,
  last_seen_at       TEXT    NOT NULL,
  misses             INTEGER NOT NULL DEFAULT 0,
  next_session_at    TEXT,
  published_at       TEXT,
  closed_at          TEXT,
  created_at         TEXT    NOT NULL,
  updated_at         TEXT    NOT NULL,
  UNIQUE (source_id, external_id)
);
CREATE INDEX IF NOT EXISTS ix_items_status      ON items(status);
CREATE INDEX IF NOT EXISTS ix_items_source      ON items(source_id);
CREATE INDEX IF NOT EXISTS ix_items_category    ON items(category_id);
CREATE INDEX IF NOT EXISTS ix_items_brand_model ON items(brand, model);
CREATE INDEX IF NOT EXISTS ix_items_price       ON items(price_cents);
CREATE INDEX IF NOT EXISTS ix_items_session     ON items(next_session_at);
CREATE INDEX IF NOT EXISTS ix_items_extraction  ON items(extraction_status);
-- O retângulo da busca por raio usa este índice antes do Haversine.
CREATE INDEX IF NOT EXISTS ix_items_lat_lng     ON items(lat, lng) WHERE lat IS NOT NULL;

-- Busca textual. Tabela externa: o FTS guarda só o texto e aponta para o id.
CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
  title, brand, model, city,
  content='items', content_rowid='id',
  tokenize='unicode61 remove_diacritics 2'
);

-- Gatilhos mantêm o índice textual em dia sem o código precisar lembrar.
CREATE TRIGGER IF NOT EXISTS items_fts_ins AFTER INSERT ON items BEGIN
  INSERT INTO items_fts(rowid, title, brand, model, city)
  VALUES (new.id, new.title, new.brand, new.model, new.city);
END;
CREATE TRIGGER IF NOT EXISTS items_fts_del AFTER DELETE ON items BEGIN
  INSERT INTO items_fts(items_fts, rowid, title, brand, model, city)
  VALUES ('delete', old.id, old.title, old.brand, old.model, old.city);
END;
CREATE TRIGGER IF NOT EXISTS items_fts_upd AFTER UPDATE ON items BEGIN
  INSERT INTO items_fts(items_fts, rowid, title, brand, model, city)
  VALUES ('delete', old.id, old.title, old.brand, old.model, old.city);
  INSERT INTO items_fts(rowid, title, brand, model, city)
  VALUES (new.id, new.title, new.brand, new.model, new.city);
END;

CREATE TABLE IF NOT EXISTS item_price_history (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id     INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  price_cents INTEGER NOT NULL,
  price_kind  TEXT,
  observed_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_price_hist_item ON item_price_history(item_id, observed_at);

CREATE TABLE IF NOT EXISTS raw_items (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id    INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  external_id  TEXT    NOT NULL,
  content_hash TEXT    NOT NULL,
  payload      TEXT    NOT NULL,
  fetched_at   TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_raw_items_src ON raw_items(source_id, external_id);

CREATE TABLE IF NOT EXISTS item_duplicates (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  canonical_item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  duplicate_item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  similarity        REAL    NOT NULL,
  reasons           TEXT,
  status            TEXT    NOT NULL DEFAULT 'suspected',
  created_at        TEXT    NOT NULL,
  reviewed_at       TEXT,
  UNIQUE (canonical_item_id, duplicate_item_id)
);

-- ── Operação ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS scrape_incidents (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id   INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  kind        TEXT    NOT NULL,
  message     TEXT    NOT NULL,
  expected    REAL,
  observed    REAL,
  status      TEXT    NOT NULL DEFAULT 'open',
  created_at  TEXT    NOT NULL,
  resolved_at TEXT,
  resolved_by TEXT
);
CREATE INDEX IF NOT EXISTS ix_incidents_status ON scrape_incidents(status, created_at);

CREATE TABLE IF NOT EXISTS job_executions (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  job_type        TEXT    NOT NULL,
  source_id       INTEGER REFERENCES sources(id) ON DELETE SET NULL,
  status          TEXT    NOT NULL,
  items_processed INTEGER NOT NULL DEFAULT 0,
  details         TEXT,
  error           TEXT,
  started_at      TEXT    NOT NULL,
  finished_at     TEXT
);
CREATE INDEX IF NOT EXISTS ix_jobs_type_started ON job_executions(job_type, started_at);

CREATE TABLE IF NOT EXISTS click_events (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id    INTEGER REFERENCES items(id) ON DELETE SET NULL,
  source_id  INTEGER REFERENCES sources(id) ON DELETE SET NULL,
  clicked_at TEXT    NOT NULL,
  referer    TEXT
);
CREATE INDEX IF NOT EXISTS ix_clicks_source_date ON click_events(source_id, clicked_at);

CREATE TABLE IF NOT EXISTS source_daily_stats (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  day       TEXT    NOT NULL,                               -- 'YYYY-MM-DD'
  views     INTEGER NOT NULL DEFAULT 0,
  clicks    INTEGER NOT NULL DEFAULT 0,
  UNIQUE (source_id, day)
);

-- ── Contas, filtros e alertas ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  email             TEXT    NOT NULL UNIQUE,
  hashed_password   TEXT    NOT NULL,
  name              TEXT,
  role              TEXT    NOT NULL DEFAULT 'user',
  is_active         INTEGER NOT NULL DEFAULT 1,
  phone             TEXT,
  whatsapp_opt_in   INTEGER NOT NULL DEFAULT 0,
  email_opt_in      INTEGER NOT NULL DEFAULT 1,
  email_verified_at TEXT,
  quiet_start       TEXT,
  quiet_end         TEXT,
  last_login_at     TEXT,
  created_at        TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS subscriptions (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id            INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  plan               TEXT    NOT NULL DEFAULT 'free',
  status             TEXT    NOT NULL DEFAULT 'active',
  started_at         TEXT    NOT NULL,
  current_period_end TEXT,
  provider           TEXT,
  provider_ref       TEXT,
  activated_by       TEXT,
  note               TEXT,
  updated_at         TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_subs_user ON subscriptions(user_id);

CREATE TABLE IF NOT EXISTS saved_filters (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name            TEXT    NOT NULL,
  criteria        TEXT    NOT NULL,                         -- JSON
  channels        TEXT    NOT NULL,                         -- JSON array
  is_active       INTEGER NOT NULL DEFAULT 1,
  last_checked_at TEXT,
  last_matched_at TEXT,
  matches_count   INTEGER NOT NULL DEFAULT 0,
  created_at      TEXT    NOT NULL,
  updated_at      TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_filters_user ON saved_filters(user_id, is_active);

CREATE TABLE IF NOT EXISTS alerts (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  item_id         INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  saved_filter_id INTEGER REFERENCES saved_filters(id) ON DELETE SET NULL,
  reason          TEXT    NOT NULL,                         -- new|price_drop|new_session
  channel         TEXT,
  status          TEXT    NOT NULL DEFAULT 'pending',
  detail          TEXT,
  error           TEXT,
  created_at      TEXT    NOT NULL,
  sent_at         TEXT,
  -- RN-006: o mesmo lote não alerta duas vezes o mesmo usuário pelo mesmo motivo.
  UNIQUE (user_id, item_id, reason)
);
CREATE INDEX IF NOT EXISTS ix_alerts_status ON alerts(status, created_at);

CREATE TABLE IF NOT EXISTS auth_tokens (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind       TEXT    NOT NULL,
  token_hash TEXT    NOT NULL,
  expires_at TEXT    NOT NULL,
  used_at    TEXT,
  created_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_tokens_user_kind ON auth_tokens(user_id, kind);

-- ── Comparador (RN-010) ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS price_references (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  vehicle_type      TEXT    NOT NULL,
  brand             TEXT    NOT NULL,
  model             TEXT    NOT NULL,
  year              INTEGER NOT NULL,
  fuel              TEXT,
  source_kind       TEXT    NOT NULL,                       -- fipe | listings
  value_cents       INTEGER NOT NULL,
  sample_size       INTEGER NOT NULL DEFAULT 1,
  min_value_cents   INTEGER,
  max_value_cents   INTEGER,
  fipe_code         TEXT,
  fipe_model_label  TEXT,
  reference_month   TEXT,
  match_ratio       REAL,
  computed_at       TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_price_ref_lookup
  ON price_references(vehicle_type, brand, model, year, fuel);

CREATE TABLE IF NOT EXISTS item_opportunities (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id            INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE UNIQUE,
  price_reference_id INTEGER REFERENCES price_references(id) ON DELETE SET NULL,
  reference_value_cents INTEGER NOT NULL,
  total_cost_cents   INTEGER NOT NULL,
  discount_pct       REAL    NOT NULL,
  score              INTEGER NOT NULL,
  reasons            TEXT,
  computed_at        TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_opp_score ON item_opportunities(score DESC);

-- ── Configuração e marca ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS system_settings (
  key        TEXT PRIMARY KEY,
  value      TEXT    NOT NULL,
  label      TEXT    NOT NULL,
  -- `group` é palavra reservada em SQL; o nome fica entre aspas para o
  -- contrato da API continuar o mesmo do backend em Python.
  "group"    TEXT    NOT NULL,
  is_secret  INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS branding_assets (
  key        TEXT PRIMARY KEY,
  mimetype   TEXT NOT NULL,
  data       BLOB NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS extraction_cache (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  content_hash       TEXT    NOT NULL,
  category_id        INTEGER REFERENCES categories(id) ON DELETE SET NULL,
  extraction_version TEXT    NOT NULL,
  result             TEXT    NOT NULL,
  created_at         TEXT    NOT NULL,
  UNIQUE (content_hash, category_id, extraction_version)
);

-- ── Fila da coleta fatiada ───────────────────────────────────────────
-- Existe só na versão Workers. No backend em Python o APScheduler segurava
-- uma coleta inteira numa chamada; aqui cada invocação tem 10 ms de CPU, e
-- o trabalho precisa ser quebrado em pedaços que caibam nisso.
CREATE TABLE IF NOT EXISTS work_queue (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  stage       TEXT    NOT NULL,          -- parse | normalize
  source_id   INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  external_id TEXT,                      -- conhecido já no recorte, quando dá
  payload     TEXT    NOT NULL,          -- bloco de HTML recortado, ou JSON
  attempts    INTEGER NOT NULL DEFAULT 0,
  last_error  TEXT,
  created_at  TEXT    NOT NULL,
  -- Marca de posse: uma invocação reserva as linhas antes de processar, para
  -- duas invocações simultâneas não pegarem o mesmo bloco.
  claimed_at  TEXT,
  claim_token TEXT
);
CREATE INDEX IF NOT EXISTS ix_queue_pendente ON work_queue(stage, claimed_at, id);
CREATE INDEX IF NOT EXISTS ix_queue_token    ON work_queue(claim_token);
