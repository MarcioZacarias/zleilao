/**
 * Gestão na borda: assinantes, alertas, e leitura de fontes e categorias.
 *
 * As contas e os alertas moram no D1 — é aqui que o administrador os
 * administra, com o mesmo contrato de `backend/app/v1/users_admin.py`.
 *
 * Fontes e categorias são espelho do que o agente local envia. A borda as
 * mostra, mas quem edita é o painel local, junto da coleta: qualquer
 * mudança feita aqui seria desfeita na próxima sincronização.
 */
import { agora, booleano, deDataParaBanco, lerJson, paraIso } from "../lib/valores";
import type { Env } from "../tipos";
import { sessaoDe } from "./admin";
import { descreverCriterios, normalizarCriterios } from "./conta";
import { JOIN_CARD, SELECT_CARD, serializarCard } from "./portal";

interface Admin {
  id: number;
  email: string;
}

async function administrador(req: Request, env: Env): Promise<Admin | null> {
  const s = await sessaoDe(req, env);
  return s && s.role === "admin" ? { id: s.id, email: s.email } : null;
}

const naoAutorizado = () => Response.json({ detail: "Não autenticado" }, { status: 401 });

function erro(status: number, detail: string): Response {
  return Response.json({ detail }, { status });
}

async function corpoJson<T>(req: Request): Promise<T | null> {
  try {
    return (await req.json()) as T;
  } catch {
    return null;
  }
}

/* ── assinantes ─────────────────────────────────────────────────────── */

// A assinatura mais recente do usuário vai junto, mais as contagens que a
// tela mostra em cada linha. Subconsultas em vez de uma consulta por linha:
// são 50 linhas por página e cada ida ao D1 custa.
const SELECT_USUARIO = `
  u.id, u.email, u.name, u.role, u.is_active, u.phone, u.email_opt_in, u.whatsapp_opt_in,
  u.email_verified_at, u.created_at, u.last_login_at,
  sub.plan, sub.status AS plan_status, sub.current_period_end AS plan_expires_at, sub.note AS plan_note,
  (SELECT COUNT(*) FROM saved_filters f WHERE f.user_id = u.id) AS filters,
  (SELECT COUNT(*) FROM alerts a WHERE a.user_id = u.id AND a.status = 'sent') AS alerts_sent`;

const JOIN_USUARIO = `
  LEFT JOIN subscriptions sub
    ON sub.id = (SELECT id FROM subscriptions WHERE user_id = u.id ORDER BY id DESC LIMIT 1)`;

function usuarioSaida(r: Record<string, unknown>) {
  return {
    id: r.id, email: r.email, name: r.name, role: r.role,
    is_active: booleano(r.is_active),
    phone: r.phone,
    email_opt_in: booleano(r.email_opt_in),
    whatsapp_opt_in: booleano(r.whatsapp_opt_in),
    email_verified: r.email_verified_at !== null && r.email_verified_at !== undefined,
    created_at: paraIso(r.created_at as string | null),
    last_login_at: paraIso(r.last_login_at as string | null),
    plan: r.plan ?? "free",
    plan_status: r.plan_status ?? "active",
    plan_expires_at: paraIso(r.plan_expires_at as string | null),
    plan_note: r.plan_note ?? null,
    filters: r.filters ?? 0,
    alerts_sent: r.alerts_sent ?? 0,
  };
}

async function buscarUsuario(env: Env, id: number) {
  const r = await env.DB.prepare(`SELECT ${SELECT_USUARIO} FROM users u ${JOIN_USUARIO} WHERE u.id = ?`)
    .bind(id)
    .first<Record<string, unknown>>();
  return r ? usuarioSaida(r) : null;
}

