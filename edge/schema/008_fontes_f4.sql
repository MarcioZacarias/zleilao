-- F4: fontes novas. A borda só aceita ingestão de fonte cadastrada
-- (`fonte desconhecida` caso contrário), então cada coletor novo entra aqui
-- antes da primeira sincronização. `config` fica vazio de propósito: quem lê
-- a configuração é o agente local, no Postgres.
--   npx wrangler d1 execute zleilao --remote --file schema/008_fontes_f4.sql
INSERT OR IGNORE INTO sources (name, slug, kind, parser_type, base_url, config, is_active, dispatch_enabled, scraping_allowed, scrape_frequency, priority_weight, health_status, created_at, updated_at)
VALUES ('Rogério Menezes', 'rogeriomenezes', 'auction', 'rogeriomenezes', 'https://rogeriomenezes.com.br', '{}', 1, 1, 1, 240, 10, 'unknown', '2026-10-17 00:00:00', '2026-10-17 00:00:00');
INSERT OR IGNORE INTO sources (name, slug, kind, parser_type, base_url, config, is_active, dispatch_enabled, scraping_allowed, scrape_frequency, priority_weight, health_status, created_at, updated_at)
VALUES ('Nakakogue Leilões', 'nakakogue', 'auction', 'nakakogue', 'https://www.nakakogueleiloes.com.br', '{}', 1, 1, 1, 240, 10, 'unknown', '2026-10-17 00:00:00', '2026-10-17 00:00:00');
INSERT OR IGNORE INTO sources (name, slug, kind, parser_type, base_url, config, is_active, dispatch_enabled, scraping_allowed, scrape_frequency, priority_weight, health_status, created_at, updated_at)
VALUES ('Parque dos Leilões', 'parquedosleiloes', 'auction', 'parquedosleiloes', 'https://www.parquedosleiloes.com.br', '{}', 1, 1, 1, 240, 10, 'unknown', '2026-10-17 00:00:00', '2026-10-17 00:00:00');
-- Pestana nasce inativa e sem permissão: os termos de uso vedam robôs (RN-009).
INSERT OR IGNORE INTO sources (name, slug, kind, parser_type, base_url, config, is_active, dispatch_enabled, scraping_allowed, scrape_frequency, priority_weight, health_status, created_at, updated_at)
VALUES ('Pestana Leilões', 'pestana', 'auction', 'pestana', 'https://www.pestanaleiloes.com.br', '{}', 0, 0, 0, 240, 10, 'unknown', '2026-10-17 00:00:00', '2026-10-17 00:00:00');
INSERT OR IGNORE INTO sources (name, slug, kind, parser_type, base_url, config, is_active, dispatch_enabled, scraping_allowed, scrape_frequency, priority_weight, health_status, created_at, updated_at)
VALUES ('Casa de Leilões', 'casadeleiloes', 'auction', 'generic_html', 'https://www.casadeleiloes.com.br', '{}', 1, 1, 1, 240, 10, 'unknown', '2026-10-17 00:00:00', '2026-10-17 00:00:00');
