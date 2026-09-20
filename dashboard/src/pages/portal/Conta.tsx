import { useCallback, useEffect, useState } from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import { BellRing, CreditCard, Filter, ShieldAlert, User } from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { accountApi } from "../../services/account";
import { errorMessage } from "../../services/api";
import type { AccountMe } from "../../services/types";
import { Skeleton } from "../../components/ui/Skeleton";
import { EmptyState } from "../../components/ui/EmptyState";
import { Button } from "../../components/ui/Button";
import { EmailBanner } from "../../components/conta/EmailBanner";
import { AlertasSection } from "../../components/conta/AlertasSection";
import { FiltrosSection } from "../../components/conta/FiltrosSection";
import { PerfilSection } from "../../components/conta/PerfilSection";
import { PlanoSection } from "../../components/conta/PlanoSection";

const TABS = [
  { key: "alertas", label: "Meus alertas", icon: BellRing },
  { key: "filtros", label: "Filtros salvos", icon: Filter },
  { key: "perfil", label: "Perfil", icon: User },
  { key: "plano", label: "Plano", icon: CreditCard },
] as const;

type TabKey = (typeof TABS)[number]["key"];

function isTab(v: string | null): v is TabKey {
  return !!v && TABS.some((t) => t.key === v);
}

/** Área do assinante. Exige sessão; o admin também pode usar (tem /me). */
export default function Conta() {
  const { token, loading: authLoading, patchUser } = useAuth();
  const [sp, setSp] = useSearchParams();
  useDocumentTitle("Minha conta");

  const [me, setMe] = useState<AccountMe | null>(null);
  const [error, setError] = useState("");
  const [autoCreate, setAutoCreate] = useState(sp.get("novo") === "1");

  const tab: TabKey = isTab(sp.get("aba")) ? (sp.get("aba") as TabKey) : "alertas";

  const load = useCallback(() => {
    setError("");
    accountApi
      .me()
      .then((data) => {
        setMe(data);
        patchUser({ name: data.name, role: data.role });
      })
      .catch((e) => setError(errorMessage(e, "Não foi possível carregar sua conta")));
  }, [patchUser]);

  useEffect(() => {
    if (token) load();
  }, [token, load]);

  // Limpa o ?novo=1 da URL depois de abrir o formulário.
  useEffect(() => {
    if (sp.get("novo") !== "1") return;
    const next = new URLSearchParams(sp);
    next.delete("novo");
    next.set("aba", "filtros");
    setSp(next, { replace: true });
  }, [sp, setSp]);

  const goTo = (key: TabKey) => {
    const next = new URLSearchParams(sp);
    next.set("aba", key);
    setSp(next);
  };

  if (!authLoading && !token) {
    const here = `${window.location.pathname}${window.location.search}`;
    return <Navigate to={`/entrar?next=${encodeURIComponent(here)}`} replace />;
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6">
      <h1 className="text-xl font-bold text-radar-text md:text-2xl">Minha conta</h1>
      <p className="mt-0.5 text-sm text-radar-muted">
        {me?.name ? `Olá, ${me.name}. ` : ""}
        Seus alertas, filtros salvos e preferências.
      </p>

      {/* Abas */}
      <nav className="no-scrollbar mt-5 flex gap-1 overflow-x-auto border-b border-radar-border" aria-label="Seções da conta">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => goTo(t.key)}
            aria-current={tab === t.key ? "page" : undefined}
            className={`-mb-px inline-flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2.5 text-sm transition-colors ${
              tab === t.key
                ? "border-accent text-accent-300"
                : "border-transparent text-radar-muted hover:text-radar-text"
            }`}
          >
            <t.icon size={15} /> {t.label}
          </button>
        ))}
      </nav>

      <div className="mt-6">
        {error ? (
          <div className="portal-card">
            <EmptyState
              tone="dark"
              icon={ShieldAlert}
              title="Não foi possível carregar sua conta"
              description={error}
              action={
                <Button variant="accent" size="sm" onClick={load}>
                  Tentar novamente
                </Button>
              }
            />
          </div>
        ) : !me ? (
          <div className="space-y-3">
            <Skeleton tone="dark" className="h-20 w-full" rounded="rounded-xl" />
            <Skeleton tone="dark" className="h-40 w-full" rounded="rounded-xl" />
          </div>
        ) : (
          <>
            {!me.email_verified && <EmailBanner email={me.email} />}

            {tab === "alertas" && (
              <AlertasSection emailVerified={me.email_verified} onGoToFilters={() => goTo("filtros")} />
            )}
            {tab === "filtros" && (
              <FiltrosSection
                me={me}
                onAccountChanged={load}
                autoCreate={autoCreate}
                onAutoCreateHandled={() => setAutoCreate(false)}
                onGoToPlan={() => goTo("plano")}
              />
            )}
            {tab === "perfil" && <PerfilSection me={me} onSaved={setMe} />}
            {tab === "plano" && <PlanoSection me={me} />}
          </>
        )}
      </div>
    </div>
  );
}
