/**
 * Painel administrativo: login e configuração.
 *
 * Escopo deliberadamente estreito. O painel completo do backend em Python
 * (fontes, itens, revisão, incidentes, duplicados, jobs) continua lá, rodando
 * junto da coleta, onde ele tem o banco de trabalho e nenhum teto de CPU. O
 * que vive aqui é só o que precisa ser mexido com a vitrine no ar: a
 * configuração que a vitrine lê — e isso hoje quer dizer publicidade e textos.
 */
import { bloqueada, conferirSenha, gerarHash, gerarToken, lerToken, registrarFalha } from "../lib/auth";
import { agora, paraIso } from "../lib/valores";
import type { Env } from "../tipos";

interface Sessao {
  id: number;
  email: string;
  role: string;
}

/** Lê o token do cabeçalho e devolve a sessão, ou null. */
export async function sessaoDe(req: Request, env: Env): Promise<Sessao | null> {
  const cab = req.headers.get("authorization") || "";
  const token = cab.startsWith("Bearer ") ? cab.slice(7) : "";
  if (!token || !env.JWT_SECRET) return null;
  const carga = await lerToken(token, env.JWT_SECRET);
  if (!carga || typeof carga.sub !== "number") return null;
  return { id: carga.sub, email: String(carga.email ?? ""), role: String(carga.role ?? "user") };
}

function naoAutorizado(): Response {
  return Response.json({ detail: "Não autenticado" }, { status: 401 });
}

export async function login(req: Request, env: Env): Promise<Response> {
  if (!env.JWT_SECRET) {
    return Response.json(
      { detail: "JWT_SECRET não configurado no Worker" },
      { status: 500 },
    );
  }

  // O IP do visitante vem do cabeçalho que a própria Cloudflare preenche;
  // ele não é falsificável pelo cliente como seria um X-Forwarded-For.
  const origem = req.headers.get("cf-connecting-ip") || "desconhecida";
  if (await bloqueada(env.DB, origem)) {
    return Response.json(
      { detail: "Muitas tentativas. Tente novamente amanhã." },
      { status: 429 },
    );
  }

  let corpo: { email?: string; password?: string };
  try {
    corpo = (await req.json()) as { email?: string; password?: string };
  } catch {
    return Response.json({ detail: "Corpo inválido" }, { status: 400 });
  }
  const email = (corpo.email || "").trim().toLowerCase();
  const senha = corpo.password || "";
  if (!email || !senha) {
    return Response.json({ detail: "Informe e-mail e senha" }, { status: 400 });
  }

  const u = await env.DB.prepare(
    "SELECT id, email, name, hashed_password, role, is_active FROM users WHERE LOWER(email) = ?",
  )
    .bind(email)
    .first<{ id: number; email: string; name: string | null; hashed_password: string; role: string; is_active: number }>();

  // Mesma resposta para usuário inexistente e senha errada: diferenciar
  // informaria quais endereços têm conta.
  const ok = u && u.is_active === 1 && (await conferirSenha(senha, u.hashed_password));
  if (!ok || !u) {
    await registrarFalha(env.DB, origem);
    return Response.json({ detail: "E-mail ou senha inválidos" }, { status: 401 });
  }

  const token = await gerarToken({ sub: u.id, email: u.email, role: u.role }, env.JWT_SECRET);
  await env.DB.prepare("UPDATE users SET last_login_at = ? WHERE id = ?")
    .bind(agora(), u.id)
    .run();

  // O dashboard lê os campos achatados (`user_email`, `role`), como o
  // backend em Python devolve; `user` fica por compatibilidade.
  return Response.json({
    access_token: token,
    token_type: "bearer",
    user_email: u.email,
    user_name: u.name,
    role: u.role,
    user: { id: u.id, email: u.email, role: u.role, name: u.name },
  });
}

export async function eu(req: Request, env: Env): Promise<Response> {
  const s = await sessaoDe(req, env);
  if (!s) return naoAutorizado();
  const u = await env.DB.prepare("SELECT id, email, name, role, is_active FROM users WHERE id = ?")
    .bind(s.id)
    .first<{ id: number; email: string; name: string | null; role: string; is_active: number }>();
  // Conta apagada ou desativada derruba a sessão, mesmo com token válido.
  if (!u || u.is_active !== 1) return naoAutorizado();
  return Response.json({ id: u.id, email: u.email, name: u.name, role: u.role, is_active: true });
}

/** Nome de cada grupo na tela, igual ao do backend em Python. */
const ROTULO_GRUPO: Record<string, string> = {
  llm: "Normalização (LLM)",
  pipeline: "Pipeline",
  health: "Saúde da coleta (RN-008)",
  scraping: "Coleta",
  portal: "Portal",
  branding: "Marca",
  alerts: "Alertas (RN-006/RN-007)",
  email: "E-mail (SMTP)",
  whatsapp: "WhatsApp",
  accounts: "Contas de usuário",
  comparator: "Comparador (RN-010)",
  ads: "Publicidade",
};

