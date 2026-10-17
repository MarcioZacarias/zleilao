import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Gavel, Radio, CalendarClock, Layers, Sparkles, Clock, Car } from "lucide-react";
import { portalApi } from "../../services/portal";
import type { Auction, Category, ItemCard as ItemCardType, PortalStats } from "../../services/types";
import { useBranding } from "../../hooks/useBranding";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { formatDateTime, formatInt, formatRelative } from "../../lib/format";
import { SearchBar } from "../../components/portal/SearchBar";
import { ItemCard } from "../../components/portal/ItemCard";
import { AuctionCard } from "../../components/portal/AuctionCard";
import { SectionHeader } from "../../components/portal/SectionHeader";
import { Countdown } from "../../components/portal/Countdown";
import { ItemCardSkeleton, Skeleton } from "../../components/ui/Skeleton";
import { EmptyState } from "../../components/ui/EmptyState";

function StatTile({
  icon,
  label,
  value,
  hint,
  loading,
}: {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
  hint?: string;
  loading: boolean;
}) {
  return (
    <div className="portal-card flex items-center gap-3 p-4">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-accent/10 text-accent">{icon}</div>
      <div className="min-w-0">
        {loading ? (
          <Skeleton tone="dark" className="h-6 w-20" />
        ) : (
          <div className="truncate text-xl font-bold tabular-nums text-radar-text">{value}</div>
        )}
        <div className="text-xs text-radar-muted">{label}</div>
        {hint && !loading && <div className="truncate text-[11px] text-radar-muted/70">{hint}</div>}
      </div>
    </div>
  );
}

