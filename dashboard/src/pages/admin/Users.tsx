import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  CreditCard,
  Filter as FilterIcon,
  MailCheck,
  RefreshCw,
  Search,
  ShieldCheck,
  ShieldOff,
  Users as UsersIcon,
} from "lucide-react";
import { toast } from "sonner";
import { usersApi } from "../../services/usersAdmin";
import { errorMessage } from "../../services/api";
import { useAuth } from "../../context/AuthContext";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import type { AdminSavedFilter, Plan, UserAdmin, UsersPage } from "../../services/types";
import { Card, CardContent } from "../../components/ui/Card";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Table, Thead, Th, Tr, Td } from "../../components/ui/Table";
import { Toggle } from "../../components/ui/Toggle";
import { Modal } from "../../components/ui/Modal";
import { Drawer } from "../../components/ui/Drawer";
import { Pagination } from "../../components/ui/Pagination";
import { TableSkeleton } from "../../components/ui/Skeleton";
import { EmptyState } from "../../components/ui/EmptyState";
import { formatDate, formatDateTime, formatRelative, maskPhone } from "../../lib/format";
import { PLAN_LABELS, PLAN_STATUS_LABELS, ROLE_LABELS } from "../../lib/labels";
import { describeCriteria } from "../../lib/criteria";

const PAGE_SIZE = 50;

/* ───────── Modal de plano ───────── */

function PlanModal({
  user,
  onClose,
  onSaved,
}: {
  user: UserAdmin | null;
  onClose: () => void;
  onSaved: (u: UserAdmin) => void;
}) {
  const [plan, setPlan] = useState<Plan>("pro");
  const [months, setMonths] = useState(1);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!user) return;
    // Começa no plano atual: salvar sem mexer renova o período, não muda o plano.
    setPlan(user.plan);
    setMonths(1);
    setNote(user.plan_note ?? "");
  }, [user]);

  const save = async () => {
    if (!user) return;
    setSaving(true);
    try {
      const updated = await usersApi.setPlan(user.id, { plan, months, note: note.trim() || null });
      onSaved(updated);
      toast.success(`Plano de ${updated.email} definido como ${PLAN_LABELS[updated.plan] ?? updated.plan}`);
      onClose();
    } catch (e) {
      toast.error(errorMessage(e, "Não foi possível alterar o plano"));
    }
    setSaving(false);
  };

  return (
    <Modal
      open={!!user}
      onClose={onClose}
      title={user ? `Plano de ${user.name || user.email}` : ""}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button onClick={save} loading={saving}>
            Salvar plano
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <div className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
          A ativação é <strong>manual</strong>: não há gateway de pagamento. O acesso vale a partir de agora.
        </div>

        <div>
          <label className="admin-label" htmlFor="plan">
            Plano
          </label>
          <select id="plan" value={plan} onChange={(e) => setPlan(e.target.value as Plan)} className="admin-input">
            <option value="free">Gratuito</option>
            <option value="pro">Pago</option>
          </select>
        </div>

        <div>
          <label className="admin-label" htmlFor="months">
            Meses de acesso
          </label>
          <input
            id="months"
            type="number"
            min={0}
            max={36}
            value={months}
            onChange={(e) => setMonths(Math.min(36, Math.max(0, Number(e.target.value) || 0)))}
            className="admin-input"
            disabled={plan === "free"}
          />
          <p className="mt-1 text-xs text-gray-500">
            {plan === "free"
              ? "No plano gratuito o vencimento é sempre removido."
              : months === 0
              ? "Meses = 0 no plano pago significa acesso sem vencimento (cortesia/parceiro)."
              : `Vence em aproximadamente ${months * 30} dias.`}
          </p>
        </div>

        <div>
          <label className="admin-label" htmlFor="note">
            Observação
          </label>
          <input
            id="note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            className="admin-input"
            placeholder="Ex.: cortesia parceiro, pago via PIX em 12/03…"
          />
        </div>

        {user && (
          <div className="border-t border-gray-100 pt-3 text-xs text-gray-500">
            Hoje: {PLAN_LABELS[user.plan] ?? user.plan} ·{" "}
            {PLAN_STATUS_LABELS[user.plan_status] ?? user.plan_status} ·{" "}
            {user.plan_expires_at ? `vence ${formatDate(user.plan_expires_at)}` : "sem vencimento"}
            {user.plan_note && <> · “{user.plan_note}”</>}
          </div>
        )}
      </div>
    </Modal>
  );
}

