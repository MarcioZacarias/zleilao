import { useEffect, useMemo, useState } from "react";
import { Plus, Pencil, Trash2, X, Check, ChevronRight, ChevronDown, FolderTree, ListPlus, ArrowUp, Link2 } from "lucide-react";
import { toast } from "sonner";
import { categoriesApi, flattenCategories, findCategory } from "../../services/categories";
import type { Category, CategoryField, CategoryFieldInput, CategoryInput } from "../../services/types";
import { errorMessage } from "../../services/api";
import { Card, CardContent, CardHeader } from "../../components/ui/Card";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Toggle } from "../../components/ui/Toggle";
import { Modal } from "../../components/ui/Modal";
import { Table, Thead, Th, Tr, Td } from "../../components/ui/Table";
import { Skeleton, TableSkeleton } from "../../components/ui/Skeleton";
import { EmptyState } from "../../components/ui/EmptyState";
import { FIELD_TYPE_LABELS } from "../../lib/labels";
import { formatInt, slugify } from "../../lib/format";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";

/* ───────── Formulário de categoria ───────── */

interface CatForm {
  name: string;
  slug: string;
  parent_id: string;
  is_active: boolean;
  sort_order: string;
  keywords: string;
  llm_hint: string;
}
const EMPTY_CAT: CatForm = { name: "", slug: "", parent_id: "", is_active: true, sort_order: "0", keywords: "", llm_hint: "" };

function catToForm(c: Category): CatForm {
  return {
    name: c.name,
    slug: c.slug,
    parent_id: c.parent_id ? String(c.parent_id) : "",
    is_active: c.is_active,
    sort_order: String(c.sort_order),
    keywords: (c.keywords ?? []).join(", "),
    llm_hint: c.llm_hint ?? "",
  };
}

function formToCat(f: CatForm): CategoryInput {
  return {
    name: f.name.trim(),
    slug: f.slug.trim(),
    parent_id: f.parent_id ? Number(f.parent_id) : null,
    is_active: f.is_active,
    sort_order: parseInt(f.sort_order) || 0,
    keywords: f.keywords.split(",").map((k) => k.trim()).filter(Boolean),
    llm_hint: f.llm_hint.trim() || null,
  };
}

/* ───────── Formulário de campo ───────── */

interface FieldForm {
  key: string;
  label: string;
  field_type: string;
  unit: string;
  required: boolean;
  options: string;
  show_in_card: boolean;
  filterable: boolean;
  sort_order: string;
  description: string;
}
const EMPTY_FIELD: FieldForm = { key: "", label: "", field_type: "string", unit: "", required: false, options: "", show_in_card: false, filterable: false, sort_order: "0", description: "" };

function fieldToForm(f: CategoryField): FieldForm {
  return {
    key: f.key,
    label: f.label,
    field_type: f.field_type,
    unit: f.unit ?? "",
    required: f.required,
    options: (f.options ?? []).join(", "),
    show_in_card: f.show_in_card,
    filterable: f.filterable,
    sort_order: String(f.sort_order),
    description: f.description ?? "",
  };
}

function formToField(f: FieldForm): CategoryFieldInput {
  return {
    key: f.key.trim(),
    label: f.label.trim(),
    field_type: f.field_type,
    unit: f.unit.trim() || null,
    required: f.required,
    options: f.field_type === "enum" ? f.options.split(",").map((o) => o.trim()).filter(Boolean) : null,
    show_in_card: f.show_in_card,
    filterable: f.filterable,
    sort_order: parseInt(f.sort_order) || 0,
    description: f.description.trim() || null,
  };
}

/* ───────── Árvore ───────── */

