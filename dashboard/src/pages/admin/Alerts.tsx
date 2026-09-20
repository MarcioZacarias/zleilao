import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AlertCircle, BellRing, ExternalLink, RefreshCw, RotateCcw, X } from "lucide-react";
import { toast } from "sonner";
import { alertsApi } from "../../services/usersAdmin";
import { errorMessage } from "../../services/api";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import type { AdminAlert } from "../../services/types";
import { Card, CardContent } from "../../components/ui/Card";
import { Badge, BadgeVariant } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Table, Thead, Th, Tr, Td } from "../../components/ui/Table";
import { TableSkeleton } from "../../components/ui/Skeleton";
import { EmptyState } from "../../components/ui/EmptyState";
import { SafeImage } from "../../components/ui/SafeImage";
import { formatDateTime, formatRelative } from "../../lib/format";
import { ALERT_CHANNEL_LABELS, ALERT_REASON_LABELS, ALERT_STATUS_LABELS } from "../../lib/labels";

const LIMIT = 200;

function statusVariant(s: string): BadgeVariant {
  switch (s) {
    case "sent":
      return "success";
    case "failed":
      return "danger";
    case "pending":
      return "warning";
    default:
      return "default";
  }
}

function reasonVariant(r: string): BadgeVariant {
  switch (r) {
    case "price_drop":
      return "success";
    case "new_session":
      return "info";
    default:
      return "default";
  }
}

