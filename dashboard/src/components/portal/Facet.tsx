import { ReactNode, useState } from "react";
import { ChevronDown, X } from "lucide-react";
import type { FacetValue } from "../../services/types";

interface FacetProps {
  title: string;
  /** Opções com contagem (facets do backend). */
  options?: FacetValue[];
  value?: string | null;
  onChange?: (value: string | null) => void;
  labelFor?: (value: FacetValue) => string;
  defaultOpen?: boolean;
  /** Conteúdo custom (ranges, selects). */
  children?: ReactNode;
  /** Mostra indicador de filtro ativo no cabeçalho. */
  active?: boolean;
  onClear?: () => void;
  max?: number;
}

/** Grupo de filtro colapsável (seleção única) com contagens. */
export function Facet({
  title,
  options,
  value,
  onChange,
  labelFor,
  defaultOpen = true,
  children,
  active,
  onClear,
  max = 8,
}: FacetProps) {
  const [open, setOpen] = useState(defaultOpen);
  const [showAll, setShowAll] = useState(false);
  const isActive = active ?? (!!value && value !== "");

  const list = options ?? [];
  const visible = showAll ? list : list.slice(0, max);

  return (
    <div className="border-b border-radar-border py-3 last:border-b-0">
      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="flex flex-1 items-center justify-between text-left text-sm font-semibold text-radar-text"
          aria-expanded={open}
        >
          <span className="inline-flex items-center gap-2">
            {title}
            {isActive && <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-label="filtro ativo" />}
          </span>
          <ChevronDown size={16} className={`text-radar-muted transition-transform ${open ? "rotate-180" : ""}`} />
        </button>
        {isActive && (onClear || onChange) && (
          <button
            type="button"
            onClick={() => (onClear ? onClear() : onChange?.(null))}
            className="rounded p-1 text-radar-muted hover:bg-white/5 hover:text-radar-text"
            title="Limpar"
          >
            <X size={13} />
          </button>
        )}
      </div>

      {open && (
        <div className="mt-2 space-y-1">
          {children}
          {options && list.length === 0 && !children && (
            <p className="text-xs text-radar-muted/70">Sem opções para os filtros atuais.</p>
          )}
          {options &&
            visible.map((opt) => {
              const selected = value === opt.value;
              const text = labelFor ? labelFor(opt) : opt.label ?? opt.value;
              return (
                <button
                  type="button"
                  key={opt.value}
                  onClick={() => onChange?.(selected ? null : opt.value)}
                  className={`flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors ${
                    selected
                      ? "bg-accent/15 text-accent-300 ring-1 ring-inset ring-accent/30"
                      : "text-radar-text/90 hover:bg-white/5"
                  }`}
                  aria-pressed={selected}
                >
                  <span className="truncate">{text}</span>
                  <span className={`shrink-0 text-xs tabular-nums ${selected ? "text-accent-300" : "text-radar-muted"}`}>
                    {opt.count.toLocaleString("pt-BR")}
                  </span>
                </button>
              );
            })}
          {options && list.length > max && (
            <button
              type="button"
              onClick={() => setShowAll((s) => !s)}
              className="px-2 pt-1 text-xs text-accent hover:underline"
            >
              {showAll ? "Mostrar menos" : `Mostrar todos (${list.length})`}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
