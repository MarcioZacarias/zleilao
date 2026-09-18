import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Search, RefreshCw, Package, AlertCircle } from "lucide-react";
import { toast } from "sonner";
import { itemsApi } from "../../services/items";
import { sourcesApi } from "../../services/sources";
import { categoriesApi, flattenCategories } from "../../services/categories";
import type { AdminItemsParams, AdminSortOption, Category, ItemAdmin, ItemAdminPage, Source } from "../../services/types";
import { errorMessage } from "../../services/api";
import { Card, CardContent } from "../../components/ui/Card";
import { Badge, BadgeVariant } from "../../components/ui/Badge";
import { Table, Thead, Th, Tr, Td } from "../../components/ui/Table";
import { Button } from "../../components/ui/Button";
import { Pagination } from "../../components/ui/Pagination";
import { TableSkeleton } from "../../components/ui/Skeleton";
import { EmptyState } from "../../components/ui/EmptyState";
import { SafeImage } from "../../components/ui/SafeImage";
import { StatusBadge } from "../../components/portal/StatusBadge";
import { ConditionBadge } from "../../components/portal/ConditionBadge";
import { formatBRL, formatDateTime, formatRelative } from "../../lib/format";
import { ADMIN_SORT_LABELS, EXTRACTION_LABELS, STATUS_LABELS_ADMIN } from "../../lib/labels";
import { ItemDrawer } from "./ItemDrawer";

const PAGE_SIZE = 50;

export function extractionVariant(s: string): BadgeVariant {
  switch (s) {
    case "done":
      return "success";
    case "failed":
      return "danger";
    case "review":
      return "purple";
    case "pending":
      return "warning";
    default:
      return "default";
  }
}

interface ItemsTableProps {
  /** Preset fixo (fila de revisão). */
  presetExtraction?: string;
  title: string;
  subtitle?: string;
  showExtractionError?: boolean;
}

