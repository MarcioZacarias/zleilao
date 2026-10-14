import { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { useBranding } from "../../hooks/useBranding";

/** Destino seguro depois do login: só caminhos internos deste app. */
export function safeNext(next: string | null): string | null {
  if (!next) return null;
  if (!next.startsWith("/") || next.startsWith("//")) return null;
  return next;
}

interface AuthShellProps {
  title: string;
  subtitle?: ReactNode;
  children: ReactNode;
  /** Links auxiliares abaixo do cartão (criar conta, esqueci a senha…). */
  footer?: ReactNode;
  width?: string;
}

/** Moldura das telas de conta do assinante — pele escura do portal. */
export function AuthShell({ title, subtitle, children, footer, width = "max-w-md" }: AuthShellProps) {
  const branding = useBranding();
  return (
    <div className="portal flex min-h-screen flex-col items-center justify-center px-4 py-10">
      <div className={`w-full ${width}`}>
        <div className="mb-8 text-center">
          <Link to="/" aria-label={branding.site_title}>
            <img src={branding.logo_dark} alt={branding.site_title} className="mx-auto h-20 w-auto object-contain" />
          </Link>
          <h1 className="mt-5 text-xl font-bold text-radar-text">{title}</h1>
          {subtitle && <div className="mt-2 text-sm text-radar-muted">{subtitle}</div>}
        </div>

        <div className="portal-card p-6">{children}</div>

        {footer && <div className="mt-5 text-center text-sm text-radar-muted">{footer}</div>}

        <div className="mt-6 text-center">
          <Link to="/" className="inline-flex items-center gap-1 text-sm text-radar-muted hover:text-radar-text">
            <ArrowLeft size={14} /> Voltar ao portal
          </Link>
        </div>
      </div>
    </div>
  );
}

/** Caixa de erro padrão das telas de conta. */
export function AuthError({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-lg border border-red-400/30 bg-red-500/10 px-3 py-2 text-sm text-red-300" role="alert">
      {children}
    </div>
  );
}

/** Caixa de sucesso/informação padrão das telas de conta. */
export function AuthNotice({ children, tone = "success" }: { children: ReactNode; tone?: "success" | "info" }) {
  const cls =
    tone === "success"
      ? "border-emerald-400/30 bg-emerald-500/10 text-emerald-200"
      : "border-accent/30 bg-accent/10 text-accent-300";
  return (
    <div className={`rounded-lg border px-3 py-2 text-sm ${cls}`} role="status">
      {children}
    </div>
  );
}

interface FieldProps {
  id: string;
  label: string;
  hint?: ReactNode;
  children: ReactNode;
}

export function Field({ id, label, hint, children }: FieldProps) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-radar-text/90" htmlFor={id}>
        {label}
      </label>
      {children}
      {hint && <p className="mt-1 text-xs text-radar-muted">{hint}</p>}
    </div>
  );
}
