import { useEffect, useState } from "react";
import { BellRing, Mail, MessageCircle } from "lucide-react";
import { ItemCard } from "../portal/ItemCard";
import { EmptyState } from "../ui/EmptyState";
import { Button } from "../ui/Button";
import { Skeleton } from "../ui/Skeleton";
import { accountApi } from "../../services/account";
import { errorMessage } from "../../services/api";
import type { MyAlert } from "../../services/types";
import { formatDateTime, formatRelative } from "../../lib/format";
import { ALERT_REASON_LABELS, ALERT_STATUS_LABELS } from "../../lib/labels";

const FIRST_PAGE = 50;
const FULL_PAGE = 200;

/** Cor do selo por motivo — o motivo é a informação que o usuário procura. */
const REASON_TONE: Record<string, string> = {
  new: "bg-accent/15 text-accent-300 ring-accent/30",
  price_drop: "bg-emerald-500/15 text-emerald-300 ring-emerald-400/30",
  new_session: "bg-blue-500/15 text-blue-300 ring-blue-400/30",
};

function ReasonBadge({ reason }: { reason: string }) {
  const tone = REASON_TONE[reason] ?? "bg-radar-surface2 text-radar-muted ring-white/10";
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${tone}`}>
      {ALERT_REASON_LABELS[reason] ?? reason}
    </span>
  );
}

export function AlertasSection({ emailVerified, onGoToFilters }: { emailVerified: boolean; onGoToFilters: () => void }) {
  const [alerts, setAlerts] = useState<MyAlert[] | null>(null);
  const [limit, setLimit] = useState(FIRST_PAGE);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    setError("");
    accountApi
      .alerts(limit)
      .then((r) => alive && setAlerts(r))
      .catch((e) => {
        if (!alive) return;
        setAlerts([]);
        setError(errorMessage(e, "Não foi possível carregar seus alertas"));
      });
    return () => {
      alive = false;
    };
  }, [limit]);

  return (
    <div>
      <div className="mb-4">
        <h2 className="text-lg font-bold text-radar-text">Meus alertas</h2>
        <p className="mt-0.5 text-sm text-radar-muted">
          Tudo o que os seus filtros encontraram, do mais recente para o mais antigo.
        </p>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-400/30 bg-red-500/10 px-4 py-3 text-sm text-red-300" role="alert">
          {error}
        </div>
      )}

      {alerts === null ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="portal-card p-4">
              <Skeleton tone="dark" className="mb-3 h-4 w-40" />
              <Skeleton tone="dark" className="h-24 w-full" />
            </div>
          ))}
        </div>
      ) : alerts.length === 0 ? (
        <div className="portal-card">
          <EmptyState
            tone="dark"
            icon={BellRing}
            title="Nenhum alerta por enquanto"
            description={
              emailVerified
                ? "Assim que um lote novo se encaixar em um dos seus filtros, o aviso aparece aqui."
                : "Confirme seu e-mail e salve um filtro para começar a receber avisos."
            }
            action={
              <Button variant="accent" size="sm" onClick={onGoToFilters}>
                Ver meus filtros
              </Button>
            }
          />
        </div>
      ) : (
        <>
          <ul className="space-y-3">
            {alerts.map((a) => (
              <li key={a.id} className="portal-card p-4">
                <div className="flex flex-col gap-4 sm:flex-row">
                  <div className="w-full shrink-0 sm:w-56">
                    {a.item ? (
                      <ItemCard item={a.item} compact />
                    ) : (
                      <div className="flex h-full min-h-[8rem] items-center justify-center rounded-lg bg-radar-surface2/60 px-3 text-center text-xs text-radar-muted">
                        O lote não está mais disponível na vitrine.
                      </div>
                    )}
                  </div>

                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <ReasonBadge reason={a.reason} />
                      <span className="text-xs text-radar-muted" title={formatDateTime(a.created_at)}>
                        {formatRelative(a.created_at)}
                      </span>
                    </div>

                    {a.detail && <p className="mt-2 text-sm text-radar-text/90">{a.detail}</p>}

                    <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-radar-muted">
                      <span>{ALERT_STATUS_LABELS[a.status] ?? a.status}</span>
                      {a.channel && (
                        <span className="inline-flex items-center gap-1">
                          {a.channel === "whatsapp" ? <MessageCircle size={12} /> : <Mail size={12} />}
                          {a.channel === "whatsapp" ? "WhatsApp" : "E-mail"}
                        </span>
                      )}
                      {a.sent_at && <span title={formatDateTime(a.sent_at)}>enviado {formatRelative(a.sent_at)}</span>}
                    </div>
                  </div>
                </div>
              </li>
            ))}
          </ul>

          {limit === FIRST_PAGE && alerts.length >= FIRST_PAGE && (
            <div className="mt-4 flex justify-center">
              <Button variant="outline-dark" size="sm" onClick={() => setLimit(FULL_PAGE)}>
                Carregar mais alertas
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
