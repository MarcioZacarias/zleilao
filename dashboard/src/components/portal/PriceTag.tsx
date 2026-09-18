import { formatBRL } from "../../lib/format";
import { PRICE_KIND_LABELS } from "../../lib/labels";

interface PriceTagProps {
  price: string | null;
  priceKind: string | null;
  priceSecond?: string | null;
  size?: "sm" | "md" | "lg";
  closed?: boolean;
}

const sizes = {
  sm: { label: "text-[11px]", price: "text-base", second: "text-xs" },
  md: { label: "text-xs", price: "text-xl", second: "text-sm" },
  lg: { label: "text-sm", price: "text-3xl md:text-4xl", second: "text-base" },
};

/** Preço com rótulo (RN: lance_inicial → "Lance inicial"; 2ª praça quando houver). */
export function PriceTag({ price, priceKind, priceSecond, size = "md", closed = false }: PriceTagProps) {
  const s = sizes[size];
  const label = priceKind ? PRICE_KIND_LABELS[priceKind] ?? priceKind : "Valor";
  return (
    <div className="min-w-0">
      <div className={`${s.label} uppercase tracking-wider text-radar-muted`}>{label}</div>
      <div
        className={`${s.price} font-bold tabular-nums leading-tight ${
          closed ? "text-radar-muted line-through decoration-radar-muted/60" : "text-accent"
        }`}
      >
        {price ? formatBRL(price) : <span className="text-radar-muted font-medium">não informado</span>}
      </div>
      {priceSecond && (
        <div className={`${s.second} mt-0.5 text-radar-text/90 tabular-nums`}>
          <span className="text-radar-muted">2ª praça:</span> {formatBRL(priceSecond)}
        </div>
      )}
    </div>
  );
}
