import { useState } from "react";
import { BellRing, Check, Clock, Copy, Mail, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { Button } from "../ui/Button";
import type { AccountMe } from "../../services/types";
import { formatDate } from "../../lib/format";
import { PLAN_LABELS, PLAN_STATUS_LABELS } from "../../lib/labels";

const SUPPORT_EMAIL = import.meta.env.VITE_SUPPORT_EMAIL ?? "";

function Line({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return (
    <li className="flex items-start gap-2 text-sm">
      <Check size={15} className={`mt-0.5 shrink-0 ${ok ? "text-emerald-400" : "text-radar-muted/50"}`} />
      <span className={ok ? "text-radar-text/90" : "text-radar-muted"}>{children}</span>
    </li>
  );
}

export function PlanoSection({ me }: { me: AccountMe }) {
  const [asking, setAsking] = useState(false);
  const pro = me.plan === "pro";

  const message =
    `Olá! Quero ativar o plano pago do ZConnect Leilão.\n\n` +
    `Nome: ${me.name ?? "-"}\n` +
    `E-mail da conta: ${me.email}\n` +
    `Plano atual: ${PLAN_LABELS[me.plan] ?? me.plan}`;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(message);
      toast.success("Mensagem copiada");
    } catch {
      toast.error("Não foi possível copiar. Selecione o texto manualmente.");
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-bold text-radar-text">Plano</h2>
        <p className="mt-0.5 text-sm text-radar-muted">O que muda na velocidade e no volume dos seus alertas.</p>
      </div>

      {/* Plano atual */}
      <div className="portal-card p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-wider text-radar-muted">Seu plano</p>
            <p className="mt-1 flex items-center gap-2 text-2xl font-bold text-radar-text">
              {PLAN_LABELS[me.plan] ?? me.plan}
              {pro && <Sparkles size={18} className="text-accent" />}
            </p>
          </div>
          <div className="text-right text-sm">
            <p className="text-radar-muted">
              Situação:{" "}
              <span className="text-radar-text">{PLAN_STATUS_LABELS[me.plan_status] ?? me.plan_status}</span>
            </p>
            <p className="mt-0.5 text-radar-muted">
              {me.plan_expires_at ? (
                <>
                  Vence em <span className="text-radar-text">{formatDate(me.plan_expires_at)}</span>
                </>
              ) : pro ? (
                "Sem data de vencimento"
              ) : (
                "Sem vencimento"
              )}
            </p>
          </div>
        </div>

        <div className="mt-5 grid gap-4 border-t border-radar-border pt-4 sm:grid-cols-2">
          <div className="flex items-start gap-3">
            <BellRing size={18} className="mt-0.5 shrink-0 text-accent" />
            <div>
              <p className="text-sm font-medium text-radar-text">
                {me.filters_used} de {me.filters_limit} filtros salvos
              </p>
              <p className="text-xs text-radar-muted">Limite de filtros do plano {PLAN_LABELS[me.plan] ?? me.plan}.</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <Clock size={18} className="mt-0.5 shrink-0 text-accent" />
            <div>
              <p className="text-sm font-medium text-radar-text">
                {me.realtime_alerts ? "Alerta quase em tempo real" : "Resumo diário"}
              </p>
              <p className="text-xs text-radar-muted">
                {me.realtime_alerts
                  ? "Avisamos logo depois de encontrar o lote."
                  : "Os achados do dia chegam juntos, uma vez por dia."}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Comparativo */}
      <div className="grid gap-4 md:grid-cols-2">
        <div className={`portal-card p-5 ${!pro ? "ring-1 ring-inset ring-accent/40" : ""}`}>
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-radar-text">Gratuito</h3>
            {!pro && (
              <span className="rounded-full bg-accent/15 px-2.5 py-0.5 text-[11px] font-medium text-accent-300">
                seu plano
              </span>
            )}
          </div>
          <ul className="mt-4 space-y-2">
            <Line ok>Filtros salvos com todos os campos da busca</Line>
            <Line ok>
              <strong className="text-radar-text">Resumo diário</strong> por e-mail com os lotes do dia
            </Line>
            <Line ok>Prévia do que cada filtro pega hoje</Line>
            <Line ok={false}>Aviso quase em tempo real</Line>
          </ul>
        </div>

        <div className={`portal-card p-5 ${pro ? "ring-1 ring-inset ring-accent/40" : ""}`}>
          <div className="flex items-center justify-between">
            <h3 className="flex items-center gap-1.5 font-semibold text-radar-text">
              Pago <Sparkles size={14} className="text-accent" />
            </h3>
            {pro && (
              <span className="rounded-full bg-accent/15 px-2.5 py-0.5 text-[11px] font-medium text-accent-300">
                seu plano
              </span>
            )}
          </div>
          <ul className="mt-4 space-y-2">
            <Line ok>Tudo do plano gratuito</Line>
            <Line ok>
              Aviso <strong className="text-radar-text">quase em tempo real</strong>, e não só uma vez por dia
            </Line>
            <Line ok>Mais filtros salvos ao mesmo tempo</Line>
            <Line ok>Prioridade no envio dos alertas</Line>
          </ul>

          {!pro && (
            <div className="mt-5 border-t border-radar-border pt-4">
              {!asking ? (
                <Button variant="accent" className="w-full" onClick={() => setAsking(true)}>
                  Quero o plano pago
                </Button>
              ) : (
                <div className="space-y-3">
                  <p className="text-sm text-radar-muted">
                    A ativação do plano pago é feita <strong className="text-radar-text">manualmente pela equipe</strong>
                    : não há pagamento automático por aqui. Fale com o suporte informando o e-mail da sua conta (
                    <span className="text-radar-text">{me.email}</span>) e liberamos o acesso.
                  </p>
                  <div className="flex flex-col gap-2 sm:flex-row">
                    {SUPPORT_EMAIL && (
                      <a
                        className="flex-1"
                        href={`mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent(
                          "Quero o plano pago — ZConnect Leilão"
                        )}&body=${encodeURIComponent(message)}`}
                      >
                        <Button variant="accent" className="w-full">
                          <Mail size={15} /> Falar com o suporte
                        </Button>
                      </a>
                    )}
                    <Button variant="outline-dark" className="flex-1" onClick={copy}>
                      <Copy size={15} /> Copiar meus dados
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <p className="text-xs leading-relaxed text-radar-muted/80">
        Em qualquer plano continuamos sendo um agregador: os alertas levam sempre à fonte oficial do lote, onde o lance
        é dado.
      </p>
    </div>
  );
}
