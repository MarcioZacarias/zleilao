import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Search, X } from "lucide-react";
import { toast } from "sonner";
import { Drawer } from "../ui/Drawer";
import { Button } from "../ui/Button";
import { Toggle } from "../ui/Toggle";
import { accountApi } from "../../services/account";
import { errorMessage, isForbidden } from "../../services/api";
import type { AlertChannel, Criteria, CriteriaKey, SavedFilter } from "../../services/types";
import { criteriaPairs, criteriaToSearch, describeCriteria, suggestFilterName } from "../../lib/criteria";

interface FilterFormDrawerProps {
  open: boolean;
  onClose: () => void;
  /** Filtro existente (edição). Ausente = criação. */
  filter?: SavedFilter | null;
  /** Critério de partida quando se cria a partir da busca. */
  criteria?: Criteria;
  whatsappAvailable: boolean;
  /** Recebe o filtro salvo (criado ou atualizado). */
  onSaved: (filter: SavedFilter, created: boolean) => void;
}

/**
 * Cria e edita o filtro salvo. Usado na conta e no botão "Criar alerta desta
 * busca" — por isso recebe o critério pronto em vez de montar um formulário
 * de busca próprio.
 */
export function FilterFormDrawer({
  open,
  onClose,
  filter,
  criteria,
  whatsappAvailable,
  onSaved,
}: FilterFormDrawerProps) {
  const editing = !!filter;
  const [name, setName] = useState("");
  const [crit, setCrit] = useState<Criteria>({});
  const [channels, setChannels] = useState<AlertChannel[]>(["email"]);
  const [active, setActive] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    const base = filter?.criteria ?? criteria ?? {};
    setCrit(base);
    setName(filter?.name ?? suggestFilterName(base));
    setChannels(filter?.channels?.length ? filter.channels : ["email"]);
    setActive(filter ? filter.is_active : true);
    setError("");
  }, [open, filter, criteria]);

  const pairs = criteriaPairs(crit);

  const removeKey = (key: CriteriaKey) => {
    setCrit((c) => {
      const next = { ...c };
      delete next[key];
      return next;
    });
  };

  const toggleChannel = (ch: AlertChannel) => {
    setChannels((list) => {
      const next = list.includes(ch) ? list.filter((c) => c !== ch) : [...list, ch];
      // Sem canal o filtro não avisa ninguém: o e-mail volta como padrão.
      return next.length ? next : ["email"];
    });
  };

  const save = async () => {
    setSaving(true);
    setError("");
    const body = { name: name.trim() || null, criteria: crit, channels, is_active: active };
    try {
      if (editing && filter) {
        const updated = await accountApi.updateFilter(filter.id, body);
        toast.success("Filtro atualizado");
        onSaved(updated, false);
      } else {
        const created = await accountApi.createFilter(body);
        toast.success("Alerta criado. Avisaremos quando aparecer um lote novo.");
        onSaved(created, true);
      }
      onClose();
    } catch (e) {
      // 403 = limite do plano; a API já manda o texto pronto para exibir.
      const msg = errorMessage(e, "Não foi possível salvar o filtro");
      setError(msg);
      if (!isForbidden(e)) toast.error(msg);
    }
    setSaving(false);
  };

  return (
    <Drawer
      open={open}
      onClose={onClose}
      tone="dark"
      width="max-w-lg"
      title={editing ? "Editar filtro" : "Criar alerta desta busca"}
      subtitle={editing ? filter?.description : describeCriteria(crit)}
      footer={
        <div className="flex gap-2">
          <Button variant="outline-dark" className="flex-1" onClick={onClose}>
            Cancelar
          </Button>
          <Button variant="accent" className="flex-1" onClick={save} loading={saving}>
            {editing ? "Salvar alterações" : "Criar alerta"}
          </Button>
        </div>
      }
    >
      <div className="space-y-6">
        <div>
          <label className="mb-1 block text-sm font-medium text-radar-text/90" htmlFor="filter-name">
            Nome do alerta
          </label>
          <input
            id="filter-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={120}
            className="portal-input"
            placeholder={suggestFilterName(crit)}
          />
          <p className="mt-1 text-xs text-radar-muted">
            Sugerimos um nome a partir dos filtros. Se deixar em branco, geramos a descrição automaticamente.
          </p>
        </div>

        <div>
          <h3 className="mb-2 text-sm font-medium text-radar-text/90">O que este alerta procura</h3>
          {pairs.length === 0 ? (
            <p className="rounded-lg bg-radar-surface2/60 px-3 py-2 text-sm text-radar-muted">
              Sem filtros: você será avisado de <strong className="text-radar-text">qualquer lote novo</strong>. Isso
              costuma gerar muitos avisos — vale restringir por marca, UF ou preço.
            </p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {pairs.map((p) => (
                <span
                  key={p.key}
                  className="inline-flex items-center gap-1.5 rounded-full bg-accent/10 px-3 py-1 text-xs text-accent-300 ring-1 ring-inset ring-accent/30"
                >
                  <span className="text-accent-300/70">{p.label}:</span> {p.value}
                  <button
                    type="button"
                    onClick={() => removeKey(p.key)}
                    className="rounded-full p-0.5 hover:bg-white/10"
                    aria-label={`Remover ${p.label}`}
                  >
                    <X size={11} />
                  </button>
                </span>
              ))}
            </div>
          )}
          <Link
            to={criteriaToSearch(crit)}
            className="mt-3 inline-flex items-center gap-1.5 text-xs text-accent hover:underline"
            onClick={onClose}
          >
            <Search size={12} /> Ver esses filtros na busca
          </Link>
        </div>

        <div>
          <h3 className="mb-2 text-sm font-medium text-radar-text/90">Onde avisar</h3>
          <div className="space-y-2">
            <label className="flex cursor-pointer items-center gap-2 rounded-lg bg-radar-surface2/40 px-3 py-2 text-sm text-radar-text">
              <input
                type="checkbox"
                checked={channels.includes("email")}
                onChange={() => toggleChannel("email")}
                className="h-4 w-4 accent-amber-500"
              />
              E-mail
            </label>
            {whatsappAvailable && (
              <label className="flex cursor-pointer items-center gap-2 rounded-lg bg-radar-surface2/40 px-3 py-2 text-sm text-radar-text">
                <input
                  type="checkbox"
                  checked={channels.includes("whatsapp")}
                  onChange={() => toggleChannel("whatsapp")}
                  className="h-4 w-4 accent-amber-500"
                />
                WhatsApp
              </label>
            )}
          </div>
          <p className="mt-2 text-xs text-radar-muted">
            O envio também respeita o consentimento e a janela de silêncio do seu perfil.
          </p>
        </div>

        <div className="flex items-center justify-between rounded-lg bg-radar-surface2/40 px-3 py-2">
          <div>
            <p className="text-sm text-radar-text">Alerta ativo</p>
            <p className="text-xs text-radar-muted">Desativado, o filtro fica salvo mas não avisa.</p>
          </div>
          <Toggle checked={active} onChange={setActive} />
        </div>

        {error && (
          <div className="rounded-lg border border-red-400/30 bg-red-500/10 px-3 py-2 text-sm text-red-300" role="alert">
            {error}
          </div>
        )}
      </div>
    </Drawer>
  );
}