/**
 * Lista a configuração, agrupada como a tela espera
 * (`{ grupo: { label, items[] } }`).
 *
 * Valor marcado como segredo sai vazio: a tela mostra o campo em branco com
 * o rótulo, e gravar por cima substitui. Devolver o valor para preencher a
 * caixa exporia a chave a qualquer um que abrisse o inspetor.
 */
export async function listarSettings(req: Request, env: Env, u: URL): Promise<Response> {
  const s = await sessaoDe(req, env);
  if (!s || s.role !== "admin") return naoAutorizado();

  const grupo = u.searchParams.get("group");
  const sql = grupo
    ? `SELECT key, value, label, "group" AS grupo, is_secret FROM system_settings WHERE "group" = ? ORDER BY key`
    : `SELECT key, value, label, "group" AS grupo, is_secret FROM system_settings ORDER BY "group", key`;
  const r = grupo
    ? await env.DB.prepare(sql).bind(grupo).all<Record<string, unknown>>()
    : await env.DB.prepare(sql).all<Record<string, unknown>>();

  const saida: Record<string, { label: string; items: unknown[] }> = {};
  for (const x of r.results) {
    const g = String(x.grupo);
    (saida[g] ||= { label: ROTULO_GRUPO[g] ?? g, items: [] }).items.push({
      key: x.key,
      value: x.is_secret === 1 ? "" : x.value,
      label: x.label,
      is_secret: x.is_secret === 1,
    });
  }
  return Response.json(saida);
}

export async function gravarSettings(req: Request, env: Env): Promise<Response> {
  const s = await sessaoDe(req, env);
  if (!s || s.role !== "admin") return naoAutorizado();

  let corpo: Record<string, string> | { settings?: Record<string, string> };
  try {
    corpo = (await req.json()) as Record<string, string>;
  } catch {
    return Response.json({ detail: "Corpo inválido" }, { status: 400 });
  }
  const pares = ("settings" in corpo && corpo.settings ? corpo.settings : corpo) as Record<string, string>;
  const chaves = Object.keys(pares);
  if (!chaves.length) return Response.json({ atualizados: 0 });

  // Só chaves que já existem: criar configuração por requisição deixaria o
  // banco com lixo que ninguém lê.
  const existentes = await env.DB.prepare(
    `SELECT key FROM system_settings WHERE key IN (${chaves.map(() => "?").join(",")})`,
  )
    .bind(...chaves)
    .all<{ key: string }>();
  const conhecidas = new Set(existentes.results.map((x) => x.key));

  const ts = agora();
  const cmds = chaves
    .filter((k) => conhecidas.has(k))
    .map((k) =>
      env.DB.prepare("UPDATE system_settings SET value = ?, updated_at = ? WHERE key = ?")
        .bind(String(pares[k] ?? ""), ts, k),
    );
  if (cmds.length) await env.DB.batch(cmds);

  return Response.json({
    status: "ok",
    updated: cmds.length,
    ignorados: chaves.filter((k) => !conhecidas.has(k)),
  });
}

/**
 * Cria o administrador do painel na primeira vez.
 *
 * Roda uma vez e só enquanto não houver nenhum admin: depois disso responde
 * 409 e não serve de porta dos fundos. A senha vem do segredo
 * `ADMIN_PASSWORD` do Worker, não do corpo da requisição — assim nem o
 * primeiro acesso depende de alguém adivinhar quem chamou primeiro.
 */
export async function semearAdmin(env: Env): Promise<Response> {
  if (!env.ADMIN_EMAIL || !env.ADMIN_PASSWORD) {
    return Response.json(
      { detail: "Defina os segredos ADMIN_EMAIL e ADMIN_PASSWORD no Worker" },
      { status: 400 },
    );
  }
  const jaTem = await env.DB.prepare("SELECT COUNT(*) AS n FROM users WHERE role = 'admin'")
    .first<{ n: number }>();
  if ((jaTem?.n ?? 0) > 0) {
    return Response.json({ detail: "Já existe administrador" }, { status: 409 });
  }

  const ts = agora();
  await env.DB.prepare(
    `INSERT INTO users (email, hashed_password, name, role, is_active, created_at)
     VALUES (?,?,?,'admin',1,?)`,
  )
    .bind(env.ADMIN_EMAIL.toLowerCase(), await gerarHash(env.ADMIN_PASSWORD), "Administrador", ts)
    .run();

  return Response.json({ criado: env.ADMIN_EMAIL });
}

/**
 * Painel inicial.
 *
 * Mostra o que a borda sabe: o que está publicado, de que fonte veio e
 * quando. O que depende do banco de trabalho da coleta — fila de revisão,
 * incidentes, duplicados, execuções de job — não vive aqui, e por isso as
 * telas correspondentes continuam no backend em Python, junto da coleta.
 */
