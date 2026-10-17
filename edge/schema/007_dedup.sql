-- F4: deduplicação plena. Os vínculos passam a chegar do agente local
-- (POST /ingest/duplicates) e a vitrine esconde o espelho confirmado enquanto
-- o canônico está visível; os índices são o que mantêm o NOT EXISTS barato.
--   npx wrangler d1 execute zleilao --remote --file schema/007_dedup.sql
CREATE INDEX IF NOT EXISTS ix_dups_duplicate ON item_duplicates(duplicate_item_id, status);
CREATE INDEX IF NOT EXISTS ix_dups_canonical ON item_duplicates(canonical_item_id, status);

-- Só para a tela de configuração mostrar o limiar; quem o lê é o job local.
INSERT OR IGNORE INTO system_settings (key, value, label, "group", is_secret, updated_at)
VALUES ('dedup_merge_threshold', '1.0', 'F4: similaridade que funde automaticamente (1.0 = so placa ou URL oficial iguais)', 'pipeline', 0, '2026-10-17 00:00:00');
