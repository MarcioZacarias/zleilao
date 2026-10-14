/**
 * API pública da vitrine. Leitura e serialização — sem parsing de HTML, que é
 * o que estoura o orçamento de CPU; estas rotas cabem folgadas nos 10 ms.
 *
 * O contrato é o mesmo do backend em Python (`docs/API.md`), para o dashboard
 * não precisar saber onde está rodando.
 */
import { booleano, lerJson, paraIso, paraReais } from "../lib/valores";
import type { Env } from "../tipos";
import { urlAsset } from "./marca";

const VISIVEIS = ["published", "auction_soon"];

/** Haversine em SQL puro, igual ao do Postgres. O D1 tem as funções de trigonometria. */
function distanciaSql(lat: number, lng: number): string {
  return `6371.0 * acos(MIN(1.0,
    cos(radians(${lat})) * cos(radians(items.lat)) * cos(radians(items.lng) - radians(${lng}))
    + sin(radians(${lat})) * sin(radians(items.lat))))`;
}

/** Retângulo que contém o círculo, para o índice (lat,lng) filtrar antes da trigonometria. */
function retangulo(lat: number, lng: number, raioKm: number) {
  const dLat = raioKm / 111.045;
  const cos = Math.cos((lat * Math.PI) / 180);
  const dLng = Math.abs(cos) > 1e-6 ? raioKm / (111.045 * cos) : 180;
  return { latMin: lat - dLat, latMax: lat + dLat, lngMin: lng - dLng, lngMax: lng + dLng };
}

export interface Filtros {
  q?: string;
  category?: string;
  brand?: string;
  model?: string;
  year_min?: number;
  year_max?: number;
  price_min?: number;
  price_max?: number;
  state?: string;
  city?: string;
  source?: string;
  condition?: string;
  auction_type?: string;
  status?: string;
  near?: { lat: number; lng: number; raio: number } | null;
}

/**
 * Monta o WHERE e os parâmetros.
 *
 * Devolve também o trecho de JOIN porque alguns filtros (busca textual,
 * categoria, pregão) exigem tabelas que nem toda consulta precisa.
 */