export default function Alerts() {
  useDocumentTitle("Alertas");
  const [sp, setSp] = useSearchParams();
  const [alerts, setAlerts] = useState<AdminAlert[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<number | null>(null);

  const status = sp.get("status") ?? "";
  const reason = sp.get("reason") ?? "";
  const userId = sp.get("user_id") ?? "";

  const load = useCallback(() => {
    setLoading(true);
    setError("");
    alertsApi
      .list({
        status: status || undefined,
        user_id: userId ? Number(userId) : undefined,
        limit: LIMIT,
      })
      .then(setAlerts)
      .catch((e) => setError(errorMessage(e, "Erro ao carregar alertas")))
      .finally(() => setLoading(false));
  }, [status, userId]);

  useEffect(load, [load]);

  const update = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(sp);
    for (const [k, v] of Object.entries(patch)) {
      if (!v) next.delete(k);
      else next.set(k, v);
    }
    setSp(next);
  };

  const retry = async (a: AdminAlert) => {
    setBusy(a.id);
    try {
      await alertsApi.retry(a.id);
      setAlerts((list) =>
        list?.map((x) => (x.id === a.id ? { ...x, status: "pending", error: null } : x)) ?? null
      );
      toast.success("Alerta reenfileirado. O job de envio cuida do resto.");
    } catch (e) {
      toast.error(errorMessage(e, "Não foi possível reenfileirar"));
    }
    setBusy(null);
  };

  // O motivo não é filtro do backend: peneiramos aqui, sobre a lista carregada.
  const visible = (alerts ?? []).filter((a) => !reason || a.reason === reason);
  const userLabel = alerts?.find((a) => String(a.user?.id) === userId)?.user;

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Alertas</h1>
          <p className="text-sm text-gray-500">
            Fila e histórico de envio (RN-006/RN-007). Os jobs <strong>match</strong> e <strong>dispatch</strong>{" "}
            alimentam esta tela.
          </p>
        </div>
        <div className="flex gap-2">
          <Link to="/admin/jobs">
            <Button variant="secondary" size="sm">
              Ver jobs <ExternalLink size={13} />
            </Button>
          </Link>
          <Button variant="secondary" size="sm" onClick={load} disabled={loading}>
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Atualizar
          </Button>
        </div>
      </div>

      <Card className="mb-4">
        <CardContent className="py-3">
          <div className="grid gap-3 md:grid-cols-3">
            <select
              value={status}
              onChange={(e) => update({ status: e.target.value || null })}
              className="admin-input"
              aria-label="Status"
            >
              <option value="">Todos os status</option>
              {Object.entries(ALERT_STATUS_LABELS).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
            <select
              value={reason}
              onChange={(e) => update({ reason: e.target.value || null })}
              className="admin-input"
              aria-label="Motivo"
            >
              <option value="">Todos os motivos</option>
              {Object.entries(ALERT_REASON_LABELS).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
            <div className="flex items-center gap-2">
              <input
                value={userId}
                onChange={(e) => update({ user_id: e.target.value.replace(/\D/g, "") || null })}
                placeholder="ID do usuário"
                inputMode="numeric"
                className="admin-input"
                aria-label="Filtrar por usuário"
              />
              {userId && (
                <button
                  type="button"
                  onClick={() => update({ user_id: null })}
                  className="shrink-0 rounded-lg p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                  aria-label="Limpar filtro de usuário"
                >
                  <X size={16} />
                </button>
              )}
            </div>
          </div>
          {userId && userLabel && (
            <p className="mt-2 text-xs text-gray-500">
              Mostrando alertas de <strong className="text-gray-700">{userLabel.name || userLabel.email}</strong>.
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          {error ? (
            <EmptyState
              icon={BellRing}
              title="Não foi possível carregar"
              description={error}
              action={
                <Button size="sm" onClick={load}>
                  Tentar novamente
                </Button>
              }
            />
          ) : loading && !alerts ? (
            <TableSkeleton rows={8} cols={6} />
          ) : visible.length === 0 ? (
            <EmptyState
              icon={BellRing}
              title="Nenhum alerta"
              description={
                status || reason || userId
                  ? "Nenhum alerta corresponde aos filtros aplicados."
                  : "Nada foi gerado ainda. Rode o job de casamento de filtros para popular a fila."
              }
            />
          ) : (
            <Table minWidth={1040}>
              <Thead>
                <tr>
                  <Th>Criado</Th>
                  <Th>Usuário</Th>
                  <Th>Lote</Th>
                  <Th>Motivo</Th>
                  <Th>Status</Th>
                  <Th>Canal</Th>
                  <Th>Detalhe / erro</Th>
                  <Th className="text-right">Ações</Th>
                </tr>
              </Thead>
              <tbody className={loading ? "opacity-60" : ""}>
                {visible.map((a) => (
                  <Tr key={a.id}>
                    <Td className="whitespace-nowrap text-xs text-gray-600" title={formatRelative(a.created_at)}>
                      {formatDateTime(a.created_at)}
                    </Td>
                    <Td>
                      {a.user ? (
                        <button
                          type="button"
                          onClick={() => update({ user_id: String(a.user!.id) })}
                          className="block max-w-[190px] text-left"
                          title={`Filtrar pelos alertas de ${a.user.email}`}
                        >
                          <div className="truncate font-medium text-gray-900">{a.user.name || "—"}</div>
                          <div className="truncate text-xs text-gray-500">{a.user.email}</div>
                        </button>
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                    </Td>
                    <Td>
                      {a.item ? (
                        <Link
                          to={`/lote/${a.item.id}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex max-w-[240px] items-center gap-2"
                        >
                          <SafeImage
                            src={a.item.image_url}
                            alt=""
                            className="h-9 w-12 shrink-0 rounded object-cover"
                            fallbackClassName="h-9 w-12 rounded"
                            iconSize={14}
                          />
                          <div className="min-w-0">
                            <div className="line-clamp-1 text-sm text-gray-900" title={a.item.title}>
                              {a.item.title}
                            </div>
                            <div className="text-xs text-gray-400">{a.item.source_name ?? `#${a.item.source_id}`}</div>
                          </div>
                        </Link>
                      ) : (
                        <span className="text-gray-400">lote removido</span>
                      )}
                    </Td>
                    <Td>
                      <Badge variant={reasonVariant(a.reason)}>{ALERT_REASON_LABELS[a.reason] ?? a.reason}</Badge>
                    </Td>
                    <Td>
                      <Badge variant={statusVariant(a.status)}>{ALERT_STATUS_LABELS[a.status] ?? a.status}</Badge>
                      {a.sent_at && (
                        <div className="mt-0.5 text-[11px] text-gray-400" title={formatDateTime(a.sent_at)}>
                          {formatRelative(a.sent_at)}
                        </div>
                      )}
                    </Td>
                    <Td className="text-xs">
                      {a.channel ? ALERT_CHANNEL_LABELS[a.channel] ?? a.channel : <span className="text-gray-400">—</span>}
                    </Td>
                    <Td className="max-w-[240px]">
                      {a.error ? (
                        <div className="flex items-start gap-1 text-xs text-red-700" title={a.error}>
                          <AlertCircle size={12} className="mt-0.5 shrink-0" />
                          <span className="line-clamp-2">{a.error}</span>
                        </div>
                      ) : a.detail ? (
                        <span className="line-clamp-2 text-xs text-gray-600" title={a.detail}>
                          {a.detail}
                        </span>
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                    </Td>
                    <Td>
                      <div className="flex justify-end">
                        {a.status === "sent" ? (
                          <span className="text-xs text-gray-400">enviado</span>
                        ) : (
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => retry(a)}
                            loading={busy === a.id}
                            disabled={busy === a.id}
                          >
                            <RotateCcw size={13} /> Tentar de novo
                          </Button>
                        )}
                      </div>
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          )}
        </CardContent>
      </Card>

      {alerts && alerts.length >= LIMIT && (
        <p className="mt-3 text-center text-xs text-gray-400">
          Mostrando os {LIMIT} alertas mais recentes. Use os filtros para chegar aos mais antigos.
        </p>
      )}
    </div>
  );
}
