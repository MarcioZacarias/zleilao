import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search } from "lucide-react";

interface SearchBarProps {
  initial?: string;
  size?: "md" | "lg";
  placeholder?: string;
  autoFocus?: boolean;
  /** Se informado, é chamado no submit em vez de navegar para /busca. */
  onSubmit?: (q: string) => void;
  className?: string;
}

export function SearchBar({
  initial = "",
  size = "md",
  placeholder = "Buscar por marca, modelo, cidade, leiloeiro…",
  autoFocus,
  onSubmit,
  className = "",
}: SearchBarProps) {
  const [q, setQ] = useState(initial);
  const navigate = useNavigate();

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const term = q.trim();
    if (onSubmit) return onSubmit(term);
    const params = new URLSearchParams();
    if (term) params.set("q", term);
    navigate(`/busca${params.toString() ? `?${params}` : ""}`);
  };

  const h = size === "lg" ? "h-12 md:h-14 text-base" : "h-10 text-sm";

  return (
    <form onSubmit={submit} role="search" className={`flex w-full items-stretch gap-2 ${className}`}>
      <div className="relative flex-1">
        <Search size={size === "lg" ? 20 : 16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-radar-muted" />
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={placeholder}
          autoFocus={autoFocus}
          className={`portal-input ${h} pl-10 ${size === "lg" ? "rounded-xl" : ""}`}
          aria-label="Buscar lotes"
        />
      </div>
      <button
        type="submit"
        className={`${h} shrink-0 rounded-lg ${size === "lg" ? "rounded-xl px-6" : "px-4"} bg-accent font-semibold text-[#0b1020] transition-colors hover:bg-accent-400 focus:outline-none focus:ring-2 focus:ring-accent/50`}
      >
        Buscar
      </button>
    </form>
  );
}
