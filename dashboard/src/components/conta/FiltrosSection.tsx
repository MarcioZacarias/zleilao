import { useCallback, useEffect, useState } from "react";
import { BellPlus, BellRing, Eye, Mail, MessageCircle, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "../ui/Button";
import { Toggle } from "../ui/Toggle";
import { EmptyState } from "../ui/EmptyState";
import { Skeleton } from "../ui/Skeleton";
import { FilterFormDrawer } from "./FilterFormDrawer";
import { FilterPreviewDrawer } from "./FilterPreviewDrawer";
import { accountApi } from "../../services/account";
import { errorMessage } from "../../services/api";
import type { AccountMe, SavedFilter } from "../../services/types";
import { formatDateTime, formatRelative } from "../../lib/format";
import { PLAN_LABELS } from "../../lib/labels";

interface FiltrosSectionProps {
  me: AccountMe;
  /** Recarrega `/me` para refletir filters_used. */
  onAccountChanged: () => void;
  /** Abre o formulário de criação já ao montar (vindo de "criar alerta"). */
  autoCreate?: boolean;
  onAutoCreateHandled?: () => void;
  onGoToPlan: () => void;
}

export function FiltrosSection({
  me,
  onAccountChanged,
  autoCreate,
  onAutoCreateHandled,
  onGoToPlan,
}: FiltrosSectionProps) {
  const [filters, setFilters] = useState<SavedFilter[] | null>(null);
  const [limit, setLimit] = useState(me.filters_limit);
  const [error, setError] = useState("");
  // Um único formulário: `formFilter` null significa criação.
  const [formOpen, setFormOpen] = useState(false);
  const [formFilter, setFormFilter] = useState<SavedFilter | null>(null);
  const [preview, setPreview] = useState<SavedFilter | null>(null);
  const [busy, setBusy] = useState<number | null>(null);

  const load = useCallback(() => {
    setError("");
    accountApi
      .filters()
      .then((r) => {
        setFilters(r.filters);
        setLimit(r.limit);
      })
      .catch((e) => {
        setFilters([]);
        setError(errorMessage(e, "Não foi possível carregar seus filtros"));
      });
  }, []);

  useEffect(load, [load]);

  useEffect(() => {
    if (autoCreate) {
      setFormFilter(null);
      setFormOpen(true);
      onAutoCreateHandled?.();
    }
  }, [autoCreate, onAutoCreateHandled]);

  const openCreate = () => {
    setFormFilter(null);
    setFormOpen(true);
  };
  const openEdit = (f: SavedFilter) => {
    setFormFilter(f);
    setFormOpen(true);
  };

  const used = filters?.length ?? me.filters_used;
  const atLimit = used >= limit;

  const onSaved = (saved: SavedFilter, created: boolean) => {
    setFilters((list) => {
      if (!list) return [saved];
      return created ? [saved, ...list] : list.map((f) => (f.id === saved.id ? saved : f));
    });
    onAccountChanged();
  };

  const toggleActive = async (f: SavedFilter) => {
    setBusy(f.id);
    try {
      const updated = await accountApi.updateFilter(f.id, {
        name: f.name,
        criteria: f.criteria,
        channels: f.channels,
        is_active: !f.is_active,
      });
      setFilters((list) => list?.map((x) => (x.id === updated.id ? updated : x)) ?? null);
      toast.success(updated.is_active ? "Alerta ativado" : "Alerta pausado");
    } catch (e) {
      toast.error(errorMessage(e, "Não foi possível alterar o filtro"));
    }
    setBusy(null);
  };

  const remove = async (f: SavedFilter) => {
    if (!window.confirm(`Excluir o alerta "${f.name}"? Você deixa de receber avisos desse filtro.`)) return;
    setBusy(f.id);
    try {
      await accountApi.deleteFilter(f.id);
      setFilters((list) => list?.filter((x) => x.id !== f.id) ?? null);
      toast.success("Filtro excluído");
      onAccountChanged();
    } catch (e) {
      toast.error(errorMessage(e, "Não foi possível excluir o filtro"));
    }
    setBusy(null);
  };

  return (
    <div>
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-lg font-bold text-radar-text">Filtros salvos</h2>
          <p className="mt-0.5 text-sm text-radar-muted">
            Cada filtro vira um alerta: avisamos quando um lote novo se encaixa nele.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-radar-muted">
            <strong className={atLimit ? "text-accent-300" : "text-radar-text"}>{used}</strong> de {limit} filtros
            <span className="ml-1 opacity-70">(plano {PLAN_LABELS[me.plan] ?? me.plan})</span>
          </span>
          <Button
            variant="accent"
            size="sm"
            onClick={openCreate}
            disabled={atLimit}
            title={atLimit ? "Limite de filtros do plano atingido" : undefined}
          >
            <BellPlus size={14} /> Novo filtro
          </Button>
        </div>
      </div>

      {atLimit && (
        <div className="mb-4 rounded-lg border border-accent/30 bg-accent/10 px-4 py-3 text-sm text-radar-text/90">
          Você usou os {limit} filtros do plano {PLAN_LABELS[me.plan] ?? me.plan}. Para criar outro, exclua um filtro
          existente
          {me.plan === "free" && (
            <>
              {" "}
              ou{" "}
              <button type="button" onClick={onGoToPlan} className="font-medium text-accent hover:underline">
                conheça o plano pago
              </button>
            </>
          )}
          .
        </div>
      )}

      {error && (
        <div className="mb-4 rounded-lg border border-red-400/30 bg-red-500/10 px-4 py-3 text-sm text-red-300" role="alert">
          {error}
        </div>
      )}

      {filters === null ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="portal-card p-4">
              <Skeleton tone="dark" className="mb-3 h-4 w-1/3" />
              <Skeleton tone="dark" className="h-3 w-2/3" />
            </div>
          ))}
        </div>
      ) : filters.length === 0 ? (
        <div className="portal-card">
          <EmptyState
            tone="dark"
            icon={BellRing}
            title="Nenhum filtro salvo ainda"
            description="Faça uma busca com os filtros que te interessam e use “Criar alerta desta busca”, ou crie um filtro aqui."
            action={
              <Button variant="accent" size="sm" onClick={openCreate} disabled={atLimit}>
                <BellPlus size={14} /> Criar meu primeiro filtro
              </Button>
            }
          />
        </div>
      ) : (
        <ul className="space-y-3">
          {filters.map((f) => (
            <li key={f.id} className="portal-card p-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-semibold text-radar-text">{f.name}</h3>
                    {!f.is_active && (
                      <span className="rounded-full bg-radar-surface2 px-2 py-0.5 text-[11px] text-radar-muted">
                        pausado
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-sm text-radar-muted">{f.description}</p>

                  <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-radar-muted">
                    <span className="inline-flex items-center gap-1.5">
                      {f.channels.includes("email") && (
                        <span className="inline-flex items-center gap-1" title="Alertas por e-mail">
                          <Mail size={12} /> E-mail
                        </span>
                      )}
                      {f.channels.includes("whatsapp") && (
                        <span className="inline-flex items-center gap-1" title="Alertas por WhatsApp">
                          <MessageCircle size={12} /> WhatsApp
                        </span>
                      )}
                      {f.channels.length === 0 && <span>sem canal</span>}
                    </span>
                    <span>
                      {f.matches_count.toLocaleString("pt-BR")}{" "}
                      {f.matches_count === 1 ? "lote encontrado" : "lotes encontrados"}
                    </span>
                    <span title={f.last_matched_at ? formatDateTime(f.last_matched_at) : undefined}>
                      {f.last_matched_at ? `último em ${formatRelative(f.last_matched_at)}` : "nenhum lote ainda"}
                    </span>
                  </div>
                </div>

                <div className="flex shrink-0 items-center gap-1">
                  <Toggle
                    checked={f.is_active}
                    onChange={() => toggleActive(f)}
                    disabled={busy === f.id}
                    title={f.is_active ? "Pausar alerta" : "Ativar alerta"}
                  />
                  <button
                    type="button"
                    onClick={() => setPreview(f)}
                    className="rounded-lg p-2 text-radar-muted transition-colors hover:bg-white/5 hover:text-radar-text"
                    title="Ver o que este filtro pega hoje"
                    aria-label="Ver o que este filtro pega hoje"
                  >
                    <Eye size={16} />
                  </button>
                  <button
                    type="button"
                    onClick={() => openEdit(f)}
                    className="rounded-lg p-2 text-radar-muted transition-colors hover:bg-white/5 hover:text-radar-text"
                    title="Editar filtro"
                    aria-label="Editar filtro"
                  >
                    <Pencil size={16} />
                  </button>
                  <button
                    type="button"
                    onClick={() => remove(f)}
                    disabled={busy === f.id}
                    className="rounded-lg p-2 text-radar-muted transition-colors hover:bg-red-500/10 hover:text-red-400 disabled:opacity-50"
                    title="Excluir filtro"
                    aria-label="Excluir filtro"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>

              <div className="mt-3 border-t border-radar-border pt-3">
                <button
                  type="button"
                  onClick={() => setPreview(f)}
                  className="inline-flex items-center gap-1.5 text-xs text-accent hover:underline"
                >
                  <Eye size={12} /> Ver o que este filtro pega hoje
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <FilterFormDrawer
        open={formOpen}
        onClose={() => setFormOpen(false)}
        filter={formFilter}
        whatsappAvailable={me.whatsapp_channel_available}
        onSaved={onSaved}
      />
      <FilterPreviewDrawer filter={preview} onClose={() => setPreview(null)} />
    </div>
  );
}
