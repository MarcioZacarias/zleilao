import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Package,
  Sparkles,
  Gavel,
  AlertTriangle,
  Copy,
  Percent,
  RefreshCw,
  Users,
  MailCheck,
  Filter,
  BellRing,
  Clock,
  XCircle,
} from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { toast } from "sonner";
import { dashboardApi } from "../../services/operations";
import { usersApi } from "../../services/usersAdmin";
import type { DashboardData, JobType, UsersSummary } from "../../services/types";
import { Card, CardContent, CardHeader } from "../../components/ui/Card";
import { Badge, BadgeVariant } from "../../components/ui/Badge";
import { Table, Thead, Th, Tr, Td } from "../../components/ui/Table";
import { Button } from "../../components/ui/Button";
import { Skeleton, TableSkeleton } from "../../components/ui/Skeleton";
import { EmptyState } from "../../components/ui/EmptyState";
import { formatDateTime, formatDayMonth, formatInt, formatPercent, formatRelative } from "../../lib/format";
import {
  EXTRACTION_LABELS,
  HEALTH_LABELS,
  JOB_STATUS_LABELS,
  JOB_TYPE_LABELS,
  PLAN_LABELS,
  STATUS_LABELS_ADMIN,
} from "../../lib/labels";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { errorMessage } from "../../services/api";

const JOB_ORDER: JobType[] = ["scrape", "normalize", "lifecycle", "dedup", "cleanup"];

function healthVariant(h: string): BadgeVariant {
  return h === "ok" ? "success" : h === "suspended" ? "danger" : "default";
}
function jobVariant(s: string | undefined): BadgeVariant {
  return s === "success" ? "success" : s === "failed" ? "danger" : s === "running" ? "info" : "default";
}

