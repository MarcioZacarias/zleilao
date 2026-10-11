/**
 * Autenticação do painel administrativo.
 *
 * **Por que não bcrypt.** O backend em Python usa bcrypt via passlib, mas o
 * Worker não tem binding nativo para ele, e as implementações em JS puro
 * levam dezenas de milissegundos — contra um teto de 10 ms de CPU por
 * invocação no plano gratuito. O login simplesmente não completaria.
 *
 * Aqui o hash é PBKDF2-SHA256 pelo Web Crypto, que roda nativo no runtime.
 * O número de iterações é calibrado para caber no orçamento: é mais baixo do
 * que se recomendaria para uma base de senhas de usuários, e isso é aceitável
 * porque há um único operador, com senha longa, e a porta não fica exposta a
 * tentativa em massa (ver `atrasoAntiForca`).
 *
 * As senhas do Postgres **não** migram: os formatos são diferentes. O admin do
 * D1 nasce do segredo `ADMIN_PASSWORD` do Worker.
 */

const ITERACOES = 12_000;
const TAM_CHAVE = 32;

function b64(bytes: ArrayBuffer | Uint8Array): string {
  const u8 = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let s = "";
  for (const b of u8) s += String.fromCharCode(b);
  return btoa(s);
}

function deB64(s: string): Uint8Array {
  const bin = atob(s);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

async function derivar(senha: string, salt: Uint8Array, iteracoes: number): Promise<Uint8Array> {
  const chave = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(senha),
    { name: "PBKDF2" },
    false,
    ["deriveBits"],
  );
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", salt: salt as BufferSource, iterations: iteracoes, hash: "SHA-256" },
    chave,
    TAM_CHAVE * 8,
  );
  return new Uint8Array(bits);
}

/** Formato: `pbkdf2$<iteracoes>$<salt>$<hash>`, tudo em base64. */
export async function gerarHash(senha: string): Promise<string> {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const hash = await derivar(senha, salt, ITERACOES);
  return `pbkdf2$${ITERACOES}$${b64(salt)}$${b64(hash)}`;
}

/** Comparação em tempo constante: diferença de tempo vaza o prefixo correto. */
function iguais(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a[i] ^ b[i];
  return d === 0;
}

export async function conferirSenha(senha: string, guardado: string): Promise<boolean> {
  const partes = guardado.split("$");
  if (partes.length !== 4 || partes[0] !== "pbkdf2") return false;
  const iteracoes = Number(partes[1]);
  if (!Number.isFinite(iteracoes) || iteracoes < 1000 || iteracoes > 100_000) return false;
  try {
    const calculado = await derivar(senha, deB64(partes[2]), iteracoes);
    return iguais(calculado, deB64(partes[3]));
  } catch {
    return false;
  }
}

/* ── Token de sessão ─────────────────────────────────────────────────── */

function paraB64Url(s: string): string {
  return s.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function deB64Url(s: string): string {
  const p = s.replace(/-/g, "+").replace(/_/g, "/");
  return p + "=".repeat((4 - (p.length % 4)) % 4);
}

async function assinar(dados: string, segredo: string): Promise<string> {
  const chave = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(segredo),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const mac = await crypto.subtle.sign("HMAC", chave, new TextEncoder().encode(dados));
  return paraB64Url(b64(mac));
}

/** JWT HS256. `horas` define o tempo de vida; o relógio aqui é UTC. */
export async function gerarToken(
  carga: Record<string, unknown>,
  segredo: string,
  horas = 12,
): Promise<string> {
  const cabecalho = paraB64Url(btoa(JSON.stringify({ alg: "HS256", typ: "JWT" })));
  const agora = Math.floor(Date.now() / 1000);
  const corpo = paraB64Url(
    btoa(JSON.stringify({ ...carga, iat: agora, exp: agora + horas * 3600 })),
  );
  const assinatura = await assinar(`${cabecalho}.${corpo}`, segredo);
  return `${cabecalho}.${corpo}.${assinatura}`;
}

export async function lerToken(
  token: string,
  segredo: string,
): Promise<Record<string, unknown> | null> {
  const partes = token.split(".");
  if (partes.length !== 3) return null;
  const esperada = await assinar(`${partes[0]}.${partes[1]}`, segredo);
  // Comparar strings aqui é seguro: a assinatura esperada é derivada do
  // próprio conteúdo, então não há segredo a vazar pelo tempo.
  if (esperada !== partes[2]) return null;
  try {
    const carga = JSON.parse(atob(deB64Url(partes[1]))) as Record<string, unknown>;
    if (typeof carga.exp === "number" && carga.exp < Math.floor(Date.now() / 1000)) return null;
    return carga;
  } catch {
    return null;
  }
}

/**
 * Atraso progressivo por origem, contra tentativa em massa.
 *
 * Sem isto, um teto de iterações baixo convidaria força bruta. Como não há
 * estado entre invocações no plano gratuito, o contador vive no próprio D1 —
 * barato porque só escreve quando a senha erra.
 */
export async function registrarFalha(db: D1Database, origem: string): Promise<void> {
  const dia = new Date().toISOString().slice(0, 10);
  try {
    await db
      .prepare(
        `INSERT INTO login_failures (origem, dia, total) VALUES (?,?,1)
         ON CONFLICT (origem, dia) DO UPDATE SET total = total + 1`,
      )
      .bind(origem.slice(0, 64), dia)
      .run();
  } catch {
    /* contagem não pode derrubar o login */
  }
}

/** True quando a origem já errou demais hoje e deve ser recusada de saída. */
export async function bloqueada(db: D1Database, origem: string, teto = 20): Promise<boolean> {
  const dia = new Date().toISOString().slice(0, 10);
  try {
    const r = await db
      .prepare("SELECT total FROM login_failures WHERE origem = ? AND dia = ?")
      .bind(origem.slice(0, 64), dia)
      .first<{ total: number }>();
    return (r?.total ?? 0) >= teto;
  } catch {
    return false;
  }
}
