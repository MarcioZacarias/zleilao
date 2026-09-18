import { Link } from "react-router-dom";
import { CalendarClock, Gavel, Layers } from "lucide-react";
import type { Auction } from "../../services/types";
import { formatDateTime, formatDayMonth, formatTime, toEpoch } from "../../lib/format";
import { AUCTION_TYPE_LABELS, MODALITY_LABELS, SESSION_KIND_LABELS } from "../../lib/labels";

/** Próxima sessão futura (ou a primeira) de um pregão. */
export function nextSession(a: Auction) {
  const now = Date.now();
  const future = a.sessions
    .filter((s) => (toEpoch(s.starts_at) ?? -1) >= now)
    .sort((x, y) => (x.starts_at! < y.starts_at! ? -1 : 1));
  return future[0] ?? a.sessions[0] ?? null;
}

export function AuctionCard({ auction }: { auction: Auction }) {
  const s = nextSession(auction);
  const when = s?.starts_at ?? auction.starts_at;
  return (
    // min-w-0: item de grid tem min-width:auto e não encolhe abaixo do
    // conteúdo — sem isso o card estoura a viewport do celular.
    <Link
      to={`/pregao/${auction.id}`}
      className="portal-card portal-card-hover flex min-w-0 items-stretch gap-4 p-4 focus:outline-none focus:ring-2 focus:ring-accent/50"
    >
      <div className="flex w-16 shrink-0 flex-col items-center justify-center rounded-lg bg-radar-surface2 ring-1 ring-inset ring-white/10">
        <span className="text-lg font-bold leading-none text-accent">{formatDayMonth(when)}</span>
        <span className="mt-1 text-[11px] text-radar-muted">{formatTime(when)}</span>
      </div>
      <div className="min-w-0 flex-1">
        <h3 className="truncate text-sm font-semibold text-radar-text">
          {auction.title ?? auction.auctioneer_name ?? `Pregão #${auction.external_id}`}
        </h3>
        <p className="mt-0.5 truncate text-xs text-radar-muted">
          {[auction.auctioneer_name, auction.source_name].filter(Boolean).join(" · ") || "Leiloeiro não informado"}
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-radar-muted">
          {s && (
            <span className="inline-flex items-center gap-1">
              <CalendarClock size={12} /> {SESSION_KIND_LABELS[s.kind] ?? s.kind}
              <span className="hidden sm:inline">· {formatDateTime(s.starts_at)}</span>
            </span>
          )}
          {auction.auction_type && (
            <span className="inline-flex items-center gap-1">
              <Gavel size={12} /> {AUCTION_TYPE_LABELS[auction.auction_type] ?? auction.auction_type}
            </span>
          )}
          {auction.modality && <span>{MODALITY_LABELS[auction.modality] ?? auction.modality}</span>}
          <span className="inline-flex items-center gap-1">
            <Layers size={12} /> {auction.items_count} {auction.items_count === 1 ? "lote" : "lotes"}
          </span>
        </div>
      </div>
    </Link>
  );
}
