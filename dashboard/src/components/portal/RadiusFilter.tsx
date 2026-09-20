import { useEffect, useRef, useState } from "react";
import { MapPin, X } from "lucide-react";
import { portalApi } from "../../services/portal";
import type { CityOption } from "../../services/types";

const RAIOS = [25, 50, 100, 200, 500];

interface Props {
  city: string | undefined;
  state: string | undefined;
  radius: string | undefined;
  onChange: (next: { near_city: string | null; near_state: string | null; radius_km: string | null }) => void;
}

/**
 * Busca por raio: cidade de referência + distância.
 *
 * Os três parâmetros andam juntos no servidor, então a interface nunca deixa
 * um estado pela metade: escolher a cidade já aplica um raio padrão, e limpar
 * a cidade limpa tudo.
 */
export function RadiusFilter({ city, state, radius, onChange }: Props) {
  const [term, setTerm] = useState("");
  const [options, setOptions] = useState<CityOption[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  const selected = city && state ? `${city} / ${state}` : null;

  useEffect(() => {
    if (term.trim().length < 2) {
      setOptions([]);
      return;
    }
    let alive = true;
    setLoading(true);
    const timer = window.setTimeout(() => {
      portalApi
        .cities(term.trim())
        .then((r) => alive && setOptions(r))
        .catch(() => alive && setOptions([]))
        .finally(() => alive && setLoading(false));
    }, 250);
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [term]);

  // Fecha ao clicar fora, senão a lista fica presa sobre o resto dos filtros.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const pick = (c: CityOption) => {
    setTerm("");
    setOpen(false);
    onChange({ near_city: c.city, near_state: c.state, radius_km: radius ?? "100" });
  };

  const clear = () => {
    setTerm("");
    setOpen(false);
    onChange({ near_city: null, near_state: null, radius_km: null });
  };

  return (
    <div ref={boxRef} className="relative">
      {selected ? (
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-2 rounded-lg bg-white/[0.04] px-3 py-2 text-sm">
            <span className="inline-flex min-w-0 items-center gap-1.5 text-radar-text">
              <MapPin size={13} className="shrink-0 text-accent" />
              <span className="truncate">{selected}</span>
            </span>
            <button
              type="button"
              onClick={clear}
              className="shrink-0 rounded p-0.5 text-radar-muted hover:text-radar-text"
              aria-label="Remover cidade de referência"
            >
              <X size={14} />
            </button>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {RAIOS.map((r) => {
              const active = String(r) === (radius ?? "100");
              return (
                <button
                  key={r}
                  type="button"
                  onClick={() => onChange({ near_city: city!, near_state: state!, radius_km: String(r) })}
                  className={`rounded-full px-2.5 py-1 text-xs transition-colors ${
                    active
                      ? "bg-accent text-[#1a1200] font-semibold"
                      : "bg-white/[0.04] text-radar-muted hover:text-radar-text"
                  }`}
                >
                  {r} km
                </button>
              );
            })}
          </div>
          <p className="text-[11px] leading-relaxed text-radar-muted">
            Distância entre os municípios. Lotes sem cidade reconhecida não entram neste filtro.
          </p>
        </div>
      ) : (
        <>
          <input
            type="text"
            value={term}
            onChange={(e) => {
              setTerm(e.target.value);
              setOpen(true);
            }}
            onFocus={() => setOpen(true)}
            placeholder="Digite sua cidade..."
            className="w-full rounded-lg border border-radar-border bg-radar-surface2 px-3 py-2 text-sm text-radar-text placeholder:text-radar-muted/60 focus:border-accent/50 focus:outline-none"
          />
          {open && term.trim().length >= 2 && (
            <ul className="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-lg border border-radar-border bg-radar-surface2 py-1 shadow-xl">
              {loading && <li className="px-3 py-2 text-xs text-radar-muted">Procurando...</li>}
              {!loading && options.length === 0 && (
                <li className="px-3 py-2 text-xs text-radar-muted">Nenhum município encontrado.</li>
              )}
              {options.map((c) => (
                <li key={`${c.state}-${c.city}`}>
                  <button
                    type="button"
                    onClick={() => pick(c)}
                    className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-radar-text hover:bg-white/[0.06]"
                  >
                    <MapPin size={12} className="shrink-0 text-radar-muted" />
                    <span className="truncate">{c.city}</span>
                    <span className="ml-auto shrink-0 text-xs text-radar-muted">{c.state}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
