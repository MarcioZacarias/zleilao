import { useEffect, useMemo, useState } from "react";
import { ExternalLink, RefreshCw, Eye, EyeOff, Save, AlertCircle, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { itemsApi } from "../../services/items";
import { categoriesApi } from "../../services/categories";
import type { Category, CategoryField, ItemAdmin, ItemUpdate } from "../../services/types";
import { errorMessage } from "../../services/api";
import { Drawer } from "../../components/ui/Drawer";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";
import { SafeImage } from "../../components/ui/SafeImage";
import { Skeleton } from "../../components/ui/Skeleton";
import { StatusBadge } from "../../components/portal/StatusBadge";
import { formatBRL, formatDateTime } from "../../lib/format";
import { CONDITION_LABELS, EXTRACTION_LABELS, PRICE_KIND_LABELS, STATUS_LABELS_ADMIN } from "../../lib/labels";
import { attributeToInput, inputToAttribute } from "../../lib/attributes";

interface ItemDrawerProps {
  item: ItemAdmin | null;
  onClose: () => void;
  onUpdated: (item: ItemAdmin | null) => void;
  categories: { category: Category; depth: number }[];
}

interface BaseForm {
  title: string;
  category_id: string;
  status: string;
  brand: string;
  model: string;
  year_model: string;
  km: string;
  condition: string;
  description: string;
}

function toBase(it: ItemAdmin): BaseForm {
  return {
    title: it.title,
    category_id: it.category_id ? String(it.category_id) : "",
    status: it.status,
    brand: it.brand ?? "",
    model: it.model ?? "",
    year_model: it.year_model ? String(it.year_model) : "",
    km: it.km !== null && it.km !== undefined ? String(it.km) : "",
    condition: it.condition ?? "",
    description: it.description ?? "",
  };
}

function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <div>
      <label className="admin-label">{label}</label>
      {children}
      {hint && <p className="mt-0.5 text-[11px] text-gray-400">{hint}</p>}
    </div>
  );
}

function AttributeInput({ field, value, onChange }: { field: CategoryField; value: string; onChange: (v: string) => void }) {
  const cls = "admin-input";
  switch (field.field_type) {
    case "bool":
      return (
        <select className={cls} value={value} onChange={(e) => onChange(e.target.value)}>
          <option value="">não informado</option>
          <option value="true">Sim</option>
          <option value="false">Não</option>
        </select>
      );
    case "enum":
      return (
        <select className={cls} value={value} onChange={(e) => onChange(e.target.value)}>
          <option value="">não informado</option>
          {(field.options ?? []).map((o) => (
            <option key={o} value={o}>{o}</option>
          ))}
          {value && !(field.options ?? []).includes(value) && <option value={value}>{value} (fora da lista)</option>}
        </select>
      );
    case "int":
    case "decimal":
      return <input className={cls} inputMode="decimal" value={value} onChange={(e) => onChange(e.target.value)} placeholder={field.unit ?? ""} />;
    case "date":
      return <input type="date" className={cls} value={value.slice(0, 10)} onChange={(e) => onChange(e.target.value)} />;
    default:
      return <input className={cls} value={value} onChange={(e) => onChange(e.target.value)} />;
  }
}

