import { AlertTriangle, Skull } from "lucide-react";
import { CONDITION_LABELS, isAlertCondition } from "../../lib/labels";

interface ConditionBadgeProps {
  condition: string | null | undefined;
  size?: "sm" | "md";
  /** Mostra também "Normal"/"Não informado" (fichas); por padrão só alertas. */
  showAll?: boolean;
  tone?: "portal" | "admin";
}

const SEVERE = new Set(["sucata", "sinistro_grande_monta"]);

/** Selo de alerta quando condition ∉ {normal, nao_informado} (sinistro/sucata). */
export function ConditionBadge({ condition, size = "sm", showAll = false, tone = "portal" }: ConditionBadgeProps) {
  if (!condition) return null;
  const alert = isAlertCondition(condition);
  if (!alert && !showAll) return null;

  const pad = size === "md" ? "px-3 py-1 text-xs" : "px-2 py-0.5 text-[11px]";
  const severe = SEVERE.has(condition);

  let cls: string;
  if (tone === "admin") {
    cls = alert
      ? severe
        ? "bg-red-100 text-red-700"
        : "bg-orange-100 text-orange-700"
      : "bg-gray-100 text-gray-600";
  } else {
    cls = alert
      ? severe
        ? "bg-red-500/15 text-red-300 ring-1 ring-inset ring-red-400/30"
        : "bg-orange-500/15 text-orange-300 ring-1 ring-inset ring-orange-400/30"
      : "bg-white/5 text-radar-muted ring-1 ring-inset ring-white/10";
  }

  return (
    <span className={`inline-flex items-center gap-1 rounded-full font-semibold whitespace-nowrap ${pad} ${cls}`}>
      {alert && (severe ? <Skull size={size === "md" ? 13 : 11} /> : <AlertTriangle size={size === "md" ? 13 : 11} />)}
      {CONDITION_LABELS[condition] ?? condition}
    </span>
  );
}