export default function Home() {
  const branding = useBranding();
  useDocumentTitle(null);

  const [stats, setStats] = useState<PortalStats | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [upcoming, setUpcoming] = useState<Auction[] | null>(null);
  const [latest, setLatest] = useState<ItemCardType[] | null>(null);
  const [soon, setSoon] = useState<ItemCardType[] | null>(null);

  useEffect(() => {
    portalApi.stats().then(setStats).catch(() => setStats(null));
    portalApi.categories().then(setCategories).catch(() => setCategories([]));
    portalApi.upcomingAuctions(7, 6).then(setUpcoming).catch(() => setUpcoming([]));
    portalApi
      .items({ sort: "newest", page_size: 12, facets: false })
      .then((p) => setLatest(p.items))
      .catch(() => setLatest([]));
    portalApi
      .items({ status: "auction_soon", sort: "session_asc", page_size: 8, facets: false })
      .then((p) => setSoon(p.items))
      .catch(() => setSoon([]));
  }, []);

  const statsLoading = stats === null;
  const chips = categories.slice(0, 12);

  return (
    <div>
      {/* Hero */}
      <section className="relative overflow-hidden border-b border-radar-border">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-60"
          style={{
            background:
              "radial-gradient(60% 50% at 50% 0%, rgba(245,158,11,0.18) 0%, rgba(11,16,32,0) 70%), radial-gradient(40% 40% at 90% 30%, rgba(37,99,235,0.15) 0%, rgba(11,16,32,0) 70%)",
          }}
        />
        <div className="relative mx-auto max-w-7xl px-4 pb-10 pt-12 sm:px-6 md:pb-14 md:pt-20">
          <div className="mx-auto max-w-3xl text-center">
            <span className="inline-flex items-center gap-2 rounded-full border border-accent/30 bg-accent/10 px-3 py-1 text-xs font-medium text-accent-300">
              <Radio size={13} className="animate-pulse" /> Radar de leilões de veículos
            </span>
            <h1 className="mt-4 text-3xl font-extrabold leading-tight tracking-tight text-radar-text sm:text-4xl md:text-5xl">
              {branding.tagline || "Todos os leilões de veículos do Brasil em um só radar"}
            </h1>
            <p className="mt-3 text-base text-radar-muted md:text-lg">
              Buscamos e normalizamos os lotes dos principais leiloeiros. O lance é sempre no site oficial.
            </p>
            <div className="mt-6">
              <SearchBar size="lg" autoFocus={false} />
            </div>
            {chips.length > 0 && (
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                {chips.map((c) => (
                  <Link
                    key={c.id}
                    to={`/busca?category=${encodeURIComponent(c.slug)}`}
                    className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-radar-surface px-3 py-1.5 text-xs text-radar-text transition-colors hover:border-accent/40 hover:text-accent-300"
                  >
                    {c.name}
                    <span className="text-radar-muted tabular-nums">{formatInt(c.items_count)}</span>
                  </Link>
                ))}
                {/* Judicial = pode propor parcelamento (CPC, art. 895); o atalho é o filtro por tipo. */}
                <Link
                  to="/busca?auction_type=judicial"
                  title="Leilões judiciais: o CPC (art. 895) admite proposta parcelada — 25% à vista e o restante em até 30 meses"
                  className="inline-flex items-center gap-1.5 rounded-full border border-sky-400/30 bg-sky-500/10 px-3 py-1.5 text-xs text-sky-200 transition-colors hover:border-sky-300/60 hover:text-sky-100"
                >
                  Pode parcelar
                  <span className="text-sky-200/60">judiciais</span>
                </Link>
              </div>
            )}
          </div>
        </div>
      </section>

      <div className="mx-auto max-w-7xl space-y-12 px-4 py-8 sm:px-6 md:py-10">
        {/* Stats */}
        <section aria-label="Resumo" className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <StatTile
            icon={<Layers size={18} />}
            label="Lotes publicados"
            value={stats ? formatInt(stats.items_published) : "—"}
            loading={statsLoading}
          />
          <StatTile
            icon={<Radio size={18} />}
            label="Fontes monitoradas"
            value={stats ? formatInt(stats.sources_active) : "—"}
            hint={stats?.last_collected_at ? `última coleta ${formatRelative(stats.last_collected_at)}` : undefined}
            loading={statsLoading}
          />
          <StatTile
            icon={<Gavel size={18} />}
            label="Pregões nos próximos 7 dias"
            value={stats ? formatInt(stats.auctions_upcoming_7d) : "—"}
            loading={statsLoading}
          />
          <StatTile
            icon={<CalendarClock size={18} />}
            label="Próxima sessão"
            value={
              stats?.next_session_at ? (
                <Countdown target={stats.next_session_at} size="sm" pastLabel="agora" />
              ) : (
                "—"
              )
            }
            hint={stats?.next_session_at ? formatDateTime(stats.next_session_at) : undefined}
            loading={statsLoading}
          />
        </section>

        {/* Pregões em breve */}
        <section>
          <SectionHeader
            icon={<Gavel size={20} className="text-accent" />}
            title="Pregões em breve"
            subtitle="Sessões agendadas para os próximos 7 dias"
            to="/busca?status=auction_soon&sort=session_asc"
            linkLabel="Ver lotes"
          />
          {upcoming === null ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} tone="dark" className="h-24" rounded="rounded-xl" />
              ))}
            </div>
          ) : upcoming.length === 0 ? (
            <div className="portal-card">
              <EmptyState
                tone="dark"
                compact
                icon={CalendarClock}
                title="Nenhum pregão nos próximos dias"
                description="Assim que as fontes publicarem novas sessões elas aparecem aqui."
              />
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {upcoming.map((a) => (
                <AuctionCard key={a.id} auction={a} />
              ))}
            </div>
          )}
        </section>

        {/* Lotes com pregão em breve */}
        {(soon === null || soon.length > 0) && (
          <section>
            <SectionHeader
              icon={<Clock size={20} className="text-accent" />}
              title="Encerrando em breve"
              subtitle="Lotes com pregão nos próximos dias — contagem regressiva ativa"
              to="/busca?status=auction_soon&sort=session_asc"
            />
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {soon === null
                ? Array.from({ length: 4 }).map((_, i) => <ItemCardSkeleton key={i} />)
                : soon.map((it) => <ItemCard key={it.id} item={it} />)}
            </div>
          </section>
        )}

        {/* Últimos lotes */}
        <section>
          <SectionHeader
            icon={<Sparkles size={20} className="text-accent" />}
            title="Últimos lotes coletados"
            subtitle="Novidades publicadas pelas fontes monitoradas"
            to="/busca?sort=newest"
          />
          {latest === null ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {Array.from({ length: 8 }).map((_, i) => (
                <ItemCardSkeleton key={i} />
              ))}
            </div>
          ) : latest.length === 0 ? (
            <div className="portal-card">
              <EmptyState
                tone="dark"
                icon={Car}
                title="Ainda não há lotes publicados"
                description="As fontes estão sendo coletadas. Volte em alguns minutos."
              />
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {latest.map((it) => (
                <ItemCard key={it.id} item={it} />
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
