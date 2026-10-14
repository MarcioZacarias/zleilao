/**
 * Logo e favicon enviados pelo painel, guardados no D1 (`branding_assets`).
 *
 * Até 14/10/2026 o Worker devolvia `null` para as imagens e a vitrine caía
 * nos SVGs do pacote: trocar o logo exigia republicar o site. Agora o upload
 * do painel funciona na borda, com o mesmo contrato do Python. O limite de
 * 2 MB é o do backend e cabe num valor do D1 (teto de 2.000.000 bytes).
 */
import { agora } from "../lib/valores";
import type { Env } from "../tipos";
import { sessaoDe } from "./admin";

const CHAVES = ["logo_dark", "logo_light", "favicon"];
const TIPOS = new Set([
  "image/png", "image/jpeg", "image/jpg", "image/svg+xml", "image/webp",
  "image/x-icon", "image/vnd.microsoft.icon",
]);
const MAX_BYTES = 2 * 1024 * 1024;

function erro(status: number, detail: string): Response {
  return Response.json({ detail }, { status });
}

/** Só dígitos da data: serve de ETag e de `?v=` para furar o cache quando a imagem muda. */
function versao(updatedAt: string): string {
  return updatedAt.replace(/\D/g, "");
}

export function urlAsset(origem: string, chave: string, updatedAt: string): string {
  return `${origem}/v1/branding/${chave}?v=${versao(updatedAt)}`;
}

/** BLOB do D1 chega como ArrayBuffer; versões antigas devolviam lista de bytes. */
function bytesDe(v: unknown): Uint8Array {
  if (v instanceof ArrayBuffer) return new Uint8Array(v);
  if (ArrayBuffer.isView(v)) return new Uint8Array(v.buffer, v.byteOffset, v.byteLength);
  if (Array.isArray(v)) return Uint8Array.from(v as number[]);
  return new Uint8Array();
}

export async function servirAsset(chave: string, env: Env, req: Request): Promise<Response> {
  if (!CHAVES.includes(chave)) return erro(404, "Chave inválida");
  const r = await env.DB.prepare("SELECT mimetype, data, updated_at FROM branding_assets WHERE key = ?")
    .bind(chave)
    .first<{ mimetype: string; data: unknown; updated_at: string }>();
  if (!r) return erro(404, "Sem imagem para esta chave");

  const etag = `"${versao(r.updated_at)}"`;
  if (req.headers.get("if-none-match") === etag) {
    return new Response(null, { status: 304, headers: { etag } });
  }
  return new Response(bytesDe(r.data), {
    headers: { "content-type": r.mimetype, "cache-control": "public, max-age=300", etag },
  });
}

export async function enviarAsset(req: Request, env: Env, origem: string): Promise<Response> {
  const s = await sessaoDe(req, env);
  if (!s || s.role !== "admin") return erro(401, "Não autenticado");

  let form: FormData;
  try {
    form = await req.formData();
  } catch {
    return erro(400, "Envie como multipart/form-data");
  }
  const chave = String(form.get("key") ?? "");
  const arquivo = form.get("file");
  if (!CHAVES.includes(chave)) return erro(400, `Chave inválida. Permitidas: ${CHAVES.join(", ")}`);
  if (!(arquivo instanceof File)) return erro(400, "Arquivo ausente");
  const tipo = (arquivo.type || "").toLowerCase();
  if (!TIPOS.has(tipo)) return erro(400, `Tipo '${tipo}' não permitido (PNG, JPEG, SVG, WEBP, ICO)`);
  if (arquivo.size === 0) return erro(400, "Arquivo vazio");
  if (arquivo.size > MAX_BYTES) return erro(413, "Arquivo maior que 2 MB");

  const ts = agora();
  await env.DB.prepare(
    `INSERT INTO branding_assets (key, mimetype, data, updated_at) VALUES (?,?,?,?)
     ON CONFLICT (key) DO UPDATE SET mimetype = excluded.mimetype, data = excluded.data,
                                     updated_at = excluded.updated_at`,
  )
    .bind(chave, tipo, await arquivo.arrayBuffer(), ts)
    .run();
  return Response.json({ key: chave, mimetype: tipo, size: arquivo.size, url: urlAsset(origem, chave, ts) });
}

export async function apagarAsset(chave: string, req: Request, env: Env): Promise<Response> {
  const s = await sessaoDe(req, env);
  if (!s || s.role !== "admin") return erro(401, "Não autenticado");
  if (!CHAVES.includes(chave)) return erro(400, "Chave inválida");
  const r = await env.DB.prepare("DELETE FROM branding_assets WHERE key = ?").bind(chave).run();
  return Response.json({ key: chave, deleted: (r.meta.changes ?? 0) > 0 });
}
