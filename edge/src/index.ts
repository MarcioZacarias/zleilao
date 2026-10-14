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
import {
  alterarFiltro, apagarFiltro, atualizarPerfil, cadastrar, criarFiltro, esqueciSenha, listarFiltros,
  meuPerfil, meusAlertas, previaFiltro, redefinirSenha, reenviarVerificacao, trocarSenha, verificarEmail,
} from "./rotas/conta";
import {
  atualizarUsuario, definirPlano, detalharFonte, filtrosDoUsuario, listarAlertas, listarCategorias,
  listarFontes, listarParsers, listarUsuarios, reenviarAlerta,
} from "./rotas/gestao";
import { ingerir } from "./rotas/ingestao";
import { apagarAsset, enviarAsset, servirAsset } from "./rotas/marca";
import {
  anuncios, branding, categorias, cidades, detalharItem, detalharPregao, estatisticas, irParaFonte,
  listarItens, marcas, modelos, pregoesProximos, registrarAnuncio, sitemap,
} from "./rotas/portal";
import type { Env } from "./tipos";

const CORS = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
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

      // Painel: login, configuração, assinantes, alertas, e leitura de fontes
      // e categorias. O que mexe no banco de trabalho da coleta continua no
      // backend em Python, junto dela.
      if (p === "/v1/auth/login" && req.method === "POST") return comCors(await login(req, env));
      if (p === "/v1/auth/me") return comCors(await eu(req, env));
      // Conta do assinante: cadastro, verificação, senha, perfil e filtros.
      if (req.method === "POST") {
        if (p === "/v1/auth/register") return comCors(await cadastrar(req, env));
        if (p === "/v1/auth/verify-email") return comCors(await verificarEmail(u, env));
        if (p === "/v1/auth/resend-verification") return comCors(await reenviarVerificacao(req, env));
        if (p === "/v1/auth/forgot-password") return comCors(await esqueciSenha(req, env));
        if (p === "/v1/auth/reset-password") return comCors(await redefinirSenha(req, env));
        if (p === "/v1/auth/change-password" || p === "/v1/me/change-password")
          return comCors(await trocarSenha(req, env));
      }
      if (p === "/v1/me" && req.method === "GET") return comCors(await meuPerfil(req, env));
      if (p === "/v1/me" && req.method === "PATCH") return comCors(await atualizarPerfil(req, env));
      if (p === "/v1/me/alerts") return comCors(await meusAlertas(u, req, env));
      if (p === "/v1/me/filters" && req.method === "GET") return comCors(await listarFiltros(req, env));
      if (p === "/v1/me/filters" && req.method === "POST") return comCors(await criarFiltro(req, env));
      const previa = /^\/v1\/me\/filters\/(\d+)\/preview$/.exec(p);
      if (previa) return comCors(await previaFiltro(Number(previa[1]), u, req, env));
      const filtro = /^\/v1\/me\/filters\/(\d+)$/.exec(p);
      if (filtro && req.method === "PUT") return comCors(await alterarFiltro(Number(filtro[1]), req, env));
      if (filtro && req.method === "DELETE") return comCors(await apagarFiltro(Number(filtro[1]), req, env));

      if (p === "/v1/settings" && req.method === "GET") return comCors(await listarSettings(req, env, u));
      if (p === "/v1/settings" && (req.method === "PUT" || req.method === "POST"))
        return comCors(await gravarSettings(req, env));
      if (p === "/v1/admin/seed" && req.method === "POST") return comCors(await semearAdmin(env));
      if (p === "/v1/dashboard") return comCors(await painel(req, env));
      if (p === "/v1/users/summary") return comCors(await resumoUsuarios(req, env));
      if (p === "/v1/users" && req.method === "GET") return comCors(await listarUsuarios(u, req, env));
      const usuarioFiltros = /^\/v1\/users\/(\d+)\/filters$/.exec(p);
      if (usuarioFiltros) return comCors(await filtrosDoUsuario(Number(usuarioFiltros[1]), req, env));
      const usuarioPlano = /^\/v1\/users\/(\d+)\/plan$/.exec(p);
      if (usuarioPlano && req.method === "PUT") return comCors(await definirPlano(Number(usuarioPlano[1]), req, env));
      const usuario = /^\/v1\/users\/(\d+)$/.exec(p);
      if (usuario && req.method === "PATCH") return comCors(await atualizarUsuario(Number(usuario[1]), req, env));
      if (p === "/v1/alerts" && req.method === "GET") return comCors(await listarAlertas(u, req, env));
      const reenvio = /^\/v1\/alerts\/(\d+)\/retry$/.exec(p);
      if (reenvio && req.method === "POST") return comCors(await reenviarAlerta(Number(reenvio[1]), req, env));
      if (p === "/v1/sources" && req.method === "GET") return comCors(await listarFontes(req, env));
      if (p === "/v1/sources/parsers") return comCors(await listarParsers(req, env));
      const fonte = /^\/v1\/sources\/(\d+)$/.exec(p);
      if (fonte && req.method === "GET") return comCors(await detalharFonte(Number(fonte[1]), req, env));
      if (p === "/v1/categories" && req.method === "GET") return comCors(await listarCategorias(req, env));

      // Logo e favicon: leitura pública, envio e remoção pelo painel.
      if (p === "/v1/branding/upload" && req.method === "POST") return comCors(await enviarAsset(req, env, u.origin));
      const asset = /^\/v1\/branding\/([a-z_]+)$/.exec(p);
      if (asset && req.method === "GET") return comCors(await servirAsset(asset[1], env, req));
      if (asset && req.method === "DELETE") return comCors(await apagarAsset(asset[1], req, env));

      // Rotas da vitrine. O prefixo /v1 mantém o contrato do backend atual.
      if (p === "/v1/portal/items") return comCors(await listarItens(u, env));
      if (p === "/v1/portal/stats") return comCors(await estatisticas(env));
      // O sitemap fica na API porque é aqui que estão os lotes; o site o
      // serve pelo mesmo caminho, via redirecionamento no robots.txt.
      if (p === "/sitemap.xml") return await sitemap(env, u.searchParams.get("site") || "https://zleilao.marcio-zacariass.workers.dev");
      if (p === "/v1/portal/branding") return comCors(await branding(env, u.origin));
      if (p === "/v1/portal/ads") return comCors(await anuncios(env));
      if (p === "/v1/portal/ads/event" && req.method === "POST")
        return comCors(await registrarAnuncio(req, env));
      if (p === "/v1/portal/categories") return comCors(await categorias(env));
      if (p === "/v1/portal/cities") return comCors(await cidades(u, env));
      if (p === "/v1/portal/brands") return comCors(await marcas(u, env));
      if (p === "/v1/portal/models") return comCors(await modelos(u, env));
      if (p === "/v1/portal/auctions/upcoming") return comCors(await pregoesProximos(u, env));

      const pregao = /^\/v1\/portal\/auctions\/(\d+)$/.exec(p);
      if (pregao) return comCors(await detalharPregao(Number(pregao[1]), env));

      const indoParaFonte = /^\/v1\/portal\/items\/(\d+)\/go$/.exec(p);
      if (indoParaFonte) return await irParaFonte(Number(indoParaFonte[1]), env, req);

      const ficha = /^\/v1\/portal\/items\/(\d+)$/.exec(p);
      if (ficha) return comCors(await detalharItem(Number(ficha[1]), env, req));

      // O que só existe no painel local, junto da coleta. Dizer o motivo
      // evita o "Not Found" seco na tela do painel.
      if (/^\/v1\/(sources|categories|items|incidents|jobs|duplicates|partners|review|alerts|users|settings)(\/|$)/.test(p)) {
        return comCors(Response.json(
          { detail: "Esta ação é do painel local, junto da coleta (http://localhost:5177/admin). Na Cloudflare, fontes e categorias são só leitura." },
          { status: 501 },
        ));
      }

      return comCors(Response.json({ detail: "Not Found", path: p }, { status: 404 }));
    } catch (e) {
      // O erro vai para o log do Worker; o cliente recebe o motivo sem pilha.
      console.error("falha em", p, e);
      return comCors(Response.json({ detail: String(e).slice(0, 300) }, { status: 500 }));
    }
  },
};
