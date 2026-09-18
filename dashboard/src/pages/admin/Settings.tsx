import { useEffect, useMemo, useState } from "react";
import { Save, Loader2, RefreshCw, Plug, CheckCircle2, XCircle, Eye, EyeOff } from "lucide-react";
import { toast } from "sonner";
import { settingsApi } from "../../services/settings";
import type { LlmTestResult, SettingItem, SettingsResponse } from "../../services/types";
import { errorMessage } from "../../services/api";
import { refreshBranding } from "../../hooks/useBranding";
import { Card, CardContent, CardHeader } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Toggle } from "../../components/ui/Toggle";
import { Skeleton } from "../../components/ui/Skeleton";
import BrandingUpload from "../../components/BrandingUpload";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";

const GROUP_ORDER = ["llm", "pipeline", "health", "scraping", "portal", "branding"];
const GROUP_DESCRIPTIONS: Record<string, string> = {
  llm: "Provedor, modelo e limites da extração por LLM.",
  pipeline: "Intervalos dos jobs, tentativas de extração, ciclo de vida e retenção.",
  health: "Detecção de incidentes e suspensão automática (RN-008).",
  scraping: "Comportamento dos scrapers: user-agent, atrasos e robots.txt (RN-009).",
  portal: "Vitrine pública: paginação e disclaimer das fichas.",
  branding: "Título e slogan. Logos e favicon são enviados na seção acima.",
};

const MASK = "********";
const BOOL_VALUES = new Set(["true", "false"]);
const LONG_KEYS = new Set(["portal_disclaimer", "scraper_user_agent"]);

function isBoolSetting(item: SettingItem): boolean {
  return BOOL_VALUES.has(item.value.trim().toLowerCase());
}

function isNumberSetting(item: SettingItem): boolean {
  return !item.is_secret && item.value.trim() !== "" && /^-?\d+(\.\d+)?$/.test(item.value.trim());
}

