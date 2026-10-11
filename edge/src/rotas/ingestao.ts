/**
 * Ingestão: recebe do agente local os lotes já normalizados e grava no D1.
 *
 * A divisão de trabalho é deliberada. Tudo que custa CPU — buscar as páginas,
 * parsear HTML, extrair marca e modelo, classificar categoria — acontece no
 * computador que roda a coleta, onde não há teto de 10 ms e onde o cliente
 * HTTP aceita ignorar certificado quebrado (que é o que mantém o Freitas
 * funcionando). Aqui sobra gravar, que é I/O e não consome orçamento de CPU.
 *
 * O agente manda em páginas de poucas dezenas de lotes; cada chamada é
 * independente e idempotente, então reenviar depois de uma queda não duplica
 * nada nem exige estado entre requisições.
 */
import { agora, gravarJson, paraCentavos, paraDataBanco } from "../lib/valores";
import type { Env } from "../tipos";

interface SessaoEntrada {
  kind?: string;
  sequence?: number;
  starts_at?: string | null;
  ends_at?: string | null;
  min_bid?: unknown;
}

interface PregaoEntrada {
  external_id: string;
  title?: string | null;
  auctioneer_name?: string | null;
  auctioneer_registration?: string | null;
  committer_name?: string | null;
  modality?: string | null;
  auction_type?: string | null;
  official_url?: string | null;
  status?: string | null;
  starts_at?: string | null;
  ends_at?: string | null;
  sessions?: SessaoEntrada[];
}

interface LoteEntrada {
  external_id: string;
  title: string;
  official_url: string;
  item_type?: string;
  description?: string | null;
  lot_number?: string | null;
  price?: unknown;
  price_kind?: string | null;
  price_second?: unknown;
  city?: string | null;
  state?: string | null;
  location_text?: string | null;
  lat?: number | null;
  lng?: number | null;
  image_url?: string | null;
  images?: string[] | null;
  attributes?: Record<string, unknown> | null;
  brand?: string | null;
  model?: string | null;
  year_model?: number | null;
  year_fab?: number | null;
  km?: number | null;
  condition?: string | null;
  status?: string | null;
  status_hint?: string | null;
  category_slug?: string | null;
  content_hash?: string | null;
  next_session_at?: string | null;
  auction?: PregaoEntrada | null;
}

interface Lote {
  source_slug: string;
  /** Coleta completa? Só então a ausência de um lote significa retirada (RN-005). */
  complete?: boolean;
  items: LoteEntrada[];
}

/** Resposta curta: o agente só precisa saber o que entrou e o que falhou. */
interface Resultado {
  recebidos: number;
  inseridos: number;
  atualizados: number;
  ignorados: number;
  erros: string[];
}

export async function ingerir(req: Request, env: Env): Promise<Response> {
  const token = req.headers.get("x-ingest-token");
  if (!env.INGEST_TOKEN || token !== env.INGEST_TOKEN) {
    return Response.json({ erro: "token de ingestão inválido" }, { status: 401 });
  }

  let corpo: Lote;
  try {
    corpo = (await req.json()) as Lote;
  } catch {
    return Response.json({ erro: "corpo não é JSON" }, { status: 400 });
  }
  if (!corpo?.source_slug || !Array.isArray(corpo.items)) {
    return Response.json({ erro: "faltam source_slug e items" }, { status: 400 });
  }

  const fonte = await env.DB.prepare("SELECT id FROM sources WHERE slug = ?")
    .bind(corpo.source_slug)
    .first<{ id: number }>();
  if (!fonte) {
    return Response.json({ erro: `fonte desconhecida: ${corpo.source_slug}` }, { status: 404 });
  }

  const res: Resultado = { recebidos: corpo.items.length, inseridos: 0, atualizados: 0, ignorados: 0, erros: [] };
  const ts = agora();

  // Mapa de categorias resolvido uma vez: o agente manda o slug, o banco
  // guarda o id.
  const cats = await env.DB.prepare("SELECT id, slug FROM categories").all<{ id: number; slug: string }>();
  const catPorSlug = new Map(cats.results.map((c) => [c.slug, c.id]));

  for (const item of corpo.items) {
    try {
      if (!item.external_id || !item.title || !item.official_url) {
        res.ignorados++;
        continue;
      }
      const auctionId = item.auction ? await gravarPregao(env, fonte.id, item.auction, ts) : null;
      const novo = await gravarLote(env, fonte.id, item, auctionId, catPorSlug, ts);
      if (novo) res.inseridos++;
      else res.atualizados++;
    } catch (e) {
      res.ignorados++;
      if (res.erros.length < 5) res.erros.push(`${item.external_id}: ${String(e).slice(0, 140)}`);
    }
  }

  // Sinais de operação da fonte, para o painel e para a RN-008.
  await env.DB.prepare(
    `UPDATE sources
        SET last_run_at = ?, last_run_status = ?, last_items_count = ?,
            avg_items_count = COALESCE(avg_items_count * 0.7 + ? * 0.3, ?),
            updated_at = ?
      WHERE id = ?`,
  )
    .bind(ts, res.erros.length ? "partial" : "success", res.recebidos, res.recebidos, res.recebidos, ts, fonte.id)
    .run();

  return Response.json(res);
}

