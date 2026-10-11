/** Ligações declaradas no `wrangler.toml` e segredos do Worker. */
export interface Env {
  DB: D1Database;
  /** Segredo compartilhado com o agente de coleta local. */
  INGEST_TOKEN?: string;
  /** Assina o token de sessão do painel. */
  JWT_SECRET?: string;
  /** Usados uma única vez, por `/admin/seed`, para criar o administrador. */
  ADMIN_EMAIL?: string;
  ADMIN_PASSWORD?: string;
}
