/**
 * Conta do assinante: cadastro, verificação de e-mail, senha, perfil,
 * filtros salvos e histórico de alertas.
 *
 * Porte de `backend/app/v1/account.py`, com o mesmo contrato — o dashboard
 * não sabe se está falando com o Python ou com o Worker. As regras também
 * são as mesmas: cadastro público, verificação antes de alertar e limite de
 * filtros por plano (RN-007).
 *
 * O que não veio junto é o disparo dos alertas: o matcher roda no agente
 * local, que é quem tem CPU para avaliar filtro contra lote novo.
 */
import { bloqueada, conferirSenha, gerarHash, gerarToken, registrarFalha } from "../lib/auth";
import { EmailIndisponivel, emailRedefinicao, emailVerificacao, enviarEmail } from "../lib/email";
import { agora, booleano, deDataParaBanco, lerJson, paraIso } from "../lib/valores";
import type { Env } from "../tipos";
import { sessaoDe } from "./admin";
import {
  JOIN_CARD, SELECT_CARD, coordenadaDe, montarFiltro, serializarCard, type Filtros,
} from "./portal";

/* ── utilidades ─────────────────────────────────────────────────────── */

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

async function setting(env: Env, chave: string, padrao: string): Promise<string> {
  const r = await env.DB.prepare("SELECT value FROM system_settings WHERE key = ?")
    .bind(chave)
    .first<{ value: string | null }>();
  return r?.value ?? padrao;
}

async function settingBool(env: Env, chave: string, padrao: boolean): Promise<boolean> {
  const v = (await setting(env, chave, padrao ? "true" : "false")).trim().toLowerCase();
  return ["1", "true", "yes", "sim", "on"].includes(v);
}

async function settingInt(env: Env, chave: string, padrao: number): Promise<number> {
  const n = parseInt(await setting(env, chave, String(padrao)), 10);
  return Number.isFinite(n) ? n : padrao;
}

/** Validação de forma, não de existência — essa é o e-mail de verificação. */
function emailValido(e: string): boolean {
  return e.length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(e);
}

/** '(11) 98765-4321' → '5511987654321'. Null se não parecer válido. */
function normalizarTelefone(bruto: string | null | undefined): string | null {
  if (!bruto) return null;
  let d = bruto.replace(/\D/g, "");
  if (d.startsWith("00")) d = d.slice(2);
  if (!d.startsWith("55")) d = "55" + d;
  return d.length >= 12 && d.length <= 13 ? d : null;
}

