import { useEffect, useState } from "react";
import { AlertTriangle, Check, CheckCheck, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { incidentsApi } from "../../services/operations";
import { sourcesApi } from "../../services/sources";
import type { Incident, IncidentStatus, Source } from "../../services/types";
import { errorMessage } from "../../services/api";
import { Card, CardContent } from "../../components/ui/Card";
import { Badge, BadgeVariant } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Table, Thead, Th, Tr, Td } from "../../components/ui/Table";
import { TableSkeleton } from "../../components/ui/Skeleton";
import { EmptyState } from "../../components/ui/EmptyState";
import { formatDateTime, formatInt, formatRelative } from "../../lib/format";
import { INCIDENT_KIND_LABELS, INCIDENT_STATUS_LABELS } from "../../lib/labels";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";

type Filter = IncidentStatus | "all";

function statusVariant(s: string): BadgeVariant {
  return s === "open" ? "danger" : s === "acknowledged" ? "warning" : "success";
}
function kindVariant(k: string): BadgeVariant {
  return k === "robots_disallowed" || k === "scraping_not_allowed" ? "purple" : k === "zero_items" ? "danger" : k === "abnormal_variation" ? "warning" : "info";
}

export default function Incidents() {
  useDocumentTitle("Incidentes");
  const [filter, setFilter] = useState<Filter>("open");
  const [sourceId, setSourceId] = useState<number | undefined>(undefined);
  const [items, setItems] = useState<Incident[] | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [reactivate, setReactivate] = useState<Record<number, boolean>>({});
  const [busy, setBusy] = useState<number | null>(null);

  const load = () => {
    setItems(null);
    incidentsApi
      .list(filter, sourceId)
      .then(setItems)
      .catch((e) => toast.error(errorMessage(e, "Erro ao carregar incidentes")));
  };

  useEffect(load, [filter, sourceId]);
  useEffect(() => {
    sourcesApi.list().then(setSources).catch(() => setSources([]));
  }, []);

  const act = async (inc: Incident, status: "acknowledged" | "resolved") => {
    setBusy(inc.id);
    try {
      await incidentsApi.update(inc.id, status, reactivate[inc.id] ?? true);
      toast.success(status === "acknowledged" ? "Incidente reconhecido" : "Incidente resolvido");
      load();
    } catch (e) {
      toast.error(errorMessage(e, "Erro ao atualizar incidente"));
    }
    setBusy(null);
  };

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Incidentes</h1>
          <p className="text-sm text-gray-500">Saúde da coleta (RN-008): zero itens, variação anormal, erros de parser/HTTP e bloqueios</p>
        </div>
        <Button variant="secondary" size="sm" onClick={load}>
          <RefreshCw size={14} /> Atualizar
        </Button>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        {(["open", "acknowledged", "resolved", "all"] as Filter[]).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              filter === f ? "bg-primary-600 text-white" : "bg-white text-gray-600 ring-1 ring-gray-200 hover:bg-gray-50"
            }`}
          >
            {f === "all" ? "Todos" : INCIDENT_STATUS_LABELS[f]}
          </button>
        ))}
        <select value={sourceId ?? ""} onChange={(e) => setSourceId(e.target.value ? Number(e.target.value) : undefined)} className="admin-input ml-auto w-auto">
          <option value="">Todas as fontes</option>
          {sources.map((s) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>
      </div>

      <Card>
        <CardContent className="p-0">
          {items === null ? (
            <TableSkeleton rows={5} cols={6} />
          ) : items.length === 0 ? (
            <EmptyState icon={AlertTriangle} title={filter === "open" ? "Nenhum incidente aberto" : "Nenhum incidente"} description={filter === "open" ? "Todas as fontes estão coletando normalmente." : undefined} />
          ) : (
            <Table minWidth={960}>
              <Thead>
                <tr>
                  <Th>Quando</Th>
                  <Th>Fonte</Th>
                  <Th>Tipo</Th>
                  <Th>Mensagem</Th>
                  <Th>Esperado / observado</Th>
                  <Th>Status</Th>
                  <Th>Ações</Th>
                </tr>
              </Thead>
              <tbody>
                {items.map((inc) => (
                  <Tr key={inc.id}>
                    <Td className="text-xs text-gray-500" title={formatDateTime(inc.created_at)}>
                      {formatRelative(inc.created_at)}
                      {inc.resolved_at && <div className="text-gray-400">resolvido {formatRelative(inc.resolved_at)}{inc.resolved_by ? ` por ${inc.resolved_by}` : ""}</div>}
                    </Td>
                    <Td className="font-medium text-gray-900">{inc.source_name ?? `#${inc.source_id}`}</Td>
                    <Td><Badge variant={kindVariant(inc.kind)}>{INCIDENT_KIND_LABELS[inc.kind] ?? inc.kind}</Badge></Td>
                    <Td className="max-w-md text-xs text-gray-700"><span className="line-clamp-3" title={inc.message}>{inc.message}</span></Td>
                    <Td className="tabular-nums text-xs">
                      {inc.expected === null && inc.observed === null ? "—" : `${inc.expected === null ? "—" : formatInt(Math.round(inc.expected))} / ${inc.observed === null ? "—" : formatInt(Math.round(inc.observed))}`}
                    </Td>
                    <Td><Badge variant={statusVariant(inc.status)}>{INCIDENT_STATUS_LABELS[inc.status] ?? inc.status}</Badge></Td>
                    <Td>
                      {inc.status !== "resolved" && (
                        <div className="flex flex-col gap-1.5">
                          <label className="inline-flex items-center gap-1.5 text-xs text-gray-600">
                            <input
                              type="checkbox"
                              checked={reactivate[inc.id] ?? true}
                              onChange={(e) => setReactivate((r) => ({ ...r, [inc.id]: e.target.checked }))}
                              className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                            />
                            reativar fonte
                          </label>
                          <div className="flex gap-1">
                            {inc.status === "open" && (
                              <Button variant="secondary" size="sm" onClick={() => act(inc, "acknowledged")} disabled={busy === inc.id} title="Reconhecer">
                                <Check size={13} /> Reconhecer
                              </Button>
                            )}
                            <Button size="sm" onClick={() => act(inc, "resolved")} loading={busy === inc.id} disabled={busy === inc.id} title="Resolver">
                              <CheckCheck size={13} /> Resolver
                            </Button>
                          </div>
                        </div>
                      )}
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