function TreeNode({
  node,
  depth,
  selected,
  onSelect,
  expanded,
  toggle,
}: {
  node: Category;
  depth: number;
  selected: number | null;
  onSelect: (c: Category) => void;
  expanded: Set<number>;
  toggle: (id: number) => void;
}) {
  const hasChildren = node.children?.length > 0;
  const open = expanded.has(node.id);
  return (
    <li>
      <div
        className={`flex items-center gap-1 rounded-lg px-2 py-1.5 text-sm transition-colors ${
          selected === node.id ? "bg-primary-50 text-primary-700" : "hover:bg-gray-50 text-gray-800"
        }`}
        style={{ paddingLeft: 8 + depth * 16 }}
      >
        <button
          type="button"
          onClick={() => hasChildren && toggle(node.id)}
          className={`rounded p-0.5 text-gray-400 ${hasChildren ? "hover:bg-gray-200" : "opacity-0"}`}
          aria-label={open ? "Recolher" : "Expandir"}
        >
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
        <button type="button" onClick={() => onSelect(node)} className="flex min-w-0 flex-1 items-center justify-between gap-2 text-left">
          <span className={`truncate ${!node.is_active ? "text-gray-400 line-through" : ""}`}>{node.name}</span>
          <span className="shrink-0 text-xs text-gray-400 tabular-nums">{formatInt(node.items_count)}</span>
        </button>
      </div>
      {hasChildren && open && (
        <ul>
          {node.children.map((c) => (
            <TreeNode key={c.id} node={c} depth={depth + 1} selected={selected} onSelect={onSelect} expanded={expanded} toggle={toggle} />
          ))}
        </ul>
      )}
    </li>
  );
}

/* ───────── Página ───────── */

