/**
 * Ingestão: recebe do agente local os lotes já normalizados e grava no D1.
 *
 * A divisão de trabalho é deliberada. Tudo que custa CPU — buscar as páginas,
 * parsear HTML, extrair marca e modelo, classificar categoria — acontece no
 * computador que roda a coleta, onde não há teto de 10 ms e onde o cliente
 * HTTP aceita ignorar certificado quebrado (que é o que mantém o Freitas
 * funcionando). Aqui sobra gravar, que é I/O e não consome orçamento de CPU.
 *
 * **Tudo vai em `batch`, e isso não é detalhe de estilo.** A primeira versão
 * fazia três consultas por lote, uma de cada vez: 40 lotes viravam mais de 120
 * idas ao banco, cada uma pagando a latência da rede, e uma única requisição
 * levava 52 segundos — até estourar em 503. Agrupando, a mesma carga vira meia
 * dúzia de idas. Ao mexer aqui, manter a regra: nenhuma consulta dentro de
 * laço sobre os itens.
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
  complete?: boolean;
  items: LoteEntrada[];
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

  const ts = agora();
  const validos = corpo.items.filter((i) => i.external_id && i.title && i.official_url);
  const ignorados = corpo.items.length - validos.length;
  if (!validos.length) {
    return Response.json({ recebidos: corpo.items.length, inseridos: 0, atualizados: 0, ignorados, erros: [] });
  }

  // ── 1 ida: categorias (o agente manda slug, o banco guarda id) ──────────
  const cats = await env.DB.prepare("SELECT id, slug FROM categories").all<{ id: number; slug: string }>();
  const catId = new Map(cats.results.map((c) => [c.slug, c.id]));

  // ── 1 ida: pregões já existentes ────────────────────────────────────────
  const pregoes = validos.map((i) => i.auction).filter((a): a is PregaoEntrada => !!a?.external_id);
  const idPorPregao = new Map<string, number>();
  if (pregoes.length) {
    const chaves = [...new Set(pregoes.map((a) => a.external_id))];
    const existentes = await env.DB.prepare(
      `SELECT id, external_id FROM auctions WHERE source_id = ? AND external_id IN (${chaves.map(() => "?").join(",")})`,
    )
      .bind(fonte.id, ...chaves)
      .all<{ id: number; external_id: string }>();
    for (const r of existentes.results) idPorPregao.set(r.external_id, r.id);

    // ── 1 ida: grava os pregões ───────────────────────────────────────────
    const porChave = new Map(pregoes.map((a) => [a.external_id, a]));
    await env.DB.batch(
      [...porChave.values()].map((a) =>
        env.DB.prepare(
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
        ).bind(
          fonte.id, a.external_id, a.title ?? null, a.auctioneer_name ?? null,
          a.auctioneer_registration ?? null, a.committer_name ?? null, a.modality ?? null,
          a.auction_type ?? null, a.official_url ?? null, a.status ?? "open",
          paraDataBanco(a.starts_at), paraDataBanco(a.ends_at), ts, ts,
        ),
      ),
    );

    // ── 1 ida: ids dos pregões recém-criados ──────────────────────────────
    const novos = chaves.filter((c) => !idPorPregao.has(c));
    if (novos.length) {
      const r = await env.DB.prepare(
        `SELECT id, external_id FROM auctions WHERE source_id = ? AND external_id IN (${novos.map(() => "?").join(",")})`,
      )
        .bind(fonte.id, ...novos)
        .all<{ id: number; external_id: string }>();
      for (const x of r.results) idPorPregao.set(x.external_id, x.id);
    }

    // ── 1 ida: sessões. Reescritas a cada coleta porque a fonte é dona da
    //    verdade sobre praça, data e lance mínimo, e remarcação é comum.
    const cmds = [];
    for (const a of porChave.values()) {
      const aid = idPorPregao.get(a.external_id);
      if (!aid || !a.sessions?.length) continue;
      cmds.push(env.DB.prepare("DELETE FROM auction_sessions WHERE auction_id = ?").bind(aid));
      let seq = 1;
      for (const s of a.sessions) {
        cmds.push(
          env.DB.prepare(
            `INSERT INTO auction_sessions (auction_id, kind, sequence, starts_at, ends_at, min_bid_cents, created_at)
             VALUES (?,?,?,?,?,?,?)`,
          ).bind(aid, s.kind ?? "unica", s.sequence ?? seq++, paraDataBanco(s.starts_at),
                 paraDataBanco(s.ends_at), paraCentavos(s.min_bid), ts),
        );
      }
    }
    if (cmds.length) await env.DB.batch(cmds);
  }

  // ── 1 ida: lotes já existentes, com o preço anterior ────────────────────
  const chavesItens = validos.map((i) => i.external_id);
  const jaExistem = await env.DB.prepare(
    `SELECT id, external_id, price_cents FROM items
      WHERE source_id = ? AND external_id IN (${chavesItens.map(() => "?").join(",")})`,
  )
    .bind(fonte.id, ...chavesItens)
    .all<{ id: number; external_id: string; price_cents: number | null }>();
  const anterior = new Map(jaExistem.results.map((r) => [r.external_id, r]));

  // ── 1 ida: grava os lotes ───────────────────────────────────────────────
  const comandos = [];
  const historico: { id: number; preco: number; kind: string | null }[] = [];
  let inseridos = 0;
  let atualizados = 0;

  for (const it of validos) {
    const preco = paraCentavos(it.price);
    const aid = it.auction?.external_id ? idPorPregao.get(it.auction.external_id) ?? null : null;
    const cid = it.category_slug ? catId.get(it.category_slug) ?? null : null;
    const velho = anterior.get(it.external_id);

    if (!velho) {
      inseridos++;
      comandos.push(
        env.DB.prepare(
          `INSERT INTO items (item_type, source_id, external_id, auction_id, category_id, title,
                              description, lot_number, price_cents, price_kind, price_second_cents,
                              city, state, location_text, lat, lng, official_url, image_url,
                              images, attributes, brand, model, year_model, year_fab, km, condition,
                              status, status_hint, content_hash, next_session_at,
                              extraction_status, first_seen_at, last_seen_at, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'done',?,?,?,?)`,
        ).bind(
          it.item_type ?? "lot", fonte.id, it.external_id, aid, cid, it.title,
          it.description ?? null, it.lot_number ?? null, preco, it.price_kind ?? null,
          paraCentavos(it.price_second), it.city ?? null, it.state ?? null, it.location_text ?? null,
          it.lat ?? null, it.lng ?? null, it.official_url, it.image_url ?? null,
          gravarJson(it.images), gravarJson(it.attributes), it.brand ?? null, it.model ?? null,
          it.year_model ?? null, it.year_fab ?? null, it.km ?? null, it.condition ?? null,
          it.status ?? "collected", it.status_hint ?? null, it.content_hash ?? null,
          paraDataBanco(it.next_session_at), ts, ts, ts, ts,
        ),
      );
    } else {
      atualizados++;
      comandos.push(
        env.DB.prepare(
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
             misses = 0, last_seen_at = ?, updated_at = ?
           WHERE id = ?`,
        ).bind(
          aid, cid, it.title, it.description ?? null, it.lot_number ?? null,
          preco, it.price_kind ?? null, paraCentavos(it.price_second), it.city ?? null, it.state ?? null,
          it.location_text ?? null, it.lat ?? null, it.lng ?? null, it.official_url, it.image_url ?? null,
          gravarJson(it.images), gravarJson(it.attributes), it.brand ?? null, it.model ?? null,
          it.year_model ?? null, it.year_fab ?? null, it.km ?? null, it.condition ?? null,
          it.status ?? "collected", it.status_hint ?? null, it.content_hash ?? null,
          paraDataBanco(it.next_session_at), ts, ts, velho.id,
        ),
      );
      // Histórico só quando o preço muda: é o que alimenta o alerta de queda.
      if (preco !== null && preco !== velho.price_cents) {
        historico.push({ id: velho.id, preco, kind: it.price_kind ?? null });
      }
    }
  }

  // O status da fonte vai junto, aproveitando a mesma ida.
  comandos.push(
    env.DB.prepare(
      `UPDATE sources
          SET last_run_at = ?, last_run_status = 'success', last_items_count = ?,
              avg_items_count = COALESCE(avg_items_count * 0.7 + ? * 0.3, ?), updated_at = ?
        WHERE id = ?`,
    ).bind(ts, validos.length, validos.length, validos.length, ts, fonte.id),
  );

  await env.DB.batch(comandos);

  if (historico.length) {
    await env.DB.batch(
      historico.map((h) =>
        env.DB.prepare(
          "INSERT INTO item_price_history (item_id, price_cents, price_kind, observed_at) VALUES (?,?,?,?)",
        ).bind(h.id, h.preco, h.kind, ts),
      ),
    );
  }

  return Response.json({
    recebidos: corpo.items.length,
    inseridos,
    atualizados,
    ignorados,
    erros: [],
  });
}

/* ── vínculos de duplicidade (RN-004 / F4) ───────────────────────────── */

