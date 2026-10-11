-- Contagem de senha errada por origem, para o login não virar alvo de força
-- bruta. O teto de iterações do PBKDF2 é baixo (cabe em 10 ms de CPU), então
-- a defesa contra tentativa em massa precisa estar aqui.
--   npx wrangler d1 execute zleilao --remote --file schema/006_admin.sql
CREATE TABLE IF NOT EXISTS login_failures (
  origem TEXT    NOT NULL,
  dia    TEXT    NOT NULL,
  total  INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (origem, dia)
);