export default function Settings() {
  useDocumentTitle("Configurações");
  const [grouped, setGrouped] = useState<SettingsResponse>({});
  const [values, setValues] = useState<Record<string, string>>({});
  const [initial, setInitial] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<LlmTestResult | null>(null);
  const [reveal, setReveal] = useState<Record<string, boolean>>({});

  const load = async () => {
    setLoading(true);
    try {
      const data = await settingsApi.list();
      setGrouped(data);
      const flat: Record<string, string> = {};
      for (const g of Object.values(data)) for (const it of g.items) flat[it.key] = it.value;
      setValues(flat);
      setInitial(flat);
    } catch (e) {
      toast.error(errorMessage(e, "Erro ao carregar configurações"));
    }
    setLoading(false);
  };

  useEffect(() => {
    load();
  }, []);

  const dirty = useMemo(() => Object.keys(values).filter((k) => values[k] !== initial[k]), [values, initial]);

  const handleSave = async () => {
    if (dirty.length === 0) {
      toast.info("Nenhuma alteração para salvar");
      return;
    }
    setSaving(true);
    try {
      const payload: Record<string, string> = {};
      for (const k of dirty) payload[k] = values[k];
      await settingsApi.save(payload);
      toast.success(`Configurações salvas (${dirty.length})`);
      if (dirty.some((k) => k.startsWith("brand_") || k === "portal_disclaimer")) await refreshBranding();
      await load();
    } catch (e) {
      toast.error(errorMessage(e, "Erro ao salvar configurações"));
    }
    setSaving(false);
  };

  // O teste usa o que está gravado no banco; salvar antes evita falso negativo.
  const handleTestLlm = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const r = await settingsApi.testLlm();
      setTestResult(r);
      if (r.ok) toast.success("LLM respondeu");
      else toast.error("LLM não respondeu como esperado");
    } catch (e) {
      setTestResult({ ok: false, detail: errorMessage(e, "Falha ao chamar o teste no backend.") });
      toast.error("Falha no teste");
    }
    setTesting(false);
  };

  const groups = [...GROUP_ORDER.filter((g) => grouped[g]), ...Object.keys(grouped).filter((g) => !GROUP_ORDER.includes(g))];

  if (loading && Object.keys(grouped).length === 0) {
    return (
      <div>
        <h1 className="mb-6 text-2xl font-bold text-gray-900">Configurações</h1>
        <div className="grid gap-6 lg:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i}>
              <CardHeader><Skeleton className="h-5 w-40" /></CardHeader>
              <CardContent className="space-y-4">
                {Array.from({ length: 4 }).map((_, j) => <Skeleton key={j} className="h-10 w-full" />)}
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  const renderInput = (item: SettingItem) => {
    const value = values[item.key] ?? "";
    if (item.is_secret) {
      const shown = reveal[item.key];
      return (
        <div className="relative">
          <input
            type={shown ? "text" : "password"}
            value={value}
            onChange={(e) => setValues((v) => ({ ...v, [item.key]: e.target.value }))}
            onFocus={(e) => {
              if (e.target.value === MASK) setValues((v) => ({ ...v, [item.key]: "" }));
            }}
            placeholder={value ? "" : "Não configurado"}
            autoComplete="off"
            className="admin-input pr-10"
          />
          <button type="button" onClick={() => setReveal((r) => ({ ...r, [item.key]: !shown }))} className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-gray-400 hover:text-gray-600" aria-label={shown ? "Ocultar" : "Mostrar"}>
            {shown ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
        </div>
      );
    }
    if (isBoolSetting({ ...item, value: initial[item.key] ?? item.value })) {
      return (
        <Toggle
          checked={value.trim().toLowerCase() === "true"}
          onChange={(v) => setValues((s) => ({ ...s, [item.key]: v ? "true" : "false" }))}
          label={value.trim().toLowerCase() === "true" ? "Ativado" : "Desativado"}
        />
      );
    }
    if (LONG_KEYS.has(item.key)) {
      return <textarea rows={item.key === "portal_disclaimer" ? 4 : 2} value={value} onChange={(e) => setValues((v) => ({ ...v, [item.key]: e.target.value }))} className="admin-input" />;
    }
    return (
      <input
        type={isNumberSetting({ ...item, value: initial[item.key] ?? item.value }) ? "number" : "text"}
        step="any"
        value={value}
        onChange={(e) => setValues((v) => ({ ...v, [item.key]: e.target.value }))}
        className="admin-input"
      />
    );
  };

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Configurações</h1>
          <p className="text-sm text-gray-500">Parâmetros de runtime (tabela settings). Segredos são exibidos mascarados.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" onClick={load} disabled={loading}>
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Recarregar
          </Button>
          <Button onClick={handleSave} disabled={saving || dirty.length === 0}>
            {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
            Salvar {dirty.length > 0 && `(${dirty.length})`}
          </Button>
        </div>
      </div>

      <div className="mb-8">
        <BrandingUpload />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {groups.map((groupKey) => {
          const g = grouped[groupKey];
          if (!g) return null;
          return (
            <Card key={groupKey}>
              <CardHeader>
                <h2 className="font-semibold text-gray-900">{g.label || groupKey}</h2>
                {GROUP_DESCRIPTIONS[groupKey] && <p className="mt-1 text-xs text-gray-500">{GROUP_DESCRIPTIONS[groupKey]}</p>}
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {g.items.map((item) => (
                    <div key={item.key}>
                      <label className="admin-label flex items-center justify-between">
                        <span>{item.label}</span>
                        <span className="font-mono text-[10px] font-normal text-gray-400">{item.key}{dirty.includes(item.key) && <span className="ml-1 text-amber-500">•</span>}</span>
                      </label>
                      {renderInput(item)}
                    </div>
                  ))}
                </div>

                {groupKey === "llm" && (
                  <div className="mt-5 border-t border-gray-200 pt-4">
                    <Button variant="secondary" size="sm" onClick={handleTestLlm} disabled={testing}>
                      {testing ? <Loader2 size={14} className="animate-spin" /> : <Plug size={14} />}
                      Testar LLM
                    </Button>
                    <p className="mt-2 text-xs text-gray-500">
                      Envia uma mensagem mínima ao provedor com a chave e o modelo gravados. Salve antes de testar.
                    </p>
                    {testResult && (
                      <div className={`mt-3 flex items-start gap-2 rounded-lg px-3 py-2 text-sm ${testResult.ok ? "bg-green-50 text-green-800" : "bg-red-50 text-red-800"}`}>
                        {testResult.ok ? <CheckCircle2 size={16} className="mt-0.5 shrink-0" /> : <XCircle size={16} className="mt-0.5 shrink-0" />}
                        <div>
                          <div>{testResult.detail}</div>
                          {testResult.ok && (
                            <div className="mt-1 text-xs opacity-80">
                              {testResult.model && <span>modelo {testResult.model}</span>}
                              {testResult.reply && <span> · resposta: “{testResult.reply}”</span>}
                              {testResult.usage && <span> · tokens {testResult.usage.input ?? "?"}/{testResult.usage.output ?? "?"}</span>}
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div className="mt-6 flex justify-end">
        <Button onClick={handleSave} disabled={saving || dirty.length === 0} size="lg">
          {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
          Salvar configurações
        </Button>
      </div>
    </div>
  );
}
