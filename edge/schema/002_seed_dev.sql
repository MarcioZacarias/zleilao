-- Dados mínimos para exercitar o esquema localmente.
-- Os três itens cobrem o que importa testar: acento no título (FTS deve
-- achar sem acento), coordenada dentro e fora do raio, e lote sem marca.
--   npx wrangler d1 execute zleilao --local --file schema/002_seed_dev.sql

INSERT INTO sources (name,slug,parser_type,created_at,updated_at)
VALUES ('Mega Leilões','megaleiloes','megaleiloes','2026-10-10 18:00:00','2026-10-10 18:00:00');

INSERT INTO items (source_id,external_id,title,brand,model,city,state,lat,lng,price_cents,official_url,status,first_seen_at,last_seen_at,created_at,updated_at) VALUES
 (1,'1','Carro Volkswagen Gol 1.6 Power - 2006','Volkswagen','Gol','Campinas','SP',-22.9099,-47.0626,2190000,'u1','published','2026-10-10 18:00:00','2026-10-10 18:00:00','2026-10-10 18:00:00','2026-10-10 18:00:00'),
 (1,'2','Caminhão Mercedes Benz L 1214','Mercedes-Benz','L 1214','Jundiaí','SP',-23.1857,-46.8978,3924300,'u2','published','2026-10-10 18:00:00','2026-10-10 18:00:00','2026-10-10 18:00:00','2026-10-10 18:00:00'),
 (1,'3','VEÍCULO CARCAÇA',NULL,NULL,'Manaus','AM',-3.1190,-60.0217,50000,'u3','published','2026-10-10 18:00:00','2026-10-10 18:00:00','2026-10-10 18:00:00','2026-10-10 18:00:00');
