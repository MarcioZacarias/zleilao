// Formatação pt-BR: moeda, datas e números.

const brl = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const intFmt = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
const decFmt = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });

export function formatBRL(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return "—";
  return brl.format(n);
}

export function formatInt(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return "—";
  return intFmt.format(n);
}

export function formatDecimal(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return "—";
  return decFmt.format(n);
}

export function formatKm(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${intFmt.format(value)} km`;
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${value.toFixed(digits).replace(".", ",")}%`;
}

interface DateParts {
  y: number;
  m: number;
  d: number;
  hh: number;
  mm: number;
  ss: number;
}

const ISO_NAIVE = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?)?$/;

/**
 * As datas da API vêm sem timezone e já em horário de Brasília. Fazemos o
 * parse textual para não sofrer deslocamento pelo fuso do navegador.
 */
function parseParts(iso: string): DateParts | null {
  const m = ISO_NAIVE.exec(iso.trim());
  if (m) {
    return {
      y: Number(m[1]),
      m: Number(m[2]),
      d: Number(m[3]),
      hh: Number(m[4] ?? 0),
      mm: Number(m[5] ?? 0),
      ss: Number(m[6] ?? 0),
    };
  }
  // Com timezone explícito: converter para Brasília.
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return null;
  const fmt = new Intl.DateTimeFormat("pt-BR", {
    timeZone: "America/Sao_Paulo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
  const parts = Object.fromEntries(fmt.formatToParts(dt).map((p) => [p.type, p.value]));
  return {
    y: Number(parts.year),
    m: Number(parts.month),
    d: Number(parts.day),
    hh: Number(parts.hour) % 24,
    mm: Number(parts.minute),
    ss: Number(parts.second),
  };
}

const pad = (n: number) => String(n).padStart(2, "0");

/** dd/mm/yyyy HH:mm */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const p = parseParts(iso);
  if (!p) return "—";
  return `${pad(p.d)}/${pad(p.m)}/${p.y} ${pad(p.hh)}:${pad(p.mm)}`;
}

/** dd/mm/yyyy */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const p = parseParts(iso);
  if (!p) return "—";
  return `${pad(p.d)}/${pad(p.m)}/${p.y}`;
}

/** dd/mm */
export function formatDayMonth(iso: string | null | undefined): string {
  if (!iso) return "—";
  const p = parseParts(iso);
  if (!p) return "—";
  return `${pad(p.d)}/${pad(p.m)}`;
}

/** HH:mm */
export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const p = parseParts(iso);
  if (!p) return "—";
  return `${pad(p.hh)}:${pad(p.mm)}`;
}

/**
 * Converte a data (horário de Brasília, sem tz) em timestamp epoch. Usado
 * pela contagem regressiva. Considera o offset de Brasília (-03:00, sem
 * horário de verão desde 2019).
 */
export function toEpoch(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const m = ISO_NAIVE.exec(iso.trim());
  if (m) {
    return Date.UTC(
      Number(m[1]),
      Number(m[2]) - 1,
      Number(m[3]),
      Number(m[4] ?? 0) + 3,
      Number(m[5] ?? 0),
      Number(m[6] ?? 0)
    );
  }
  const t = new Date(iso).getTime();
  return Number.isNaN(t) ? null : t;
}

/** "há 3 min", "há 2 h", "há 5 dias" ou a data completa quando muito antiga. */
export function formatRelative(iso: string | null | undefined): string {
  const t = toEpoch(iso);
  if (t === null) return "—";
  const diff = Date.now() - t;
  const abs = Math.abs(diff);
  const future = diff < 0;
  const min = Math.round(abs / 60000);
  if (min < 1) return future ? "em instantes" : "agora";
  if (min < 60) return future ? `em ${min} min` : `há ${min} min`;
  const h = Math.round(min / 60);
  if (h < 48) return future ? `em ${h} h` : `há ${h} h`;
  const d = Math.round(h / 24);
  if (d < 30) return future ? `em ${d} dias` : `há ${d} dias`;
  return formatDate(iso);
}

/** Duração humana a partir de ms. */
export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms} ms`;
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  const rs = s % 60;
  if (m < 60) return rs ? `${m} min ${rs} s` : `${m} min`;
  const h = Math.floor(m / 60);
  return `${h} h ${m % 60} min`;
}

/** Intervalo em MINUTOS (scrape_frequency) → "4 h", "90 min". Não confundir
 *  com formatDuration, que recebe milissegundos. */
export function formatMinutes(min: number): string {
  if (!Number.isFinite(min) || min <= 0) return "—";
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  const m = min % 60;
  return m ? `${h} h ${m} min` : `${h} h`;
}

/** Converte "yyyy-mm-dd" de um <input type=date> para o filtro session_from/to. */
export function dateInputToIso(value: string, endOfDay = false): string | undefined {
  if (!value) return undefined;
  return `${value}T${endOfDay ? "23:59:59" : "00:00:00"}`;
}

export function isoToDateInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const m = ISO_NAIVE.exec(iso.trim());
  return m ? `${m[1]}-${m[2]}-${m[3]}` : "";
}

export function slugify(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/* ───────── Telefone (Onda 2) ─────────
 * O backend guarda só dígitos com DDI ("5511987654321"); a interface mostra
 * e digita no formato brasileiro "(11) 98765-4321".
 */

/** Dígitos do telefone sem o DDI 55, para alimentar a máscara. */
export function phoneDigits(value: string | null | undefined): string {
  let d = (value ?? "").replace(/\D/g, "");
  if (d.startsWith("55") && d.length > 11) d = d.slice(2);
  return d.slice(0, 11);
}

/** Máscara progressiva: aceita digitação parcial sem travar o cursor. */
export function maskPhone(value: string | null | undefined): string {
  const d = phoneDigits(value);
  if (!d) return "";
  if (d.length <= 2) return `(${d}`;
  const ddd = d.slice(0, 2);
  const rest = d.slice(2);
  if (rest.length <= 4) return `(${ddd}) ${rest}`;
  const split = rest.length > 8 ? 5 : 4;
  return `(${ddd}) ${rest.slice(0, split)}-${rest.slice(split)}`;
}

/** Telefone válido para o backend: DDD + 8 ou 9 dígitos. */
export function isValidPhone(value: string | null | undefined): boolean {
  const d = phoneDigits(value);
  return d.length === 10 || d.length === 11;
}

/** Só HH:MM (janela de silêncio). Vazio é válido: usa a janela global. */
export function isValidTimeWindow(value: string): boolean {
  return value === "" || /^([01]\d|2[0-3]):([0-5]\d)$/.test(value.trim());
}
