import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { SlidersHorizontal, X, SearchX, ChevronRight } from "lucide-react";
import { portalApi } from "../../services/portal";
import type { Category, FacetValue, ItemPage, PortalSearchParams, SortOption } from "../../services/types";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import {
  AUCTION_TYPE_LABELS,
  CONDITION_LABELS,
  SORT_LABELS,
  STATUS_LABELS,
} from "../../lib/labels";
import { dateInputToIso, formatBRL, isoToDateInput } from "../../lib/format";
import { ItemCard } from "../../components/portal/ItemCard";
import { Facet } from "../../components/portal/Facet";
import { Pagination } from "../../components/ui/Pagination";
import { ItemCardSkeleton } from "../../components/ui/Skeleton";
import { EmptyState } from "../../components/ui/EmptyState";
import { Drawer } from "../../components/ui/Drawer";
import { Button } from "../../components/ui/Button";
import { errorMessage } from "../../services/api";

const PAGE_SIZE = 24;
const FILTER_KEYS = [
  "q",
  "category",
  "brand",
  "model",
  "year_min",
  "year_max",
  "price_min",
  "price_max",
  "state",
  "source",
  "condition",
  "auction_type",
  "session_from",
  "session_to",
  "status",
] as const;
type FilterKey = (typeof FILTER_KEYS)[number];

type Filters = Partial<Record<FilterKey, string>> & { sort: SortOption; page: number };

function parseFilters(sp: URLSearchParams): Filters {
  const f: Filters = { sort: (sp.get("sort") as SortOption) || "relevance", page: Math.max(1, Number(sp.get("page")) || 1) };
  for (const k of FILTER_KEYS) {
    const v = sp.get(k);
    if (v) f[k] = v;
  }
  if (!sp.get("sort") && f.q) f.sort = "relevance";
  return f;
}

function toApiParams(f: Filters): PortalSearchParams {
  const num = (v?: string) => (v && Number.isFinite(Number(v)) ? Number(v) : undefined);
  return {
    q: f.q,
    category: f.category,
    brand: f.brand,
    model: f.model,
    year_min: num(f.year_min),
    year_max: num(f.year_max),
    price_min: num(f.price_min),
    price_max: num(f.price_max),
    state: f.state,
    source: f.source,
    condition: f.condition,
    auction_type: f.auction_type,
    session_from: f.session_from,
    session_to: f.session_to,
    status: f.status,
    sort: f.sort,
    page: f.page,
    page_size: PAGE_SIZE,
    facets: true,
  };
}

/* ───────── Range inputs (aplicam no blur / Enter) ───────── */

