/** Ligações declaradas no `wrangler.toml` e segredos do Worker. */
export interface Env {
  DB: D1Database;
  /** Segredo compartilhado com o agente de coleta local. */
  INGEST_TOKEN?: string;
}
