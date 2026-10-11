-- Publicidade na vitrine.
--   npx wrangler d1 execute zleilao --remote --file schema/005_ads.sql
--
-- Dois modos, e eles não competem:
--
-- `adsense` é rede de terceiros: paga por impressão/clique, não exige
-- negociação, mas exige aprovação do Google e domínio próprio — subdomínio
-- de plataforma costuma ser recusado.
--
-- `proprio` é espaço vendido direto, tipicamente ao leiloeiro que já está na
-- vitrine. Rende mais por impressão e não depende de aprovação de ninguém,
-- mas alguém precisa vender. É o mesmo caminho do "destaque pago" da onda 5.
--
-- Em qualquer um dos dois o bloco é rotulado como publicidade. Vitrine que
-- empurra anúncio disfarçado de resultado perde a única coisa que tem para
-- vender, que é ser confiável.

INSERT OR REPLACE INTO system_settings (key, value, label, "group", is_secret, updated_at) VALUES
  ('ads_enabled', '0', 'Exibir publicidade na vitrine', 'ads', 0, datetime('now','-3 hours')),
  ('ads_provider', 'proprio', 'Origem do anúncio: adsense ou proprio', 'ads', 0, datetime('now','-3 hours')),

  -- AdSense: o client vem da conta ("ca-pub-..."); cada slot é um bloco criado
  -- no painel do Google. Slot vazio desliga aquela posição.
  ('ads_adsense_client', '', 'AdSense: ID do cliente (ca-pub-...)', 'ads', 0, datetime('now','-3 hours')),
  ('ads_adsense_slot_busca', '', 'AdSense: slot no meio dos resultados', 'ads', 0, datetime('now','-3 hours')),
  ('ads_adsense_slot_ficha', '', 'AdSense: slot na ficha do lote', 'ads', 0, datetime('now','-3 hours')),

  -- Anúncio próprio: uma peça por posição. `alvo` é para onde o clique vai.
  ('ads_proprio_busca_imagem', '', 'Próprio: imagem do anúncio na busca (URL)', 'ads', 0, datetime('now','-3 hours')),
  ('ads_proprio_busca_alvo', '', 'Próprio: link do anúncio na busca', 'ads', 0, datetime('now','-3 hours')),
  ('ads_proprio_busca_texto', '', 'Próprio: texto alternativo do anúncio na busca', 'ads', 0, datetime('now','-3 hours')),
  ('ads_proprio_ficha_imagem', '', 'Próprio: imagem do anúncio na ficha (URL)', 'ads', 0, datetime('now','-3 hours')),
  ('ads_proprio_ficha_alvo', '', 'Próprio: link do anúncio na ficha', 'ads', 0, datetime('now','-3 hours')),
  ('ads_proprio_ficha_texto', '', 'Próprio: texto alternativo do anúncio na ficha', 'ads', 0, datetime('now','-3 hours')),

  -- A cada quantos cards entra um anúncio na listagem. Valor baixo irrita e
  -- derruba o uso; 12 deixa um por tela cheia.
  ('ads_intervalo_cards', '12', 'Um anúncio a cada N lotes na listagem', 'ads', 0, datetime('now','-3 hours'));

-- Medição por posição, para saber se o espaço vale o incômodo.
CREATE TABLE IF NOT EXISTS ad_events (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  posicao  TEXT NOT NULL,              -- busca | ficha
  tipo     TEXT NOT NULL,              -- impressao | clique
  dia      TEXT NOT NULL,              -- 'YYYY-MM-DD'
  total    INTEGER NOT NULL DEFAULT 0,
  UNIQUE (posicao, tipo, dia)
);