async function gravarPregao(
  env: Env,
  sourceId: number,
  a: PregaoEntrada,
  ts: string,
): Promise<number | null> {
  if (!a.external_id) return null;

  await env.DB.prepare(
    `INSERT INTO auctions (source_id, external_id, title, auctioneer_name, auctioneer_registration,
                           committer_name, modality, auction_type, official_url, status,
                           starts_at, ends_at, created_at, updated_at)
     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
     ON CONFLICT (source_id, external_id) DO UPDATE SET
       title = COALESCE(excluded.title, auctions.title),
       auctioneer_name = COALESCE(excluded.auctioneer_name, auctions.auctioneer_name),
       auctioneer_registration = COALESCE(excluded.auctioneer_registration, auctions.auctioneer_registration),
       committer_name = COALESCE(excluded.committer_name, auctions.committer_name),
       modality = COALESCE(excluded.modality, auctions.modality),
       auction_type = COALESCE(excluded.auction_type, auctions.auction_type),
       official_url = COALESCE(excluded.official_url, auctions.official_url),
       starts_at = COALESCE(excluded.starts_at, auctions.starts_at),
       updated_at = excluded.updated_at`,
  )
    .bind(
      sourceId, a.external_id, a.title ?? null, a.auctioneer_name ?? null, a.auctioneer_registration ?? null,
      a.committer_name ?? null, a.modality ?? null, a.auction_type ?? null, a.official_url ?? null,
      a.status ?? "open", paraDataBanco(a.starts_at), paraDataBanco(a.ends_at), ts, ts,
    )
    .run();

  const row = await env.DB.prepare("SELECT id FROM auctions WHERE source_id = ? AND external_id = ?")
    .bind(sourceId, a.external_id)
    .first<{ id: number }>();
  if (!row) return null;

  // As sessões são reescritas a cada coleta: a fonte é a dona da verdade
  // sobre praça, data e lance mínimo, e remarcação é comum.
  if (a.sessions?.length) {
    await env.DB.prepare("DELETE FROM auction_sessions WHERE auction_id = ?").bind(row.id).run();
    let seq = 1;
    for (const s of a.sessions) {
      await env.DB.prepare(
        `INSERT INTO auction_sessions (auction_id, kind, sequence, starts_at, ends_at, min_bid_cents, created_at)
         VALUES (?,?,?,?,?,?,?)`,
      )
        .bind(row.id, s.kind ?? "unica", s.sequence ?? seq++, paraDataBanco(s.starts_at),
              paraDataBanco(s.ends_at), paraCentavos(s.min_bid), ts)
        .run();
    }
  }
  return row.id;
}