export default function Categories() {
  useDocumentTitle("Categorias");
  const [tree, setTree] = useState<Category[] | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [fields, setFields] = useState<CategoryField[] | null>(null);

  const [catModal, setCatModal] = useState<{ mode: "new" | "edit"; form: CatForm; id?: number } | null>(null);
  const [fieldModal, setFieldModal] = useState<{ mode: "new" | "edit"; form: FieldForm; id?: number } | null>(null);
  const [saving, setSaving] = useState(false);

  const load = () =>
    categoriesApi
      .tree()
      .then((t) => {
        setTree(t);
        if (expanded.size === 0) setExpanded(new Set(t.map((c) => c.id)));
      })
      .catch((e) => toast.error(errorMessage(e, "Erro ao carregar categorias")));

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selected = useMemo(() => (tree && selectedId ? findCategory(tree, selectedId) : null), [tree, selectedId]);
  const flat = useMemo(() => (tree ? flattenCategories(tree) : []), [tree]);

  const loadFields = (id: number) => {
    setFields(null);
    categoriesApi
      .fields(id)
      .then(setFields)
      .catch((e) => toast.error(errorMessage(e, "Erro ao carregar campos")));
  };

  useEffect(() => {
    if (selectedId) loadFields(selectedId);
    else setFields(null);
  }, [selectedId]);

  const toggle = (id: number) =>
    setExpanded((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  /* categorias */
  const saveCat = async () => {
    if (!catModal) return;
    const body = formToCat(catModal.form);
    if (!body.name || !body.slug) {
      toast.error("Nome e slug são obrigatórios");
      return;
    }
    setSaving(true);
    try {
      if (catModal.mode === "edit" && catModal.id) {
        await categoriesApi.update(catModal.id, body);
        toast.success("Categoria atualizada");
      } else {
        const created = await categoriesApi.create(body);
        toast.success("Categoria criada");
        setSelectedId(created.id);
        if (body.parent_id) setExpanded((s) => new Set(s).add(body.parent_id!));
      }
      setCatModal(null);
      await load();
    } catch (e) {
      toast.error(errorMessage(e, "Erro ao salvar categoria"));
    }
    setSaving(false);
  };

  const removeCat = async (c: Category) => {
    if (!confirm(`Remover a categoria "${c.name}"? Subcategorias e campos próprios serão afetados.`)) return;
    try {
      await categoriesApi.remove(c.id);
      toast.success("Categoria removida");
      setSelectedId(null);
      load();
    } catch (e) {
      toast.error(errorMessage(e, "Não foi possível remover"));
    }
  };

  const toggleActive = async (c: Category, v: boolean) => {
    try {
      await categoriesApi.update(c.id, { is_active: v });
      toast.success(v ? "Categoria ativada" : "Categoria desativada");
      load();
    } catch (e) {
      toast.error(errorMessage(e, "Erro ao atualizar"));
    }
  };

  /* campos */
  const saveField = async () => {
    if (!fieldModal || !selectedId) return;
    const body = formToField(fieldModal.form);
    if (!body.key || !body.label) {
      toast.error("Chave e rótulo são obrigatórios");
      return;
    }
    if (body.field_type === "enum" && (!body.options || body.options.length === 0)) {
      toast.error("Campos do tipo Lista precisam de opções");
      return;
    }
    setSaving(true);
    try {
      if (fieldModal.mode === "edit" && fieldModal.id) {
        await categoriesApi.updateField(fieldModal.id, body);
        toast.success("Campo atualizado");
      } else {
        await categoriesApi.createField(selectedId, body);
        toast.success("Campo criado");
      }
      setFieldModal(null);
      loadFields(selectedId);
    } catch (e) {
      toast.error(errorMessage(e, "Erro ao salvar campo"));
    }
    setSaving(false);
  };

  const removeField = async (f: CategoryField) => {
    if (!confirm(`Remover o campo "${f.label}" (${f.key})?`)) return;
    try {
      await categoriesApi.removeField(f.id);
      toast.success("Campo removido");
      if (selectedId) loadFields(selectedId);
    } catch (e) {
      toast.error(errorMessage(e, "Erro ao remover campo"));
    }
  };

  const quickToggleField = async (f: CategoryField, patch: Partial<CategoryFieldInput>) => {
    setFields((prev) => prev?.map((x) => (x.id === f.id ? { ...x, ...patch } : x)) ?? prev);
    try {
      await categoriesApi.updateField(f.id, patch);
    } catch (e) {
      toast.error(errorMessage(e, "Erro ao atualizar campo"));
      if (selectedId) loadFields(selectedId);
    }
  };

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Categorias</h1>
          <p className="text-sm text-gray-500">Árvore de categorias e campos dinâmicos da ficha (RN-002)</p>
        </div>
        <Button size="sm" onClick={() => setCatModal({ mode: "new", form: { ...EMPTY_CAT, parent_id: selectedId ? String(selectedId) : "" } })}>
          <Plus size={16} /> Nova categoria
        </Button>
      </div>

      <div className="grid gap-4 lg:grid-cols-[320px_1fr] md:gap-6">
        {/* Árvore */}
        <Card className="self-start">
          <CardHeader>
            <h2 className="flex items-center gap-2 font-semibold text-gray-900"><FolderTree size={16} /> Árvore</h2>
          </CardHeader>
          <CardContent className="p-2">
            {tree === null ? (
              <div className="space-y-2 p-2">
                {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-6 w-full" />)}
              </div>
            ) : tree.length === 0 ? (
              <EmptyState compact title="Nenhuma categoria" description="Crie a primeira categoria (ex.: Veículos)." />
            ) : (
              <ul>
                {tree.map((c) => (
                  <TreeNode key={c.id} node={c} depth={0} selected={selectedId} onSelect={(n) => setSelectedId(n.id)} expanded={expanded} toggle={toggle} />
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        {/* Detalhe */}
        <div className="space-y-4 md:space-y-6">
          {!selected ? (
            <Card>
              <EmptyState icon={FolderTree} title="Selecione uma categoria" description="Clique em um item da árvore para ver e editar seus campos." />
            </Card>
          ) : (
            <>
              <Card>
                <CardHeader className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="text-lg font-semibold text-gray-900">{selected.name}</h2>
                      <Badge variant={selected.is_active ? "success" : "default"}>{selected.is_active ? "Ativa" : "Inativa"}</Badge>
                      <span className="font-mono text-xs text-gray-400">{selected.path || selected.slug}</span>
                    </div>
                    <p className="mt-1 text-xs text-gray-500">
                      {formatInt(selected.items_count)} itens · ordem {selected.sort_order}
                      {selected.keywords?.length ? ` · palavras-chave: ${selected.keywords.join(", ")}` : ""}
                    </p>
                    {selected.llm_hint && <p className="mt-1 text-xs italic text-gray-500">Dica LLM: {selected.llm_hint}</p>}
                  </div>
                  <div className="flex items-center gap-2">
                    <Toggle size="sm" checked={selected.is_active} onChange={(v) => toggleActive(selected, v)} label="Ativa" />
                    <Button variant="secondary" size="sm" onClick={() => setCatModal({ mode: "edit", id: selected.id, form: catToForm(selected) })}>
                      <Pencil size={14} /> Editar
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => removeCat(selected)} title="Remover">
                      <Trash2 size={14} className="text-red-500" />
                    </Button>
                  </div>
                </CardHeader>
              </Card>

              <Card>
                <CardHeader className="flex items-center justify-between">
                  <div>
                    <h3 className="font-semibold text-gray-900">Campos da ficha</h3>
                    <p className="text-xs text-gray-500">Campos herdados da categoria-mãe aparecem em cinza e são editados na origem.</p>
                  </div>
                  <Button size="sm" onClick={() => setFieldModal({ mode: "new", form: { ...EMPTY_FIELD, sort_order: String((fields?.length ?? 0) * 10) } })}>
                    <ListPlus size={14} /> Novo campo
                  </Button>
                </CardHeader>
                <CardContent className="p-0">
                  {fields === null ? (
                    <TableSkeleton rows={5} cols={6} />
                  ) : fields.length === 0 ? (
                    <EmptyState compact title="Nenhum campo" description="Adicione campos como Placa, KM, Combustível…" />
                  ) : (
                    <Table minWidth={860}>
                      <Thead>
                        <tr>
                          <Th>Ordem</Th>
                          <Th>Chave</Th>
                          <Th>Rótulo</Th>
                          <Th>Tipo</Th>
                          <Th>Unid.</Th>
                          <Th>Obrig.</Th>
                          <Th>Card</Th>
                          <Th>Filtro</Th>
                          <Th>Origem</Th>
                          <Th>Ações</Th>
                        </tr>
                      </Thead>
                      <tbody>
                        {[...fields]
                          .sort((a, b) => a.sort_order - b.sort_order)
                          .map((f) => {
                            const inherited = !!f.inherited_from;
                            return (
                              <Tr key={f.id} className={inherited ? "bg-gray-50/60 text-gray-400" : ""}>
                                <Td className={inherited ? "text-gray-400" : ""}>{f.sort_order}</Td>
                                <Td className={`font-mono text-xs ${inherited ? "text-gray-400" : ""}`}>{f.key}</Td>
                                <Td className={inherited ? "text-gray-400" : "text-gray-900"}>
                                  {f.label}
                                  {f.description && <div className="text-xs text-gray-400">{f.description}</div>}
                                  {f.field_type === "enum" && f.options?.length ? (
                                    <div className="mt-0.5 text-[11px] text-gray-400">{f.options.join(" · ")}</div>
                                  ) : null}
                                </Td>
                                <Td><Badge variant={inherited ? "default" : "info"}>{FIELD_TYPE_LABELS[f.field_type] ?? f.field_type}</Badge></Td>
                                <Td className={inherited ? "text-gray-400" : ""}>{f.unit ?? "—"}</Td>
                                <Td>{inherited ? (f.required ? "sim" : "—") : <Toggle size="sm" checked={f.required} onChange={(v) => quickToggleField(f, { required: v })} />}</Td>
                                <Td>{inherited ? (f.show_in_card ? "sim" : "—") : <Toggle size="sm" checked={f.show_in_card} onChange={(v) => quickToggleField(f, { show_in_card: v })} />}</Td>
                                <Td>{inherited ? (f.filterable ? "sim" : "—") : <Toggle size="sm" checked={f.filterable} onChange={(v) => quickToggleField(f, { filterable: v })} />}</Td>
                                <Td>
                                  {inherited ? (
                                    <button
                                      className="inline-flex items-center gap-1 text-xs text-gray-500 hover:text-primary-600"
                                      onClick={() => {
                                        const parent = flat.find((x) => x.category.slug === f.inherited_from)?.category;
                                        if (parent) setSelectedId(parent.id);
                                      }}
                                      title="Ir para a categoria de origem"
                                    >
                                      <ArrowUp size={12} /> herdado de {f.inherited_from}
                                    </button>
                                  ) : (
                                    <span className="inline-flex items-center gap-1 text-xs text-gray-500"><Link2 size={12} /> próprio</span>
                                  )}
                                </Td>
                                <Td>
                                  {!inherited && (
                                    <div className="flex gap-1">
                                      <Button variant="ghost" size="sm" onClick={() => setFieldModal({ mode: "edit", id: f.id, form: fieldToForm(f) })} title="Editar">
                                        <Pencil size={14} />
                                      </Button>
                                      <Button variant="ghost" size="sm" onClick={() => removeField(f)} title="Remover">
                                        <Trash2 size={14} className="text-red-500" />
                                      </Button>
                                    </div>
                                  )}
                                </Td>
                              </Tr>
                            );
                          })}
                      </tbody>
                    </Table>
                  )}
                </CardContent>
              </Card>
            </>
          )}
        </div>
      </div>

      {/* Modal categoria */}
      <Modal
        open={!!catModal}
        onClose={() => setCatModal(null)}
        title={catModal?.mode === "edit" ? "Editar categoria" : "Nova categoria"}
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="secondary" size="sm" onClick={() => setCatModal(null)}><X size={14} /> Cancelar</Button>
            <Button size="sm" onClick={saveCat} loading={saving}><Check size={14} /> Salvar</Button>
          </div>
        }
      >
        {catModal && (
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="admin-label">Nome</label>
              <input
                className="admin-input"
                value={catModal.form.name}
                onChange={(e) =>
                  setCatModal({
                    ...catModal,
                    form: { ...catModal.form, name: e.target.value, slug: catModal.mode === "new" ? slugify(e.target.value) : catModal.form.slug },
                  })
                }
                autoFocus
              />
            </div>
            <div>
              <label className="admin-label">Slug</label>
              <input className="admin-input font-mono" value={catModal.form.slug} onChange={(e) => setCatModal({ ...catModal, form: { ...catModal.form, slug: e.target.value } })} />
            </div>
            <div>
              <label className="admin-label">Categoria-mãe</label>
              <select className="admin-input" value={catModal.form.parent_id} onChange={(e) => setCatModal({ ...catModal, form: { ...catModal.form, parent_id: e.target.value } })}>
                <option value="">(raiz)</option>
                {flat
                  .filter((x) => x.category.id !== catModal.id)
                  .map((x) => (
                    <option key={x.category.id} value={x.category.id}>
                      {"— ".repeat(x.depth)}{x.category.name}
                    </option>
                  ))}
              </select>
            </div>
            <div>
              <label className="admin-label">Ordem</label>
              <input type="number" className="admin-input" value={catModal.form.sort_order} onChange={(e) => setCatModal({ ...catModal, form: { ...catModal.form, sort_order: e.target.value } })} />
            </div>
            <div className="sm:col-span-2">
              <label className="admin-label">Palavras-chave (separadas por vírgula)</label>
              <input className="admin-input" value={catModal.form.keywords} onChange={(e) => setCatModal({ ...catModal, form: { ...catModal.form, keywords: e.target.value } })} placeholder="caminhão, cavalo mecânico, truck" />
              <p className="mt-1 text-xs text-gray-500">Usadas para classificar automaticamente os lotes coletados.</p>
            </div>
            <div className="sm:col-span-2">
              <label className="admin-label">Dica para o LLM (opcional)</label>
              <textarea className="admin-input" rows={3} value={catModal.form.llm_hint} onChange={(e) => setCatModal({ ...catModal, form: { ...catModal.form, llm_hint: e.target.value } })} placeholder="Instruções extras para a extração dos campos desta categoria" />
            </div>
            <div className="sm:col-span-2">
              <Toggle checked={catModal.form.is_active} onChange={(v) => setCatModal({ ...catModal, form: { ...catModal.form, is_active: v } })} label="Categoria ativa (visível no portal)" />
            </div>
          </div>
        )}
      </Modal>

      {/* Modal campo */}
      <Modal
        open={!!fieldModal}
        onClose={() => setFieldModal(null)}
        title={fieldModal?.mode === "edit" ? "Editar campo" : `Novo campo em ${selected?.name ?? ""}`}
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="secondary" size="sm" onClick={() => setFieldModal(null)}><X size={14} /> Cancelar</Button>
            <Button size="sm" onClick={saveField} loading={saving}><Check size={14} /> Salvar</Button>
          </div>
        }
      >
        {fieldModal && (
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="admin-label">Rótulo</label>
              <input
                className="admin-input"
                value={fieldModal.form.label}
                onChange={(e) =>
                  setFieldModal({
                    ...fieldModal,
                    form: { ...fieldModal.form, label: e.target.value, key: fieldModal.mode === "new" ? slugify(e.target.value).replace(/-/g, "_") : fieldModal.form.key },
                  })
                }
                autoFocus
                placeholder="Combustível"
              />
            </div>
            <div>
              <label className="admin-label">Chave (attributes)</label>
              <input className="admin-input font-mono" value={fieldModal.form.key} onChange={(e) => setFieldModal({ ...fieldModal, form: { ...fieldModal.form, key: e.target.value } })} placeholder="combustivel" />
            </div>
            <div>
              <label className="admin-label">Tipo</label>
              <select className="admin-input" value={fieldModal.form.field_type} onChange={(e) => setFieldModal({ ...fieldModal, form: { ...fieldModal.form, field_type: e.target.value } })}>
                {Object.entries(FIELD_TYPE_LABELS).map(([v, l]) => (
                  <option key={v} value={v}>{l}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="admin-label">Unidade</label>
              <input className="admin-input" value={fieldModal.form.unit} onChange={(e) => setFieldModal({ ...fieldModal, form: { ...fieldModal.form, unit: e.target.value } })} placeholder="km, cc, BRL…" />
            </div>
            {fieldModal.form.field_type === "enum" && (
              <div className="sm:col-span-2">
                <label className="admin-label">Opções (separadas por vírgula)</label>
                <input className="admin-input" value={fieldModal.form.options} onChange={(e) => setFieldModal({ ...fieldModal, form: { ...fieldModal.form, options: e.target.value } })} placeholder="flex, gasolina, diesel, eletrico, nao_informado" />
              </div>
            )}
            <div>
              <label className="admin-label">Ordem</label>
              <input type="number" className="admin-input" value={fieldModal.form.sort_order} onChange={(e) => setFieldModal({ ...fieldModal, form: { ...fieldModal.form, sort_order: e.target.value } })} />
            </div>
            <div>
              <label className="admin-label">Descrição</label>
              <input className="admin-input" value={fieldModal.form.description} onChange={(e) => setFieldModal({ ...fieldModal, form: { ...fieldModal.form, description: e.target.value } })} />
            </div>
            <div className="flex flex-wrap gap-5 sm:col-span-2">
              <Toggle checked={fieldModal.form.required} onChange={(v) => setFieldModal({ ...fieldModal, form: { ...fieldModal.form, required: v } })} label="Obrigatório" />
              <Toggle checked={fieldModal.form.show_in_card} onChange={(v) => setFieldModal({ ...fieldModal, form: { ...fieldModal.form, show_in_card: v } })} label="Mostrar no card" />
              <Toggle checked={fieldModal.form.filterable} onChange={(v) => setFieldModal({ ...fieldModal, form: { ...fieldModal.form, filterable: v } })} label="Filtrável" />
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