export async function listarUsuarios(u: URL, req: Request, env: Env): Promise<Response> {
  if (!(await administrador(req, env))) return naoAutorizado();

  const where: string[] = [];
  const params: unknown[] = [];
  const q = u.searchParams.get("q")?.trim();
  if (q) {
    where.push("(u.email LIKE ? OR u.name LIKE ? OR u.phone LIKE ?)");
    params.push(`%${q}%`, `%${q}%`, `%${q}%`);
  }
  const plano = u.searchParams.get("plan");
  if (plano) {
    where.push("sub.plan = ?");
    params.push(plano);
  }
  const filtro = where.length ? `WHERE ${where.join(" AND ")}` : "";

  const page = Math.max(1, Number(u.searchParams.get("page")) || 1);
  const pageSize = Math.min(200, Math.max(1, Number(u.searchParams.get("page_size")) || 50));

  const [total, linhas] = await env.DB.batch<Record<string, unknown>>([
    env.DB.prepare(`SELECT COUNT(*) AS n FROM users u ${JOIN_USUARIO} ${filtro}`).bind(...params),
    env.DB.prepare(
      `SELECT ${SELECT_USUARIO} FROM users u ${JOIN_USUARIO} ${filtro}
        ORDER BY u.created_at DESC, u.id DESC LIMIT ? OFFSET ?`,
    ).bind(...params, pageSize, (page - 1) * pageSize),
  ]);
  const n = Number(total.results[0]?.n ?? 0);
  return Response.json({
    users: linhas.results.map(usuarioSaida),
    meta: { page, page_size: pageSize, total: n, pages: Math.max(1, Math.ceil(n / pageSize)) },
  });
}

export async function atualizarUsuario(id: number, req: Request, env: Env): Promise<Response> {
  const adm = await administrador(req, env);
  if (!adm) return naoAutorizado();
  const c = await corpoJson<{ is_active?: boolean; role?: string; email_verified?: boolean }>(req);
  if (!c) return erro(400, "Corpo inválido");
  if (c.role !== undefined && c.role !== "user" && c.role !== "admin") return erro(422, "Papel inválido");

  const existe = await env.DB.prepare("SELECT id FROM users WHERE id = ?").bind(id).first();
  if (!existe) return erro(404, "Usuário não encontrado");
  // Quem se tranca do lado de fora não tem como voltar: o seed só cria
  // admin quando não existe nenhum.
  if (id === adm.id && c.role === "user") return erro(400, "Você não pode remover o próprio acesso de administrador");
  if (id === adm.id && c.is_active === false) return erro(400, "Você não pode desativar a própria conta");

  const sets: string[] = [];
  const params: unknown[] = [];
  if (c.is_active !== undefined) { sets.push("is_active = ?"); params.push(c.is_active ? 1 : 0); }
  if (c.role !== undefined) { sets.push("role = ?"); params.push(c.role); }
  if (c.email_verified !== undefined) {
    sets.push("email_verified_at = ?");
    params.push(c.email_verified ? agora() : null);
  }
  if (sets.length) {
    await env.DB.prepare(`UPDATE users SET ${sets.join(", ")} WHERE id = ?`).bind(...params, id).run();
  }
  return Response.json(await buscarUsuario(env, id));
}

/**
 * Ativação manual do plano (`provider = 'manual'`): a cobrança automática
 * exige credenciais de gateway que ainda não existem, e isso permite vender
 * antes de integrar pagamento.
 */
