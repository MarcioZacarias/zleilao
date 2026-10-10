/**
 * Prova de conceito: o parsing cabe no orçamento de 10 ms de CPU do free tier?
 *
 * Mede o parsing de listagens reais com HTMLRewriter e separa o custo que só
 * existe no teste (transformar a fixture em `Response`) do custo que existe em
 * produção (o parsing em si, sobre a `Response` que o `fetch` já devolve).
 */
import { extrairLista, type ListaSpec } from "./parsers/htmlrewriter";
import megaleiloes from "../fixtures/megaleiloes_listing.html";
import freitas from "../fixtures/freitas_listing.html";

/** Mesmos seletores de `app/scrapers/megaleiloes.py`, em forma declarativa. */
const MEGA: ListaSpec = {
  raiz: "div[data-key]",
  raizAttr: "data-key",
  campos: [
    { sel: ".card-title", campo: "titulo" },
    { sel: ".card-title", campo: "url", attr: "href" },
    { sel: ".card-image", campo: "imagem", attr: "data-bg" },
    { sel: ".card-price", campo: "preco" },
    { sel: ".card-locality", campo: "local_attr", attr: "title" },
    { sel: ".card-locality", campo: "local" },
    { sel: ".card-status", campo: "situacao" },
    { sel: ".card-number", campo: "codigo" },
    { sel: ".card-batch-number", campo: "lote" },
    { sel: ".card-instance-title a", campo: "tipo" },
    { sel: ".card-gavet-link", campo: "pregao_href", attr: "href" },
  ],
  grupos: [
    {
      sel: ".instance",
      nome: "sessoes",
      campos: [
        { sel: "[class*=instance-date]", campo: "quando" },
        { sel: ".card-instance-value", campo: "lance_min" },
      ],
    },
  ],
};

/** Custo que só existe no teste: virar `Response` e consumir, sem parsing. */
async function baseline(html: string, reps: number) {
  const t0 = Date.now();
  for (let i = 0; i < reps; i++) await new Response(html).arrayBuffer();
  return (Date.now() - t0) / reps;
}

async function medir(html: string, spec: ListaSpec, reps: number) {
  await extrairLista(html, spec); // rodada fria: compila os seletores
  const t0 = Date.now();
  let itens: Awaited<ReturnType<typeof extrairLista>> = [];
  for (let i = 0; i < reps; i++) itens = await extrairLista(html, spec);
  return { itens, ms: (Date.now() - t0) / reps };
}

export default {
  async fetch(req: Request): Promise<Response> {
    const url = new URL(req.url);
    const reps = Number(url.searchParams.get("n") ?? 50);

    // Controle: queima CPU em JS puro. Se ESTE endpoint nao morrer, o teto de
    // 10 ms nao esta sendo aplicado e nenhuma medicao acima vale.
    const queima = Number(url.searchParams.get("queima") ?? 0);
    if (queima > 0) {
      let x = 0;
      for (let i = 0; i < queima * 1_000_000; i++) x += Math.sqrt(i) % 7;
      return Response.json({ controle: "queimou CPU em JS", milhoes: queima, x });
    }

    // As tres fontes sao alcancaveis de dentro de um Worker? Testa TLS,
    // bloqueio por IP de datacenter e tamanho real da pagina.
    if (url.searchParams.has("fontes")) {
      const alvos = [
        ["megaleiloes", "https://www.megaleiloes.com.br/veiculos"],
        ["freitas", "https://www.freitasleiloeiro.com.br/"],
        ["leilo", "https://www.leilo.com.br/leilao"],
      ];
      const res = [];
      for (const [nome, alvo] of alvos) {
        const t0 = Date.now();
        try {
          const r = await fetch(alvo, {
            headers: { "user-agent": "ZConnectLeilaoBot/1.0 (+https://leilao.zconnect.ia.br)" },
          });
          const corpo = await r.text();
          res.push({
            fonte: nome, status: r.status, kb: Math.round(corpo.length / 1024),
            ms: Date.now() - t0, ok: r.ok,
          });
        } catch (e) {
          res.push({ fonte: nome, erro: String(e).slice(0, 180), ms: Date.now() - t0 });
        }
      }
      return Response.json({ teste: "alcance das fontes a partir do Worker", resultado: res });
    }

    // Parsing da pagina REAL, nao da fixture recortada.
    if (url.searchParams.has("real")) {
      const r = await fetch("https://www.megaleiloes.com.br/veiculos", {
        headers: { "user-agent": "ZConnectLeilaoBot/1.0 (+https://leilao.zconnect.ia.br)" },
      });
      const html = await r.text();
      const n = Number(url.searchParams.get("real")) || 5;
      const b0 = Date.now();
      for (let i = 0; i < n; i++) await new Response(html).arrayBuffer();
      const over = (Date.now() - b0) / n;
      await extrairLista(html, MEGA);
      const t0 = Date.now();
      let itens: Awaited<ReturnType<typeof extrairLista>> = [];
      for (let i = 0; i < n; i++) itens = await extrairLista(html, MEGA);
      const ms = (Date.now() - t0) / n;
      return Response.json({
        pagina: "megaleiloes.com.br/veiculos (real)",
        kb: Math.round(html.length / 1024),
        lotes: itens.length,
        total_ms: Number(ms.toFixed(1)),
        overhead_ms: Number(over.toFixed(1)),
        parsing_ms: Number((ms - over).toFixed(1)),
        orcamento_free_ms: 10,
        cabe: ms - over <= 10,
        primeiro: itens[0]?.campos.titulo,
      });
    }

    const base = await baseline(megaleiloes, reps);
    const r = await medir(megaleiloes, MEGA, reps);
    const parsingPuro = Math.max(0, r.ms - base);

    const fBase = await baseline(freitas, reps);

    return Response.json({
      orcamento_free_ms: 10,
      megaleiloes: {
        kb: Math.round(megaleiloes.length / 1024),
        lotes: r.itens.length,
        total_ms: Number(r.ms.toFixed(2)),
        overhead_do_teste_ms: Number(base.toFixed(2)),
        parsing_puro_ms: Number(parsingPuro.toFixed(2)),
        cabe: parsingPuro <= 10,
        python_lxml_ms: 31.2,
        python_htmlparser_ms: 31.2,
      },
      freitas_kb: Math.round(freitas.length / 1024),
      freitas_overhead_ms: Number(fBase.toFixed(2)),
      lotes: r.itens.map((i) => ({
        id: i.raiz,
        titulo: i.campos.titulo,
        url: i.campos.url,
        preco: i.campos.preco,
        local: i.campos.local_attr ?? i.campos.local,
        situacao: i.campos.situacao,
        codigo: i.campos.codigo,
        lote: i.campos.lote,
        tipo: i.campos.tipo,
        imagem: i.campos.imagem,
        pregao_href: i.campos.pregao_href,
        sessoes: i.grupos.sessoes ?? [],
      })),
    });
  },
};