function RangeInputs({
  min,
  max,
  onApply,
  placeholderMin,
  placeholderMax,
  prefix,
}: {
  min?: string;
  max?: string;
  onApply: (min: string, max: string) => void;
  placeholderMin: string;
  placeholderMax: string;
  prefix?: string;
}) {
  const [lo, setLo] = useState(min ?? "");
  const [hi, setHi] = useState(max ?? "");
  useEffect(() => setLo(min ?? ""), [min]);
  useEffect(() => setHi(max ?? ""), [max]);
  const apply = () => {
    if (lo !== (min ?? "") || hi !== (max ?? "")) onApply(lo, hi);
  };
  return (
    <div className="flex items-center gap-2">
      <div className="relative flex-1">
        {prefix && <span className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-xs text-radar-muted">{prefix}</span>}
        <input
          type="number"
          inputMode="numeric"
          value={lo}
          onChange={(e) => setLo(e.target.value)}
          onBlur={apply}
          onKeyDown={(e) => e.key === "Enter" && apply()}
          placeholder={placeholderMin}
          className={`portal-input py-1.5 text-xs ${prefix ? "pl-7" : ""}`}
          aria-label={`${placeholderMin}`}
        />
      </div>
      <span className="text-xs text-radar-muted">–</span>
      <div className="relative flex-1">
        {prefix && <span className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-xs text-radar-muted">{prefix}</span>}
        <input
          type="number"
          inputMode="numeric"
          value={hi}
          onChange={(e) => setHi(e.target.value)}
          onBlur={apply}
          onKeyDown={(e) => e.key === "Enter" && apply()}
          placeholder={placeholderMax}
          className={`portal-input py-1.5 text-xs ${prefix ? "pl-7" : ""}`}
          aria-label={`${placeholderMax}`}
        />
      </div>
    </div>
  );
}

/* ───────── Árvore de categorias ───────── */

function CategoryTree({
  nodes,
  selected,
  onSelect,
  depth = 0,
}: {
  nodes: Category[];
  selected?: string;
  onSelect: (slug: string | null) => void;
  depth?: number;
}) {
  return (
    <ul className={depth ? "ml-3 border-l border-radar-border pl-2" : ""}>
      {nodes.map((c) => {
        const active = selected === c.slug;
        return (
          <li key={c.id}>
            <button
              type="button"
              onClick={() => onSelect(active ? null : c.slug)}
              className={`flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors ${
                active ? "bg-accent/15 text-accent-300 ring-1 ring-inset ring-accent/30" : "text-radar-text/90 hover:bg-white/5"
              }`}
              aria-pressed={active}
            >
              <span className="inline-flex min-w-0 items-center gap-1">
                {c.children?.length > 0 && <ChevronRight size={12} className="shrink-0 text-radar-muted" />}
                <span className="truncate">{c.name}</span>
              </span>
              <span className={`shrink-0 text-xs tabular-nums ${active ? "text-accent-300" : "text-radar-muted"}`}>
                {c.items_count.toLocaleString("pt-BR")}
              </span>
            </button>
            {c.children?.length > 0 && (
              <CategoryTree nodes={c.children} selected={selected} onSelect={onSelect} depth={depth + 1} />
            )}
          </li>
        );
      })}
    </ul>
  );
}

/* ───────── Painel de filtros ───────── */

interface FilterPanelProps {
  filters: Filters;
  facets: ItemPage["facets"];
  categories: Category[];
  models: FacetValue[];
  update: (patch: Partial<Record<FilterKey, string | null>>) => void;
  clearAll: () => void;
  activeCount: number;
}

function FilterPanel({ filters, facets, categories, models, update, clearAll, activeCount }: FilterPanelProps) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <h2 className="text-sm font-bold uppercase tracking-wider text-radar-muted">Filtros</h2>
        {activeCount > 0 && (
          <button type="button" onClick={clearAll} className="text-xs text-accent hover:underline">
            Limpar tudo ({activeCount})
          </button>
        )}
      </div>

      <Facet title="Categoria" active={!!filters.category} onClear={() => update({ category: null })}>
        {categories.length ? (
          <CategoryTree nodes={categories} selected={filters.category} onSelect={(slug) => update({ category: slug })} />
        ) : (
          (facets.categories ?? []).map((c) => (
            <button
              key={c.value}
              type="button"
              onClick={() => update({ category: filters.category === c.value ? null : c.value })}
              className={`flex w-full items-center justify-between rounded-md px-2 py-1.5 text-sm ${
                filters.category === c.value ? "bg-accent/15 text-accent-300" : "text-radar-text/90 hover:bg-white/5"
              }`}
            >
              <span>{c.label ?? c.value}</span>
              <span className="text-xs text-radar-muted">{c.count}</span>
            </button>
          ))
        )}
      </Facet>

      <Facet
        title="Marca"
        options={facets.brands ?? []}
        value={filters.brand}
        onChange={(v) => update({ brand: v, model: null })}
        max={8}
      />

      {filters.brand && (
        <Facet title="Modelo" active={!!filters.model} onClear={() => update({ model: null })}>
          <select
            value={filters.model ?? ""}
            onChange={(e) => update({ model: e.target.value || null })}
            className="portal-select py-1.5 text-xs"
            aria-label="Modelo"
          >
            <option value="">Todos os modelos</option>
            {models.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label ?? m.value} ({m.count})
              </option>
            ))}
          </select>
        </Facet>
      )}

      <Facet title="Ano do modelo" active={!!(filters.year_min || filters.year_max)} onClear={() => update({ year_min: null, year_max: null })}>
        <RangeInputs
          min={filters.year_min}
          max={filters.year_max}
          placeholderMin="De"
          placeholderMax="Até"
          onApply={(lo, hi) => update({ year_min: lo || null, year_max: hi || null })}
        />
      </Facet>

      <Facet title="Preço" active={!!(filters.price_min || filters.price_max)} onClear={() => update({ price_min: null, price_max: null })}>
        <RangeInputs
          min={filters.price_min}
          max={filters.price_max}
          placeholderMin="Mín."
          placeholderMax="Máx."
          prefix="R$"
          onApply={(lo, hi) => update({ price_min: lo || null, price_max: hi || null })}
        />
      </Facet>

      <Facet title="UF" options={facets.states ?? []} value={filters.state} onChange={(v) => update({ state: v })} max={10} />

      <Facet title="Fonte" options={facets.sources ?? []} value={filters.source} onChange={(v) => update({ source: v })} />

      <Facet
        title="Condição"
        options={facets.conditions ?? []}
        value={filters.condition}
        onChange={(v) => update({ condition: v })}
        labelFor={(o) => o.label ?? CONDITION_LABELS[o.value] ?? o.value}
      />

      <Facet
        title="Tipo de leilão"
        options={facets.auction_types ?? []}
        value={filters.auction_type}
        onChange={(v) => update({ auction_type: v })}
        labelFor={(o) => o.label ?? AUCTION_TYPE_LABELS[o.value] ?? o.value}
      />

      <Facet title="Data do pregão" active={!!(filters.session_from || filters.session_to)} onClear={() => update({ session_from: null, session_to: null })}>
        <div className="grid grid-cols-2 gap-2">
          <label className="text-[11px] text-radar-muted">
            De
            <input
              type="date"
              value={isoToDateInput(filters.session_from)}
              onChange={(e) => update({ session_from: dateInputToIso(e.target.value) ?? null })}
              className="portal-input mt-0.5 py-1.5 text-xs"
            />
          </label>
          <label className="text-[11px] text-radar-muted">
            Até
            <input
              type="date"
              value={isoToDateInput(filters.session_to)}
              onChange={(e) => update({ session_to: dateInputToIso(e.target.value, true) ?? null })}
              className="portal-input mt-0.5 py-1.5 text-xs"
            />
          </label>
        </div>
      </Facet>

      <Facet title="Situação" active={!!filters.status} onClear={() => update({ status: null })}>
        <div className="flex flex-wrap gap-1.5">
          {[
            { v: "auction_soon", l: "Pregão em breve" },
            { v: "published", l: "Aberto" },
          ].map((o) => (
            <button
              type="button"
              key={o.v}
              onClick={() => update({ status: filters.status === o.v ? null : o.v })}
              className={`rounded-full px-3 py-1 text-xs ring-1 ring-inset transition-colors ${
                filters.status === o.v
                  ? "bg-accent/15 text-accent-300 ring-accent/40"
                  : "text-radar-muted ring-white/10 hover:text-radar-text"
              }`}
              aria-pressed={filters.status === o.v}
            >
              {o.l}
            </button>
          ))}
        </div>
      </Facet>
    </div>
  );
}