export async function definirPlano(id: number, req: Request, env: Env): Promise<Response> {
  const adm = await administrador(req, env);
  if (!adm) return naoAutorizado();
  const c = await corpoJson<{ plan?: string; months?: number; note?: string | null }>(req);
  if (!c) return erro(400, "Corpo inválido");
  if (c.plan !== "free" && c.plan !== "pro") return erro(422, "Plano inválido");
  const meses = c.months === undefined ? 1 : Math.trunc(Number(c.months));
  if (!Number.isFinite(meses) || meses < 0 || meses > 36) return erro(422, "Meses entre 0 e 36");

  const usuario = await env.DB.prepare("SELECT id, email FROM users WHERE id = ?")
    .bind(id)
    .first<{ id: number; email: string }>();
  if (!usuario) return erro(404, "Usuário não encontrado");

  const ts = agora();
  // `months = 0` no plano pago = acesso sem vencimento (cortesia, parceiro).
  const vencimento = c.plan === "pro" && meses > 0
    ? deDataParaBanco(new Date(Date.now() + meses * 30 * 86_400_000))
    : null;
  const nota = c.note ? String(c.note).slice(0, 500) : null;

  const sub = await env.DB.prepare("SELECT id FROM subscriptions WHERE user_id = ? ORDER BY id DESC LIMIT 1")
    .bind(id)
    .first<{ id: number }>();
  if (sub) {
    await env.DB.prepare(
      `UPDATE subscriptions SET plan = ?, status = 'active', provider = 'manual', activated_by = ?,
              note = ?, current_period_end = ?, updated_at = ? WHERE id = ?`,
    ).bind(c.plan, adm.email, nota, vencimento, ts, sub.id).run();
  } else {
    await env.DB.prepare(
      `INSERT INTO subscriptions (user_id, plan, status, started_at, current_period_end, provider,
                                  activated_by, note, updated_at)
       VALUES (?,?,'active',?,?,'manual',?,?,?)`,
    ).bind(id, c.plan, ts, vencimento, adm.email, nota, ts).run();
  }
  console.log(`plano de ${usuario.email} alterado para ${c.plan} por ${adm.email}`);
  return Response.json(await buscarUsuario(env, id));
}

export async function filtrosDoUsuario(id: number, req: Request, env: Env): Promise<Response> {
  if (!(await administrador(req, env))) return naoAutorizado();
  const r = await env.DB.prepare("SELECT * FROM saved_filters WHERE user_id = ? ORDER BY created_at DESC, id DESC")
    .bind(id)
    .all<Record<string, unknown>>();
  return Response.json(
    r.results.map((f) => {
      const criteria = normalizarCriterios(lerJson(f.criteria, {}));
      return {
        id: f.id, name: f.name, criteria,
        channels: lerJson<string[]>(f.channels, []),
        is_active: booleano(f.is_active),
        matches_count: f.matches_count ?? 0,
        last_matched_at: paraIso(f.last_matched_at as string | null),
        created_at: paraIso(f.created_at as string | null),
        description: descreverCriterios(criteria),
      };
    }),
  );
}

/* ── alertas ────────────────────────────────────────────────────────── */

export async function listarAlertas(u: URL, req: Request, env: Env): Promise<Response> {
  if (!(await administrador(req, env))) return naoAutorizado();

  const where: string[] = [];
  const params: unknown[] = [];
  const lista = (k: string) => (u.searchParams.get(k) || "").split(",").map((x) => x.trim()).filter(Boolean);
  const status = lista("status");
  if (status.length) {
    where.push(`al.status IN (${status.map(() => "?").join(",")})`);
    params.push(...status);
  }
  const motivos = lista("reason");
  if (motivos.length) {
    where.push(`al.reason IN (${motivos.map(() => "?").join(",")})`);
    params.push(...motivos);
  }
  const userId = Number(u.searchParams.get("user_id"));
  if (userId > 0) {
    where.push("al.user_id = ?");
    params.push(userId);
  }
  const limite = Math.min(500, Math.max(1, Number(u.searchParams.get("limit")) || 100));

  const r = await env.DB.prepare(
    `SELECT al.id AS alert_id, al.reason, al.status AS alert_status, al.channel, al.detail, al.error,
            al.created_at AS alert_created_at, al.sent_at, al.user_id,
            us.email AS user_email, us.name AS user_name,
            ${SELECT_CARD}
       FROM alerts al
       LEFT JOIN users us ON us.id = al.user_id
       LEFT JOIN items ON items.id = al.item_id
       ${JOIN_CARD}
       ${where.length ? `WHERE ${where.join(" AND ")}` : ""}
      ORDER BY al.created_at DESC, al.id DESC LIMIT ?`,
  )
    .bind(...params, limite)
    .all<Record<string, unknown>>();

  return Response.json(
    r.results.map((a) => ({
      id: a.alert_id,
      reason: a.reason,
      status: a.alert_status,
      channel: a.channel,
      detail: a.detail,
      error: a.error,
      created_at: paraIso(a.alert_created_at as string | null),
      sent_at: paraIso(a.sent_at as string | null),
      user: a.user_email ? { id: a.user_id, email: a.user_email, name: a.user_name } : null,
      item: a.id ? serializarCard(a) : null,
    })),
  );
}

