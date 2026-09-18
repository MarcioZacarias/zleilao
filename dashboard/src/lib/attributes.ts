import type { CategoryField } from "../services/types";
import { formatBRL, formatDate, formatDecimal, formatInt } from "./format";

export const NOT_INFORMED = "não informado";

/**
 * RN-002: valor de atributo formatado conforme o field_def. Ausente/null ou
 * enum "nao_informado" → "não informado". Unidade acompanha o valor.
 */
export function formatAttribute(field: CategoryField, value: unknown): string {
  if (value === null || value === undefined || value === "") return NOT_INFORMED;
  if (typeof value === "string" && value.trim().toLowerCase() === "nao_informado") return NOT_INFORMED;

  const unit = field.unit?.trim();

  switch (field.field_type) {
    case "bool":
      if (typeof value === "boolean") return value ? "Sim" : "Não";
      if (typeof value === "string") {
        const v = value.toLowerCase();
        if (["true", "sim", "1", "yes"].includes(v)) return "Sim";
        if (["false", "nao", "não", "0", "no"].includes(v)) return "Não";
      }
      return String(value);
    case "int":
    case "decimal": {
      const n = typeof value === "number" ? value : Number(String(value).replace(",", "."));
      if (!Number.isFinite(n)) return withUnit(String(value), unit);
      if (unit && unit.toUpperCase() === "BRL") return formatBRL(n);
      // Ano é numeral, não quantidade: 2017, nunca "2.017".
      if (isYearField(field)) return String(Math.trunc(n));
      return withUnit(field.field_type === "int" ? formatInt(n) : formatDecimal(n), unit);
    }
    case "date":
      return typeof value === "string" ? formatDate(value) : String(value);
    default:
      if (Array.isArray(value)) return value.map((v) => String(v)).join(", ") || NOT_INFORMED;
      if (typeof value === "object") return JSON.stringify(value);
      return withUnit(String(value), unit);
  }
}

/** Campo de ano: inteiro sem unidade cuja chave/rótulo fala de ano. */
function isYearField(field: CategoryField): boolean {
  if (field.field_type !== "int" || field.unit) return false;
  return /(^|_)ano($|_)/.test(field.key) || /\bano\b/i.test(field.label);
}

function withUnit(text: string, unit?: string): string {
  if (!unit) return text;
  if (unit.toUpperCase() === "BRL") return text;
  return `${text} ${unit}`;
}

/** Valor bruto → string editável em formulário admin. */
export function attributeToInput(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/** String de input → valor tipado para PATCH /items (attributes). */
export function inputToAttribute(field: CategoryField, text: string): unknown {
  const t = text.trim();
  if (t === "") return null;
  switch (field.field_type) {
    case "bool":
      return t === "true";
    case "int": {
      const n = parseInt(t.replace(/\./g, ""), 10);
      return Number.isFinite(n) ? n : null;
    }
    case "decimal": {
      const n = Number(t.replace(/\./g, "").replace(",", "."));
      return Number.isFinite(n) ? n : null;
    }
    default:
      return t;
  }
}
