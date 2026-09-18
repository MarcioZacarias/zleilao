import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ChevronRight, ExternalLink, Gavel, Layers, AlertTriangle } from "lucide-react";
import axios from "axios";
import { portalApi } from "../../services/portal";
import type { Auction, ItemCard as ItemCardType } from "../../services/types";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { formatBRL, formatDateTime } from "../../lib/format";
import { AUCTION_TYPE_LABELS, MODALITY_LABELS, SESSION_KIND_LABELS } from "../../lib/labels";
import { NOT_INFORMED } from "../../lib/attributes";
import { ItemCard } from "../../components/portal/ItemCard";
import { Countdown } from "../../components/portal/Countdown";
import { nextSession } from "../../components/portal/AuctionCard";
import { ItemCardSkeleton, Skeleton } from "../../components/ui/Skeleton";
import { EmptyState } from "../../components/ui/EmptyState";
import { Button } from "../../components/ui/Button";
import { errorMessage } from "../../services/api";

function Info({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wider text-radar-muted">{label}</dt>
      <dd className={`text-sm ${value ? "text-radar-text" : "italic text-radar-muted/70"}`}>{value ?? NOT_INFORMED}</dd>
    </div>
  );
}

export default function AuctionPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<{ auction: Auction; items: ItemCardType[] } | null>(null);
  const [error, setError] = useState<{ status?: number; message: string } | null>(null);
  const [loading, setLoading] = useState(true);
  useDocumentTitle(data?.auction.title ?? "Pregão");

  useEffect(() => {
    if (!id) return;
    let alive = true;
    setLoading(true);
    setError(null);
    portalApi
      .auction(id)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError({ status: axios.isAxiosError(e) ? e.response?.status : undefined, message: errorMessage(e) }))
      .finally(() => alive && setLoading(false));
    window.scrollTo({ top: 0 });
    return () => {
      alive = false;
    };
  }, [id]);

  if (loading) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        <Skeleton tone="dark" className="mb-4 h-3 w-48" />
        <Skeleton tone="dark" className="mb-6 h-40 w-full" rounded="rounded-xl" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <ItemCardSkeleton key={i} />
          ))}
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16 sm:px-6">
        <div className="portal-card">
          <EmptyState
            tone="dark"
            icon={error?.status === 404 ? Gavel : AlertTriangle}
            title={error?.status === 404 ? "Pregão não encontrado" : "Não foi possível carregar o pregão"}
            description={error?.status === 404 ? "Este pregão pode ter sido removido da fonte." : error?.message}
            action={
              <Link to="/busca">
                <Button variant="accent" size="sm">Buscar lotes</Button>
              </Link>
            }
          />
        </div>
      </div>
    );
  }

  const { auction, items } = data;
  const s = nextSession(auction);
  const title = auction.title ?? auction.auctioneer_name ?? `Pregão #${auction.external_id}`;

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
      <nav className="mb-4 flex flex-wrap items-center gap-1 text-xs text-radar-muted" aria-label="Navegação">
        <Link to="/" className="hover:text-radar-text">Início</Link>
        <ChevronRight size={12} />
        <Link to="/busca?status=auction_soon&sort=session_asc" className="hover:text-radar-text">Pregões</Link>
        <ChevronRight size={12} />
        <span className="truncate text-radar-text/80">{title}</span>
      </nav>

      {/* Cabeçalho do pregão */}
      <header className="portal-card p-5 md:p-6">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0 flex-1">
            <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
              <span className="inline-flex items-center gap-1 rounded-full bg-accent/10 px-2.5 py-1 font-semibold text-accent-300 ring-1 ring-inset ring-accent/30">
                <Gavel size={12} /> Pregão
              </span>
              {auction.auction_type && (
                <span className="rounded-full bg-white/5 px-2.5 py-1 text-radar-muted ring-1 ring-inset ring-white/10">
                  {AUCTION_TYPE_LABELS[auction.auction_type] ?? auction.auction_type}
                </span>
              )}
              {auction.modality && (
                <span className="rounded-full bg-white/5 px-2.5 py-1 text-radar-muted ring-1 ring-inset ring-white/10">
                  {MODALITY_LABELS[auction.modality] ?? auction.modality}
                </span>
              )}
            </div>
            <h1 className="text-xl font-bold text-radar-text md:text-2xl">{title}</h1>
            <p className="mt-1 text-sm text-radar-muted">
              Fonte: <span className="text-radar-text">{auction.source_name ?? NOT_INFORMED}</span>
            </p>
            <dl className="mt-4 grid grid-cols-2 gap-4 md:grid-cols-4">
              <Info label="Leiloeiro" value={auction.auctioneer_name} />
              <Info label="Registro" value={auction.auctioneer_registration} />
              <Info label="Comitente / Vara" value={auction.committer_name} />
              <Info label="Lotes" value={String(auction.items_count)} />
            </dl>
          </div>

          <div className="shrink-0 space-y-3 lg:w-72">
            {s?.starts_at && (
              <div className="rounded-xl bg-radar-surface2 p-3 ring-1 ring-inset ring-white/10">
                <div className="text-[11px] uppercase tracking-wider text-radar-muted">
                  Próxima sessão · {SESSION_KIND_LABELS[s.kind] ?? s.kind}
                </div>
                <div className="mt-1 text-sm text-radar-text">{formatDateTime(s.starts_at)}</div>
                <div className="mt-2">
                  <Countdown target={s.starts_at} size="sm" pastLabel="Sessão iniciada" />
                </div>
              </div>
            )}
            {auction.official_url && (
              <a
                href={auction.official_url}
                target="_blank"
                rel="noopener"
                className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-accent px-4 py-2.5 text-sm font-bold text-[#0b1020] hover:bg-accent-400"
              >
                Ver pregão no site oficial <ExternalLink size={15} />
              </a>
            )}
          </div>
        </div>

        {auction.sessions.length > 0 && (
          <div className="mt-5 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wider text-radar-muted">
                  <th className="py-1.5 pr-3 font-medium">Sessão</th>
                  <th className="py-1.5 pr-3 font-medium">Início</th>
                  <th className="py-1.5 pr-3 font-medium">Término</th>
                  <th className="py-1.5 text-right font-medium">Lance mín.</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-radar-border">
                {[...auction.sessions]
                  .sort((a, b) => a.sequence - b.sequence)
                  .map((se) => (
                    <tr key={se.id}>
                      <td className="py-2 pr-3 font-medium text-radar-text">{SESSION_KIND_LABELS[se.kind] ?? se.kind}</td>
                      <td className="py-2 pr-3 text-radar-text/90">{formatDateTime(se.starts_at)}</td>
                      <td className="py-2 pr-3 text-radar-text/90">{formatDateTime(se.ends_at)}</td>
                      <td className="py-2 text-right tabular-nums text-radar-text/90">{se.min_bid ? formatBRL(se.min_bid) : "—"}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        )}
      </header>

      {/* Lotes */}
      <section className="mt-8">
        <h2 className="mb-4 flex items-center gap-2 text-lg font-bold text-radar-text">
          <Layers size={18} className="text-accent" /> Lotes deste pregão
          <span className="text-sm font-normal text-radar-muted">({items.length})</span>
        </h2>
        {items.length === 0 ? (
          <div className="portal-card">
            <EmptyState tone="dark" icon={Layers} title="Nenhum lote visível" description="Os lotes deste pregão ainda não foram publicados ou já foram encerrados." />
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {items.map((it) => (
              <ItemCard key={it.id} item={it} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
