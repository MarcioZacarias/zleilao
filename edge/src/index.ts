/**
 * Roteador do Worker.
 *
 * A divisão de trabalho do sistema está aqui: a Cloudflare recebe dados já
 * normalizados (`/ingest`) e serve leitura (`/v1/portal/*`). Nada que custe
 * CPU — buscar páginas, parsear HTML, extrair marca e modelo — roda aqui;
 * isso é do agente de coleta, no computador do operador.
 */
import {
  eu, gravarSettings, listarSettings, login, painel, resumoUsuarios, semearAdmin,
} from "./rotas/admin";
import { ingerir } from "./rotas/ingestao";
import {
  anuncios, branding, categorias, cidades, detalharItem, estatisticas, irParaFonte,
  listarItens, marcas, modelos, pregoesProximos, registrarAnuncio, sitemap,
} from "./rotas/portal";
import type { Env } from "./tipos";

const CORS = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET,POST,PUT,DELETE,OPTIONS",
  "access-control-allow-headers": "content-type,x-ingest-token,authorization",
};

function comCors(r: Response): Response {
  const h = new Headers(r.headers);
  for (const [k, v] of Object.entries(CORS)) h.set(k, v);
  return new Response(r.body, { status: r.status, headers: h });
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });

    const u = new URL(req.url);
    const p = u.pathname.replace(/\/+$/, "") || "/";

    try {
      if (p === "/health") {
        const r = await env.DB.prepare("SELECT COUNT(*) AS n FROM items").first<{ n: number }>();
        return comCors(Response.json({ status: "ok", itens: r?.n ?? 0 }));
      }

      if (p === "/ingest/batch" && req.method === "POST") {
        return comCors(await ingerir(req, env));
      }

      // Painel: login e configuração. O resto do admin continua no backend
      // em Python, junto da coleta.
      if (p === "/v1/auth/login" && req.method === "POST") return comCors(await login(req, env));
      if (p === "/v1/auth/me") return comCors(await eu(req, env));
      if (p === "/v1/settings" && req.method === "GET") return comCors(await listarSettings(req, env, u));
      if (p === "/v1/settings" && (req.method === "PUT" || req.method === "POST"))
        return comCors(await gravarSettings(req, env));
      if (p === "/v1/admin/seed" && req.method === "POST") return comCors(await semearAdmin(env));
      if (p === "/v1/dashboard") return comCors(await painel(req, env));
      if (p === "/v1/users/summary") return comCors(await resumoUsuarios(req, env));

      // Rotas da vitrine. O prefixo /v1 mantém o contrato do backend atual.
      if (p === "/v1/portal/items") return comCors(await listarItens(u, env));
      if (p === "/v1/portal/stats") return comCors(await estatisticas(env));
      // O sitemap fica na API porque é aqui que estão os lotes; o site o
      // serve pelo mesmo caminho, via redirecionamento no robots.txt.
      if (p === "/sitemap.xml") return await sitemap(env, u.searchParams.get("site") || "https://zleilao.marcio-zacariass.workers.dev");
      if (p === "/v1/portal/branding") return comCors(await branding(env));
      if (p === "/v1/portal/ads") return comCors(await anuncios(env));
      if (p === "/v1/portal/ads/event" && req.method === "POST")
        return comCors(await registrarAnuncio(req, env));
      if (p === "/v1/portal/categories") return comCors(await categorias(env));
      if (p === "/v1/portal/cities") return comCors(await cidades(u, env));
      if (p === "/v1/portal/brands") return comCors(await marcas(u, env));
      if (p === "/v1/portal/models") return comCors(await modelos(u, env));
      if (p === "/v1/portal/auctions/upcoming") return comCors(await pregoesProximos(u, env));

      const indoParaFonte = /^\/v1\/portal\/items\/(\d+)\/go$/.exec(p);
      if (indoParaFonte) return await irParaFonte(Number(indoParaFonte[1]), env, req);

      const ficha = /^\/v1\/portal\/items\/(\d+)$/.exec(p);
      if (ficha) return comCors(await detalharItem(Number(ficha[1]), env, req));

      return comCors(Response.json({ detail: "Not Found", path: p }, { status: 404 }));
    } catch (e) {
      // O erro vai para o log do Worker; o cliente recebe o motivo sem pilha.
      console.error("falha em", p, e);
      return comCors(Response.json({ detail: String(e).slice(0, 300) }, { status: 500 }));
    }
  },
};