/* ───────── Página ───────── */

export default function Search() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = useMemo(() => parseFilters(searchParams), [searchParams]);
  useDocumentTitle(filters.q ? `Busca: ${filters.q}` : "Buscar lotes");

  const [page, setPage] = useState<ItemPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [models, setModels] = useState<FacetValue[]>([]);
  const [drawer, setDrawer] = useState(false);

  useEffect(() => {
    portalApi.categories().then(setCategories).catch(() => setCategories([]));
  }, []);

  useEffect(() => {
    if (!filters.brand) {
      setModels([]);
      return;
    }
    let alive = true;
    portalApi
      .models(filters.brand)
      .then((m) => alive && setModels(m))
      .catch(() => alive && setModels([]));
    return () => {
      alive = false;
    };
  }, [filters.brand]);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    portalApi
      .items(toApiParams(filters))
      .then((p) => {
        if (!alive) return;
        setPage(p);
      })
      .catch((e) => alive && setError(errorMessage(e, "Não foi possível carregar os lotes")))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [filters]);

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [filters.page]);

  const update = useCallback(
    (patch: Partial<Record<FilterKey | "sort" | "page", string | null>>, resetPage = true) => {
      const next = new URLSearchParams(searchParams);
      for (const [k, v] of Object.entries(patch)) {
        if (v === null || v === undefined || v === "") next.delete(k);
        else next.set(k, v);
      }
      if (resetPage) next.delete("page");
      setSearchParams(next);
    },
    [searchParams, setSearchParams]
  );

  const clearAll = () => {
    const next = new URLSearchParams();
    if (filters.q) next.set("q", filters.q);
    setSearchParams(next);
  };

  const activeFilters = FILTER_KEYS.filter((k) => k !== "q" && filters[k]);
  const facets = page?.facets ?? {};

  const chipLabel = (k: FilterKey): string => {
    const v = filters[k]!;
    switch (k) {
      case "category": {
        const f = (facets.categories ?? []).find((c) => c.value === v);
        return `Categoria: ${f?.label ?? findCategoryName(categories, v) ?? v}`;
      }
      case "brand":
        return `Marca: ${v}`;
      case "model":
        return `Modelo: ${v}`;
      case "year_min":
        return `Ano ≥ ${v}`;
      case "year_max":
        return `Ano ≤ ${v}`;
      case "price_min":
        return `Preço ≥ ${formatBRL(v)}`;
      case "price_max":
        return `Preço ≤ ${formatBRL(v)}`;
      case "state":
        return `UF: ${v}`;
      case "source": {
        const f = (facets.sources ?? []).find((c) => c.value === v);
        return `Fonte: ${f?.label ?? v}`;
      }
      case "condition":
        return `Condição: ${CONDITION_LABELS[v] ?? v}`;
      case "auction_type":
        return `Tipo: ${AUCTION_TYPE_LABELS[v] ?? v}`;
      case "session_from":
        return `Pregão a partir de ${isoToDateInput(v).split("-").reverse().join("/")}`;
      case "session_to":
        return `Pregão até ${isoToDateInput(v).split("-").reverse().join("/")}`;
      case "status":
        return STATUS_LABELS[v] ?? v;
      default:
        return `${k}: ${v}`;
    }
  };

  const panelProps: FilterPanelProps = {
    filters,
    facets,
    categories,
    models,
    update: (patch) => update(patch),
    clearAll,
    activeCount: activeFilters.length,
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
      {/* Cabeçalho */}
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-xl font-bold text-radar-text md:text-2xl">
            {filters.q ? (
              <>
                Resultados para <span className="text-accent">“{filters.q}”</span>
              </>
            ) : filters.status === "auction_soon" ? (
              "Pregões em breve"
            ) : (
              "Todos os lotes"
            )}
          </h1>
          <p className="mt-0.5 text-sm text-radar-muted">
            {loading && !page ? "Carregando…" : page ? `${page.meta.total.toLocaleString("pt-BR")} ${page.meta.total === 1 ? "lote encontrado" : "lotes encontrados"}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline-dark" size="sm" className="lg:hidden" onClick={() => setDrawer(true)}>
            <SlidersHorizontal size={14} /> Filtros
            {activeFilters.length > 0 && (
              <span className="rounded-full bg-accent px-1.5 text-[10px] font-bold text-[#0b1020]">{activeFilters.length}</span>
            )}
          </Button>
          <label className="flex items-center gap-2 text-xs text-radar-muted">
            <span className="hidden sm:inline">Ordenar</span>
            <select
              value={filters.sort}
              onChange={(e) => update({ sort: e.target.value })}
              className="portal-select w-auto py-1.5 text-xs"
              aria-label="Ordenar por"
            >
              {Object.entries(SORT_LABELS).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {/* Chips de filtros ativos */}
      {(activeFilters.length > 0 || filters.q) && (
        <div className="mb-4 flex flex-wrap items-center gap-2">
          {filters.q && (
            <button
              type="button"
              onClick={() => update({ q: null })}
              className="inline-flex items-center gap-1 rounded-full bg-radar-surface2 px-3 py-1 text-xs text-radar-text ring-1 ring-inset ring-white/10 hover:ring-white/25"
            >
              “{filters.q}” <X size={12} />
            </button>
          )}
          {activeFilters.map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => update({ [k]: null, ...(k === "brand" ? { model: null } : {}) })}
              className="inline-flex items-center gap-1 rounded-full bg-accent/10 px-3 py-1 text-xs text-accent-300 ring-1 ring-inset ring-accent/30 hover:ring-accent/60"
            >
              {chipLabel(k)} <X size={12} />
            </button>
          ))}
          {activeFilters.length > 1 && (
            <button type="button" onClick={clearAll} className="text-xs text-radar-muted hover:text-radar-text">
              Limpar tudo
            </button>
          )}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
        {/* Sidebar desktop */}
        <aside className="hidden lg:block">
          <div className="portal-card sticky top-20 max-h-[calc(100vh-6rem)] overflow-y-auto p-4">
            <FilterPanel {...panelProps} />
          </div>
        </aside>

        {/* Resultados */}
        <section className="min-w-0">
          {error ? (
            <div className="portal-card">
              <EmptyState
                tone="dark"
                icon={SearchX}
                title="Erro ao carregar"
                description={error}
                action={
                  <Button variant="accent" size="sm" onClick={() => update({}, false)}>
                    Tentar novamente
                  </Button>
                }
              />
            </div>
          ) : loading && !page ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {Array.from({ length: 9 }).map((_, i) => (
                <ItemCardSkeleton key={i} />
              ))}
            </div>
          ) : page && page.items.length === 0 ? (
            <div className="portal-card">
              <EmptyState
                tone="dark"
                icon={SearchX}
                title="Nenhum lote encontrado"
                description="Tente remover alguns filtros ou buscar por outro termo."
                action={
                  activeFilters.length > 0 ? (
                    <Button variant="outline-dark" size="sm" onClick={clearAll}>
                      Limpar filtros
                    </Button>
                  ) : undefined
                }
              />
            </div>
          ) : page ? (
            <>
              <div className={`grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 ${loading ? "opacity-60 transition-opacity" : ""}`}>
                {page.items.map((it) => (
                  <ItemCard key={it.id} item={it} />
                ))}
              </div>
              <div className="mt-6">
                <Pagination
                  tone="dark"
                  page={page.meta.page}
                  pages={page.meta.pages}
                  total={page.meta.total}
                  pageSize={page.meta.page_size}
                  onChange={(p) => update({ page: String(p) }, false)}
                />
              </div>
            </>
          ) : null}
        </section>
      </div>

      {/* Drawer mobile */}
      <Drawer open={drawer} onClose={() => setDrawer(false)} title="Filtros" side="left" width="max-w-sm" tone="dark"
        footer={
          <Button variant="accent" className="w-full" onClick={() => setDrawer(false)}>
            Ver {page ? page.meta.total.toLocaleString("pt-BR") : ""} resultados
          </Button>
        }
      >
        <FilterPanel {...panelProps} />
      </Drawer>
    </div>
  );
}

function findCategoryName(tree: Category[], slug: string): string | null {
  for (const c of tree) {
    if (c.slug === slug) return c.name;
    const f = c.children?.length ? findCategoryName(c.children, slug) : null;
    if (f) return f;
  }
  return null;
}