export default function Dashboard() {
  useDocumentTitle("Dashboard");
  const [data, setData] = useState<DashboardData | null>(null);
  const [users, setUsers] = useState<UsersSummary | null>(null);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    dashboardApi
      .get()
      .then(setData)
      .catch((e) => toast.error(errorMessage(e, "Erro ao carregar o dashboard")))
      .finally(() => setLoading(false));
    // Bloco da Onda 2: falha aqui não derruba o resto do painel.
    usersApi
      .summary()
      .then(setUsers)
      .catch(() => setUsers(null));
  };

  useEffect(load, []);

  const kpis = data
    ? [
        { label: "Itens no total", value: formatInt(data.items_total), icon: Package, color: "text-blue-600 bg-blue-50", to: "/admin/itens" },
        { label: "Novos (24 h)", value: formatInt(data.items_new_24h), icon: Sparkles, color: "text-emerald-600 bg-emerald-50", to: "/admin/itens?sort=first_seen_desc" },
        { label: "Pregões em 7 dias", value: formatInt(data.auctions_upcoming_7d), icon: Gavel, color: "text-amber-600 bg-amber-50", to: "/admin/itens?status=auction_soon" },
        { label: "Taxa de extração", value: data.extraction_rate === null ? "—" : formatPercent(data.extraction_rate * (data.extraction_rate <= 1 ? 100 : 1), 0), icon: Percent, color: "text-purple-600 bg-purple-50", to: "/admin/revisao" },
        { label: "Incidentes abertos", value: formatInt(data.open_incidents), icon: AlertTriangle, color: data.open_incidents ? "text-red-600 bg-red-50" : "text-gray-500 bg-gray-100", to: "/admin/incidentes" },
        { label: "Duplicados suspeitos", value: formatInt(data.suspected_duplicates), icon: Copy, color: "text-rose-600 bg-rose-50", to: "/admin/duplicados" },
      ]
    : [];

  const chart = (data?.daily_collected ?? []).map((d) => ({ day: formatDayMonth(d.day), count: d.count }));

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <Button variant="secondary" size="sm" onClick={load} disabled={loading}>
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Atualizar
        </Button>
      </div>

      {/* KPIs */}
      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6 md:gap-4">
        {loading && !data
          ? Array.from({ length: 6 }).map((_, i) => (
              <Card key={i}>
                <CardContent className="py-4">
                  <Skeleton className="mb-2 h-7 w-16" />
                  <Skeleton className="h-3 w-24" />
                </CardContent>
              </Card>
            ))
          : kpis.map((k) => (
              <Link key={k.label} to={k.to} className="block">
                <Card className="h-full transition-shadow hover:shadow-md">
                  <CardContent className="py-4">
                    <div className="flex items-center gap-3">
                      <div className={`rounded-lg p-2 ${k.color}`}>
                        <k.icon size={20} />
                      </div>
                      <div className="min-w-0">
                        <p className="truncate text-2xl font-bold text-gray-900 tabular-nums">{k.value}</p>
                        <p className="text-xs text-gray-500">{k.label}</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            ))}
      </div>

      {/* Status chips */}
      {data && (
        <div className="mb-6 flex flex-wrap gap-2 text-xs">
          {Object.entries(data.items_by_status).map(([s, n]) => (
            <Link key={s} to={`/admin/itens?status=${s}`} className="rounded-full border border-gray-200 bg-white px-3 py-1 text-gray-700 hover:border-primary-300">
              {STATUS_LABELS_ADMIN[s] ?? s}: <strong className="tabular-nums">{formatInt(n)}</strong>
            </Link>
          ))}
          <span className="mx-1 hidden text-gray-300 sm:inline">|</span>
          {Object.entries(data.items_by_extraction).map(([s, n]) => (
            <Link key={s} to={`/admin/itens?extraction_status=${s}`} className="rounded-full border border-dashed border-gray-300 bg-white px-3 py-1 text-gray-600 hover:border-primary-300">
              extração {EXTRACTION_LABELS[s]?.toLowerCase() ?? s}: <strong className="tabular-nums">{formatInt(n)}</strong>
            </Link>
          ))}
        </div>
      )}

      {/* Assinantes e alertas (Onda 2) */}
      <Card className="mb-4 md:mb-6">
        <CardHeader className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-base font-semibold text-gray-900 md:text-lg">Assinantes e alertas</h2>
            <p className="text-xs text-gray-500">Contas, filtros salvos e fila de envio (RN-006/RN-007)</p>
          </div>
          <div className="flex gap-3 text-xs">
            <Link to="/admin/usuarios" className="text-primary-600 hover:underline">
              Usuários
            </Link>
            <Link to="/admin/alertas" className="text-primary-600 hover:underline">
              Alertas
            </Link>
          </div>
        </CardHeader>
        <CardContent>
          {loading && !users ? (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-14 w-full" />
              ))}
            </div>
          ) : !users ? (
            <EmptyState
              compact
              icon={Users}
              title="Resumo de assinantes indisponível"
              description="Não foi possível ler /users/summary agora."
            />
          ) : (
            <>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
                {[
                  { label: "Assinantes", value: users.users_total, icon: Users, color: "text-blue-600 bg-blue-50", to: "/admin/usuarios" },
                  { label: "E-mail verificado", value: users.users_verified, icon: MailCheck, color: "text-emerald-600 bg-emerald-50", to: "/admin/usuarios" },
                  { label: "Filtros ativos", value: users.active_filters, icon: Filter, color: "text-indigo-600 bg-indigo-50", to: "/admin/usuarios" },
                  { label: "Enviados hoje", value: users.alerts_sent_today, icon: BellRing, color: "text-green-600 bg-green-50", to: "/admin/alertas?status=sent" },
                  { label: "Na fila", value: users.alerts_pending, icon: Clock, color: "text-amber-600 bg-amber-50", to: "/admin/alertas?status=pending" },
                  {
                    label: "Falharam",
                    value: users.alerts_failed,
                    icon: XCircle,
                    color: users.alerts_failed ? "text-red-600 bg-red-50" : "text-gray-500 bg-gray-100",
                    to: "/admin/alertas?status=failed",
                  },
                ].map((k) => (
                  <Link key={k.label} to={k.to} className="block">
                    <div className="flex items-center gap-3 rounded-lg border border-gray-200 p-3 transition-colors hover:border-primary-300">
                      <div className={`rounded-lg p-2 ${k.color}`}>
                        <k.icon size={18} />
                      </div>
                      <div className="min-w-0">
                        <p className="text-xl font-bold tabular-nums text-gray-900">{formatInt(k.value)}</p>
                        <p className="truncate text-[11px] text-gray-500">{k.label}</p>
                      </div>
                    </div>
                  </Link>
                ))}
              </div>

              <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
                <span className="text-gray-500">Assinaturas ativas por plano:</span>
                {Object.keys(users.by_plan).length === 0 ? (
                  <span className="text-gray-400">nenhuma registrada</span>
                ) : (
                  Object.entries(users.by_plan).map(([plan, n]) => (
                    <Link
                      key={plan}
                      to={`/admin/usuarios?plan=${plan}`}
                      className="rounded-full border border-gray-200 bg-white px-3 py-1 text-gray-700 hover:border-primary-300"
                    >
                      {PLAN_LABELS[plan] ?? plan}: <strong className="tabular-nums">{formatInt(n)}</strong>
                    </Link>
                  ))
                )}
                {users.users_total > users.users_verified && (
                  <span className="text-amber-600">
                    {formatInt(users.users_total - users.users_verified)} sem e-mail verificado não recebem alerta
                  </span>
                )}
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 md:gap-6 lg:grid-cols-3">
        {/* Gráfico */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <h2 className="text-base font-semibold text-gray-900 md:text-lg">Itens coletados por dia</h2>
            <p className="text-xs text-gray-500">Últimos 14 dias</p>
          </CardHeader>
          <CardContent className="px-2 md:px-6">
            {loading && !data ? (
              <Skeleton className="h-[220px] w-full" />
            ) : chart.length === 0 ? (
              <EmptyState compact title="Sem coletas registradas" description="Os dados aparecem após a primeira execução de coleta." />
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                {/* margin left 0: com margem negativa o eixo Y corta o primeiro
                    digito e 120 aparece como "20" */}
                <BarChart data={chart} margin={{ left: 0, right: 5, top: 5, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                  <XAxis dataKey="day" tick={{ fontSize: 10 }} stroke="#94a3b8" interval={chart.length > 10 ? 1 : 0} />
                  <YAxis stroke="#94a3b8" tick={{ fontSize: 10 }} width={40} allowDecimals={false} />
                  <Tooltip
                    cursor={{ fill: "rgba(37,99,235,0.06)" }}
                    formatter={(v: number) => [formatInt(v), "Itens"]}
                    contentStyle={{ fontSize: 12, borderRadius: 8 }}
                  />
                  <Bar dataKey="count" fill="#2563eb" name="Itens" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* Últimos jobs */}
        <Card>
          <CardHeader className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-gray-900 md:text-lg">Últimos jobs</h2>
            <Link to="/admin/jobs" className="text-xs text-primary-600 hover:underline">Ver todos</Link>
          </CardHeader>
          <CardContent className="p-0">
            {loading && !data ? (
              <TableSkeleton rows={5} cols={3} />
            ) : (
              <ul className="divide-y divide-gray-100">
                {JOB_ORDER.map((jt) => {
                  const j = data?.last_jobs?.[jt] ?? null;
                  return (
                    <li key={jt} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
                      <div className="min-w-0">
                        <div className="font-medium text-gray-900">{JOB_TYPE_LABELS[jt]}</div>
                        <div className="truncate text-xs text-gray-500">
                          {j ? `${formatRelative(j.started_at)} · ${formatInt(j.items_processed)} itens${j.source_name ? ` · ${j.source_name}` : ""}` : "nunca executado"}
                        </div>
                        {j?.error && <div className="truncate text-xs text-red-600" title={j.error}>{j.error}</div>}
                      </div>
                      <Badge variant={jobVariant(j?.status)}>{j ? JOB_STATUS_LABELS[j.status] ?? j.status : "—"}</Badge>
                    </li>
                  );
                })}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Fontes */}
      <Card className="mt-4 md:mt-6">
        <CardHeader className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-gray-900 md:text-lg">Fontes</h2>
            <p className="text-xs text-gray-500">Saúde, volume e CTR para a fonte oficial (7 dias)</p>
          </div>
          <Link to="/admin/fontes" className="text-xs text-primary-600 hover:underline">Gerenciar</Link>
        </CardHeader>
        <CardContent className="p-0">
          {loading && !data ? (
            <TableSkeleton rows={4} cols={7} />
          ) : !data || data.sources.length === 0 ? (
            <EmptyState compact title="Nenhuma fonte cadastrada" action={<Link to="/admin/fontes"><Button size="sm">Cadastrar fonte</Button></Link>} />
          ) : (
            <Table minWidth={860}>
              <Thead>
                <tr>
                  <Th>Fonte</Th>
                  <Th>Saúde</Th>
                  <Th>Última coleta</Th>
                  <Th>Última / média</Th>
                  <Th>Itens</Th>
                  <Th>Publicados</Th>
                  <Th>Aberturas 7d</Th>
                  <Th>Cliques 7d</Th>
                  <Th>CTR 7d</Th>
                </tr>
              </Thead>
              <tbody>
                {data.sources.map((s) => (
                  <Tr key={s.id}>
                    <Td className="font-medium text-gray-900">
                      <div className="flex items-center gap-2">
                        <span className={`h-2 w-2 rounded-full ${s.is_active ? "bg-green-500" : "bg-gray-300"}`} title={s.is_active ? "Ativa" : "Inativa"} />
                        {s.name}
                        {!s.dispatch_enabled && <span className="text-xs text-gray-400" title="Publicação desativada">(sem publicação)</span>}
                      </div>
                    </Td>
                    <Td><Badge variant={healthVariant(s.health_status)}>{HEALTH_LABELS[s.health_status] ?? s.health_status}</Badge></Td>
                    <Td className="text-xs text-gray-500" title={formatDateTime(s.last_run_at)}>
                      {s.last_run_at ? formatRelative(s.last_run_at) : "—"}
                      {s.last_run_status && <span className={`ml-1 ${s.last_run_status === "failed" ? "text-red-600" : ""}`}>({s.last_run_status})</span>}
                    </Td>
                    <Td className="tabular-nums">{formatInt(s.last_items_count)} / {s.avg_items_count === null ? "—" : formatInt(Math.round(s.avg_items_count))}</Td>
                    <Td className="tabular-nums">{formatInt(s.items_total)}</Td>
                    <Td className="tabular-nums">{formatInt(s.items_published)}</Td>
                    <Td className="tabular-nums">{formatInt(s.views_7d)}</Td>
                    <Td className="tabular-nums">{formatInt(s.clicks_7d)}</Td>
                    <Td className="tabular-nums">{s.ctr_7d === null ? "—" : formatPercent(s.ctr_7d * (s.ctr_7d <= 1 ? 100 : 1))}</Td>
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