export async function reenviarAlerta(id: number, req: Request, env: Env): Promise<Response> {
  if (!(await administrador(req, env))) return naoAutorizado();
  const a = await env.DB.prepare("SELECT status FROM alerts WHERE id = ?").bind(id).first<{ status: string }>();
  if (!a) return erro(404, "Alerta não encontrado");
  if (a.status === "sent") return erro(400, "Este alerta já foi enviado");
  await env.DB.prepare("UPDATE alerts SET status = 'pending', error = NULL WHERE id = ?").bind(id).run();
  return Response.json({ status: "ok", id });
}

/* ── fontes (leitura) ───────────────────────────────────────────────── */

const SELECT_FONTE = `
  s.*,
  (SELECT COUNT(*) FROM items i WHERE i.source_id = s.id) AS items_total,
  (SELECT COUNT(*) FROM items i WHERE i.source_id = s.id
     AND i.status IN ('published','auction_soon')) AS items_published`;

function fonteSaida(r: Record<string, unknown>) {
  return {
    id: r.id, name: r.name, slug: r.slug, kind: r.kind, parser_type: r.parser_type,
    base_url: r.base_url,
    config: lerJson<Record<string, unknown> | null>(r.config, null),
    is_active: booleano(r.is_active),
    dispatch_enabled: booleano(r.dispatch_enabled),
    scraping_allowed: booleano(r.scraping_allowed),
    scrape_frequency: r.scrape_frequency,
    priority_weight: r.priority_weight,
    robots_status: r.robots_status,
    robots_checked_at: paraIso(r.robots_checked_at as string | null),
    last_run_at: paraIso(r.last_run_at as string | null),
    last_run_status: r.last_run_status,
    last_items_count: r.last_items_count ?? 0,
    avg_items_count: r.avg_items_count,
    health_status: r.health_status ?? "unknown",
    suspended_reason: r.suspended_reason,
    created_at: paraIso(r.created_at as string | null),
    updated_at: paraIso(r.updated_at as string | null),
    items_total: r.items_total ?? 0,
    items_published: r.items_published ?? 0,
    // Incidentes ficam no banco de trabalho da coleta; a borda não os vê.
    open_incidents: 0,
  };
}

export async function listarFontes(req: Request, env: Env): Promise<Response> {
  if (!(await administrador(req, env))) return naoAutorizado();
  const r = await env.DB.prepare(`SELECT ${SELECT_FONTE} FROM sources s ORDER BY s.name`)
    .all<Record<string, unknown>>();
  return Response.json(r.results.map(fonteSaida));
}

export async function detalharFonte(id: number, req: Request, env: Env): Promise<Response> {
  if (!(await administrador(req, env))) return naoAutorizado();
  const r = await env.DB.prepare(`SELECT ${SELECT_FONTE} FROM sources s WHERE s.id = ?`)
    .bind(id)
    .first<Record<string, unknown>>();
  if (!r) return erro(404, "Fonte não encontrada");
  return Response.json(fonteSaida(r));
}

/**
 * Os parsers existem só no agente local; a lista aqui serve para a tela
 * montar o formulário e dar nome a cada fonte. Mesmo formato de
 * `available_parsers()` do Python.
 */
export async function listarParsers(req: Request, env: Env): Promise<Response> {
  if (!(await administrador(req, env))) return naoAutorizado();
  return Response.json([
    { key: "megaleiloes", name: "Mega Leilões", default_config: {} },
    { key: "freitas", name: "Freitas Leiloeiro", default_config: {} },
    { key: "leilo", name: "Leilo", default_config: {} },
    { key: "generic_html", name: "Genérico (HTML por seletores)", default_config: {} },
  ]);
}

