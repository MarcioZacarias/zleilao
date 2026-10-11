/**
 * Diagnóstico do Freitas: o que exatamente impede o Worker de alcançar a fonte?
 *
 * O `fetch` devolve "internal error", que não diz nada. Falando TCP na mão dá
 * para separar as hipóteses: se a porta 80 responde, o problema é só o TLS; se
 * o TLS falha mas o TCP conecta, é a cadeia de certificado; se nem conecta, é
 * bloqueio de rede.
 *
 * Contexto medido de fora: o servidor apresenta o intermediário errado
 * (`AlphaSSL CA - SHA256 - G2`, expirado em 2024) para um certificado emitido
 * pela `GlobalSign GCC R6 AlphaSSL CA 2025`. Navegador contorna buscando o
 * intermediário pelo AIA; `fetch` de Worker não faz isso.
 */
import { connect } from "cloudflare:sockets";

const HOST = "www.freitasleiloeiro.com.br";
const UA = "ZConnectLeilaoBot/1.0 (+https://leilao.zconnect.ia.br)";

async function falarHttp(
  hostname: string,
  port: number,
  path: string,
  secureTransport: "off" | "on",
  timeoutMs = 12000,
): Promise<Record<string, unknown>> {
  const t0 = Date.now();
  let socket: ReturnType<typeof connect> | null = null;
  try {
    socket = connect({ hostname, port }, { secureTransport, allowHalfOpen: false });

    const req =
      `GET ${path} HTTP/1.1\r\n` +
      `Host: ${hostname}\r\n` +
      `User-Agent: ${UA}\r\n` +
      `Accept: text/html,application/xhtml+xml\r\n` +
      `Accept-Encoding: identity\r\n` +
      `Connection: close\r\n\r\n`;

    const writer = socket.writable.getWriter();
    await writer.write(new TextEncoder().encode(req));
    writer.releaseLock();

    const reader = socket.readable.getReader();
    const pedacos: Uint8Array[] = [];
    let lidos = 0;
    const prazo = Promise.race([
      (async () => {
        while (lidos < 64 * 1024) {
          const { done, value } = await reader.read();
          if (done) break;
          if (value) {
            pedacos.push(value);
            lidos += value.length;
          }
        }
      })(),
      new Promise((_, rej) => setTimeout(() => rej(new Error("timeout")), timeoutMs)),
    ]);
    await prazo;

    const bruto = new TextDecoder().decode(
      pedacos.reduce((acc, p) => {
        const out = new Uint8Array(acc.length + p.length);
        out.set(acc);
        out.set(p, acc.length);
        return out;
      }, new Uint8Array()),
    );
    const corte = bruto.indexOf("\r\n\r\n");
    const cabecalho = corte === -1 ? bruto : bruto.slice(0, corte);
    const corpo = corte === -1 ? "" : bruto.slice(corte + 4);
    const linha1 = cabecalho.split("\r\n")[0] ?? "";
    const location = /^location:\s*(.+)$/im.exec(cabecalho)?.[1]?.trim();

    return {
      alvo: `${secureTransport === "on" ? "https" : "http"}://${hostname}:${port}${path}`,
      conectou: true,
      status: linha1,
      location,
      bytes: lidos,
      amostra_corpo: corpo.slice(0, 120).replace(/\s+/g, " "),
      ms: Date.now() - t0,
    };
  } catch (e) {
    return {
      alvo: `${secureTransport === "on" ? "https" : "http"}://${hostname}:${port}${path}`,
      conectou: false,
      erro: String(e).slice(0, 200),
      ms: Date.now() - t0,
    };
  } finally {
    try {
      await socket?.close();
    } catch {
      /* fechar é melhor-esforço */
    }
  }
}

export default {
  async fetch(req: Request): Promise<Response> {
    const url = new URL(req.url);
    const path = url.searchParams.get("path") ?? "/";

    const testes = [
      // TCP puro na 80: separa "é TLS" de "é bloqueio de rede".
      () => falarHttp(HOST, 80, path, "off"),
      // TLS pelo runtime: deve reproduzir a falha de cadeia do `fetch`.
      () => falarHttp(HOST, 443, path, "on"),
      // O endpoint que o scraper usa de fato, não a home.
      () => falarHttp(HOST, 80, "/Leiloes/PesquisarLotes?Categoria=1", "off"),
    ];

    const resultado = [];
    for (const t of testes) resultado.push(await t());
    return Response.json({ host: HOST, resultado });
  },
};
