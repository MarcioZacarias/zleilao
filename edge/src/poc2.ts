/**
 * Segunda rodada: a coleta cabe no plano gratuito se for fatiada?
 *
 * O teto de 10 ms é POR INVOCAÇÃO. Parsear a página inteira custa 96 ms, mas
 * ninguém obriga a parsear a página inteira de uma vez. Se cortar o HTML por
 * string (operação nativa, barata) e passar ao HTMLRewriter só o bloco de um
 * lote (~4 KB), cada invocação faz um punhado de lotes e a coleta vira uma
 * fila de invocações pequenas.
 *
 * Mede-se aqui: (a) o custo de recortar, (b) o custo de parsear um bloco,
 * (c) quantos blocos cabem num orçamento de 10 ms.
 */
import { extrairLista, type ListaSpec } from "./parsers/htmlrewriter";

const UA = "ZConnectLeilaoBot/1.0 (+https://leilao.zconnect.ia.br)";

const MEGA: ListaSpec = {
  raiz: "div[data-key]",
  raizAttr: "data-key",
  campos: [
    { sel: ".card-title", campo: "titulo" },
    { sel: ".card-title", campo: "url", attr: "href" },
    { sel: ".card-image", campo: "imagem", attr: "data-bg" },
    { sel: ".card-price", campo: "preco" },
    { sel: ".card-locality", campo: "local_attr", attr: "title" },
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

/**
 * Recorta o HTML nos limites de cada lote, por busca de string.
 *
 * `indexOf` é operação nativa sobre a string: ordens de grandeza mais barata
 * que construir a árvore. O corte não precisa ser um parser — basta achar onde
 * cada `<div data-key=` começa; o bloco vai até o começo do próximo.
 */
function recortar(html: string, atributo: string, tag = "<div", tetoKb = 8): string[] {
  const inicios: number[] = [];
  let i = html.indexOf(atributo);
  while (i !== -1) {
    // O atributo vem depois das classes ("<div class=... data-key=..."), então
    // o começo do bloco é a abertura da tag, não a posição do atributo.
    const abre = html.lastIndexOf(tag, i);
    if (abre !== -1) inicios.push(abre);
    i = html.indexOf(atributo, i + atributo.length);
  }
  const teto = tetoKb * 1024;
  return inicios.map((ini, k) => {
    const fim = k + 1 < inicios.length ? inicios[k + 1] : html.length;
    // Teto por bloco: o último iria até o fim do documento e pagaria por todo
    // o rodapé da página.
    return html.slice(ini, Math.min(fim, ini + teto));
  });
}

export default {
  async fetch(req: Request): Promise<Response> {
    const url = new URL(req.url);

    // ── O Freitas responde em HTTP puro? O TLS dele tem cadeia incompleta e
    //    o fetch do Worker recusa; sem TLS a questão não se coloca.
    if (url.searchParams.has("freitas")) {
      const tentativas: unknown[] = [];
      for (const alvo of [
        "http://www.freitasleiloeiro.com.br/",
        "https://freitasleiloeiro.com.br/",
        "http://freitasleiloeiro.com.br/",
      ]) {
        const t0 = Date.now();
        try {
          const r = await fetch(alvo, { headers: { "user-agent": UA }, redirect: "follow" });
          const corpo = await r.text();
          tentativas.push({ alvo, status: r.status, kb: Math.round(corpo.length / 1024), ms: Date.now() - t0 });
        } catch (e) {
          tentativas.push({ alvo, erro: String(e).slice(0, 140), ms: Date.now() - t0 });
        }
      }
      return Response.json({ teste: "Freitas sem TLS", tentativas });
    }

    // ── Fatiamento: quanto custa recortar e quanto custa parsear um bloco.
    const r = await fetch("https://www.megaleiloes.com.br/veiculos", { headers: { "user-agent": UA } });
    const html = await r.text();
    const reps = Number(url.searchParams.get("n") ?? 10);

    const c0 = Date.now();
    let blocos: string[] = [];
    for (let i = 0; i < reps; i++) blocos = recortar(html, 'data-key="');
    const msRecorte = (Date.now() - c0) / reps;

    const tamanhos = blocos.map((b) => b.length);
    const medioKb = tamanhos.length ? tamanhos.reduce((a, b) => a + b, 0) / tamanhos.length / 1024 : 0;

    // Custo de parsear UM bloco.
    const amostra = blocos[0] ?? "";
    await extrairLista(amostra, MEGA);
    const p0 = Date.now();
    let um: Awaited<ReturnType<typeof extrairLista>> = [];
    for (let i = 0; i < reps * 5; i++) um = await extrairLista(amostra, MEGA);
    const msBloco = (Date.now() - p0) / (reps * 5);

    // Qual o melhor K: parsear K blocos numa passada so' divide o overhead
    // fixo do HTMLRewriter (compilar os seletores) entre eles.
    if (url.searchParams.has("lote")) {
      const curva: unknown[] = [];
      for (const k of [1, 2, 3, 4, 6, 8, 12]) {
        const junto = blocos.slice(0, k).join("");
        await extrairLista(junto, MEGA);
        const t0 = Date.now();
        const voltas = 20;
        let res: Awaited<ReturnType<typeof extrairLista>> = [];
        for (let i = 0; i < voltas; i++) res = await extrairLista(junto, MEGA);
        const ms = (Date.now() - t0) / voltas;
        curva.push({
          blocos: k,
          kb: Number((junto.length / 1024).toFixed(1)),
          ms: Number(ms.toFixed(2)),
          ms_por_bloco: Number((ms / k).toFixed(2)),
          extraidos: res.length,
          cabe_em_10ms: ms <= 10,
        });
      }
      return Response.json({ teste: "quantos lotes por invocacao", curva });
    }

    // Quantos blocos cabem em 10 ms, descontando o recorte.
    const sobra = Math.max(0, 10 - msRecorte);
    const porInvocacao = msBloco > 0 ? Math.floor(sobra / msBloco) : 0;

    return Response.json({
      pagina_kb: Math.round(html.length / 1024),
      blocos_encontrados: blocos.length,
      bloco_medio_kb: Number(medioKb.toFixed(1)),
      ms_para_recortar_a_pagina: Number(msRecorte.toFixed(2)),
      ms_para_parsear_um_bloco: Number(msBloco.toFixed(2)),
      orcamento_ms: 10,
      blocos_por_invocacao: porInvocacao,
      invocacoes_para_a_pagina: porInvocacao > 0 ? Math.ceil(blocos.length / porInvocacao) : null,
      cabe: porInvocacao >= 1,
      conferencia: { titulo: um[0]?.campos.titulo, preco: um[0]?.campos.preco, lote: um[0]?.campos.lote },
    });
  },
};
