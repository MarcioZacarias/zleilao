import { useEffect, useMemo, useState } from "react";
import { Plus, Pencil, Trash2, X, Check, Play, FlaskConical, RotateCcw, ShieldCheck, ShieldOff, Loader2, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { sourcesApi } from "../../services/sources";
import type { ParserInfo, Source, SourceInput, SourceTestResult } from "../../services/types";
import { errorMessage } from "../../services/api";
import { Card, CardContent, CardHeader } from "../../components/ui/Card";
import { Badge, BadgeVariant } from "../../components/ui/Badge";
import { Table, Thead, Th, Tr, Td } from "../../components/ui/Table";
import { Button } from "../../components/ui/Button";
import { Toggle } from "../../components/ui/Toggle";
import { JsonEditor, parseJsonSafe } from "../../components/ui/JsonEditor";
import { Modal } from "../../components/ui/Modal";
import { TableSkeleton } from "../../components/ui/Skeleton";
import { EmptyState } from "../../components/ui/EmptyState";
import { formatDateTime, formatInt, formatRelative, formatDuration, formatMinutes, slugify } from "../../lib/format";
import { HEALTH_LABELS, ROBOTS_LABELS, SOURCE_KIND_LABELS } from "../../lib/labels";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";

interface FormState {
  name: string;
  slug: string;
  kind: "auction" | "marketplace";
  parser_type: string;
  base_url: string;
  config: string;
  is_active: boolean;
  dispatch_enabled: boolean;
  scraping_allowed: boolean;
  scrape_frequency: string;
  priority_weight: string;
}

const EMPTY: FormState = {
  name: "",
  slug: "",
  kind: "auction",
  parser_type: "",
  base_url: "",
  config: "",
  is_active: true,
  dispatch_enabled: true,
  scraping_allowed: true,
  scrape_frequency: "240",
  priority_weight: "1",
};

function healthVariant(h: string): BadgeVariant {
  return h === "ok" ? "success" : h === "suspended" ? "danger" : "default";
}

export default function Sources() {
  useDocumentTitle("Fontes");
  const [sources, setSources] = useState<Source[] | null>(null);
  const [parsers, setParsers] = useState<ParserInfo[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Source | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY);
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState<Record<number, "run" | "test" | "reactivate" | undefined>>({});
  const [testResult, setTestResult] = useState<{ source: Source; result: SourceTestResult } | null>(null);
  const [slugTouched, setSlugTouched] = useState(false);

  const load = () =>
    sourcesApi
      .list()
      .then(setSources)
      .catch((e) => toast.error(errorMessage(e, "Erro ao carregar fontes")));

  useEffect(() => {
    load();
    sourcesApi
      .parsers()
      .then(setParsers)
      .catch(() => toast.error("Não foi possível carregar a lista de parsers"));
  }, []);

  const parserByKey = useMemo(() => Object.fromEntries(parsers.map((p) => [p.key, p])), [parsers]);

  const openNew = () => {
    setEditing(null);
    setSlugTouched(false);
    const first = parsers[0];
    setForm({
      ...EMPTY,
      parser_type: first?.key ?? "",
      config: first ? JSON.stringify(first.default_config ?? {}, null, 2) : "",
    });
    setShowForm(true);
  };

  const openEdit = (s: Source) => {
    setEditing(s);
    setSlugTouched(true);
    setForm({
      name: s.name,
      slug: s.slug,
      kind: s.kind,
      parser_type: s.parser_type,
      base_url: s.base_url ?? "",
      config: s.config ? JSON.stringify(s.config, null, 2) : "",
      is_active: s.is_active,
      dispatch_enabled: s.dispatch_enabled,
      scraping_allowed: s.scraping_allowed,
      scrape_frequency: String(s.scrape_frequency),
      priority_weight: String(s.priority_weight),
    });
    setShowForm(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const onParserChange = (key: string) => {
    const p = parserByKey[key];
    setForm((f) => ({
      ...f,
      parser_type: key,
      // Pré-preenche o config só se estiver vazio ou igual ao default anterior.
      config:
        !f.config.trim() || f.config === JSON.stringify(parserByKey[f.parser_type]?.default_config ?? {}, null, 2)
          ? JSON.stringify(p?.default_config ?? {}, null, 2)
          : f.config,
    }));
  };

  const restoreDefault = () => {
    const p = parserByKey[form.parser_type];
    setForm((f) => ({ ...f, config: JSON.stringify(p?.default_config ?? {}, null, 2) }));
  };

  const save = async () => {
    if (!form.name.trim() || !form.slug.trim() || !form.parser_type) {
      toast.error("Nome, slug e parser são obrigatórios");
      return;
    }
    let config: Record<string, unknown> | null = null;
    if (form.config.trim()) {
      const r = parseJsonSafe(form.config);
      if (!r.ok || typeof r.value !== "object" || r.value === null || Array.isArray(r.value)) {
        toast.error("JSON de configuração inválido");
        return;
      }
      config = r.value as Record<string, unknown>;
    }
    const payload: SourceInput = {
      name: form.name.trim(),
      slug: form.slug.trim(),
      kind: form.kind,
      parser_type: form.parser_type,
      base_url: form.base_url.trim() || null,
      config,
      is_active: form.is_active,
      dispatch_enabled: form.dispatch_enabled,
      scraping_allowed: form.scraping_allowed,
      scrape_frequency: Math.max(1, parseInt(form.scrape_frequency) || 240),
      priority_weight: Math.max(0, parseInt(form.priority_weight) || 0),
    };
    setSaving(true);
    try {
      if (editing) {
        await sourcesApi.update(editing.id, payload);
        toast.success("Fonte atualizada");
      } else {
        await sourcesApi.create(payload);
        toast.success("Fonte criada");
      }
      setShowForm(false);
      load();
    } catch (e) {
      toast.error(errorMessage(e, "Erro ao salvar"));
    }
    setSaving(false);
  };

  const remove = async (s: Source) => {
    if (!confirm(`Remover a fonte "${s.name}"?`)) return;
    try {
      await sourcesApi.remove(s.id);
      toast.success("Fonte removida");
      load();
    } catch (e) {
      toast.error(errorMessage(e, "Não foi possível remover (a fonte possui itens?)"));
    }
  };

  const toggleField = async (s: Source, field: "is_active" | "dispatch_enabled" | "scraping_allowed", value: boolean) => {
    setSources((prev) => prev?.map((x) => (x.id === s.id ? { ...x, [field]: value } : x)) ?? prev);
    try {
      await sourcesApi.update(s.id, { [field]: value });
      const labels = { is_active: "Coleta", dispatch_enabled: "Publicação", scraping_allowed: "Permissão de scraping" };
      toast.success(`${labels[field]} ${value ? "ativada" : "desativada"}`);
    } catch (e) {
      toast.error(errorMessage(e, "Erro ao atualizar"));
      load();
    }
  };

  const setBusyFor = (id: number, what: "run" | "test" | "reactivate" | undefined) =>
    setBusy((b) => ({ ...b, [id]: what }));

  const runNow = async (s: Source) => {
    setBusyFor(s.id, "run");
    try {
      await sourcesApi.run(s.id);
      toast.success(`Coleta de "${s.name}" iniciada em background`);
      window.setTimeout(load, 8000);
    } catch (e) {
      toast.error(errorMessage(e, "Erro ao iniciar coleta"));
    }
    setBusyFor(s.id, undefined);
  };

  const testParser = async (s: Source) => {
    setBusyFor(s.id, "test");
    try {
      const result = await sourcesApi.test(s.id);
      setTestResult({ source: s, result });
      if (result.ok) toast.success(`Parser OK: ${result.items_found} itens em ${formatDuration(result.duration_ms)}`);
      else toast.error("Parser falhou — veja os detalhes");
    } catch (e) {
      toast.error(errorMessage(e, "Erro ao testar parser"));
    }
    setBusyFor(s.id, undefined);
  };

  const reactivate = async (s: Source) => {
    setBusyFor(s.id, "reactivate");
    try {
      await sourcesApi.reactivate(s.id);
      toast.success(`Fonte "${s.name}" reativada`);
      load();
    } catch (e) {
      toast.error(errorMessage(e, "Erro ao reativar"));
    }
    setBusyFor(s.id, undefined);
  };

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Fontes</h1>
          <p className="text-sm text-gray-500">Leiloeiros e portais monitorados pelos scrapers</p>
        </div>
        <Button onClick={openNew} size="sm" disabled={parsers.length === 0}>
          <Plus size={16} /> Nova fonte
        </Button>
      </div>

      {showForm && (
        <Card className="mb-6">
          <CardHeader className="flex items-center justify-between">
            <h2 className="font-semibold text-gray-900">{editing ? `Editar fonte — ${editing.name}` : "Nova fonte"}</h2>
            <button onClick={() => setShowForm(false)} className="rounded p-1 text-gray-400 hover:bg-gray-100" aria-label="Fechar">
              <X size={16} />
            </button>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              <div>
                <label className="admin-label">Nome</label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, name: e.target.value, slug: slugTouched ? f.slug : slugify(e.target.value) }))
                  }
                  className="admin-input"
                  placeholder="Leiloeiro Exemplo"
                />
              </div>
              <div>
                <label className="admin-label">Slug</label>
                <input
                  type="text"
                  value={form.slug}
                  onChange={(e) => {
                    setSlugTouched(true);
                    setForm({ ...form, slug: slugify(e.target.value) || e.target.value });
                  }}
                  className="admin-input font-mono"
                  placeholder="leiloeiro-exemplo"
                />
              </div>
              <div>
                <label className="admin-label">Tipo</label>
                <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as FormState["kind"] })} className="admin-input">
                  <option value="auction">Leilão</option>
                  <option value="marketplace">Marketplace</option>
                </select>
              </div>
              <div>
                <label className="admin-label">Parser</label>
                <select value={form.parser_type} onChange={(e) => onParserChange(e.target.value)} className="admin-input">
                  {parsers.map((p) => (
                    <option key={p.key} value={p.key}>
                      {p.name} ({p.key})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="admin-label">URL base (opcional)</label>
                <input type="url" value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })} className="admin-input" placeholder="https://…" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="admin-label">Frequência (min)</label>
                  <input type="number" min={1} value={form.scrape_frequency} onChange={(e) => setForm({ ...form, scrape_frequency: e.target.value })} className="admin-input" />
                </div>
                <div>
                  <label className="admin-label">Peso</label>
                  <input type="number" min={0} value={form.priority_weight} onChange={(e) => setForm({ ...form, priority_weight: e.target.value })} className="admin-input" />
                </div>
              </div>
            </div>

            <div className="mt-4 flex flex-wrap gap-6">
              <Toggle checked={form.is_active} onChange={(v) => setForm({ ...form, is_active: v })} label="Coleta ativa" />
              <Toggle checked={form.dispatch_enabled} onChange={(v) => setForm({ ...form, dispatch_enabled: v })} label="Publicar na vitrine" />
              <Toggle checked={form.scraping_allowed} onChange={(v) => setForm({ ...form, scraping_allowed: v })} label="Scraping permitido (RN-009)" />
            </div>

            <div className="mt-4">
              <div className="mb-1 flex items-center justify-between">
                <label className="admin-label mb-0">Configuração do parser (JSON)</label>
                <Button variant="ghost" size="sm" onClick={restoreDefault} title="Restaurar padrão do parser">
                  <RotateCcw size={12} /> Padrão do parser
                </Button>
              </div>
              <JsonEditor value={form.config} onChange={(v) => setForm({ ...form, config: v })} rows={12} />
            </div>

            <div className="mt-4 flex gap-2">
              <Button onClick={save} size="sm" loading={saving}>
                <Check size={14} /> Salvar
              </Button>
              <Button variant="secondary" size="sm" onClick={() => setShowForm(false)}>
                <X size={14} /> Cancelar
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="p-0">
          {sources === null ? (
            <TableSkeleton rows={4} cols={7} />
          ) : sources.length === 0 ? (
            <EmptyState title="Nenhuma fonte cadastrada" description="Cadastre o primeiro leiloeiro para começar a coletar." action={<Button size="sm" onClick={openNew}><Plus size={14} /> Nova fonte</Button>} />
          ) : (
            <Table minWidth={860}>
              <Thead>
                <tr>
                  <Th>Fonte</Th>
                  <Th>Coleta</Th>
                  <Th>Publicar</Th>
                  <Th>Conformidade</Th>
                  <Th>Estado</Th>
                  <Th>Volume</Th>
                  <Th>Ações</Th>
                </tr>
              </Thead>
              <tbody>
                {sources.map((s) => {
                  const b = busy[s.id];
                  return (
                    <Tr key={s.id}>
                      <Td>
                        <div className="whitespace-nowrap font-medium text-gray-900">{s.name}</div>
                        <div className="whitespace-nowrap text-xs text-gray-400">
                          {parserByKey[s.parser_type]?.name ?? s.parser_type} · {SOURCE_KIND_LABELS[s.kind] ?? s.kind} ·{" "}
                          a cada {formatMinutes(s.scrape_frequency)}
                        </div>
                        {s.suspended_reason && (
                          <div className="mt-0.5 flex items-start gap-1 text-xs text-red-600" title={s.suspended_reason}>
                            <AlertTriangle size={12} className="mt-0.5 shrink-0" />
                            <span className="line-clamp-2">{s.suspended_reason}</span>
                          </div>
                        )}
                      </Td>
                      <Td><Toggle size="sm" checked={s.is_active} onChange={(v) => toggleField(s, "is_active", v)} title="Coleta ativa" /></Td>
                      <Td><Toggle size="sm" checked={s.dispatch_enabled} onChange={(v) => toggleField(s, "dispatch_enabled", v)} title="Publicar na vitrine" /></Td>
                      {/* RN-009 numa coluna só: a permissão do cadastro e o que
                          o robots.txt respondeu são a mesma decisão operacional. */}
                      <Td className="whitespace-nowrap">
                        <button
                          onClick={() => toggleField(s, "scraping_allowed", !s.scraping_allowed)}
                          className={`inline-flex items-center gap-1 text-xs ${s.scraping_allowed ? "text-green-700" : "text-red-600"}`}
                          title="Permissão de scraping no cadastro (RN-009)"
                        >
                          {s.scraping_allowed ? <ShieldCheck size={14} /> : <ShieldOff size={14} />}
                          {s.scraping_allowed ? "permitido" : "bloqueado"}
                        </button>
                        <div
                          className={`text-xs ${s.robots_status === "disallowed" ? "text-red-600" : "text-gray-400"}`}
                          title={s.robots_checked_at ? `robots.txt verificado ${formatRelative(s.robots_checked_at)}` : "robots.txt ainda não verificado"}
                        >
                          robots: {ROBOTS_LABELS[s.robots_status ?? "unknown"] ?? s.robots_status}
                        </div>
                      </Td>
                      {/* Saúde e última coleta juntas: uma fonte suspensa e a
                          hora em que isso aconteceu se leem sempre em par. */}
                      <Td className="whitespace-nowrap">
                        <Badge variant={healthVariant(s.health_status)}>{HEALTH_LABELS[s.health_status] ?? s.health_status}</Badge>
                        <div className="mt-1 text-xs text-gray-500" title={formatDateTime(s.last_run_at)}>
                          {s.last_run_at ? formatRelative(s.last_run_at) : "nunca coletada"}
                          {s.last_run_status && s.last_run_status !== "success" && (
                            <span className="ml-1 text-red-600">({s.last_run_status})</span>
                          )}
                        </div>
                        {s.open_incidents > 0 && (
                          <div className="text-xs text-red-600">{s.open_incidents} incidente(s)</div>
                        )}
                      </Td>
                      {/* Volume numa coluna só: a última coleta contra a média é
                          o que dispara a RN-008; o acervo é o contexto dela. */}
                      <Td className="whitespace-nowrap tabular-nums">
                        <span title="Última coleta / média móvel — base da RN-008">
                          {formatInt(s.last_items_count)} / {s.avg_items_count === null ? "—" : formatInt(Math.round(s.avg_items_count))}
                        </span>
                        <div className="text-xs text-gray-400" title="Itens no acervo / publicados na vitrine">
                          {formatInt(s.items_total)} itens · {formatInt(s.items_published)} publ.
                        </div>
                      </Td>
                      <Td>
                        <div className="flex gap-1">
                          <Button variant="ghost" size="sm" onClick={() => runNow(s)} disabled={!!b} title="Coletar agora">
                            {b === "run" ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} className="text-green-600" />}
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => testParser(s)} disabled={!!b} title="Testar parser (coleta a seco, 1 página)">
                            {b === "test" ? <Loader2 size={14} className="animate-spin" /> : <FlaskConical size={14} className="text-purple-600" />}
                          </Button>
                          {s.health_status === "suspended" && (
                            <Button variant="ghost" size="sm" onClick={() => reactivate(s)} disabled={!!b} title="Reativar (limpa suspensão)">
                              {b === "reactivate" ? <Loader2 size={14} className="animate-spin" /> : <RotateCcw size={14} className="text-amber-600" />}
                            </Button>
                          )}
                          <Button variant="ghost" size="sm" onClick={() => openEdit(s)} title="Editar">
                            <Pencil size={14} />
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => remove(s)} title="Remover">
                            <Trash2 size={14} className="text-red-500" />
                          </Button>
                        </div>
                      </Td>
                    </Tr>
                  );
                })}
              </tbody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Resultado do teste de parser */}
      <Modal
        open={!!testResult}
        onClose={() => setTestResult(null)}
        size="lg"
        title={testResult ? `Teste do parser — ${testResult.source.name}` : ""}
        footer={
          <div className="flex justify-end">
            <Button variant="secondary" size="sm" onClick={() => setTestResult(null)}>Fechar</Button>
          </div>
        }
      >
        {testResult && (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <Badge variant={testResult.result.ok ? "success" : "danger"}>{testResult.result.ok ? "OK" : "Falhou"}</Badge>
              <span className="text-gray-700">
                <strong>{testResult.result.items_found}</strong> itens encontrados
              </span>
              <span className="text-gray-500">em {formatDuration(testResult.result.duration_ms)}</span>
            </div>
            {testResult.result.error && (
              <pre className="whitespace-pre-wrap rounded-lg bg-red-50 p-3 text-xs text-red-800">{testResult.result.error}</pre>
            )}
            {testResult.result.sample.length > 0 ? (
              <div>
                <h3 className="mb-2 text-sm font-semibold text-gray-900">Amostra ({testResult.result.sample.length})</h3>
                <div className="space-y-2">
                  {testResult.result.sample.map((s, i) => (
                    <details key={i} className="rounded-lg border border-gray-200 bg-gray-50">
                      <summary className="cursor-pointer px-3 py-2 text-sm text-gray-800">
                        {String(s.title ?? s.lot_number ?? s.external_id ?? `Item ${i + 1}`)}
                        {s.price !== undefined && s.price !== null && <span className="ml-2 text-xs text-gray-500">R$ {String(s.price)}</span>}
                      </summary>
                      <pre className="overflow-x-auto border-t border-gray-200 px-3 py-2 text-[11px] leading-relaxed text-gray-700">
                        {JSON.stringify(s, null, 2)}
                      </pre>
                    </details>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-sm text-gray-500">Nenhum item na amostra.</p>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
