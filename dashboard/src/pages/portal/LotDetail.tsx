import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ExternalLink,
  MapPin,
  Copy,
  Gavel,
  CalendarClock,
  Radio,
  Clock,
  ChevronRight,
  AlertTriangle,
  Info,
  History,
  ShieldAlert,
} from "lucide-react";
import { portalApi } from "../../services/portal";
import type { ItemDetail } from "../../services/types";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { formatBRL, formatDateTime, formatKm, formatRelative } from "../../lib/format";
import {
  AUCTION_TYPE_LABELS,
  MODALITY_LABELS,
  PRICE_KIND_LABELS,
  SESSION_KIND_LABELS,
  DUPLICATE_STATUS_LABELS,
  isAlertCondition,
  CONDITION_LABELS,
} from "../../lib/labels";
import { formatAttribute, NOT_INFORMED } from "../../lib/attributes";
import { ParcelamentoAviso } from "../../components/portal/ParcelamentoJudicial";
import { Gallery } from "../../components/portal/Gallery";
import { PriceTag } from "../../components/portal/PriceTag";
import { StatusBadge } from "../../components/portal/StatusBadge";
import { ConditionBadge } from "../../components/portal/ConditionBadge";
import { Countdown } from "../../components/portal/Countdown";
import { OpportunityPanel } from "../../components/portal/OpportunityPanel";
import { Anuncio } from "../../components/portal/Anuncio";
import { Skeleton, SkeletonText } from "../../components/ui/Skeleton";
import { EmptyState } from "../../components/ui/EmptyState";
import { Button } from "../../components/ui/Button";
import { errorMessage } from "../../services/api";
import axios from "axios";

function Block({ title, icon, children, className = "" }: { title: string; icon?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <section className={`portal-card p-4 md:p-5 ${className}`}>
      <h2 className="mb-3 flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-radar-muted">
        {icon}
        {title}
      </h2>
      {children}
    </section>
  );
}

function Row({ label, value, muted }: { label: string; value: React.ReactNode; muted?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-radar-border py-2 last:border-b-0">
      <dt className="shrink-0 text-sm text-radar-muted">{label}</dt>
      <dd className={`text-right text-sm ${muted ? "italic text-radar-muted/70" : "text-radar-text"}`}>{value}</dd>
    </div>
  );
}

function DetailSkeleton() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
      <Skeleton tone="dark" className="mb-4 h-3 w-64" />
      <div className="grid gap-6 lg:grid-cols-12">
        <div className="lg:col-span-7">
          <Skeleton tone="dark" className="aspect-[4/3] w-full" rounded="rounded-xl" />
        </div>
        <div className="space-y-4 lg:col-span-5">
          <Skeleton tone="dark" className="h-5 w-32" />
          <Skeleton tone="dark" className="h-8 w-full" />
          <Skeleton tone="dark" className="h-8 w-2/3" />
          <Skeleton tone="dark" className="h-16 w-1/2" />
          <Skeleton tone="dark" className="h-12 w-full" rounded="rounded-xl" />
          <SkeletonText tone="dark" lines={4} />
        </div>
      </div>
    </div>
  );
}

