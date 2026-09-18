import { useMemo } from "react";
import { AlertCircle, CheckCircle2, Wand2 } from "lucide-react";

interface JsonEditorProps {
  value: string;
  onChange: (value: string) => void;
  rows?: number;
  placeholder?: string;
  disabled?: boolean;
  /** Quando vazio conta como válido (null). */
  allowEmpty?: boolean;
  className?: string;
}

export function parseJsonSafe(text: string): { ok: true; value: unknown } | { ok: false; error: string } {
  try {
    return { ok: true, value: JSON.parse(text) };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "JSON inválido" };
  }
}

export function JsonEditor({
  value,
  onChange,
  rows = 14,
  placeholder = "{ }",
  disabled,
  allowEmpty = true,
  className = "",
}: JsonEditorProps) {
  const state = useMemo(() => {
    if (!value.trim()) {
      return allowEmpty ? { ok: true as const, empty: true } : { ok: false as const, error: "Obrigatório" };
    }
    const r = parseJsonSafe(value);
    if (r.ok && (typeof r.value !== "object" || r.value === null || Array.isArray(r.value))) {
      return { ok: false as const, error: "Deve ser um objeto JSON ({ ... })" };
    }
    return r.ok ? { ok: true as const, empty: false } : r;
  }, [value, allowEmpty]);

  const format = () => {
    const r = parseJsonSafe(value);
    if (r.ok) onChange(JSON.stringify(r.value, null, 2));
  };

  return (
    <div className={className}>
      <div className="relative">
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          rows={rows}
          spellCheck={false}
          disabled={disabled}
          placeholder={placeholder}
          className={`w-full rounded-lg border px-3 py-2 font-mono text-xs leading-relaxed focus:outline-none focus:ring-2 ${
            state.ok
              ? "border-gray-300 bg-gray-50 focus:ring-primary-500"
              : "border-red-300 bg-red-50/40 focus:ring-red-400"
          } disabled:opacity-60`}
        />
        <button
          type="button"
          onClick={format}
          disabled={disabled || !state.ok || ("empty" in state && state.empty)}
          className="absolute right-2 top-2 inline-flex items-center gap-1 rounded-md bg-white/90 px-2 py-1 text-[11px] text-gray-600 shadow-sm ring-1 ring-gray-200 hover:bg-white disabled:opacity-40"
          title="Formatar JSON"
        >
          <Wand2 size={12} /> Formatar
        </button>
      </div>
      <div className="mt-1 flex items-center gap-1 text-xs">
        {state.ok ? (
          <span className="inline-flex items-center gap-1 text-green-600">
            <CheckCircle2 size={12} /> {"empty" in state && state.empty ? "Vazio (null)" : "JSON válido"}
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 text-red-600">
            <AlertCircle size={12} /> {state.error}
          </span>
        )}
      </div>
    </div>
  );
}