async function gravarLote(
  env: Env,
  sourceId: number,
  it: LoteEntrada,
  auctionId: number | null,
  catPorSlug: Map<string, number>,
  ts: string,
): Promise<boolean> {
  const existente = await env.DB.prepare(
    "SELECT id, price_cents FROM items WHERE source_id = ? AND external_id = ?",
  )
    .bind(sourceId, it.external_id)
    .first<{ id: number; price_cents: number | null }>();

  const preco = paraCentavos(it.price);
  const categoriaId = it.category_slug ? catPorSlug.get(it.category_slug) ?? null : null;

  const campos = [
    it.item_type ?? "lot", sourceId, it.external_id, auctionId, categoriaId, it.title,
    it.description ?? null, it.lot_number ?? null, preco, it.price_kind ?? null,
    paraCentavos(it.price_second), it.city ?? null, it.state ?? null, it.location_text ?? null,
    it.lat ?? null, it.lng ?? null, it.official_url, it.image_url ?? null,
    gravarJson(it.images), gravarJson(it.attributes), it.brand ?? null, it.model ?? null,
    it.year_model ?? null, it.year_fab ?? null, it.km ?? null, it.condition ?? null,
    it.status ?? "collected", it.status_hint ?? null, it.content_hash ?? null,
    paraDataBanco(it.next_session_at),
  ];

  if (!existente) {
    await env.DB.prepare(
      `INSERT INTO items (item_type, source_id, external_id, auction_id, category_id, title,
                          description, lot_number, price_cents, price_kind, price_second_cents,
                          city, state, location_text, lat, lng, official_url, image_url,
                          images, attributes, brand, model, year_model, year_fab, km, condition,
                          status, status_hint, content_hash, next_session_at,
                          extraction_status, first_seen_at, last_seen_at, created_at, updated_at)
       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'done', ?,?,?,?)`,
    )
      .bind(...campos, ts, ts, ts, ts)
      .run();
    if (preco !== null) await gravarPreco(env, sourceId, it.external_id, preco, it.price_kind ?? null, ts);
    return true;
  }

  await env.DB.prepare(
    `UPDATE items SET
       auction_id = COALESCE(?, auction_id), category_id = COALESCE(?, category_id),
       title = ?, description = COALESCE(?, description), lot_number = COALESCE(?, lot_number),
       price_cents = ?, price_kind = COALESCE(?, price_kind), price_second_cents = ?,
       city = COALESCE(?, city), state = COALESCE(?, state), location_text = COALESCE(?, location_text),
       lat = COALESCE(?, lat), lng = COALESCE(?, lng),
       official_url = ?, image_url = COALESCE(?, image_url),
       images = COALESCE(?, images), attributes = COALESCE(?, attributes),
       brand = COALESCE(?, brand), model = COALESCE(?, model),
       year_model = COALESCE(?, year_model), year_fab = COALESCE(?, year_fab),
       km = COALESCE(?, km), condition = COALESCE(?, condition),
       status = ?, status_hint = COALESCE(?, status_hint), content_hash = COALESCE(?, content_hash),
       next_session_at = COALESCE(?, next_session_at),
       -- Visto nesta coleta: zera o contador de ausências da RN-005.
       misses = 0, last_seen_at = ?, updated_at = ?
     WHERE id = ?`,
  )
    .bind(auctionId, categoriaId, it.title, it.description ?? null, it.lot_number ?? null,
          preco, it.price_kind ?? null, paraCentavos(it.price_second), it.city ?? null, it.state ?? null,
          it.location_text ?? null, it.lat ?? null, it.lng ?? null, it.official_url, it.image_url ?? null,
          gravarJson(it.images), gravarJson(it.attributes), it.brand ?? null, it.model ?? null,
          it.year_model ?? null, it.year_fab ?? null, it.km ?? null, it.condition ?? null,
          it.status ?? "collected", it.status_hint ?? null, it.content_hash ?? null,
          paraDataBanco(it.next_session_at), ts, ts, existente.id)
    .run();

  // Histórico só quando o preço muda: é o que alimenta o alerta de queda.
  if (preco !== null && preco !== existente.price_cents) {
    await env.DB.prepare(
      "INSERT INTO item_price_history (item_id, price_cents, price_kind, observed_at) VALUES (?,?,?,?)",
    )
      .bind(existente.id, preco, it.price_kind ?? null, ts)
      .run();
  }
  return false;
}

async function gravarPreco(
  env: Env,
  sourceId: number,
  externalId: string,
  preco: number,
  kind: string | null,
  ts: string,
): Promise<void> {
  const row = await env.DB.prepare("SELECT id FROM items WHERE source_id = ? AND external_id = ?")
    .bind(sourceId, externalId)
    .first<{ id: number }>();
  if (!row) return;
  await env.DB.prepare(
    "INSERT INTO item_price_history (item_id, price_cents, price_kind, observed_at) VALUES (?,?,?,?)",
  )
    .bind(row.id, preco, kind, ts)
    .run();
}
