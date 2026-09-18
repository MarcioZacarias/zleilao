import { ChevronLeft, ChevronRight } from "lucide-react";

interface PaginationProps {
  page: number;
  pages: number;
  total?: number;
  pageSize?: number;
  onChange: (page: number) => void;
  tone?: "light" | "dark";
}

function range(page: number, pages: number): (number | "…")[] {
  if (pages <= 7) return Array.from({ length: pages }, (_, i) => i + 1);
  const out: (number | "…")[] = [1];
  const start = Math.max(2, page - 1);
  const end = Math.min(pages - 1, page + 1);
  if (start > 2) out.push("…");
  for (let i = start; i <= end; i++) out.push(i);
  if (end < pages - 1) out.push("…");
  out.push(pages);
  return out;
}

export function Pagination({ page, pages, total, pageSize, onChange, tone = "light" }: PaginationProps) {
  if (pages <= 1 && !total) return null;
  const dark = tone === "dark";
  const base = `inline-flex h-9 min-w-9 items-center justify-center rounded-lg px-2 text-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed`;
  const idle = dark
    ? "text-radar-muted hover:bg-white/5 hover:text-radar-text"
    : "text-gray-600 hover:bg-gray-100";
  const active = dark ? "bg-accent text-[#0b1020] font-semibold" : "bg-primary-600 text-white font-semibold";

  const from = total !== undefined && pageSize ? Math.min(total, (page - 1) * pageSize + 1) : null;
  const to = total !== undefined && pageSize ? Math.min(total, page * pageSize) : null;

  return (
    <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
      {total !== undefined && (
        <p className={`text-xs ${dark ? "text-radar-muted" : "text-gray-500"}`}>
          {total === 0
            ? "Nenhum resultado"
            : `Exibindo ${from}–${to} de ${total.toLocaleString("pt-BR")}`}
        </p>
      )}
      {pages > 1 && (
        <nav className="flex items-center gap-1" aria-label="Paginação">
          <button
            className={`${base} ${idle}`}
            onClick={() => onChange(page - 1)}
            disabled={page <= 1}
            aria-label="Página anterior"
          >
            <ChevronLeft size={16} />
          </button>
          {range(page, pages).map((p, i) =>
            p === "…" ? (
              <span key={`e${i}`} className={`px-1 text-sm ${dark ? "text-radar-muted" : "text-gray-400"}`}>
                …
              </span>
            ) : (
              <button
                key={p}
                className={`${base} ${p === page ? active : idle}`}
                onClick={() => onChange(p)}
                aria-current={p === page ? "page" : undefined}
              >
                {p}
              </button>
            )
          )}
          <button
            className={`${base} ${idle}`}
            onClick={() => onChange(page + 1)}
            disabled={page >= pages}
            aria-label="Próxima página"
          >
            <ChevronRight size={16} />
          </button>
        </nav>
      )}
    </div>
  );
}