export default function LotDetail() {
  const { id } = useParams<{ id: string }>();
  const [item, setItem] = useState<ItemDetail | null>(null);
  const [error, setError] = useState<{ status?: number; message: string } | null>(null);
  const [loading, setLoading] = useState(true);
  useDocumentTitle(item?.title ?? "Lote");

  useEffect(() => {
    if (!id) return;
    let alive = true;
    setLoading(true);
    setError(null);
    setItem(null);
    portalApi
      .item(id)
      .then((d) => alive && setItem(d))
      .catch((e) => {
        if (!alive) return;
        setError({ status: axios.isAxiosError(e) ? e.response?.status : undefined, message: errorMessage(e) });
      })
      .finally(() => alive && setLoading(false));
    window.scrollTo({ top: 0 });
    return () => {
      alive = false;
    };
  }, [id]);

  if (loading) return <DetailSkeleton />;

  if (error || !item) {
    const notFound = error?.status === 404;
    return (
      <div className="mx-auto max-w-3xl px-4 py-16 sm:px-6">
        <div className="portal-card">
          <EmptyState
            tone="dark"
            icon={notFound ? Gavel : AlertTriangle}
            title={notFound ? "Lote fora da vitrine" : "Não foi possível carregar o lote"}
            description={
              notFound
                ? "Este lote foi retirado, encerrado há muito tempo ou ainda não foi publicado."
                : error?.message
            }
            action={
              <Link to="/busca">
                <Button variant="accent" size="sm">Buscar outros lotes</Button>
              </Link>
            }
          />
        </div>
      </div>
    );
  }

  const closed = item.status === "closed";
  const soon = item.status === "auction_soon";
  const withdrawn = item.status === "withdrawn" || item.status === "possibly_withdrawn";
  const goUrl = portalApi.goUrl(item.id);
  const sub = [item.brand, item.model, item.year_model ? String(item.year_model) : null].filter(Boolean).join(" · ");
  const location = item.location_text ?? [item.city, item.state].filter(Boolean).join(" / ");
  const auction = item.auction;

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
      {/* Breadcrumb */}
      <nav className="mb-4 flex flex-wrap items-center gap-1 text-xs text-radar-muted" aria-label="Navegação">
        <Link to="/" className="hover:text-radar-text">Início</Link>
        <ChevronRight size={12} />
        <Link to="/busca" className="hover:text-radar-text">Lotes</Link>
        {item.category_slug && (
          <>
            <ChevronRight size={12} />
            <Link to={`/busca?category=${encodeURIComponent(item.category_slug)}`} className="hover:text-radar-text">
              {item.category_name ?? item.category_slug}
            </Link>
          </>
        )}
        <ChevronRight size={12} />
        <span className="truncate text-radar-text/80">{item.lot_number ? `Lote ${item.lot_number}` : item.title}</span>
      </nav>

      <div className="grid gap-6 lg:grid-cols-12">
        {/* Galeria */}
        <div className="space-y-4 lg:col-span-7">
          <Gallery images={item.images?.length ? item.images : item.image_url ? [item.image_url] : []} alt={item.title} />
          {/* RN-010: só aparece quando há referência confiável. Sem ela, nada —
              melhor silêncio que um score de amostra fraca.
              Fica sob a galeria, e não na coluna fixa: a memória de cálculo
              precisa de largura, e a coluna da direita já é a mais alta. */}
          {item.opportunity && <OpportunityPanel opportunity={item.opportunity} />}
          <Anuncio posicao="ficha" />
        </div>

        {/* Painel principal */}
        <div className="lg:col-span-5">
          <div className="lg:sticky lg:top-20 space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge status={item.status} size="md" />
              <ConditionBadge condition={item.condition} size="md" />
              {item.possible_duplicate && (
                <span className="inline-flex items-center gap-1 rounded-full bg-white/5 px-3 py-1 text-xs font-medium text-radar-muted ring-1 ring-inset ring-white/10" title="RN-004: similaridade abaixo do limiar de fusão; publicações mantidas separadas">
                  <Copy size={12} /> possível duplicado
                </span>
              )}
              {item.lot_number && <span className="text-xs text-radar-muted">Lote {item.lot_number}</span>}
            </div>

            <div>
              <h1 className="text-xl font-bold leading-snug text-radar-text md:text-2xl">{item.title}</h1>
              {sub && <p className="mt-1 text-sm text-radar-muted">{sub}</p>}
              <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-radar-muted">
                {location && (
                  <span className="inline-flex items-center gap-1"><MapPin size={14} /> {location}</span>
                )}
                {item.km !== null && <span>{formatKm(item.km)}</span>}
              </div>
            </div>

            {/* Preço */}
            <div className="portal-card p-4">
              <PriceTag price={item.price} priceKind={item.price_kind} priceSecond={item.price_second} size="lg" closed={closed} />
              {isAlertCondition(item.condition) && (
                <p className="mt-3 flex items-start gap-2 rounded-lg bg-orange-500/10 p-2 text-xs text-orange-200 ring-1 ring-inset ring-orange-400/20">
                  <ShieldAlert size={14} className="mt-0.5 shrink-0" />
                  Condição informada pela fonte: <strong>{CONDITION_LABELS[item.condition!] ?? item.condition}</strong>. Verifique o edital antes de dar lance.
                </p>
              )}
            </div>

            {/* Judicial: parcelamento pelo CPC, art. 895 */}
            {(auction?.auction_type ?? item.auction_type) === "judicial" && !closed && <ParcelamentoAviso />}

            {/* Pregão em breve / contagem regressiva (RN-005) */}
            {soon && item.next_session_at && (
              <div className="rounded-xl border border-accent/30 bg-accent/10 p-4">
                <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-accent-300">
                  <Clock size={16} /> Pregão em breve
                </div>
                <Countdown target={item.next_session_at} size="md" />
                <p className="mt-2 text-xs text-radar-muted">Sessão em {formatDateTime(item.next_session_at)}</p>
              </div>
            )}
            {!soon && !closed && !withdrawn && item.next_session_at && (
              <p className="inline-flex items-center gap-2 text-sm text-radar-muted">
                <CalendarClock size={15} /> Próxima sessão: <span className="text-radar-text">{formatDateTime(item.next_session_at)}</span>
              </p>
            )}
            {closed && (
              <p className="rounded-xl bg-white/5 p-3 text-sm text-radar-muted ring-1 ring-inset ring-white/10">
                Este lote está <strong className="text-radar-text">encerrado</strong>. A ficha permanece disponível para consulta.
              </p>
            )}

            {/* CTA (RN-001) */}
            {closed || withdrawn ? (
              <a
                href={goUrl}
                target="_blank"
                rel="noopener"
                className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-white/15 px-4 py-3 text-sm font-medium text-radar-muted transition-colors hover:border-white/30 hover:text-radar-text"
              >
                Ver na fonte oficial <ExternalLink size={15} />
              </a>
            ) : (
              <a
                href={goUrl}
                target="_blank"
                rel="noopener"
                className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-accent px-4 py-3.5 text-base font-bold text-[#0b1020] shadow-lift transition-colors hover:bg-accent-400 focus:outline-none focus:ring-2 focus:ring-accent/50"
              >
                Ver no leilão oficial <ExternalLink size={17} />
              </a>
            )}
            <p className="text-center text-[11px] text-radar-muted/80">
              Os lances são feitos exclusivamente no site do leiloeiro. Não intermediamos nem cobramos comissão.
            </p>

            {/* Atribuição à fonte (RN-001) */}
            <div className="portal-card divide-y divide-radar-border text-sm">
              <div className="flex items-center justify-between gap-3 px-4 py-2.5">
                <span className="inline-flex items-center gap-2 text-radar-muted"><Radio size={14} /> Fonte</span>
                <span className="text-right font-medium text-radar-text">{item.source_name ?? "não informada"}</span>
              </div>
              <div className="flex items-center justify-between gap-3 px-4 py-2.5">
                <span className="text-radar-muted">Última coleta</span>
                <span className="text-right text-radar-text" title={formatRelative(item.last_seen_at)}>
                  {formatDateTime(item.last_seen_at)}
                </span>
              </div>
              <div className="flex items-center justify-between gap-3 px-4 py-2.5">
                <span className="text-radar-muted">Primeira coleta</span>
                <span className="text-right text-radar-text">{formatDateTime(item.first_seen_at)}</span>
              </div>
              {auction && (
                <div className="flex items-center justify-between gap-3 px-4 py-2.5">
                  <span className="text-radar-muted">Pregão</span>
                  <Link to={`/pregao/${auction.id}`} className="inline-flex items-center gap-1 text-accent hover:underline">
                    {auction.title ?? auction.auctioneer_name ?? `#${auction.external_id}`} <ChevronRight size={14} />
                  </Link>
                </div>
              )}
            </div>
          </div>

        </div>
      </div>

      {/* Conteúdo inferior */}
      <div className="mt-8 grid gap-6 lg:grid-cols-12">
        <div className="space-y-6 lg:col-span-7">
          {/* Ficha normalizada (RN-002) */}
          <Block title="Ficha do lote" icon={<Info size={14} />}>
            {item.field_defs.length === 0 ? (
              <p className="text-sm italic text-radar-muted">Categoria sem campos definidos.</p>
            ) : (
              <dl className="grid gap-x-8 md:grid-cols-2">
                {item.field_defs.map((f) => {
                  const text = formatAttribute(f, item.attributes?.[f.key]);
                  return <Row key={f.id ?? f.key} label={f.label} value={text} muted={text === NOT_INFORMED} />;
                })}
              </dl>
            )}
            <p className="mt-3 text-[11px] text-radar-muted/70">
              Campos não presentes na fonte aparecem como “não informado” — nunca inferidos.
            </p>
          </Block>

          {/* Descrição */}
          <Block title="Descrição da fonte">
            {item.description ? (
              <p className="whitespace-pre-line text-sm leading-relaxed text-radar-text/90">{item.description}</p>
            ) : (
              <p className="text-sm italic text-radar-muted">Descrição não informada.</p>
            )}
          </Block>

          {/* Duplicados (RN-004) */}
          {item.duplicates.length > 0 && (
            <Block title="Possíveis duplicados" icon={<Copy size={14} />}>
              <p className="mb-3 text-xs text-radar-muted">
                Publicações semelhantes em outras fontes. Mantidas separadas por precaução.
              </p>
              <ul className="divide-y divide-radar-border">
                {item.duplicates.map((d) => (
                  <li key={d.item_id} className="flex items-center justify-between gap-3 py-2 text-sm">
                    <div className="min-w-0">
                      <Link to={`/lote/${d.item_id}`} className="block truncate font-medium text-radar-text hover:text-accent">
                        {d.title}
                      </Link>
                      <div className="text-xs text-radar-muted">
                        {d.source_name ?? "fonte não informada"} · similaridade {Math.round(d.similarity * 100)}% ·{" "}
                        {DUPLICATE_STATUS_LABELS[d.status] ?? d.status}
                      </div>
                    </div>
                    <a
                      href={d.official_url}
                      target="_blank"
                      rel="noopener"
                      className="shrink-0 text-radar-muted hover:text-accent"
                      title="Abrir na fonte"
                    >
                      <ExternalLink size={15} />
                    </a>
                  </li>
                ))}
              </ul>
            </Block>
          )}
        </div>

        <div className="space-y-6 lg:col-span-5">
          {/* Pregão */}
          <Block title="Pregão" icon={<Gavel size={14} />}>
            {auction ? (
              <>
                <dl>
                  <Row label="Leiloeiro" value={auction.auctioneer_name ?? NOT_INFORMED} muted={!auction.auctioneer_name} />
                  <Row label="Registro" value={auction.auctioneer_registration ?? NOT_INFORMED} muted={!auction.auctioneer_registration} />
                  <Row label="Comitente / Vara" value={auction.committer_name ?? NOT_INFORMED} muted={!auction.committer_name} />
                  <Row label="Modalidade" value={auction.modality ? MODALITY_LABELS[auction.modality] ?? auction.modality : NOT_INFORMED} muted={!auction.modality} />
                  <Row label="Tipo" value={auction.auction_type ? AUCTION_TYPE_LABELS[auction.auction_type] ?? auction.auction_type : NOT_INFORMED} muted={!auction.auction_type} />
                </dl>
                {auction.sessions.length > 0 && (
                  <div className="mt-3 overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-[11px] uppercase tracking-wider text-radar-muted">
                          <th className="py-1.5 pr-2 font-medium">Sessão</th>
                          <th className="py-1.5 pr-2 font-medium">Início</th>
                          <th className="py-1.5 text-right font-medium">Lance mín.</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-radar-border">
                        {[...auction.sessions]
                          .sort((a, b) => a.sequence - b.sequence)
                          .map((s) => (
                            <tr key={s.id}>
                              <td className="py-2 pr-2 font-medium text-radar-text">{SESSION_KIND_LABELS[s.kind] ?? s.kind}</td>
                              <td className="py-2 pr-2 text-radar-text/90">{formatDateTime(s.starts_at)}</td>
                              <td className="py-2 text-right tabular-nums text-radar-text/90">{s.min_bid ? formatBRL(s.min_bid) : "—"}</td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <Link to={`/pregao/${auction.id}`} className="mt-3 inline-flex items-center gap-1 text-sm text-accent hover:underline">
                  Ver todos os {auction.items_count} lotes deste pregão <ChevronRight size={14} />
                </Link>
              </>
            ) : (
              <p className="text-sm italic text-radar-muted">Pregão não informado pela fonte.</p>
            )}
          </Block>

          {/* Histórico de preço */}
          {item.price_history.length > 1 && (
            <Block title="Histórico de valores" icon={<History size={14} />}>
              <ul className="divide-y divide-radar-border text-sm">
                {[...item.price_history]
                  .sort((a, b) => (a.observed_at < b.observed_at ? 1 : -1))
                  .slice(0, 8)
                  .map((h, i) => (
                    <li key={`${h.observed_at}-${i}`} className="flex items-center justify-between py-1.5">
                      <span className="text-radar-muted">{formatDateTime(h.observed_at)}</span>
                      <span className="tabular-nums text-radar-text">
                        {formatBRL(h.price)}
                        {h.price_kind && <span className="ml-1 text-xs text-radar-muted">({PRICE_KIND_LABELS[h.price_kind] ?? h.price_kind})</span>}
                      </span>
                    </li>
                  ))}
              </ul>
            </Block>
          )}
        </div>
      </div>

      {/* Disclaimer */}
      {item.disclaimer && (
        <p className="mt-8 rounded-xl border border-radar-border bg-radar-surface/60 p-4 text-xs leading-relaxed text-radar-muted">
          {item.disclaimer}
        </p>
      )}
    </div>
  );
}
