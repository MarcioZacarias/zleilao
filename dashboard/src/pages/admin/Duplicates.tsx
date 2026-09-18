import { useEffect, useState } from "react";
import { Copy, Check, X, RefreshCw, ExternalLink, ArrowLeftRight } from "lucide-react";
import { toast } from "sonner";
import { duplicatesApi } from "../../services/operations";
import type { Duplicate, DuplicateStatus, ItemCard as ItemCardType } from "../../services/types";
import { errorMessage } from "../../services/api";
import { Card, CardContent } from "../../components/ui/Card";
import { Badge, BadgeVariant } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { SafeImage } from "../../components/ui/SafeImage";
import { Skeleton } from "../../components/ui/Skeleton";
import { EmptyState } from "../../components/ui/EmptyState";
import { StatusBadge } from "../../components/portal/StatusBadge";
import { formatBRL, formatDateTime, formatKm, formatRelative } from "../../lib/format";
import { DUPLICATE_STATUS_LABELS } from "../../lib/labels";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";

type Filter = DuplicateStatus | "all";

function statusVariant(s: string): BadgeVariant {
  return s === "suspected" ? "warning" : s === "confirmed" ? "success" : "default";
}

function MiniCard({ item, role }: { item: ItemCardType; role: "canonical" | "duplicate" }) {
  return (
    <div className={`flex gap-3 rounded-lg border p-3 ${role === "canonical" ? "border-primary-200 bg-primary-50/40" : "border-gray-200 bg-white"}`}>
      <SafeImage src={item.image_url} alt="" className="h-20 w-28 shrink-0 rounded object-cover" fallbackClassName="h-20 w-28 rounded" iconSize={20} />
      <div className="min-w-0 flex-1 text-sm">
        <div className="mb-1 flex items-center gap-2 text-[11px] uppercase tracking-wider text-gray-500">
          {role === "canonical" ? "Canônico" : "Duplicado"} · #{item.id}
          <StatusBadge status={item.status} tone="admin" />
        </div>
        <div className="line-clamp-2 font-medium text-gray-900" title={item.title}>{item.title}</div>
        <div className="mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs text-gray-600">
          <span>{[item.brand, item.model, item.year_model].filter(Boolean).join(" ") || "—"}</span>
          <span>{item.km !== null ? formatKm(item.km) : "km —"}</span>
          <span>{[item.city, item.state].filter(Boolean).join(" / ") || "local —"}</span>
          <span className="font-semibold text-gray-900 tabular-nums">{item.price ? formatBRL(item.price) : "—"}</span>
          <span className="col-span-2 text-gray-500">
            {item.source_name ?? "fonte —"} · {item.lot_number ? `lote ${item.lot_number} · ` : ""}coleta {formatRelative(item.last_seen_at)}
          </span>
        </div>
        <a href={`/lote/${item.id}`} target="_blank" rel="noopener" className="mt-1 inline-flex items-center gap-1 text-xs text-primary-600 hover:underline">
          Ver no portal <ExternalLink size={11} />
        </a>
      </div>
    </div>
  );
}

export default function Duplicates() {
  useDocumentTitle("Duplicados");
  const [filter, setFilter] = useState<Filter>("suspected");
  const [items, setItems] = useState<Duplicate[] | null>(null);
  const [busy, setBusy] = useState<number | null>(null);

  const load = () => {
    setItems(null);
    duplicatesApi
      .list(filter)
      .then(setItems)
      .catch((e) => toast.error(errorMessage(e, "Erro ao carregar duplicados")));
  };
  useEffect(load, [filter]);

  const decide = async (d: Duplicate, status: "confirmed" | "rejected") => {
    setBusy(d.id);
    try {
      await duplicatesApi.update(d.id, status);
      toast.success(status === "confirmed" ? "Duplicado confirmado" : "Duplicado rejeitado — itens seguem separados");
      setItems((prev) => prev?.filter((x) => filter === "all" ? true : x.id !== d.id).map((x) => (x.id === d.id ? { ...x, status } : x)) ?? prev);
    } catch (e) {
      toast.error(errorMessage(e, "Erro ao atualizar"));
    }
    setBusy(null);
  };

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Duplicados</h1>
          <p className="text-sm text-gray-500">Deduplicação conservadora (RN-004): confirme ou rejeite os pares suspeitos</p>
        </div>
        <Button variant="secondary" size="sm" onClick={load}>
          <RefreshCw size={14} /> Atualizar
        </Button>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        {(["suspected", "confirmed", "rejected", "all"] as Filter[]).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              filter === f ? "bg-primary-600 text-white" : "bg-white text-gray-600 ring-1 ring-gray-200 hover:bg-gray-50"
            }`}
          >
            {f === "all" ? "Todos" : DUPLICATE_STATUS_LABELS[f]}
          </button>
        ))}
      </div>

      {items === null ? (
        <div className="space-y-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <Card key={i}><CardContent><Skeleton className="h-28 w-full" /></CardContent></Card>
          ))}
        </div>
      ) : items.length === 0 ? (
        <Card>
          <EmptyState icon={Copy} title={filter === "suspected" ? "Nenhum duplicado suspeito" : "Nenhum registro"} description={filter === "suspected" ? "O job de deduplicação não encontrou pares acima do limiar." : undefined} />
        </Card>
      ) : (
        <div className="space-y-4">
          {items.map((d) => (
            <Card key={d.id}>
              <CardContent>
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <Badge variant={statusVariant(d.status)}>{DUPLICATE_STATUS_LABELS[d.status] ?? d.status}</Badge>
                    <span className="font-semibold text-gray-900">Similaridade {Math.round(d.similarity * 100)}%</span>
                    <span className="text-xs text-gray-400" title={formatDateTime(d.created_at)}>detectado {formatRelative(d.created_at)}</span>
                  </div>
                  {d.status === "suspected" && (
                    <div className="flex gap-2">
                      <Button variant="secondary" size="sm" onClick={() => decide(d, "rejected")} disabled={busy === d.id}>
                        <X size={13} /> Rejeitar
                      </Button>
                      <Button size="sm" onClick={() => decide(d, "confirmed")} loading={busy === d.id} disabled={busy === d.id}>
                        <Check size={13} /> Confirmar duplicado
                      </Button>
                    </div>
                  )}
                </div>
                <div className="grid items-stretch gap-3 lg:grid-cols-[1fr_auto_1fr]">
                  <MiniCard item={d.canonical} role="canonical" />
                  <div className="hidden items-center justify-center text-gray-300 lg:flex"><ArrowLeftRight size={20} /></div>
                  <MiniCard item={d.duplicate} role="duplicate" />
                </div>
                {d.reasons && Object.keys(d.reasons).length > 0 && (
                  <details className="mt-3">
                    <summary className="cursor-pointer text-xs text-gray-500">Motivos da similaridade</summary>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {Object.entries(d.reasons).map(([k, v]) => (
                        <span key={k} className="rounded-md bg-gray-100 px-2 py-0.5 font-mono text-[11px] text-gray-700">
                          {k}: {typeof v === "object" ? JSON.stringify(v) : String(v)}
                        </span>
                      ))}
                    </div>
                  </details>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