export default function ItemsTable({ presetExtraction, title, subtitle, showExtractionError = false }: ItemsTableProps) {
  const [sp, setSp] = useSearchParams();
  const [page, setPage] = useState<ItemAdminPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [sources, setSources] = useState<Source[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [selected, setSelected] = useState<ItemAdmin | null>(null);
  const [q, setQ] = useState(sp.get("q") ?? "");

  const params: AdminItemsParams = useMemo(
    () => ({
      q: sp.get("q") ?? undefined,
      status: sp.get("status") ?? undefined,
      extraction_status: presetExtraction ?? sp.get("extraction_status") ?? undefined,
      source_id: sp.get("source_id") ? Number(sp.get("source_id")) : undefined,
      category_id: sp.get("category_id") ? Number(sp.get("category_id")) : undefined,
      sort: (sp.get("sort") as AdminSortOption) || "updated_desc",
      page: Math.max(1, Number(sp.get("page")) || 1),
      page_size: PAGE_SIZE,
    }),
    [sp, presetExtraction]
  );

  useEffect(() => {
    sourcesApi.list().then(setSources).catch(() => setSources([]));
    categoriesApi.tree().then(setCategories).catch(() => setCategories([]));
  }, []);

  const load = useCallback(() => {
    setLoading(true);
    return itemsApi
      .list(params)
      .then(setPage)
      .catch((e) => toast.error(errorMessage(e, "Erro ao carregar itens")))
      .finally(() => setLoading(false));
  }, [params]);

  useEffect(() => {
    load();
  }, [load]);

  const update = (patch: Record<string, string | null | undefined>, resetPage = true) => {
    const next = new URLSearchParams(sp);
    for (const [k, v] of Object.entries(patch)) {
      if (!v) next.delete(k);
      else next.set(k, v);
    }
    if (resetPage) next.delete("page");
    setSp(next);
  };

  const flatCats = useMemo(() => flattenCategories(categories), [categories]);

  const onItemUpdated = (it: ItemAdmin | null) => {
    if (it) {
      setSelected(it);
      setPage((p) => (p ? { ...p, items: p.items.map((x) => (x.id === it.id ? it : x)) } : p));
    }
    load();
  };

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{title}</h1>
          {subtitle && <p className="text-sm text-gray-500">{subtitle}</p>}
        </div>
        <Button variant="secondary" size="sm" onClick={load} disabled={loading}>
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Atualizar
        </Button>
      </div>

      {/* Filtros */}
      <Card className="mb-4">
        <CardContent className="py-3">
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-6">
            <form
              className="relative lg:col-span-2"
              onSubmit={(e) => {
                e.preventDefault();
                update({ q: q.trim() || null });
              }}
            >
              <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Buscar título, marca, modelo, lote…"
                className="admin-input pl-9"
                aria-label="Buscar"
              />
            </form>
            {!presetExtraction && (
              <>
                <select value={sp.get("status") ?? ""} onChange={(e) => update({ status: e.target.value || null })} className="admin-input" aria-label="Status">
                  <option value="">Todos os status</option>
                  {Object.entries(STATUS_LABELS_ADMIN).map(([v, l]) => (
                    <option key={v} value={v}>{l}</option>
                  ))}
                </select>
                <select value={sp.get("extraction_status") ?? ""} onChange={(e) => update({ extraction_status: e.target.value || null })} className="admin-input" aria-label="Extração">
                  <option value="">Toda extração</option>
                  {Object.entries(EXTRACTION_LABELS).map(([v, l]) => (
                    <option key={v} value={v}>Extração: {l}</option>
                  ))}
                </select>
              </>
            )}
            <select value={sp.get("source_id") ?? ""} onChange={(e) => update({ source_id: e.target.value || null })} className="admin-input" aria-label="Fonte">
              <option value="">Todas as fontes</option>
              {sources.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
            <select value={sp.get("category_id") ?? ""} onChange={(e) => update({ category_id: e.target.value || null })} className="admin-input" aria-label="Categoria">
              <option value="">Todas as categorias</option>
              {flatCats.map((x) => (
                <option key={x.category.id} value={x.category.id}>{"— ".repeat(x.depth)}{x.category.name}</option>
              ))}
            </select>
            {presetExtraction && (
              <select value={sp.get("status") ?? ""} onChange={(e) => update({ status: e.target.value || null })} className="admin-input" aria-label="Status">
                <option value="">Todos os status</option>
                {Object.entries(STATUS_LABELS_ADMIN).map(([v, l]) => (
                  <option key={v} value={v}>{l}</option>
                ))}
              </select>
            )}
            <select value={params.sort} onChange={(e) => update({ sort: e.target.value }, false)} className="admin-input" aria-label="Ordenação">
              {Object.entries(ADMIN_SORT_LABELS).map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </select>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          {loading && !page ? (
            <TableSkeleton rows={8} cols={7} />
          ) : !page || page.items.length === 0 ? (
            <EmptyState icon={Package} title="Nenhum item encontrado" description="Ajuste os filtros ou aguarde a próxima coleta." />
          ) : (
            <Table minWidth={showExtractionError ? 1100 : 960}>
              <Thead>
                <tr>
                  <Th>Item</Th>
                  <Th>Fonte</Th>
                  <Th>Categoria</Th>
                  <Th>Preço</Th>
                  <Th>Status</Th>
                  <Th>Extração</Th>
                  {showExtractionError && <Th>Erro</Th>}
                  <Th>Pregão</Th>
                  <Th>Atualizado</Th>
                </tr>
              </Thead>
              <tbody className={loading ? "opacity-60" : ""}>
                {page.items.map((it) => (
                  <Tr key={it.id} onClick={() => setSelected(it)}>
                    <Td>
                      <div className="flex items-center gap-3">
                        <SafeImage src={it.image_url} alt="" className="h-10 w-14 shrink-0 rounded object-cover" fallbackClassName="h-10 w-14 rounded" iconSize={16} />
                        <div className="min-w-0">
                          <div className="line-clamp-1 font-medium text-gray-900" title={it.title}>{it.title}</div>
                          <div className="flex flex-wrap items-center gap-1 text-xs text-gray-400">
                            #{it.id}
                            {it.lot_number && <span>· lote {it.lot_number}</span>}
                            {[it.brand, it.model, it.year_model].filter(Boolean).length > 0 && (
                              <span>· {[it.brand, it.model, it.year_model].filter(Boolean).join(" ")}</span>
                            )}
                            <ConditionBadge condition={it.condition} tone="admin" />
                            {it.possible_duplicate && <Badge variant="warning">dup?</Badge>}
                          </div>
                        </div>
                      </div>
                    </Td>
                    <Td className="text-xs">{it.source_name ?? `#${it.source_id}`}</Td>
                    <Td className="text-xs">{it.category_name ?? <span className="text-gray-400">—</span>}</Td>
                    <Td className="tabular-nums">
                      {it.price ? formatBRL(it.price) : <span className="text-gray-400">—</span>}
                      {it.price_second && <div className="text-xs text-gray-400">2ª: {formatBRL(it.price_second)}</div>}
                    </Td>
                    <Td><StatusBadge status={it.status} tone="admin" /></Td>
                    <Td>
                      <Badge variant={extractionVariant(it.extraction_status)}>{EXTRACTION_LABELS[it.extraction_status] ?? it.extraction_status}</Badge>
                      {it.extraction_attempts > 0 && <div className="mt-0.5 text-[11px] text-gray-400">{it.extraction_attempts} tent.</div>}
                    </Td>
                    {showExtractionError && (
                      <Td className="max-w-[260px]">
                        {it.extraction_error ? (
                          <div className="flex items-start gap-1 text-xs text-red-700" title={it.extraction_error}>
                            <AlertCircle size={12} className="mt-0.5 shrink-0" />
                            <span className="line-clamp-2">{it.extraction_error}</span>
                          </div>
                        ) : (
                          <span className="text-gray-400">—</span>
                        )}
                      </Td>
                    )}
                    <Td className="text-xs text-gray-600">{it.next_session_at ? formatDateTime(it.next_session_at) : "—"}</Td>
                    <Td className="text-xs text-gray-500" title={formatDateTime(it.updated_at)}>{formatRelative(it.updated_at)}</Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          )}
        </CardContent>
      </Card>

      {page && (
        <div className="mt-4">
          <Pagination page={page.meta.page} pages={page.meta.pages} total={page.meta.total} pageSize={page.meta.page_size} onChange={(p) => update({ page: String(p) }, false)} />
        </div>
      )}

      <ItemDrawer item={selected} onClose={() => setSelected(null)} onUpdated={onItemUpdated} categories={flatCats} />
    </div>
  );
}