export function ItemDrawer({ item, onClose, onUpdated, categories }: ItemDrawerProps) {
  const [detail, setDetail] = useState<ItemAdmin | null>(item);
  const [base, setBase] = useState<BaseForm | null>(item ? toBase(item) : null);
  const [fields, setFields] = useState<CategoryField[] | null>(null);
  const [attrs, setAttrs] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<"save" | "renorm" | "publish" | "hide" | null>(null);

  // Carrega detalhe completo ao abrir (a lista já traz ItemAdmin, mas garantimos frescor).
  useEffect(() => {
    if (!item) {
      setDetail(null);
      setBase(null);
      return;
    }
    setDetail(item);
    setBase(toBase(item));
    setAttrs(Object.fromEntries(Object.entries(item.attributes ?? {}).map(([k, v]) => [k, attributeToInput(v)])));
    itemsApi
      .get(item.id)
      .then((d) => {
        setDetail(d);
        setBase(toBase(d));
        setAttrs(Object.fromEntries(Object.entries(d.attributes ?? {}).map(([k, v]) => [k, attributeToInput(v)])));
      })
      .catch(() => undefined);
  }, [item]);

  const categoryId = base?.category_id ? Number(base.category_id) : detail?.category_id ?? null;

  useEffect(() => {
    if (!categoryId) {
      setFields([]);
      return;
    }
    setFields(null);
    let alive = true;
    categoriesApi
      .fields(categoryId)
      .then((f) => alive && setFields([...f].sort((a, b) => a.sort_order - b.sort_order)))
      .catch(() => alive && setFields([]));
    return () => {
      alive = false;
    };
  }, [categoryId]);

  const extraAttrKeys = useMemo(() => {
    const known = new Set((fields ?? []).map((f) => f.key));
    return Object.keys(attrs).filter((k) => !known.has(k));
  }, [fields, attrs]);

  const save = async () => {
    if (!detail || !base) return;
    const attributes: Record<string, unknown> = {};
    for (const f of fields ?? []) {
      if (f.key in attrs) attributes[f.key] = inputToAttribute(f, attrs[f.key]);
    }
    for (const k of extraAttrKeys) attributes[k] = attrs[k] === "" ? null : attrs[k];

    const body: ItemUpdate = {
      title: base.title.trim(),
      category_id: base.category_id ? Number(base.category_id) : null,
      status: base.status,
      brand: base.brand.trim() || null,
      model: base.model.trim() || null,
      year_model: base.year_model ? parseInt(base.year_model) : null,
      km: base.km ? parseInt(base.km.replace(/\./g, "")) : null,
      condition: base.condition || null,
      description: base.description.trim() || null,
      attributes,
    };
    setBusy("save");
    try {
      const updated = await itemsApi.update(detail.id, body);
      toast.success("Item salvo");
      onUpdated(updated);
    } catch (e) {
      toast.error(errorMessage(e, "Erro ao salvar item"));
    }
    setBusy(null);
  };

  const action = async (kind: "renorm" | "publish" | "hide") => {
    if (!detail) return;
    if (kind === "hide" && !confirm("Ocultar este item da vitrine (marcar como retirado)?")) return;
    setBusy(kind);
    try {
      const fn = kind === "renorm" ? itemsApi.renormalize : kind === "publish" ? itemsApi.publish : itemsApi.hide;
      const updated = await fn(detail.id);
      toast.success(kind === "renorm" ? "Reextração concluída" : kind === "publish" ? "Item publicado" : "Item ocultado");
      onUpdated(updated);
    } catch (e) {
      toast.error(errorMessage(e, "Erro na operação"));
    }
    setBusy(null);
  };

  const open = !!item;

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={detail ? `#${detail.id} · ${detail.title}` : ""}
      subtitle={
        detail && (
          <span className="flex flex-wrap items-center gap-2">
            <StatusBadge status={detail.status} tone="admin" />
            <Badge variant={detail.extraction_status === "done" ? "success" : detail.extraction_status === "review" ? "purple" : detail.extraction_status === "failed" ? "danger" : "warning"}>
              extração: {EXTRACTION_LABELS[detail.extraction_status] ?? detail.extraction_status}
            </Badge>
            <span>{detail.source_name}</span>
            <span>· ext. {detail.external_id}</span>
          </span>
        )
      }
      footer={
        detail && (
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" size="sm" onClick={() => action("renorm")} loading={busy === "renorm"} disabled={!!busy} title="Reextrair agora via LLM">
                <Sparkles size={14} /> Reextrair
              </Button>
              <Button variant="secondary" size="sm" onClick={() => action("publish")} loading={busy === "publish"} disabled={!!busy || detail.status === "published"} title="Forçar publicação">
                <Eye size={14} /> Publicar
              </Button>
              <Button variant="secondary" size="sm" onClick={() => action("hide")} loading={busy === "hide"} disabled={!!busy || detail.status === "withdrawn"} title="Ocultar (withdrawn)">
                <EyeOff size={14} /> Ocultar
              </Button>
            </div>
            <Button size="sm" onClick={save} loading={busy === "save"} disabled={!!busy}>
              <Save size={14} /> Salvar alterações
            </Button>
          </div>
        )
      }
    >
      {!detail || !base ? null : (
        <div className="space-y-6">
          {/* Cabeçalho visual */}
          <div className="flex gap-4">
            <SafeImage src={detail.image_url} alt="" className="h-24 w-32 shrink-0 rounded-lg object-cover" fallbackClassName="h-24 w-32 rounded-lg" />
            <div className="min-w-0 flex-1 text-sm">
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-gray-600">
                <span>Preço: <strong className="text-gray-900">{detail.price ? formatBRL(detail.price) : "—"}</strong> {detail.price_kind && <span className="text-gray-400">({PRICE_KIND_LABELS[detail.price_kind] ?? detail.price_kind})</span>}</span>
                <span>2ª praça: <strong className="text-gray-900">{detail.price_second ? formatBRL(detail.price_second) : "—"}</strong></span>
                <span>Pregão: <strong className="text-gray-900">{detail.next_session_at ? formatDateTime(detail.next_session_at) : "—"}</strong></span>
                <span>Local: <strong className="text-gray-900">{[detail.city, detail.state].filter(Boolean).join(" / ") || "—"}</strong></span>
                <span>1ª coleta: {formatDateTime(detail.first_seen_at)}</span>
                <span>Última coleta: {formatDateTime(detail.last_seen_at)}</span>
                <span>Misses: {detail.misses}</span>
                <span>Tentativas: {detail.extraction_attempts}{detail.extraction_model ? ` · ${detail.extraction_model}` : ""}{detail.extraction_version ? ` · v${detail.extraction_version}` : ""}</span>
                {detail.status_hint && <span className="col-span-2">Dica de status da fonte: <em>{detail.status_hint}</em></span>}
              </div>
              <div className="mt-2 flex flex-wrap gap-3 text-xs">
                <a href={detail.official_url} target="_blank" rel="noopener" className="inline-flex items-center gap-1 text-primary-600 hover:underline">
                  Fonte oficial <ExternalLink size={12} />
                </a>
                {(detail.status === "published" || detail.status === "auction_soon" || detail.status === "closed") && (
                  <a href={`/lote/${detail.id}`} target="_blank" rel="noopener" className="inline-flex items-center gap-1 text-primary-600 hover:underline">
                    Ver no portal <ExternalLink size={12} />
                  </a>
                )}
              </div>
            </div>
          </div>

          {detail.extraction_error && (
            <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-800">
              <AlertCircle size={14} className="mt-0.5 shrink-0" />
              <div>
                <strong>Erro de extração:</strong>
                <pre className="mt-1 whitespace-pre-wrap font-sans">{detail.extraction_error}</pre>
              </div>
            </div>
          )}

          {/* Campos base */}
          <section>
            <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500">Dados principais</h3>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <Field label="Título">
                  <input className="admin-input" value={base.title} onChange={(e) => setBase({ ...base, title: e.target.value })} />
                </Field>
              </div>
              <Field label="Categoria" hint="Define os campos da ficha abaixo">
                <select className="admin-input" value={base.category_id} onChange={(e) => setBase({ ...base, category_id: e.target.value })}>
                  <option value="">— sem categoria —</option>
                  {categories.map((x) => (
                    <option key={x.category.id} value={x.category.id}>{"— ".repeat(x.depth)}{x.category.name}</option>
                  ))}
                </select>
              </Field>
              <Field label="Status">
                <select className="admin-input" value={base.status} onChange={(e) => setBase({ ...base, status: e.target.value })}>
                  {Object.entries(STATUS_LABELS_ADMIN).map(([v, l]) => (
                    <option key={v} value={v}>{l}</option>
                  ))}
                </select>
              </Field>
              <Field label="Marca">
                <input className="admin-input" value={base.brand} onChange={(e) => setBase({ ...base, brand: e.target.value })} />
              </Field>
              <Field label="Modelo">
                <input className="admin-input" value={base.model} onChange={(e) => setBase({ ...base, model: e.target.value })} />
              </Field>
              <Field label="Ano modelo">
                <input className="admin-input" inputMode="numeric" value={base.year_model} onChange={(e) => setBase({ ...base, year_model: e.target.value })} />
              </Field>
              <Field label="KM">
                <input className="admin-input" inputMode="numeric" value={base.km} onChange={(e) => setBase({ ...base, km: e.target.value })} />
              </Field>
              <Field label="Condição">
                <select className="admin-input" value={base.condition} onChange={(e) => setBase({ ...base, condition: e.target.value })}>
                  <option value="">—</option>
                  {Object.entries(CONDITION_LABELS).map(([v, l]) => (
                    <option key={v} value={v}>{l}</option>
                  ))}
                </select>
              </Field>
              <div className="sm:col-span-2">
                <Field label="Descrição">
                  <textarea className="admin-input" rows={4} value={base.description} onChange={(e) => setBase({ ...base, description: e.target.value })} />
                </Field>
              </div>
            </div>
          </section>

          {/* Atributos dinâmicos */}
          <section>
            <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500">
              Ficha da categoria {fields && fields.length > 0 && <span className="text-gray-400">({fields.length} campos)</span>}
            </h3>
            {fields === null ? (
              <div className="grid gap-3 sm:grid-cols-2">
                {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
              </div>
            ) : fields.length === 0 ? (
              <p className="text-sm text-gray-400">{categoryId ? "Categoria sem campos definidos." : "Selecione uma categoria para editar a ficha."}</p>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {fields.map((f) => (
                  <Field
                    key={f.id}
                    label={`${f.label}${f.unit ? ` (${f.unit})` : ""}${f.required ? " *" : ""}`}
                    hint={f.inherited_from ? `herdado de ${f.inherited_from}` : f.description ?? undefined}
                  >
                    <AttributeInput field={f} value={attrs[f.key] ?? ""} onChange={(v) => setAttrs((a) => ({ ...a, [f.key]: v }))} />
                  </Field>
                ))}
              </div>
            )}
            {extraAttrKeys.length > 0 && (
              <details className="mt-3 rounded-lg border border-dashed border-gray-300 p-3">
                <summary className="cursor-pointer text-xs text-gray-500">Atributos fora do schema ({extraAttrKeys.length})</summary>
                <div className="mt-2 grid gap-3 sm:grid-cols-2">
                  {extraAttrKeys.map((k) => (
                    <Field key={k} label={k}>
                      <input className="admin-input font-mono text-xs" value={attrs[k]} onChange={(e) => setAttrs((a) => ({ ...a, [k]: e.target.value }))} />
                    </Field>
                  ))}
                </div>
              </details>
            )}
          </section>

          {/* Imagens */}
          {detail.images?.length > 0 && (
            <section>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500">Imagens ({detail.images.length})</h3>
              <div className="flex flex-wrap gap-2">
                {detail.images.slice(0, 12).map((src, i) => (
                  <a key={`${src}-${i}`} href={src} target="_blank" rel="noopener">
                    <SafeImage src={src} alt="" className="h-16 w-20 rounded object-cover" fallbackClassName="h-16 w-20 rounded" iconSize={16} />
                  </a>
                ))}
              </div>
            </section>
          )}

          <p className="flex items-center gap-1 text-[11px] text-gray-400">
            <RefreshCw size={11} /> Salvar mescla os atributos e revalida o item; itens em revisão passam a “done”.
          </p>
        </div>
      )}
    </Drawer>
  );
}
