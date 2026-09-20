// O `criteria` do filtro salvo usa exatamente as chaves da busca pública
// (docs/API.md → "Critério do filtro salvo"), então a query string de /busca
// vira filtro sem tradução. Aqui ficam a extração, o resumo legível e a volta
// para a URL de busca.
import type { Criteria, CriteriaKey } from "../services/types";
import { AUCTION_TYPE_LABELS, CONDITION_LABELS, CRITERIA_LABELS } from "./labels";
import { formatBRL } from "./format";

export const CRITERIA_KEYS: CriteriaKey[] = [
  "q",
  "category",
  "brand",
  "model",
  "year_min",
  "year_max",
  "price_min",
  "price_max",
  "state",
  "city",
  "source",
  "condition",
  "auction_type",
];

const INT_KEYS = new Set<CriteriaKey>(["year_min", "year_max"]);
const FLOAT_KEYS = new Set<CriteriaKey>(["price_min", "price_max"]);

/** Só as chaves que viram critério — `sort`, `page` e `status` ficam de fora. */
export function criteriaFromParams(sp: URLSearchParams): Criteria {
  const out: Criteria = {};
  for (const key of CRITERIA_KEYS) {
    const raw = sp.get(key);
    if (raw === null || raw.trim() === "") continue;
    if (INT_KEYS.has(key) || FLOAT_KEYS.has(key)) {
      const n = Number(raw);
      if (Number.isFinite(n)) out[key] = INT_KEYS.has(key) ? Math.trunc(n) : n;
      continue;
    }
    out[key] = raw.trim().slice(0, 120);
  }
  return out;
}

/** Query string de /busca equivalente ao critério (para "ver na busca"). */
export function criteriaToSearch(criteria: Criteria): string {
  const sp = new URLSearchParams();
  for (const key of CRITERIA_KEYS) {
    const v = criteria[key];
    if (v === undefined || v === null || v === "") continue;
    sp.set(key, String(v));
  }
  const qs = sp.toString();
  return qs ? `/busca?${qs}` : "/busca";
}

export function criteriaCount(criteria: Criteria): number {
  return CRITERIA_KEYS.filter((k) => {
    const v = criteria[k];
    return v !== undefined && v !== null && v !== "";
  }).length;
}

/** Valor formatado para exibição (preço em BRL, enums com rótulo pt-BR). */
export function criteriaValueLabel(key: CriteriaKey, value: unknown): string {
  const s = String(value);
  switch (key) {
    case "price_min":
    case "price_max":
      return formatBRL(s);
    case "condition":
      return CONDITION_LABELS[s] ?? s;
    case "auction_type":
      return AUCTION_TYPE_LABELS[s] ?? s;
    default:
      return s;
  }
}

/** Lista "Marca: Fiat", "Preço até: R$ 50.000,00"… para chips e resumos. */
export function criteriaPairs(criteria: Criteria): { key: CriteriaKey; label: string; value: string }[] {
  return CRITERIA_KEYS.filter((k) => {
    const v = criteria[k];
    return v !== undefined && v !== null && v !== "";
  }).map((k) => ({
    key: k,
    label: CRITERIA_LABELS[k] ?? k,
    value: criteriaValueLabel(k, criteria[k]),
  }));
}

/** Resumo em uma linha. Critério vazio = "qualquer lote novo". */
export function describeCriteria(criteria: Criteria): string {
  const pairs = criteriaPairs(criteria);
  if (!pairs.length) return "Qualquer lote novo";
  return pairs.map((p) => `${p.label}: ${p.value}`).join(" · ");
}

/**
 * Nome sugerido para o filtro: curto o bastante para caber na lista, mas
 * reconhecível. O servidor gera o dele quando o nome vem vazio; aqui o
 * usuário vê e edita antes de salvar.
 */
export function suggestFilterName(criteria: Criteria): string {
  const bits: string[] = [];
  if (criteria.q) bits.push(String(criteria.q));
  if (criteria.brand) bits.push(String(criteria.brand));
  if (criteria.model) bits.push(String(criteria.model));
  if (!bits.length && criteria.category) bits.push(String(criteria.category).replace(/-/g, " "));

  const extras: string[] = [];
  if (criteria.year_min && criteria.year_max) extras.push(`${criteria.year_min}–${criteria.year_max}`);
  else if (criteria.year_min) extras.push(`a partir de ${criteria.year_min}`);
  else if (criteria.year_max) extras.push(`até ${criteria.year_max}`);

  if (criteria.price_max) extras.push(`até ${formatBRL(criteria.price_max)}`);
  else if (criteria.price_min) extras.push(`acima de ${formatBRL(criteria.price_min)}`);

  if (criteria.state) extras.push(String(criteria.state));
  if (criteria.city) extras.push(String(criteria.city));
  if (criteria.condition) extras.push(CONDITION_LABELS[String(criteria.condition)] ?? String(criteria.condition));

  const head = bits.join(" ").trim();
  const name = [head || "Todos os lotes", extras.join(" · ")].filter(Boolean).join(" · ");
  return name.slice(0, 120);
}