export async function painel(req: Request, env: Env): Promise<Response> {
  const s = await sessaoDe(req, env);
  if (!s || s.role !== "admin") return naoAutorizado();

  const [porStatus, fontes, resumo, porDia, audiencia] = await env.DB.batch<Record<string, unknown>>([
    env.DB.prepare("SELECT status, COUNT(*) AS n FROM items GROUP BY status"),
    env.DB.prepare(
      `SELECT s.id, s.name, s.slug, s.is_active, s.dispatch_enabled, s.health_status,
              s.last_run_at, s.last_run_status, s.last_items_count, s.avg_items_count,
              (SELECT COUNT(*) FROM items i WHERE i.source_id = s.id) AS items_total,
              (SELECT COUNT(*) FROM items i WHERE i.source_id = s.id
                 AND i.status IN ('published','auction_soon')) AS items_published
         FROM sources s ORDER BY s.name`,
    ),
    env.DB.prepare(
      `SELECT
         (SELECT COUNT(*) FROM items WHERE first_seen_at >= datetime('now','-27 hours')) AS novos_24h,
         (SELECT COUNT(*) FROM auctions WHERE starts_at BETWEEN datetime('now','-3 hours')
            AND datetime('now','+165 hours')) AS pregoes_7d,
         (SELECT COUNT(*) FROM item_opportunities) AS com_score`,
    ),
    env.DB.prepare(
      `SELECT substr(first_seen_at,1,10) AS day, COUNT(*) AS count FROM items
        WHERE first_seen_at >= datetime('now','-14 days')
        GROUP BY day ORDER BY day`,
    ),
    env.DB.prepare(
      `SELECT source_id, SUM(views) AS v, SUM(clicks) AS c FROM source_daily_stats
        WHERE day >= date('now','-7 days') GROUP BY source_id`,
    ),
  ]);

  const status: Record<string, number> = {};
  for (const r of porStatus.results) status[String(r.status)] = Number(r.n);
  const total = Object.values(status).reduce((a, b) => a + b, 0);
  const r0 = resumo.results[0] ?? {};
  const aud = new Map(
    audiencia.results.map((x) => [Number(x.source_id), { v: Number(x.v ?? 0), c: Number(x.c ?? 0) }]),
  );

  return Response.json({
    items_total: total,
    items_by_status: status,
    items_by_extraction: { done: total },
    extraction_rate: 1,
    items_new_24h: r0.novos_24h ?? 0,
    auctions_upcoming_7d: r0.pregoes_7d ?? 0,
    // A borda não guarda fila de revisão nem incidentes: isso é do banco de
    // trabalho da coleta. Zero aqui significa "não se mede daqui".
    open_incidents: 0,
    suspected_duplicates: 0,
    sources: fontes.results.map((f) => {
      const a = aud.get(Number(f.id)) ?? { v: 0, c: 0 };
      return {
        id: f.id, name: f.name, slug: f.slug,
        is_active: f.is_active === 1, dispatch_enabled: f.dispatch_enabled === 1,
        health_status: f.health_status, last_run_at: paraIso(f.last_run_at as string | null),
        last_run_status: f.last_run_status, last_items_count: f.last_items_count,
        avg_items_count: f.avg_items_count,
        items_total: f.items_total, items_published: f.items_published,
        views_7d: a.v, clicks_7d: a.c,
        ctr_7d: a.v ? Math.round((a.c / a.v) * 10000) / 10000 : null,
      };
    }),
    last_jobs: {},
    daily_collected: porDia.results.map((d) => ({ day: d.day, count: d.count })),
  });
}

/** Resumo de assinantes. Contas vivem na borda, alertas ainda não. */
export async function resumoUsuarios(req: Request, env: Env): Promise<Response> {
  const s = await sessaoDe(req, env);
  if (!s || s.role !== "admin") return naoAutorizado();
  const r = await env.DB.prepare(
    `SELECT
       (SELECT COUNT(*) FROM users WHERE role = 'user') AS users_total,
       (SELECT COUNT(*) FROM users WHERE role = 'user' AND email_verified_at IS NOT NULL) AS users_verified,
       (SELECT COUNT(*) FROM saved_filters WHERE is_active = 1) AS active_filters,
       (SELECT COUNT(*) FROM alerts WHERE status = 'sent'
          AND substr(created_at,1,10) = date('now','-3 hours')) AS alerts_sent_today,
       (SELECT COUNT(*) FROM alerts WHERE status = 'pending') AS alerts_pending,
       (SELECT COUNT(*) FROM alerts WHERE status = 'failed') AS alerts_failed`,
  ).first<Record<string, unknown>>();
  // `by_plan` precisa existir como objeto: a tela faz Object.keys nele, e
  // undefined ali derruba o painel inteiro.
  const planos = await env.DB.prepare(
    "SELECT plan, COUNT(*) AS n FROM subscriptions WHERE status = 'active' GROUP BY plan",
  ).all<{ plan: string; n: number }>();
  const by_plan: Record<string, number> = {};
  for (const p of planos.results) by_plan[p.plan] = p.n;

  return Response.json({ ...(r ?? {}), by_plan });
}