/* ───────── Painel de filtros do usuário ───────── */

function UserFiltersDrawer({ user, onClose }: { user: UserAdmin | null; onClose: () => void }) {
  const [filters, setFilters] = useState<AdminSavedFilter[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!user) return;
    let alive = true;
    setFilters(null);
    setError("");
    usersApi
      .filters(user.id)
      .then((f) => alive && setFilters(f))
      .catch((e) => alive && setError(errorMessage(e, "Erro ao carregar os filtros")));
    return () => {
      alive = false;
    };
  }, [user]);

  return (
    <Drawer
      open={!!user}
      onClose={onClose}
      width="max-w-xl"
      title={user ? `Filtros de ${user.name || user.email}` : ""}
      subtitle={user ? `${user.filters} filtro(s) · ${user.alerts_sent} alerta(s) enviado(s)` : ""}
    >
      {error ? (
        <EmptyState icon={FilterIcon} title="Erro ao carregar" description={error} />
      ) : filters === null ? (
        <TableSkeleton rows={4} cols={3} />
      ) : filters.length === 0 ? (
        <EmptyState icon={FilterIcon} title="Nenhum filtro salvo" description="Este usuário ainda não criou alertas." />
      ) : (
        <ul className="space-y-3">
          {filters.map((f) => (
            <li key={f.id} className="rounded-lg border border-gray-200 p-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-medium text-gray-900">{f.name}</p>
                  <p className="mt-0.5 text-xs text-gray-500">{describeCriteria(f.criteria)}</p>
                </div>
                <Badge variant={f.is_active ? "success" : "default"}>{f.is_active ? "Ativo" : "Pausado"}</Badge>
              </div>
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
                <span>canais: {f.channels.join(", ") || "—"}</span>
                <span>{f.matches_count} lote(s)</span>
                <span title={f.last_matched_at ? formatDateTime(f.last_matched_at) : undefined}>
                  {f.last_matched_at ? `último ${formatRelative(f.last_matched_at)}` : "nenhum lote ainda"}
                </span>
                <span title={formatDateTime(f.created_at)}>criado {formatRelative(f.created_at)}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Drawer>
  );
}

/* ───────── Página ───────── */

export default function Users() {
  useDocumentTitle("Usuários");
  const { user: me } = useAuth();
  const [sp, setSp] = useSearchParams();
  const [data, setData] = useState<UsersPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [q, setQ] = useState(sp.get("q") ?? "");
  const [busy, setBusy] = useState<number | null>(null);
  const [planFor, setPlanFor] = useState<UserAdmin | null>(null);
  const [filtersFor, setFiltersFor] = useState<UserAdmin | null>(null);

  const params = useMemo(
    () => ({
      q: sp.get("q") ?? undefined,
      plan: sp.get("plan") ?? undefined,
      page: Math.max(1, Number(sp.get("page")) || 1),
      page_size: PAGE_SIZE,
    }),
    [sp]
  );

  const load = useCallback(() => {
    setLoading(true);
    setError("");
    usersApi
      .list(params)
      .then(setData)
      .catch((e) => setError(errorMessage(e, "Erro ao carregar usuários")))
      .finally(() => setLoading(false));
  }, [params]);

  useEffect(load, [load]);

  const update = (patch: Record<string, string | null>, resetPage = true) => {
    const next = new URLSearchParams(sp);
    for (const [k, v] of Object.entries(patch)) {
      if (!v) next.delete(k);
      else next.set(k, v);
    }
    if (resetPage) next.delete("page");
    setSp(next);
  };

  const replaceUser = (u: UserAdmin) =>
    setData((d) => (d ? { ...d, users: d.users.map((x) => (x.id === u.id ? u : x)) } : d));

  const patchUser = async (u: UserAdmin, body: Parameters<typeof usersApi.update>[1], okMsg: string) => {
    setBusy(u.id);
    try {
      replaceUser(await usersApi.update(u.id, body));
      toast.success(okMsg);
    } catch (e) {
      toast.error(errorMessage(e, "Não foi possível atualizar o usuário"));
    }
    setBusy(null);
  };

  const isSelf = (u: UserAdmin) => !!me && u.email === me.email;

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Usuários</h1>
          <p className="text-sm text-gray-500">Contas, planos e permissões. A ativação do plano pago é manual.</p>
        </div>
        <Button variant="secondary" size="sm" onClick={load} disabled={loading}>
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Atualizar
        </Button>
      </div>

      <Card className="mb-4">
        <CardContent className="py-3">
          <div className="grid gap-3 md:grid-cols-3">
            <form
              className="relative md:col-span-2"
              onSubmit={(e) => {
                e.preventDefault();
                update({ q: q.trim() || null });
              }}
            >
              <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Buscar por nome, e-mail ou telefone…"
                className="admin-input pl-9"
                aria-label="Buscar usuários"
              />
            </form>
            <select
              value={sp.get("plan") ?? ""}
              onChange={(e) => update({ plan: e.target.value || null })}
              className="admin-input"
              aria-label="Plano"
            >
              <option value="">Todos os planos</option>
              <option value="free">Gratuito</option>
              <option value="pro">Pago</option>
            </select>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          {error ? (
            <EmptyState
              icon={UsersIcon}
              title="Não foi possível carregar"
              description={error}
              action={
                <Button size="sm" onClick={load}>
                  Tentar novamente
                </Button>
              }
            />
          ) : loading && !data ? (
            <TableSkeleton rows={8} cols={6} />
          ) : !data || data.users.length === 0 ? (
            <EmptyState icon={UsersIcon} title="Nenhum usuário encontrado" description="Ajuste a busca ou o filtro de plano." />
          ) : (
            <Table minWidth={1040}>
              <Thead>
                <tr>
                  <Th>Usuário</Th>
                  <Th>Situação</Th>
                  <Th>Plano</Th>
                  <Th>Filtros</Th>
                  <Th>Alertas</Th>
                  <Th>Último acesso</Th>
                  <Th className="text-right">Ações</Th>
                </tr>
              </Thead>
              <tbody className={loading ? "opacity-60" : ""}>
                {data.users.map((u) => (
                  <Tr key={u.id}>
                    <Td>
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="font-medium text-gray-900">{u.name || "—"}</span>
                          {u.role === "admin" && <Badge variant="purple">{ROLE_LABELS.admin}</Badge>}
                          {isSelf(u) && <Badge variant="info">você</Badge>}
                        </div>
                        <div className="truncate text-xs text-gray-500" title={u.email}>
                          {u.email}
                        </div>
                        {u.phone && <div className="text-xs text-gray-400">{maskPhone(u.phone)}</div>}
                      </div>
                    </Td>
                    <Td>
                      <div className="flex flex-wrap gap-1">
                        <Badge variant={u.is_active ? "success" : "danger"}>{u.is_active ? "Ativo" : "Desativado"}</Badge>
                        <Badge variant={u.email_verified ? "success" : "warning"}>
                          {u.email_verified ? "Verificado" : "Não verificado"}
                        </Badge>
                      </div>
                    </Td>
                    <Td>
                      <Badge variant={u.plan === "pro" ? "purple" : "default"}>{PLAN_LABELS[u.plan] ?? u.plan}</Badge>
                      <div className="mt-0.5 text-[11px] text-gray-500">
                        {PLAN_STATUS_LABELS[u.plan_status] ?? u.plan_status}
                        {u.plan_expires_at ? ` · vence ${formatDate(u.plan_expires_at)}` : u.plan === "pro" ? " · sem vencimento" : ""}
                      </div>
                      {u.plan_note && (
                        <div className="max-w-[180px] truncate text-[11px] text-gray-400" title={u.plan_note}>
                          {u.plan_note}
                        </div>
                      )}
                    </Td>
                    <Td className="tabular-nums">
                      <button
                        type="button"
                        onClick={() => setFiltersFor(u)}
                        className="text-primary-600 hover:underline"
                        title="Ver filtros deste usuário"
                      >
                        {u.filters}
                      </button>
                    </Td>
                    <Td className="tabular-nums">{u.alerts_sent}</Td>
                    <Td className="text-xs text-gray-500" title={u.last_login_at ? formatDateTime(u.last_login_at) : undefined}>
                      {u.last_login_at ? formatRelative(u.last_login_at) : "nunca"}
                      <div className="text-[11px] text-gray-400" title={formatDateTime(u.created_at)}>
                        criado {formatRelative(u.created_at)}
                      </div>
                    </Td>
                    <Td>
                      <div className="flex items-center justify-end gap-1">
                        <Toggle
                          checked={u.is_active}
                          onChange={(v) =>
                            patchUser(u, { is_active: v }, v ? "Usuário ativado" : "Usuário desativado")
                          }
                          disabled={busy === u.id || isSelf(u)}
                          size="sm"
                          title={isSelf(u) ? "Você não pode desativar a própria conta" : u.is_active ? "Desativar" : "Ativar"}
                        />
                        {!u.email_verified && (
                          <button
                            type="button"
                            onClick={() => patchUser(u, { email_verified: true }, "E-mail marcado como verificado")}
                            disabled={busy === u.id}
                            className="rounded-lg p-1.5 text-gray-500 hover:bg-gray-100 hover:text-green-600 disabled:opacity-50"
                            title="Marcar e-mail como verificado"
                            aria-label="Marcar e-mail como verificado"
                          >
                            <MailCheck size={16} />
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() =>
                            patchUser(
                              u,
                              { role: u.role === "admin" ? "user" : "admin" },
                              u.role === "admin" ? "Rebaixado para assinante" : "Promovido a administrador"
                            )
                          }
                          disabled={busy === u.id || isSelf(u)}
                          className="rounded-lg p-1.5 text-gray-500 hover:bg-gray-100 hover:text-primary-600 disabled:opacity-50"
                          title={
                            isSelf(u)
                              ? "Você não pode remover o próprio acesso de administrador"
                              : u.role === "admin"
                              ? "Rebaixar para assinante"
                              : "Promover a administrador"
                          }
                          aria-label="Alterar papel"
                        >
                          {u.role === "admin" ? <ShieldOff size={16} /> : <ShieldCheck size={16} />}
                        </button>
                        <button
                          type="button"
                          onClick={() => setPlanFor(u)}
                          className="rounded-lg p-1.5 text-gray-500 hover:bg-gray-100 hover:text-primary-600"
                          title="Mudar plano"
                          aria-label="Mudar plano"
                        >
                          <CreditCard size={16} />
                        </button>
                        <button
                          type="button"
                          onClick={() => setFiltersFor(u)}
                          className="rounded-lg p-1.5 text-gray-500 hover:bg-gray-100 hover:text-primary-600"
                          title="Ver filtros do usuário"
                          aria-label="Ver filtros do usuário"
                        >
                          <FilterIcon size={16} />
                        </button>
                      </div>
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          )}
        </CardContent>
      </Card>

      {data && (
        <div className="mt-4">
          <Pagination
            page={data.meta.page}
            pages={data.meta.pages}
            total={data.meta.total}
            pageSize={data.meta.page_size}
            onChange={(p) => update({ page: String(p) }, false)}
          />
        </div>
      )}

      <PlanModal user={planFor} onClose={() => setPlanFor(null)} onSaved={replaceUser} />
      <UserFiltersDrawer user={filtersFor} onClose={() => setFiltersFor(null)} />
    </div>
  );
}