interface RefLote {
  source_slug?: string;
  external_id?: string;
}

interface VinculoEntrada {
  canonical?: RefLote;
  duplicate?: RefLote;
  similarity?: number;
  reasons?: unknown;
  status?: string;
  created_at?: string | null;
  reviewed_at?: string | null;
}

/** O D1 aceita no máximo 100 parâmetros por consulta; cada referência usa dois. */
const REFS_POR_CONSULTA = 45;

/**
 * Recebe os vínculos do agente. A borda tem ids próprios, então cada lado do
 * par chega como (fonte, id externo) e é resolvido aqui, em lotes de
 * consulta — nunca uma ida ao banco por vínculo.
 */
export async function ingerirVinculos(req: Request, env: Env): Promise<Response> {
  const token = req.headers.get("x-ingest-token");
  if (!env.INGEST_TOKEN || token !== env.INGEST_TOKEN) {
    return Response.json({ erro: "token de ingestão inválido" }, { status: 401 });
  }
  let corpo: { links?: VinculoEntrada[] };
  try {
    corpo = (await req.json()) as { links?: VinculoEntrada[] };
  } catch {
    return Response.json({ erro: "corpo não é JSON" }, { status: 400 });
  }
  const links = Array.isArray(corpo?.links) ? corpo.links : [];
  const validos = links.filter(
    (l) => l.canonical?.source_slug && l.canonical.external_id && l.duplicate?.source_slug && l.duplicate.external_id,
  );
  if (!validos.length) return Response.json({ recebidos: links.length, gravados: 0, ignorados: links.length });

  const fontes = await env.DB.prepare("SELECT id, slug FROM sources").all<{ id: number; slug: string }>();
  const idFonte = new Map(fontes.results.map((f) => [f.slug, f.id]));

  const refs = new Map<string, [number, string]>();
  for (const l of validos) {
    for (const r of [l.canonical!, l.duplicate!]) {
      const sid = idFonte.get(r.source_slug!);
      if (sid) refs.set(`${sid}|${r.external_id}`, [sid, r.external_id!]);
    }
  }
  const idItem = new Map<string, number>();
  const lista = [...refs.values()];
  for (let i = 0; i < lista.length; i += REFS_POR_CONSULTA) {
    const fatia = lista.slice(i, i + REFS_POR_CONSULTA);
    const r = await env.DB.prepare(
      `SELECT id, source_id, external_id FROM items
        WHERE (source_id, external_id) IN (${fatia.map(() => "(?,?)").join(",")})`,
    )
      .bind(...fatia.flat())
      .all<{ id: number; source_id: number; external_id: string }>();
    for (const x of r.results) idItem.set(`${x.source_id}|${x.external_id}`, x.id);
  }

  const ts = agora();
  const comandos = [];
  let ignorados = links.length - validos.length;
  for (const l of validos) {
    const a = idItem.get(`${idFonte.get(l.canonical!.source_slug!)}|${l.canonical!.external_id}`);
    const b = idItem.get(`${idFonte.get(l.duplicate!.source_slug!)}|${l.duplicate!.external_id}`);
    if (!a || !b || a === b) {
      ignorados++;
      continue;
    }
    comandos.push(
      env.DB.prepare(
        `INSERT INTO item_duplicates (canonical_item_id, duplicate_item_id, similarity, reasons, status, created_at, reviewed_at)
         VALUES (?,?,?,?,?,?,?)
         ON CONFLICT (canonical_item_id, duplicate_item_id) DO UPDATE SET
           similarity = excluded.similarity, reasons = excluded.reasons,
           status = excluded.status, reviewed_at = excluded.reviewed_at`,
      ).bind(
        a, b, Number(l.similarity ?? 0), gravarJson(l.reasons), l.status ?? "suspected",
        paraDataBanco(l.created_at) ?? ts, paraDataBanco(l.reviewed_at),
      ),
    );
  }
  if (comandos.length) await env.DB.batch(comandos);
  return Response.json({ recebidos: links.length, gravados: comandos.length, ignorados });
}
