import { useEffect, useState } from "react";
import { Play, RefreshCw, Timer, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { jobsApi } from "../../services/operations";
import type { JobExecution, JobRunType, SchedulerJob } from "../../services/types";
import { errorMessage } from "../../services/api";
import { Card, CardContent, CardHeader } from "../../components/ui/Card";
import { Badge, BadgeVariant } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Table, Thead, Th, Tr, Td } from "../../components/ui/Table";
import { Skeleton, TableSkeleton } from "../../components/ui/Skeleton";
import { EmptyState } from "../../components/ui/EmptyState";
import { formatDateTime, formatDuration, formatInt, formatRelative, toEpoch } from "../../lib/format";
import { JOB_STATUS_LABELS, JOB_TYPE_LABELS } from "../../lib/labels";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";

const RUN_TYPES: { run: JobRunType; list: string; label: string; description: string }[] = [
  { run: "scrape_tick", list: "scrape", label: "Coleta", description: "Verifica as fontes vencidas e dispara os scrapers" },
  { run: "normalize", list: "normalize", label: "Normalização", description: "Extrai campos estruturados (LLM / regras)" },
  { run: "lifecycle", list: "lifecycle", label: "Ciclo de vida", description: "Pregão em breve, encerrados, possivelmente retirados (RN-005)" },
  { run: "dedup", list: "dedup", label: "Deduplicação", description: "Procura pares semelhantes entre fontes (RN-004)" },
  { run: "cleanup", list: "cleanup", label: "Limpeza", description: "Aplica as retenções de payload bruto e itens encerrados" },
];

function statusVariant(s: string): BadgeVariant {
  return s === "success" ? "success" : s === "failed" ? "danger" : s === "running" ? "info" : "default";
}

function duration(j: JobExecution): string {
  const a = toEpoch(j.started_at);
  const b = j.finished_at ? toEpoch(j.finished_at) : null;
  if (a === null || b === null) return j.status === "running" ? "em execução" : "—";
  return formatDuration(Math.max(0, b - a));
}

export default function Jobs() {
  useDocumentTitle("Jobs");
  const [scheduler, setScheduler] = useState<SchedulerJob[] | null>(null);
  const [jobs, setJobs] = useState<JobExecution[] | null>(null);
  const [typeFilter, setTypeFilter] = useState<string>("");
  const [running, setRunning] = useState<JobRunType | null>(null);

  const loadScheduler = () =>
    jobsApi
      .scheduler()
      .then((r) => setScheduler(r.jobs))
      .catch(() => setScheduler([]));

  const loadJobs = () => {
    setJobs(null);
    jobsApi
      .list(typeFilter || undefined, 100)
      .then(setJobs)
      .catch((e) => toast.error(errorMessage(e, "Erro ao carregar execuções")));
  };

  useEffect(() => {
    loadScheduler();
    const id = window.setInterval(loadScheduler, 15000);
    return () => window.clearInterval(id);
  }, []);
  useEffect(loadJobs, [typeFilter]);

  const run = async (t: JobRunType) => {
    setRunning(t);
    try {
      await jobsApi.run(t);
      toast.success(`${JOB_TYPE_LABELS[t]} disparado`);
      window.setTimeout(() => {
        loadScheduler();
        loadJobs();
      }, 2500);
    } catch (e) {
      toast.error(errorMessage(e, "Erro ao disparar job"));
    }
    setRunning(null);
  };

  const schedById = Object.fromEntries((scheduler ?? []).map((s) => [s.id, s]));

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Jobs</h1>
          <p className="text-sm text-gray-500">Agendador (APScheduler) e histórico de execuções</p>
        </div>
        <Button variant="secondary" size="sm" onClick={() => { loadScheduler(); loadJobs(); }}>
          <RefreshCw size={14} /> Atualizar
        </Button>
      </div>

      {/* Scheduler */}
      <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {RUN_TYPES.map((t) => {
          const s = schedById[t.run] ?? schedById[t.list] ?? Object.values(schedById).find((x) => x.id.includes(t.list));
          return (
            <Card key={t.run}>
              <CardContent className="py-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 font-semibold text-gray-900">
                      <Timer size={15} className="text-gray-400" /> {t.label}
                    </div>
                    <p className="mt-0.5 text-[11px] leading-snug text-gray-500">{t.description}</p>
                  </div>
                  {s?.running && <Badge variant="info"><Loader2 size={10} className="animate-spin" /> rodando</Badge>}
                </div>
                <div className="mt-3 text-xs text-gray-500">
                  {scheduler === null ? (
                    <Skeleton className="h-3 w-24" />
                  ) : s ? (
                    <>Próxima: <span className="text-gray-800" title={formatDateTime(s.next_run_at)}>{s.next_run_at ? formatRelative(s.next_run_at) : "pausado"}</span></>
                  ) : (
                    <span className="text-gray-400">não agendado</span>
                  )}
                </div>
                <Button size="sm" variant="secondary" className="mt-3 w-full" onClick={() => run(t.run)} loading={running === t.run} disabled={!!running || !!s?.running}>
                  <Play size={13} /> Rodar agora
                </Button>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Execuções */}
      <Card>
        <CardHeader className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-semibold text-gray-900">Execuções recentes</h2>
          <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} className="admin-input w-auto">
            <option value="">Todos os tipos</option>
            {RUN_TYPES.map((t) => (
              <option key={t.list} value={t.list}>{t.label}</option>
            ))}
          </select>
        </CardHeader>
        <CardContent className="p-0">
          {jobs === null ? (
            <TableSkeleton rows={8} cols={6} />
          ) : jobs.length === 0 ? (
            <EmptyState icon={Timer} title="Nenhuma execução registrada" />
          ) : (
            <Table minWidth={860}>
              <Thead>
                <tr>
                  <Th>Início</Th>
                  <Th>Job</Th>
                  <Th>Fonte</Th>
                  <Th>Status</Th>
                  <Th>Itens</Th>
                  <Th>Duração</Th>
                  <Th>Detalhes</Th>
                </tr>
              </Thead>
              <tbody>
                {jobs.map((j) => (
                  <Tr key={j.id}>
                    <Td className="text-xs text-gray-600 whitespace-nowrap" title={formatRelative(j.started_at)}>{formatDateTime(j.started_at)}</Td>
                    <Td className="font-medium text-gray-900">{JOB_TYPE_LABELS[j.job_type] ?? j.job_type}</Td>
                    <Td className="text-xs">{j.source_name ?? (j.source_id ? `#${j.source_id}` : <span className="text-gray-400">—</span>)}</Td>
                    <Td><Badge variant={statusVariant(j.status)}>{JOB_STATUS_LABELS[j.status] ?? j.status}</Badge></Td>
                    <Td className="tabular-nums">{formatInt(j.items_processed)}</Td>
                    <Td className="text-xs text-gray-600">{duration(j)}</Td>
                    <Td className="max-w-md text-xs">
                      {j.error && <div className="line-clamp-2 text-red-700" title={j.error}>{j.error}</div>}
                      {j.details && Object.keys(j.details).length > 0 && (
                        <details>
                          <summary className="cursor-pointer text-gray-500">detalhes</summary>
                          <pre className="mt-1 max-h-40 overflow-auto rounded bg-gray-50 p-2 text-[11px] text-gray-700">{JSON.stringify(j.details, null, 2)}</pre>
                        </details>
                      )}
                      {!j.error && (!j.details || Object.keys(j.details).length === 0) && <span className="text-gray-400">—</span>}
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