/* ── categorias (leitura) ───────────────────────────────────────────── */

interface Categoria {
  id: number;
  parent_id: number | null;
  name: string;
  slug: string;
  path: string;
  is_active: number;
  sort_order: number;
  keywords: string | null;
  llm_hint: string | null;
  created_at: string;
}

interface Campo {
  id: number;
  category_id: number;
  key: string;
  label: string;
  field_type: string;
  unit: string | null;
  required: number;
  options: string | null;
  show_in_card: number;
  filterable: number;
  sort_order: number;
  description: string | null;
}

interface NoCategoria {
  id: number;
  name: string;
  slug: string;
  parent_id: number | null;
  is_active: boolean;
  sort_order: number;
  keywords: string[];
  llm_hint: string | null;
  path: string;
  created_at: string | null;
  items_count: number;
  fields: ReturnType<typeof campoSaida>[];
  children: NoCategoria[];
}

export async function listarCategorias(req: Request, env: Env): Promise<Response> {
  if (!(await administrador(req, env))) return naoAutorizado();
  const [cats, campos, contagens] = await env.DB.batch<Record<string, unknown>>([
    env.DB.prepare("SELECT * FROM categories ORDER BY sort_order, id"),
    env.DB.prepare("SELECT * FROM category_fields ORDER BY sort_order, id"),
    env.DB.prepare("SELECT category_id, COUNT(*) AS n FROM items GROUP BY category_id"),
  ]);
  const categorias = cats.results as unknown as Categoria[];
  const porId = new Map(categorias.map((c) => [c.id, c]));
  const itens = new Map(contagens.results.map((x) => [Number(x.category_id), Number(x.n)]));
  const proprios = new Map<number, Campo[]>();
  for (const f of campos.results as unknown as Campo[]) {
    (proprios.get(f.category_id) ?? proprios.set(f.category_id, []).get(f.category_id)!).push(f);
  }

  // RN-002: campo da categoria-mãe vale para as filhas; campo próprio com a
  // mesma chave sobrepõe. `inherited_from` diz de onde veio.
  const camposDe = (c: Categoria) => {
    const cadeia: Categoria[] = [];
    for (let atual: Categoria | undefined = c; atual; atual = atual.parent_id ? porId.get(atual.parent_id) : undefined) {
      cadeia.unshift(atual);
    }
    const porChave = new Map<string, ReturnType<typeof campoSaida>>();
    for (const anc of cadeia) {
      for (const f of proprios.get(anc.id) ?? []) {
        porChave.set(f.key, campoSaida(f, anc.id === c.id ? null : anc.slug));
      }
    }
    return [...porChave.values()].sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);
  };

  const noDe = (c: Categoria): NoCategoria => ({
    id: c.id, name: c.name, slug: c.slug, parent_id: c.parent_id,
    is_active: booleano(c.is_active), sort_order: c.sort_order,
    keywords: lerJson<string[]>(c.keywords, []), llm_hint: c.llm_hint, path: c.path,
    created_at: paraIso(c.created_at),
    items_count: itens.get(c.id) ?? 0,
    fields: camposDe(c),
    children: [],
  });

  const nos = new Map(categorias.map((c) => [c.id, noDe(c)]));
  const raizes: NoCategoria[] = [];
  for (const c of categorias) {
    const pai = c.parent_id ? nos.get(c.parent_id) : undefined;
    if (pai) pai.children.push(nos.get(c.id)!);
    else raizes.push(nos.get(c.id)!);
  }
  return Response.json(raizes);
}

function campoSaida(f: Campo, herdadoDe: string | null) {
  return {
    id: f.id, category_id: f.category_id, key: f.key, label: f.label, field_type: f.field_type,
    unit: f.unit, required: booleano(f.required),
    options: lerJson<string[] | null>(f.options, null),
    show_in_card: booleano(f.show_in_card), filterable: booleano(f.filterable),
    sort_order: f.sort_order, description: f.description,
    inherited_from: herdadoDe,
  };
}
