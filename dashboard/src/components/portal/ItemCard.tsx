import { Link } from "react-router-dom";
import { CalendarClock, Copy, MapPin, Gauge } from "lucide-react";
import type { ItemCard as ItemCardType } from "../../services/types";
import { formatDateTime, formatKm, formatRelative } from "../../lib/format";
import { ENUM_VALUE_LABELS } from "../../lib/labels";
import { SafeImage } from "../ui/SafeImage";
import { PriceTag } from "./PriceTag";
import { StatusBadge } from "./StatusBadge";
import { ConditionBadge } from "./ConditionBadge";
import { Countdown } from "./Countdown";
import { OpportunityBadge } from "./OpportunityPanel";
import { ParcelamentoBadge } from "./ParcelamentoJudicial";

interface ItemCardProps {
  item: ItemCardType;
  compact?: boolean;
}

function subtitle(item: ItemCardType): string | null {
  const bits = [item.brand, item.model, item.year_model ? String(item.year_model) : null].filter(Boolean);
  return bits.length ? bits.join(" · ") : null;
}

/**
 * Chips do card. `card_fields` vem sem os field_defs, então o valor cru de
 * enum precisa virar rótulo aqui — senão o card mostra "nao_informado".
 * E "não informado" não vira chip: chip é para o que a fonte informou.
 */
function cardFieldEntries(item: ItemCardType): [string, string][] {
  return Object.entries(item.card_fields ?? {})
    .filter(([, v]) => v !== null && v !== undefined && v !== "" && !isNotInformed(v))
    .slice(0, 3)
    .map(([k, v]) => [k, chipValue(v)]);
}

function isNotInformed(v: unknown): boolean {
  return typeof v === "string" && v.trim().toLowerCase().replace(/\s/g, "_") === "nao_informado";
}

function chipValue(v: unknown): string {
  if (typeof v === "boolean") return v ? "sim" : "não";
  const s = String(v);
  return ENUM_VALUE_LABELS[s] ?? s;
}

/** Card da vitrine — sempre mostra fonte e última coleta (RN-001). */
export function ItemCard({ item, compact = false }: ItemCardProps) {
  const sub = subtitle(item);
  const closed = item.status === "closed";
  const soon = item.status === "auction_soon";
  const extra = cardFieldEntries(item);

  return (
    <Link
      to={`/lote/${item.id}`}
      className={`portal-card portal-card-hover group flex flex-col overflow-hidden focus:outline-none focus:ring-2 focus:ring-accent/50 ${
        closed ? "opacity-80" : ""
      }`}
    >
      <div className="relative aspect-[4/3] w-full overflow-hidden bg-radar-surface2">
        <SafeImage
          src={item.image_url}
          alt={item.title}
          className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
          fallbackClassName="h-full w-full"
        />
        <div className="absolute left-2 top-2 flex flex-wrap gap-1">
          <StatusBadge status={item.status} />
          <ConditionBadge condition={item.condition} />
        </div>
        {item.possible_duplicate && (
          <span
            title="Este lote pode estar publicado em mais de uma fonte (RN-004)"
            className="absolute right-2 top-2 inline-flex items-center gap-1 rounded-full bg-radar-bg/80 px-2 py-0.5 text-[11px] font-medium text-radar-muted ring-1 ring-inset ring-white/10 backdrop-blur"
          >
            <Copy size={11} /> possível duplicado
          </span>
        )}
        {item.lot_number && (
          <span className="absolute bottom-2 left-2 rounded-md bg-radar-bg/80 px-2 py-0.5 text-[11px] font-medium text-radar-text backdrop-blur">
            Lote {item.lot_number}
          </span>
        )}
        {item.auction_type && (
          <span className="absolute bottom-2 right-2 rounded-md bg-radar-bg/80 px-2 py-0.5 text-[11px] text-radar-muted backdrop-blur">
            {item.auction_type === "judicial" ? "Judicial" : item.auction_type === "extrajudicial" ? "Extrajudicial" : item.auction_type}
          </span>
        )}
      </div>

      <div className={`flex flex-1 flex-col ${compact ? "p-3" : "p-4"}`}>
        {item.category_name && (
          <div className="mb-1 text-[11px] uppercase tracking-wider text-radar-muted">{item.category_name}</div>
        )}
        <h3 className="line-clamp-2 text-sm font-semibold leading-snug text-radar-text group-hover:text-white">
          {item.title}
        </h3>
        {sub && <p className="mt-0.5 truncate text-xs text-radar-muted">{sub}</p>}

        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-radar-muted">
          {(item.city || item.state) && (
            <span className="inline-flex items-center gap-1">
              <MapPin size={12} />
              {[item.city, item.state].filter(Boolean).join(" / ")}
              {/* Distância só aparece na busca por raio — é o que explica a ordem. */}
              {item.distance_km !== null && item.distance_km !== undefined && (
                <span className="text-accent-300" title="Distância entre a sua cidade e a cidade do lote">
                  {/* Abaixo de 1 km é o mesmo município: "0 km" só confundiria. */}
                  · {item.distance_km < 1 ? "sua cidade" : `${Math.round(item.distance_km)} km`}
                </span>
              )}
            </span>
          )}
          {item.km !== null && item.km !== undefined && (
            <span className="inline-flex items-center gap-1">
              <Gauge size={12} />
              {formatKm(item.km)}
            </span>
          )}
          {extra.map(([k, v]) => (
            <span key={k} className="truncate" title={k}>
              {v}
            </span>
          ))}
        </div>

        <div className="mt-3 flex items-end justify-between gap-2">
          <PriceTag price={item.price} priceKind={item.price_kind} priceSecond={item.price_second} size="sm" closed={closed} />
        </div>

        {/* RN-010: selo só quando há referência confiável. Ausência de score
            não é desconto zero — é "não sabemos". */}
        {(item.auction_type === "judicial" ||
          (item.opportunity_discount !== null && item.opportunity_discount !== undefined)) && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            {item.opportunity_discount !== null && item.opportunity_discount !== undefined && (
              <OpportunityBadge discount={item.opportunity_discount} />
            )}
            {item.auction_type === "judicial" && <ParcelamentoBadge />}
          </div>
        )}

        {item.next_session_at && !closed && (
          <div
            className={`mt-2 inline-flex items-center gap-1.5 text-xs ${soon ? "text-accent-300" : "text-radar-muted"}`}
            title={formatDateTime(item.next_session_at)}
          >
            <CalendarClock size={13} />
            {soon ? (
              <>
                Pregão em <Countdown target={item.next_session_at} size="sm" pastLabel="andamento" />
              </>
            ) : (
              <>Pregão {formatDateTime(item.next_session_at)}</>
            )}
          </div>
        )}

        <div className="mt-3 flex items-center justify-between gap-2 border-t border-radar-border pt-2 text-[11px] text-radar-muted">
          <span className="truncate" title="Fonte">
            {item.source_name ?? "Fonte não informada"}
          </span>
          <span className="shrink-0" title={`Última coleta: ${formatDateTime(item.last_seen_at)}`}>
            coleta {formatRelative(item.last_seen_at)}
          </span>
        </div>
      </div>
    </Link>
  );
}
