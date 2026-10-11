/**
 * Conversões de borda: o banco guarda centavos e texto ISO, a API fala reais
 * e ISO-8601. Centralizado aqui porque errar a unidade em um lugar só já
 * basta para mostrar um Gol a R$ 219,00 em vez de R$ 21.900,00.
 */

/** "21900.00" | 21900 | "R$ 21.900,00" → 2190000 centavos. */
export function paraCentavos(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  if (typeof v === "number") {
    if (!Number.isFinite(v)) return null;
    return Math.round(v * 100);
  }
  const s = String(v).trim();
  if (!s) return null;
  // Aceita tanto "21900.00" (JSON) quanto "R$ 21.900,00" (texto da fonte).
  const limpo = s.replace(/[^\d,.-]/g, "");
  const ptbr = /,\d{1,2}$/.test(limpo);
  const normal = ptbr ? limpo.replace(/\./g, "").replace(",", ".") : limpo.replace(/,/g, "");
  const n = Number(normal);
  return Number.isFinite(n) ? Math.round(n * 100) : null;
}

/** 2190000 centavos → 21900 (reais, com decimais). */
export function paraReais(c: number | null | undefined): number | null {
  if (c === null || c === undefined) return null;
  return Math.round(c) / 100;
}

/**
 * Normaliza data/hora para o formato do banco: 'YYYY-MM-DD HH:MM:SS' em
 * horário de Brasília, sem fuso — a mesma convenção do backend em Python.
 *
 * Entrada com fuso ("2026-09-16T14:00:00-03:00") é convertida; entrada sem
 * fuso é aceita como já estando em horário de Brasília, que é o que o agente
 * local envia.
 */
export function paraDataBanco(v: unknown): string | null {
  if (!v) return null;
  const s = String(v).trim();
  if (!s) return null;
  const semFuso = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?(\.\d+)?$/.test(s);
  if (semFuso) {
    const [data, hora] = s.replace("T", " ").split(" ");
    const hh = (hora ?? "00:00:00").split(".")[0];
    return `${data} ${hh.length === 5 ? hh + ":00" : hh}`;
  }
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return null;
  return deDataParaBanco(d);
}

const BRT_MS = -3 * 60 * 60 * 1000;

/** Instante → 'YYYY-MM-DD HH:MM:SS' em horário de Brasília. */
export function deDataParaBanco(d: Date): string {
  const t = new Date(d.getTime() + BRT_MS);
  return t.toISOString().slice(0, 19).replace("T", " ");
}

/** Agora, em horário de Brasília, no formato do banco. */
export function agora(): string {
  return deDataParaBanco(new Date());
}

/** 'YYYY-MM-DD HH:MM:SS' (BRT) → ISO-8601 com fuso, para a API. */
export function paraIso(s: string | null | undefined): string | null {
  if (!s) return null;
  return s.replace(" ", "T") + "-03:00";
}

/** Texto JSON do banco → objeto; nulo e texto inválido viram o padrão. */
export function lerJson<T>(s: unknown, padrao: T): T {
  if (s === null || s === undefined || s === "") return padrao;
  if (typeof s === "object") return s as T;
  try {
    const v = JSON.parse(String(s));
    return (v ?? padrao) as T;
  } catch {
    return padrao;
  }
}

/** Objeto → texto JSON para o banco; vazio vira NULL. */
export function gravarJson(v: unknown): string | null {
  if (v === null || v === undefined) return null;
  if (Array.isArray(v) && v.length === 0) return null;
  if (typeof v === "object" && !Array.isArray(v) && Object.keys(v as object).length === 0) return null;
  return JSON.stringify(v);
}

/** 0/1 do SQLite → booleano. */
export function booleano(v: unknown): boolean {
  return v === 1 || v === true || v === "1" || v === "true";
}