export function montarFiltro(f: Filtros) {
  const where: string[] = [];
  const params: unknown[] = [];
  const joins: string[] = [];

  const status = f.status && f.status !== "all" ? [f.status] : VISIVEIS;
  where.push(`items.status IN (${status.map(() => "?").join(",")})`);
  params.push(...status);

  if (f.q) {
    // FTS5 externo: casa o termo inteiro ou por prefixo, já que não há
    // stemming de português ("gol" precisa achar "Gol", "golzinho" não).
    joins.push("JOIN items_fts ON items_fts.rowid = items.id");
    where.push("items_fts MATCH ?");
    const termo = f.q.trim().replace(/["']/g, " ").trim();
    params.push(termo.split(/\s+/).map((t) => `"${t}"*`).join(" "));
  }
  if (f.category) {
    joins.push("JOIN categories ON categories.id = items.category_id");
    where.push("categories.path LIKE (SELECT path || '%' FROM categories WHERE slug = ?)");
    params.push(f.category);
  }
  if (f.brand) {
    where.push("LOWER(items.brand) = LOWER(?)");
    params.push(f.brand);
  }
  if (f.model) {
    where.push("items.model LIKE ?");
    params.push(`%${f.model}%`);
  }
  if (f.year_min !== undefined) { where.push("items.year_model >= ?"); params.push(f.year_min); }
  if (f.year_max !== undefined) { where.push("items.year_model <= ?"); params.push(f.year_max); }
  if (f.price_min !== undefined) { where.push("items.price_cents >= ?"); params.push(Math.round(f.price_min * 100)); }
  if (f.price_max !== undefined) { where.push("items.price_cents <= ?"); params.push(Math.round(f.price_max * 100)); }
  if (f.state) { where.push("items.state = ?"); params.push(f.state.toUpperCase()); }
  if (f.city) { where.push("items.city LIKE ?"); params.push(`%${f.city}%`); }
  if (f.source) {
    joins.push("JOIN sources ON sources.id = items.source_id");
    where.push("sources.slug = ?");
    params.push(f.source);
  }
  if (f.condition) { where.push("items.condition = ?"); params.push(f.condition); }
  if (f.auction_type) {
    joins.push("LEFT JOIN auctions ON auctions.id = items.auction_id");
    where.push("auctions.auction_type = ?");
    params.push(f.auction_type);
  }
  if (f.near) {
    const r = retangulo(f.near.lat, f.near.lng, f.near.raio);
    where.push("items.lat IS NOT NULL AND items.lng IS NOT NULL");
    where.push("items.lat BETWEEN ? AND ? AND items.lng BETWEEN ? AND ?");
    params.push(r.latMin, r.latMax, r.lngMin, r.lngMax);
    where.push(`${distanciaSql(f.near.lat, f.near.lng)} <= ?`);
    params.push(f.near.raio);
  }

  // JOIN repetido quebra a consulta; dois filtros podem pedir a mesma tabela.
  const unicos = [...new Set(joins)];
  return { where: where.join(" AND "), params, joins: unicos.join(" ") };
}

function lerFiltros(u: URL, near: Filtros["near"]): Filtros {
  const num = (k: string) => {
    const v = u.searchParams.get(k);
    if (v === null || v === "") return undefined;
    const n = Number(v);
    return Number.isFinite(n) ? n : undefined;
  };
  const txt = (k: string) => u.searchParams.get(k) || undefined;
  return {
    q: txt("q"), category: txt("category"), brand: txt("brand"), model: txt("model"),
    year_min: num("year_min"), year_max: num("year_max"),
    price_min: num("price_min"), price_max: num("price_max"),
    state: txt("state"), city: txt("city"), source: txt("source"),
    condition: txt("condition"), auction_type: txt("auction_type"), status: txt("status"),
    near,
  };
}

/** Linha do banco → card da vitrine, com RN-001 (fonte e data de coleta). */
export function serializarCard(r: Record<string, unknown>) {
  return {
    id: r.id,
    item_type: r.item_type,
    title: r.title,
    lot_number: r.lot_number,
    price: paraReais(r.price_cents as number | null),
    price_kind: r.price_kind,
    price_second: paraReais(r.price_second_cents as number | null),
    image_url: r.image_url,
    city: r.city,
    state: r.state,
    brand: r.brand,
    model: r.model,
    year_model: r.year_model,
    km: r.km,
    condition: r.condition,
    status: r.status,
    next_session_at: paraIso(r.next_session_at as string | null),
    last_seen_at: paraIso(r.last_seen_at as string | null),
    source_id: r.source_id,
    source_name: r.source_name ?? null,
    source_slug: r.source_slug ?? null,
    category_id: r.category_id,
    category_slug: r.category_slug ?? null,
    category_name: r.category_name ?? null,
    auction_id: r.auction_id,
    auction_type: r.auction_type ?? null,
    card_fields: {},
    possible_duplicate: false,
    opportunity_score: r.opportunity_score ?? null,
    opportunity_discount: r.discount_pct ?? null,
    distance_km: r.distance_km !== undefined && r.distance_km !== null
      ? Math.round((r.distance_km as number) * 10) / 10
      : null,
  };
}

export const SELECT_CARD = `
  items.id, items.item_type, items.title, items.lot_number, items.price_cents, items.price_kind,
  items.price_second_cents, items.image_url, items.city, items.state, items.brand, items.model,
  items.year_model, items.km, items.condition, items.status, items.next_session_at, items.last_seen_at,
  items.source_id, items.category_id, items.auction_id,
  s2.name AS source_name, s2.slug AS source_slug,
  c2.slug AS category_slug, c2.name AS category_name,
  a2.auction_type AS auction_type,
  o2.score AS opportunity_score, o2.discount_pct AS discount_pct`;

export const JOIN_CARD = `
  LEFT JOIN sources s2 ON s2.id = items.source_id
  LEFT JOIN categories c2 ON c2.id = items.category_id
  LEFT JOIN auctions a2 ON a2.id = items.auction_id
  LEFT JOIN item_opportunities o2 ON o2.item_id = items.id`;

export async function listarItens(u: URL, env: Env): Promise<Response> {
  // A cidade de referência vira coordenada antes de montar o filtro.
  let near: Filtros["near"] = null;
  const cidade = u.searchParams.get("near_city");
  const uf = u.searchParams.get("near_state");
  const raio = Number(u.searchParams.get("radius_km"));
  if (cidade && raio > 0) {
    const coord = await coordenadaDe(env, cidade, uf);
    if (!coord) {
      return Response.json(
        { detail: "Cidade de referência não reconhecida para a busca por raio" },
        { status: 400 },
      );
    }
    near = { ...coord, raio: Math.min(raio, 3000) };
  }

  const f = lerFiltros(u, near);
  const { where, params, joins } = montarFiltro(f);

  const page = Math.max(1, Number(u.searchParams.get("page")) || 1);
  const pageSize = Math.min(100, Math.max(1, Number(u.searchParams.get("page_size")) || 24));
  const sort = u.searchParams.get("sort") || "relevance";

  const total = await env.DB.prepare(`SELECT COUNT(*) AS n FROM items ${joins} WHERE ${where}`)
    .bind(...params)
    .first<{ n: number }>();

  let ordem: string;
  switch (sort) {
    case "price_asc": ordem = "items.price_cents IS NULL, items.price_cents ASC, items.id DESC"; break;
    case "price_desc": ordem = "items.price_cents IS NULL, items.price_cents DESC, items.id DESC"; break;
    case "newest": ordem = "items.first_seen_at DESC, items.id DESC"; break;
    case "distance":
      ordem = near ? `${distanciaSql(near.lat, near.lng)} ASC` : "items.next_session_at IS NULL, items.next_session_at ASC";
      break;
    case "opportunity":
      // Lote sem score vai para o fim: ausência de referência não é desconto zero.
      ordem = "o2.score IS NULL, o2.score DESC, items.next_session_at ASC";
      break;
    default: ordem = "items.next_session_at IS NULL, items.next_session_at ASC, items.first_seen_at DESC";
  }

  const distancia = near ? `, ${distanciaSql(near.lat, near.lng)} AS distance_km` : "";
  const sql = `SELECT ${SELECT_CARD}${distancia}
               FROM items ${joins} ${JOIN_CARD}
               WHERE ${where}
               ORDER BY ${ordem}
               LIMIT ? OFFSET ?`;
  const linhas = await env.DB.prepare(sql)
    .bind(...params, pageSize, (page - 1) * pageSize)
    .all<Record<string, unknown>>();

  const n = total?.n ?? 0;
  return Response.json({
    items: linhas.results.map(serializarCard),
    meta: { page, page_size: pageSize, total: n, pages: Math.max(1, Math.ceil(n / pageSize)) },
    facets: u.searchParams.get("facets") === "false" ? {} : await facetas(env, where, params, joins),
  });
}

async function facetas(env: Env, where: string, params: unknown[], joins: string) {
  const uma = async (col: string, rotulo?: string) => {
    const sel = rotulo ? `${col} AS value, ${rotulo} AS label` : `${col} AS value, ${col} AS label`;
    const r = await env.DB.prepare(
      `SELECT ${sel}, COUNT(*) AS count
         FROM items ${joins}
         LEFT JOIN sources sf ON sf.id = items.source_id
         LEFT JOIN categories cf ON cf.id = items.category_id
         LEFT JOIN auctions af ON af.id = items.auction_id
        WHERE ${where} AND ${col} IS NOT NULL
        GROUP BY ${col} ORDER BY COUNT(*) DESC LIMIT 30`,
    )
      .bind(...params)
      .all<{ value: string; label: string; count: number }>();
    return r.results;
  };
  return {
    states: await uma("items.state"),
    sources: await uma("sf.slug", "sf.name"),
    categories: await uma("cf.slug", "cf.name"),
    brands: await uma("items.brand"),
    conditions: await uma("items.condition"),
    auction_types: await uma("af.auction_type"),
  };
}

/** Busca a coordenada do município na tabela de apoio carregada no D1. */
export async function coordenadaDe(env: Env, cidade: string, uf: string | null): Promise<{ lat: number; lng: number } | null> {
  const chave = normalizarCidade(cidade);
  const r = await env.DB.prepare(
    `SELECT lat, lng FROM municipios WHERE nome_norm = ?${uf ? " AND uf = ?" : ""} LIMIT 1`,
  )
    .bind(...(uf ? [chave, uf.toUpperCase()] : [chave]))
    .first<{ lat: number; lng: number }>();
  return r ?? null;
}

/** "São Paulo" → "sao paulo"; tira acento e sufixo de UF. */
export function normalizarCidade(nome: string): string {
  return nome
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/\s*[-/(,]\s*[A-Za-z]{2}\s*\)?\s*$/, "")
    .toLowerCase()
    .replace(/[^a-z0-9\s'-]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export async function detalharItem(id: number, env: Env, req: Request): Promise<Response> {
  const r = await env.DB.prepare(
    `SELECT ${SELECT_CARD}, items.description, items.attributes, items.images, items.official_url,
            items.location_text, items.first_seen_at, items.year_fab, items.plate_hash,
            o2.reference_value_cents, o2.total_cost_cents, o2.reasons, o2.computed_at
       FROM items ${JOIN_CARD}
      WHERE items.id = ?`,
  )
    .bind(id)
    .first<Record<string, unknown>>();

  if (!r || !["published", "auction_soon", "closed"].includes(String(r.status))) {
    return Response.json({ detail: "Lote não encontrado ou fora da vitrine" }, { status: 404 });
  }

  // Abertura de ficha: denominador do CTR por fonte (F5). Robô não conta.
  const ua = req.headers.get("user-agent") ?? "";
  if (!/bot|crawler|spider|headless|curl|wget|python-requests/i.test(ua) && ua.length >= 10) {
    await contabilizar(env, r.source_id as number, "views");
  }

  const base = serializarCard(r);
  return Response.json({
    ...base,
    description: r.description,
    official_url: r.official_url,
    location_text: r.location_text,
    first_seen_at: paraIso(r.first_seen_at as string | null),
    year_fab: r.year_fab,
    plate_hash: r.plate_hash,
    images: lerJson<string[]>(r.images, []),
    attributes: lerJson<Record<string, unknown>>(r.attributes, {}),
    field_defs: [],
    duplicates: [],
    price_history: [],
    opportunity: r.opportunity_score === null || r.opportunity_score === undefined ? null : {
      score: r.opportunity_score,
      discount_pct: r.discount_pct,
      reference_value: String(paraReais(r.reference_value_cents as number) ?? ""),
      total_cost: String(paraReais(r.total_cost_cents as number) ?? ""),
      reference_label: null,
      computed_at: paraIso(r.computed_at as string | null),
      reasons: lerJson<Record<string, unknown>>(r.reasons, {}),
    },
  });
}

async function contabilizar(env: Env, sourceId: number, campo: "views" | "clicks"): Promise<void> {
  if (!sourceId) return;
  const dia = new Date(Date.now() - 3 * 3600 * 1000).toISOString().slice(0, 10);
  try {
    await env.DB.prepare(
      `INSERT INTO source_daily_stats (source_id, day, views, clicks) VALUES (?,?,?,?)
       ON CONFLICT (source_id, day) DO UPDATE SET ${campo} = ${campo} + 1`,
    )
      .bind(sourceId, dia, campo === "views" ? 1 : 0, campo === "clicks" ? 1 : 0)
      .run();
  } catch {
    // Métrica é subordinada à navegação: falhar aqui não pode derrubar a ficha.
  }
}

export async function irParaFonte(id: number, env: Env, req: Request): Promise<Response> {
  const r = await env.DB.prepare("SELECT official_url, source_id FROM items WHERE id = ?")
    .bind(id)
    .first<{ official_url: string; source_id: number }>();
  if (!r) return Response.json({ detail: "Lote não encontrado" }, { status: 404 });

  const ua = req.headers.get("user-agent") ?? "";
  if (!/bot|crawler|spider|headless|curl|wget/i.test(ua) && ua.length >= 10) {
    await contabilizar(env, r.source_id, "clicks");
    await env.DB.prepare("INSERT INTO click_events (item_id, source_id, clicked_at, referer) VALUES (?,?,?,?)")
      .bind(id, r.source_id, new Date(Date.now() - 3 * 3600 * 1000).toISOString().slice(0, 19).replace("T", " "),
            (req.headers.get("referer") ?? "").slice(0, 500))
      .run();
  }
  return Response.redirect(r.official_url, 302);
}

export async function estatisticas(env: Env): Promise<Response> {
  const r = await env.DB.prepare(
    `SELECT
       (SELECT COUNT(*) FROM items WHERE status IN ('published','auction_soon')) AS items_published,
       (SELECT COUNT(*) FROM auctions WHERE starts_at >= datetime('now','-3 hours')) AS auctions_upcoming,
       (SELECT COUNT(*) FROM sources WHERE is_active = 1) AS sources_active,
       (SELECT MAX(last_seen_at) FROM items) AS last_collected_at`,
  ).first<Record<string, unknown>>();
  return Response.json({
    items_published: r?.items_published ?? 0,
    auctions_upcoming: r?.auctions_upcoming ?? 0,
    sources_active: r?.sources_active ?? 0,
    last_collected_at: paraIso(r?.last_collected_at as string | null),
  });
}

export async function categorias(env: Env): Promise<Response> {
  const r = await env.DB.prepare(
    `SELECT c.id, c.parent_id, c.name, c.slug, c.path, c.sort_order,
            (SELECT COUNT(*) FROM items i
              WHERE i.category_id = c.id AND i.status IN ('published','auction_soon')) AS items_count
       FROM categories c WHERE c.is_active = 1 ORDER BY c.sort_order, c.id`,
  ).all<Record<string, unknown>>();

  // Árvore montada aqui: o dashboard espera `children`, e fazer isso no
  // cliente obrigaria cada tela a repetir a lógica.
  const porId = new Map<number, Record<string, unknown>>();
  for (const c of r.results) porId.set(c.id as number, { ...c, children: [] });
  const raiz: Record<string, unknown>[] = [];
  for (const c of porId.values()) {
    const pai = c.parent_id ? porId.get(c.parent_id as number) : null;
    if (pai) (pai.children as unknown[]).push(c);
    else raiz.push(c);
  }
  return Response.json(raiz);
}

export async function cidades(u: URL, env: Env): Promise<Response> {
  const q = normalizarCidade(u.searchParams.get("q") ?? "");
  if (q.length < 2) return Response.json([]);
  const limite = Math.min(20, Number(u.searchParams.get("limit")) || 8);
  const r = await env.DB.prepare(
    `SELECT nome, uf, lat, lng FROM municipios
      WHERE nome_norm LIKE ? AND apelido = 0
      ORDER BY (INSTR(nome_norm, ?) <> 1), populacao DESC
      LIMIT ?`,
  )
    .bind(`%${q}%`, q, limite)
    .all<{ nome: string; uf: string; lat: number; lng: number }>();
  return Response.json(r.results.map((c) => ({ city: c.nome, state: c.uf, lat: c.lat, lng: c.lng })));
}

export async function marcas(u: URL, env: Env): Promise<Response> {
  const r = await env.DB.prepare(
    `SELECT brand AS value, COUNT(*) AS count FROM items
      WHERE brand IS NOT NULL AND status IN ('published','auction_soon')
      GROUP BY brand ORDER BY COUNT(*) DESC LIMIT ?`,
  )
    .bind(Math.min(200, Number(u.searchParams.get("limit")) || 100))
    .all<{ value: string; count: number }>();
  return Response.json(r.results);
}

export async function modelos(u: URL, env: Env): Promise<Response> {
  const marca = u.searchParams.get("brand");
  if (!marca) return Response.json([]);
  const r = await env.DB.prepare(
    `SELECT model AS value, COUNT(*) AS count FROM items
      WHERE LOWER(brand) = LOWER(?) AND model IS NOT NULL
        AND status IN ('published','auction_soon')
      GROUP BY model ORDER BY COUNT(*) DESC LIMIT 100`,
  )
    .bind(marca)
    .all<{ value: string; count: number }>();
  return Response.json(r.results);
}

export async function pregoesProximos(u: URL, env: Env): Promise<Response> {
  const limite = Math.min(50, Number(u.searchParams.get("limit")) || 10);
  const r = await env.DB.prepare(
    `SELECT a.id, a.title, a.auction_type, a.modality, a.starts_at, a.official_url,
            s.name AS source_name, s.slug AS source_slug,
            COUNT(i.id) AS items_count
       FROM auctions a
       JOIN sources s ON s.id = a.source_id
       LEFT JOIN items i ON i.auction_id = a.id AND i.status IN ('published','auction_soon')
      WHERE a.starts_at >= datetime('now','-3 hours')
      GROUP BY a.id HAVING COUNT(i.id) > 0
      ORDER BY a.starts_at ASC LIMIT ?`,
  )
    .bind(limite)
    .all<Record<string, unknown>>();
  return Response.json(
    r.results.map((a) => ({
      id: a.id, title: a.title, auction_type: a.auction_type, modality: a.modality,
      starts_at: paraIso(a.starts_at as string | null), official_url: a.official_url,
      source_name: a.source_name, source_slug: a.source_slug,
      items_count: a.items_count, sessions: [],
    })),
  );
}

/** Página do pregão: dados do leilão, sessões (praças) e os lotes dele. */
export async function detalharPregao(id: number, env: Env): Promise<Response> {
  const [pregao, sessoes, lotes] = await env.DB.batch<Record<string, unknown>>([
    env.DB.prepare(
      `SELECT a.*, s.name AS source_name FROM auctions a
         LEFT JOIN sources s ON s.id = a.source_id WHERE a.id = ?`,
    ).bind(id),
    env.DB.prepare(
      "SELECT id, kind, sequence, starts_at, ends_at, min_bid_cents FROM auction_sessions WHERE auction_id = ? ORDER BY sequence, id",
    ).bind(id),
    // Encerrado entra: quem chega pelo link de um pregão que já passou ainda
    // quer ver o que foi a pregão.
    env.DB.prepare(
      `SELECT ${SELECT_CARD} FROM items ${JOIN_CARD}
        WHERE items.auction_id = ? AND items.status IN ('published','auction_soon','closed')
        ORDER BY items.lot_number IS NULL, CAST(items.lot_number AS INTEGER), items.lot_number, items.id`,
    ).bind(id),
  ]);
  const a = pregao.results[0];
  if (!a) return Response.json({ detail: "Pregão não encontrado" }, { status: 404 });

  return Response.json({
    auction: {
      id: a.id, source_id: a.source_id, source_name: a.source_name ?? null,
      external_id: a.external_id, title: a.title,
      auctioneer_name: a.auctioneer_name, auctioneer_registration: a.auctioneer_registration,
      committer_name: a.committer_name, modality: a.modality, auction_type: a.auction_type,
      official_url: a.official_url, status: a.status,
      starts_at: paraIso(a.starts_at as string | null), ends_at: paraIso(a.ends_at as string | null),
      sessions: sessoes.results.map((x) => ({
        id: x.id, kind: x.kind, sequence: x.sequence,
        starts_at: paraIso(x.starts_at as string | null), ends_at: paraIso(x.ends_at as string | null),
        min_bid: x.min_bid_cents === null ? null : String(paraReais(x.min_bid_cents as number)),
      })),
      items_count: lotes.results.length,
    },
    items: lotes.results.map(serializarCard),
  });
}

/**
 * Identidade visual e textos da vitrine: textos de `system_settings`,
 * imagens de `branding_assets`. Chave sem imagem enviada sai `null`, e o
 * dashboard cai no SVG do pacote.
 */
export async function branding(env: Env, origem: string): Promise<Response> {
  const [cfg, imagens] = await env.DB.batch<Record<string, string>>([
    env.DB.prepare(
      `SELECT key, value FROM system_settings
        WHERE key IN ('brand_site_title','brand_tagline','portal_disclaimer')`,
    ),
    env.DB.prepare("SELECT key, updated_at FROM branding_assets"),
  ]);
  const v = new Map(cfg.results.map((x) => [x.key, x.value]));
  const enviadas = new Map(imagens.results.map((x) => [x.key, x.updated_at]));
  const url = (k: string) => (enviadas.has(k) ? urlAsset(origem, k, enviadas.get(k)!) : null);
  return Response.json({
    logo_dark: url("logo_dark"),
    logo_light: url("logo_light"),
    favicon: url("favicon"),
    site_title: v.get("brand_site_title") || "ZConnect Leilão",
    tagline: v.get("brand_tagline") || "",
    disclaimer: v.get("portal_disclaimer") || "",
  });
}

/**
 * Configuração de publicidade que a vitrine precisa conhecer.
 *
 * Só o necessário para montar o bloco: nada aqui é segredo, e o cliente
 * precisa saber de antemão se deve reservar espaço — anúncio que aparece
 * depois empurra o conteúdo e é pior que anúncio nenhum.
 */
export async function anuncios(env: Env): Promise<Response> {
  const r = await env.DB.prepare(
    `SELECT key, value FROM system_settings WHERE "group" = 'ads'`,
  ).all<{ key: string; value: string }>();
  const v = new Map(r.results.map((x) => [x.key, x.value]));
  const ligado = v.get("ads_enabled") === "1";
  const origem = v.get("ads_provider") || "proprio";

  const proprio = (pos: string) => {
    const imagem = v.get(`ads_proprio_${pos}_imagem`) || "";
    const alvo = v.get(`ads_proprio_${pos}_alvo`) || "";
    return imagem && alvo ? { imagem, alvo, texto: v.get(`ads_proprio_${pos}_texto`) || "" } : null;
  };
  const adsense = (pos: string) => {
    const slot = v.get(`ads_adsense_slot_${pos}`) || "";
    return slot ? { slot } : null;
  };

  return Response.json({
    enabled: ligado,
    provider: origem,
    adsense_client: origem === "adsense" ? v.get("ads_adsense_client") || "" : "",
    intervalo_cards: Number(v.get("ads_intervalo_cards") || 12),
    posicoes: {
      busca: !ligado ? null : origem === "adsense" ? adsense("busca") : proprio("busca"),
      ficha: !ligado ? null : origem === "adsense" ? adsense("ficha") : proprio("ficha"),
    },
  });
}

/** Impressão e clique por posição, agregados por dia. */
export async function registrarAnuncio(req: Request, env: Env): Promise<Response> {
  let corpo: { posicao?: string; tipo?: string };
  try {
    corpo = (await req.json()) as { posicao?: string; tipo?: string };
  } catch {
    return Response.json({ ok: false }, { status: 400 });
  }
  const pos = corpo.posicao === "ficha" ? "ficha" : "busca";
  const tipo = corpo.tipo === "clique" ? "clique" : "impressao";
  const dia = new Date(Date.now() - 3 * 3600 * 1000).toISOString().slice(0, 10);
  try {
    await env.DB.prepare(
      `INSERT INTO ad_events (posicao, tipo, dia, total) VALUES (?,?,?,1)
       ON CONFLICT (posicao, tipo, dia) DO UPDATE SET total = total + 1`,
    )
      .bind(pos, tipo, dia)
      .run();
  } catch {
    // Métrica não derruba a página.
  }
  return Response.json({ ok: true });
}

/**
 * Sitemap das fichas de lote.
 *
 * Importa por dois motivos: é como o buscador acha as fichas (a vitrine é um
 * SPA, e sem sitemap o rastreador depende de seguir links), e uma rede de
 * publicidade que avalia o site olha se as páginas são indexáveis.
 *
 * Só lotes visíveis entram. Apontar o buscador para ficha encerrada gera
 * visita que termina em decepção, e isso conta contra o domínio.
 */
export async function sitemap(env: Env, origem: string): Promise<Response> {
  const r = await env.DB.prepare(
    `SELECT id, last_seen_at FROM items
      WHERE status IN ('published','auction_soon')
      ORDER BY last_seen_at DESC LIMIT 5000`,
  ).all<{ id: number; last_seen_at: string }>();

  const estaticas = ["", "/busca", "/pregoes", "/privacidade", "/termos"];
  const partes: string[] = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
  ];
  for (const p of estaticas) {
    partes.push(
      `<url><loc>${origem}${p}</loc><changefreq>${p === "" || p === "/busca" ? "hourly" : "monthly"}</changefreq></url>`,
    );
  }
  for (const it of r.results) {
    const d = (it.last_seen_at || "").slice(0, 10);
    partes.push(`<url><loc>${origem}/lote/${it.id}</loc>${d ? `<lastmod>${d}</lastmod>` : ""}<changefreq>daily</changefreq></url>`);
  }
  partes.push("</urlset>");

  return new Response(partes.join("\n"), {
    headers: {
      "content-type": "application/xml; charset=utf-8",
      // O conteúdo muda a cada coleta; uma hora de cache evita refazer a
      // consulta a cada passagem de rastreador.
      "cache-control": "public, max-age=3600",
    },
  });
}