async function hashToken(token: string): Promise<string> {
  const h = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(token));
  return [...new Uint8Array(h)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function tokenAleatorio(): string {
  const b = crypto.getRandomValues(new Uint8Array(32));
  let s = "";
  for (const x of b) s += String.fromCharCode(x);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function emitirToken(env: Env, userId: number, tipo: string): Promise<string> {
  const ttl = await settingInt(env, "token_ttl_hours", 48);
  const token = tokenAleatorio();
  await env.DB.prepare(
    "INSERT INTO auth_tokens (user_id, kind, token_hash, expires_at, created_at) VALUES (?,?,?,?,?)",
  )
    .bind(userId, tipo, await hashToken(token), deDataParaBanco(new Date(Date.now() + ttl * 3600_000)), agora())
    .run();
  return token;
}

/** Marca o token como usado e devolve o id do usuário, ou null se não vale. */
async function consumirToken(env: Env, token: string, tipo: string): Promise<number | null> {
  if (!token) return null;
  const r = await env.DB.prepare(
    "SELECT id, user_id, expires_at, used_at FROM auth_tokens WHERE token_hash = ? AND kind = ?",
  )
    .bind(await hashToken(token), tipo)
    .first<{ id: number; user_id: number; expires_at: string; used_at: string | null }>();
  const ts = agora();
  if (!r || r.used_at || r.expires_at < ts) return null;
  await env.DB.prepare("UPDATE auth_tokens SET used_at = ? WHERE id = ?").bind(ts, r.id).run();
  return r.user_id;
}

async function baseUrl(env: Env): Promise<string> {
  return (await setting(env, "public_base_url", "")).replace(/\/+$/, "");
}

/** Envia sem deixar a falha do provedor virar erro para o usuário. */
async function tentarEnviar(env: Env, para: string, [assunto, html]: [string, string]): Promise<boolean> {
  try {
    await enviarEmail(env, para, assunto, html);
    return true;
  } catch (e) {
    if (!(e instanceof EmailIndisponivel)) console.error("falha no envio de e-mail", e);
    else console.warn("e-mail não enviado:", e.message);
    return false;
  }
}

interface Usuario {
  id: number;
  email: string;
  name: string | null;
  role: string;
  is_active: number;
  hashed_password: string;
  phone: string | null;
  email_opt_in: number;
  whatsapp_opt_in: number;
  email_verified_at: string | null;
  quiet_start: string | null;
  quiet_end: string | null;
}

/** Sessão do token + linha atual do banco. Conta apagada ou desativada não passa. */
async function usuarioDaSessao(req: Request, env: Env): Promise<Usuario | null> {
  const s = await sessaoDe(req, env);
  if (!s) return null;
  const u = await env.DB.prepare("SELECT * FROM users WHERE id = ?").bind(s.id).first<Usuario>();
  return u && u.is_active === 1 ? u : null;
}

const naoAutenticado = () => erro(401, "Não autenticado");

async function planoDe(env: Env, userId: number) {
  const sub = await env.DB.prepare(
    "SELECT plan, status, current_period_end FROM subscriptions WHERE user_id = ? ORDER BY id DESC LIMIT 1",
  )
    .bind(userId)
    .first<{ plan: string; status: string; current_period_end: string | null }>();
  const plano = sub && sub.status === "active" ? sub.plan : "free";
  return { plano, sub };
}

async function limiteFiltros(env: Env, plano: string): Promise<number> {
  return plano === "pro"
    ? await settingInt(env, "pro_max_filters", 30)
    : await settingInt(env, "free_max_filters", 3);
}

async function filtrosUsados(env: Env, userId: number): Promise<number> {
  const r = await env.DB.prepare("SELECT COUNT(*) AS n FROM saved_filters WHERE user_id = ?")
    .bind(userId)
    .first<{ n: number }>();
  return r?.n ?? 0;
}

/* ── critérios do filtro (porte de engine/search.py) ─────────────────── */

const CHAVES = [
  "q", "category", "brand", "model", "year_min", "year_max", "price_min", "price_max",
  "state", "city", "source", "condition", "auction_type",
  "near_city", "near_state", "radius_km",
] as const;
const INTEIRAS = new Set(["year_min", "year_max"]);
const DECIMAIS = new Set(["price_min", "price_max", "radius_km"]);

type Criterios = Record<string, string | number>;

/** Descarta chave desconhecida e coage tipo. Critério vazio vale "qualquer lote novo". */
export function normalizarCriterios(bruto: unknown): Criterios {
  const ent = (bruto && typeof bruto === "object" ? bruto : {}) as Record<string, unknown>;
  const out: Criterios = {};
  for (const k of CHAVES) {
    const v = ent[k];
    if (v === null || v === undefined || (typeof v === "string" && !v.trim())) continue;
    if (INTEIRAS.has(k)) {
      const n = Math.trunc(Number(v));
      if (Number.isFinite(n)) out[k] = n;
    } else if (DECIMAIS.has(k)) {
      const n = Number(v);
      if (Number.isFinite(n)) out[k] = n;
    } else {
      out[k] = String(v).trim().slice(0, 120);
    }
  }
  return out;
}

const ROTULOS: Record<string, string> = {
  q: "busca", category: "categoria", brand: "marca", model: "modelo",
  year_min: "ano de", year_max: "ano ate", price_min: "preco de",
  price_max: "preco ate", state: "UF", city: "cidade", source: "fonte",
  condition: "condicao", auction_type: "tipo",
};

export function descreverCriterios(c: Criterios): string {
  const raio = Boolean(c.near_city);
  const partes = Object.entries(c)
    .filter(([k, v]) => v !== "" && !(raio && ["near_city", "near_state", "radius_km"].includes(k)))
    .map(([k, v]) => `${ROTULOS[k] ?? k}: ${v}`);
  if (raio) {
    const uf = c.near_state ? `/${c.near_state}` : "";
    partes.push(`ate ${c.radius_km || 100} km de ${c.near_city}${uf}`);
  }
  return partes.length ? partes.join(", ") : "todos os lotes";
}

function canaisValidos(bruto: unknown, whatsappLigado: boolean): string[] {
  const lista = Array.isArray(bruto) ? bruto.map(String) : [];
  const ok = lista.filter((c) => c === "email" || (c === "whatsapp" && whatsappLigado));
  return ok.length ? [...new Set(ok)] : ["email"];
}

function filtroSaida(f: Record<string, unknown>) {
  const criteria = normalizarCriterios(lerJson(f.criteria, {}));
  return {
    id: f.id,
    name: f.name,
    criteria,
    channels: lerJson<string[]>(f.channels, []),
    is_active: booleano(f.is_active),
    last_matched_at: paraIso(f.last_matched_at as string | null),
    matches_count: f.matches_count ?? 0,
    created_at: paraIso(f.created_at as string | null),
    description: descreverCriterios(criteria),
  };
}

/* ── cadastro e verificação ─────────────────────────────────────────── */

export async function cadastrar(req: Request, env: Env): Promise<Response> {
  if (!(await settingBool(env, "signup_enabled", true))) {
    return erro(403, "Cadastro temporariamente fechado");
  }

  // Cada tentativa conta, não só as que falham: cadastro em massa a partir
  // de um IP é abuso mesmo quando cada um "dá certo".
  const origem = `cadastro:${req.headers.get("cf-connecting-ip") || "desconhecida"}`;
  if (await bloqueada(env.DB, origem, 10)) {
    return erro(429, "Muitos cadastros a partir desta rede hoje. Tente novamente amanhã.");
  }
  await registrarFalha(env.DB, origem);

  const c = await corpoJson<{ name?: string; email?: string; password?: string; phone?: string | null }>(req);
  if (!c) return erro(400, "Corpo inválido");
  const nome = (c.name || "").trim();
  const email = (c.email || "").trim().toLowerCase();
  const senha = c.password || "";
  if (nome.length < 2 || nome.length > 100) return erro(422, "Informe seu nome (2 a 100 caracteres)");
  if (!emailValido(email)) return erro(422, "E-mail inválido");
  if (senha.length < 8 || senha.length > 200) return erro(422, "A senha precisa ter ao menos 8 caracteres");

  const telefone = c.phone ? normalizarTelefone(c.phone) : null;
  if (c.phone && !telefone) return erro(400, "Telefone inválido. Use DDD + número.");

  const existe = await env.DB.prepare("SELECT 1 FROM users WHERE email = ?").bind(email).first();
  if (existe) {
    // Não confirma nem nega a existência da conta para quem não está logado.
    return erro(409, "Não foi possível criar a conta com esse e-mail");
  }

  const exigeVerificacao = await settingBool(env, "require_email_verification", true);
  const ts = agora();
  const hash = await gerarHash(senha);
  try {
    await env.DB.batch([
      env.DB.prepare(
        `INSERT INTO users (email, hashed_password, name, role, is_active, phone,
                            whatsapp_opt_in, email_opt_in, email_verified_at, created_at)
         VALUES (?,?,?,'user',1,?,0,1,?,?)`,
      ).bind(email, hash, nome, telefone, exigeVerificacao ? null : ts, ts),
      env.DB.prepare(
        `INSERT INTO subscriptions (user_id, plan, status, started_at, provider, updated_at)
         SELECT id, 'free', 'active', ?, 'manual', ? FROM users WHERE email = ?`,
      ).bind(ts, ts, email),
    ]);
  } catch (e) {
    // Dois envios simultâneos do mesmo e-mail: o segundo bate no UNIQUE.
    if (String(e).includes("UNIQUE")) return erro(409, "Não foi possível criar a conta com esse e-mail");
    throw e;
  }

  let enviado = false;
  if (exigeVerificacao) {
    const u = await env.DB.prepare("SELECT id FROM users WHERE email = ?").bind(email).first<{ id: number }>();
    const token = await emitirToken(env, u!.id, "verify_email");
    const base = await baseUrl(env);
    enviado = await tentarEnviar(env, email, emailVerificacao(`${base}/verificar-email?token=${token}`, base));
  }

  return Response.json(
    {
      status: "ok",
      verification_required: exigeVerificacao,
      verification_sent: enviado,
      detail: enviado
        ? "Enviamos um e-mail de confirmação."
        : "Conta criada. O e-mail de confirmação não pôde ser enviado agora — peça o reenvio.",
    },
    { status: 201 },
  );
}

export async function verificarEmail(u: URL, env: Env): Promise<Response> {
  const id = await consumirToken(env, u.searchParams.get("token") || "", "verify_email");
  if (!id) return erro(400, "Link inválido ou expirado. Peça um novo.");
  await env.DB.prepare("UPDATE users SET email_verified_at = COALESCE(email_verified_at, ?) WHERE id = ?")
    .bind(agora(), id)
    .run();
  const r = await env.DB.prepare("SELECT email FROM users WHERE id = ?").bind(id).first<{ email: string }>();
  if (!r) return erro(400, "Conta não encontrada");
  return Response.json({ status: "ok", email: r.email });
}

/** Resposta igual exista ou não a conta, para não vazar quem tem cadastro. */
const RESPOSTA_NEUTRA = { status: "ok", detail: "Se houver uma conta com esse e-mail, enviamos o link." };

export async function reenviarVerificacao(req: Request, env: Env): Promise<Response> {
  const c = await corpoJson<{ email?: string }>(req);
  const email = (c?.email || "").trim().toLowerCase();
  const u = await env.DB.prepare("SELECT id, email_verified_at FROM users WHERE email = ?")
    .bind(email)
    .first<{ id: number; email_verified_at: string | null }>();
  if (u && !u.email_verified_at) {
    const token = await emitirToken(env, u.id, "verify_email");
    const base = await baseUrl(env);
    await tentarEnviar(env, email, emailVerificacao(`${base}/verificar-email?token=${token}`, base));
  }
  return Response.json(RESPOSTA_NEUTRA);
}

export async function esqueciSenha(req: Request, env: Env): Promise<Response> {
  const c = await corpoJson<{ email?: string }>(req);
  const email = (c?.email || "").trim().toLowerCase();
  const u = await env.DB.prepare("SELECT id, is_active FROM users WHERE email = ?")
    .bind(email)
    .first<{ id: number; is_active: number }>();
  if (u && u.is_active === 1) {
    const token = await emitirToken(env, u.id, "reset_password");
    const base = await baseUrl(env);
    await tentarEnviar(env, email, emailRedefinicao(`${base}/redefinir-senha?token=${token}`, base));
  }
  return Response.json(RESPOSTA_NEUTRA);
}

export async function redefinirSenha(req: Request, env: Env): Promise<Response> {
  if (!env.JWT_SECRET) return erro(500, "JWT_SECRET não configurado no Worker");
  const c = await corpoJson<{ token?: string; new_password?: string }>(req);
  const nova = c?.new_password || "";
  if (nova.length < 8 || nova.length > 200) return erro(422, "A nova senha precisa ter ao menos 8 caracteres");
  const id = await consumirToken(env, c?.token || "", "reset_password");
  if (!id) return erro(400, "Link inválido ou expirado. Peça um novo.");

  // Quem provou controlar a caixa de e-mail também verificou o endereço.
  await env.DB.prepare(
    "UPDATE users SET hashed_password = ?, email_verified_at = COALESCE(email_verified_at, ?) WHERE id = ?",
  )
    .bind(await gerarHash(nova), agora(), id)
    .run();
  const u = await env.DB.prepare("SELECT id, email, name, role FROM users WHERE id = ?")
    .bind(id)
    .first<{ id: number; email: string; name: string | null; role: string }>();
  if (!u) return erro(400, "Conta não encontrada");
  const token = await gerarToken({ sub: u.id, email: u.email, role: u.role }, env.JWT_SECRET);
  return Response.json({
    status: "ok", access_token: token, token_type: "bearer",
    user_email: u.email, user_name: u.name, role: u.role,
  });
}

/* ── perfil ─────────────────────────────────────────────────────────── */

async function perfil(env: Env, u: Usuario) {
  const { plano, sub } = await planoDe(env, u.id);
  return {
    id: u.id, email: u.email, name: u.name, role: u.role,
    phone: u.phone,
    email_opt_in: booleano(u.email_opt_in),
    whatsapp_opt_in: booleano(u.whatsapp_opt_in),
    email_verified: u.email_verified_at !== null,
    quiet_start: u.quiet_start, quiet_end: u.quiet_end,
    plan: plano,
    plan_status: sub?.status ?? "active",
    plan_expires_at: paraIso(sub?.current_period_end ?? null),
    filters_used: await filtrosUsados(env, u.id),
    filters_limit: await limiteFiltros(env, plano),
    whatsapp_channel_available: await settingBool(env, "whatsapp_enabled", false),
    realtime_alerts: plano === "pro",
  };
}

export async function meuPerfil(req: Request, env: Env): Promise<Response> {
  const u = await usuarioDaSessao(req, env);
  if (!u) return naoAutenticado();
  return Response.json(await perfil(env, u));
}

export async function atualizarPerfil(req: Request, env: Env): Promise<Response> {
  const u = await usuarioDaSessao(req, env);
  if (!u) return naoAutenticado();
  const c = await corpoJson<Record<string, unknown>>(req);
  if (!c) return erro(400, "Corpo inválido");

  if ("phone" in c) {
    if (c.phone) {
      const tel = normalizarTelefone(String(c.phone));
      if (!tel) return erro(400, "Telefone inválido. Use DDD + número.");
      u.phone = tel;
    } else {
      u.phone = null;
      u.whatsapp_opt_in = 0;
    }
  }
  if (c.whatsapp_opt_in && !u.phone) return erro(400, "Cadastre um telefone antes de ativar o WhatsApp");
  if ("name" in c && c.name !== undefined) u.name = c.name ? String(c.name).trim().slice(0, 100) : null;
  if ("email_opt_in" in c) u.email_opt_in = c.email_opt_in ? 1 : 0;
  if ("whatsapp_opt_in" in c) u.whatsapp_opt_in = c.whatsapp_opt_in ? 1 : 0;
  if ("quiet_start" in c) u.quiet_start = c.quiet_start ? String(c.quiet_start).slice(0, 5) : null;
  if ("quiet_end" in c) u.quiet_end = c.quiet_end ? String(c.quiet_end).slice(0, 5) : null;

  await env.DB.prepare(
    `UPDATE users SET name = ?, phone = ?, email_opt_in = ?, whatsapp_opt_in = ?,
                      quiet_start = ?, quiet_end = ? WHERE id = ?`,
  )
    .bind(u.name, u.phone, u.email_opt_in, u.whatsapp_opt_in, u.quiet_start, u.quiet_end, u.id)
    .run();
  return Response.json(await perfil(env, u));
}

export async function trocarSenha(req: Request, env: Env): Promise<Response> {
  const u = await usuarioDaSessao(req, env);
  if (!u) return naoAutenticado();
  const c = await corpoJson<{ current_password?: string; new_password?: string }>(req);
  const nova = c?.new_password || "";
  if (!(await conferirSenha(c?.current_password || "", u.hashed_password))) {
    return erro(400, "Senha atual incorreta");
  }
  if (nova.length < 8 || nova.length > 200) return erro(400, "A nova senha precisa ter ao menos 8 caracteres");
  await env.DB.prepare("UPDATE users SET hashed_password = ? WHERE id = ?")
    .bind(await gerarHash(nova), u.id)
    .run();
  return Response.json({ status: "ok" });
}

/* ── filtros salvos ─────────────────────────────────────────────────── */

export async function listarFiltros(req: Request, env: Env): Promise<Response> {
  const u = await usuarioDaSessao(req, env);
  if (!u) return naoAutenticado();
  const r = await env.DB.prepare("SELECT * FROM saved_filters WHERE user_id = ? ORDER BY created_at DESC, id DESC")
    .bind(u.id)
    .all<Record<string, unknown>>();
  const { plano } = await planoDe(env, u.id);
  return Response.json({
    filters: r.results.map(filtroSaida),
    limit: await limiteFiltros(env, plano),
    plan: plano,
  });
}

interface EntradaFiltro {
  name?: string | null;
  criteria?: unknown;
  channels?: unknown;
  is_active?: boolean;
}

export async function criarFiltro(req: Request, env: Env): Promise<Response> {
  const u = await usuarioDaSessao(req, env);
  if (!u) return naoAutenticado();
  const c = await corpoJson<EntradaFiltro>(req);
  if (!c) return erro(400, "Corpo inválido");

  const { plano } = await planoDe(env, u.id);
  const limite = await limiteFiltros(env, plano);
  if ((await filtrosUsados(env, u.id)) >= limite) {
    return erro(403, `Seu plano permite ${limite} filtro(s) salvo(s). Remova um ou mude de plano para criar mais.`);
  }

  const criterios = normalizarCriterios(c.criteria);
  const canais = canaisValidos(c.channels, await settingBool(env, "whatsapp_enabled", false));
  const nome = (c.name || descreverCriterios(criterios)).slice(0, 120);
  const ts = agora();
  // Nasce já avaliado (last_checked_at = agora): sem isso o usuário recebe
  // de imediato tudo que foi publicado na janela de lookback, o que parece spam.
  const r = await env.DB.prepare(
    `INSERT INTO saved_filters (user_id, name, criteria, channels, is_active, last_checked_at,
                                matches_count, created_at, updated_at)
     VALUES (?,?,?,?,?,?,0,?,?) RETURNING *`,
  )
    .bind(u.id, nome, JSON.stringify(criterios), JSON.stringify(canais), c.is_active === false ? 0 : 1, ts, ts, ts)
    .first<Record<string, unknown>>();
  return Response.json(filtroSaida(r!), { status: 201 });
}

export async function alterarFiltro(id: number, req: Request, env: Env): Promise<Response> {
  const u = await usuarioDaSessao(req, env);
  if (!u) return naoAutenticado();
  const c = await corpoJson<EntradaFiltro>(req);
  if (!c) return erro(400, "Corpo inválido");

  const criterios = normalizarCriterios(c.criteria);
  const canais = canaisValidos(c.channels, await settingBool(env, "whatsapp_enabled", false));
  const r = await env.DB.prepare(
    `UPDATE saved_filters SET name = ?, criteria = ?, channels = ?, is_active = ?, updated_at = ?
      WHERE id = ? AND user_id = ? RETURNING *`,
  )
    .bind(
      (c.name || descreverCriterios(criterios)).slice(0, 120),
      JSON.stringify(criterios), JSON.stringify(canais), c.is_active === false ? 0 : 1, agora(),
      id, u.id,
    )
    .first<Record<string, unknown>>();
  if (!r) return erro(404, "Filtro não encontrado");
  return Response.json(filtroSaida(r));
}

export async function apagarFiltro(id: number, req: Request, env: Env): Promise<Response> {
  const u = await usuarioDaSessao(req, env);
  if (!u) return naoAutenticado();
  const r = await env.DB.prepare("DELETE FROM saved_filters WHERE id = ? AND user_id = ?").bind(id, u.id).run();
  if (!r.meta.changes) return erro(404, "Filtro não encontrado");
  return Response.json({ status: "ok" });
}

/** Mostra o que o filtro pegaria hoje — o usuário confere antes de esperar o alerta. */
export async function previaFiltro(id: number, u0: URL, req: Request, env: Env): Promise<Response> {
  const u = await usuarioDaSessao(req, env);
  if (!u) return naoAutenticado();
  const f = await env.DB.prepare("SELECT criteria FROM saved_filters WHERE id = ? AND user_id = ?")
    .bind(id, u.id)
    .first<{ criteria: string }>();
  if (!f) return erro(404, "Filtro não encontrado");

  const c = normalizarCriterios(lerJson(f.criteria, {}));
  let near: Filtros["near"] = null;
  if (c.near_city && Number(c.radius_km) > 0) {
    const coord = await coordenadaDe(env, String(c.near_city), c.near_state ? String(c.near_state) : null);
    if (coord) near = { ...coord, raio: Math.min(Number(c.radius_km), 3000) };
  }
  const txt = (k: string) => (c[k] !== undefined ? String(c[k]) : undefined);
  const num = (k: string) => (c[k] !== undefined ? Number(c[k]) : undefined);
  const { where, params, joins } = montarFiltro({
    q: txt("q"), category: txt("category"), brand: txt("brand"), model: txt("model"),
    year_min: num("year_min"), year_max: num("year_max"),
    price_min: num("price_min"), price_max: num("price_max"),
    state: txt("state"), city: txt("city"), source: txt("source"),
    condition: txt("condition"), auction_type: txt("auction_type"),
    near,
  });

  const limite = Math.min(24, Math.max(1, Number(u0.searchParams.get("limit")) || 6));
  const [total, linhas] = await env.DB.batch<Record<string, unknown>>([
    env.DB.prepare(`SELECT COUNT(*) AS n FROM items ${joins} WHERE ${where}`).bind(...params),
    env.DB.prepare(
      `SELECT ${SELECT_CARD} FROM items ${joins} ${JOIN_CARD}
        WHERE ${where}
        ORDER BY items.first_seen_at DESC, items.id DESC LIMIT ?`,
    ).bind(...params, limite),
  ]);
  return Response.json({
    total: Number(total.results[0]?.n ?? 0),
    items: linhas.results.map(serializarCard),
  });
}

/* ── alertas recebidos ──────────────────────────────────────────────── */

export async function meusAlertas(u0: URL, req: Request, env: Env): Promise<Response> {
  const u = await usuarioDaSessao(req, env);
  if (!u) return naoAutenticado();
  const limite = Math.min(200, Math.max(1, Number(u0.searchParams.get("limit")) || 50));
  const r = await env.DB.prepare(
    `SELECT al.id AS alert_id, al.reason, al.status AS alert_status, al.channel, al.detail,
            al.created_at AS alert_created_at, al.sent_at, al.saved_filter_id,
            ${SELECT_CARD}
       FROM alerts al
       LEFT JOIN items ON items.id = al.item_id
       ${JOIN_CARD}
      WHERE al.user_id = ?
      ORDER BY al.created_at DESC, al.id DESC LIMIT ?`,
  )
    .bind(u.id, limite)
    .all<Record<string, unknown>>();
  return Response.json(
    r.results.map((a) => ({
      id: a.alert_id,
      reason: a.reason,
      status: a.alert_status,
      channel: a.channel,
      detail: a.detail,
      created_at: paraIso(a.alert_created_at as string | null),
      sent_at: paraIso(a.sent_at as string | null),
      saved_filter_id: a.saved_filter_id,
      item: a.id ? serializarCard(a) : null,
    })),
  );
}
