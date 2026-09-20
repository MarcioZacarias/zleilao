import { TrendingDown, Info, AlertTriangle, HelpCircle } from "lucide-react";
import type { Opportunity } from "../../services/types";
import { formatBRL, formatPercent } from "../../lib/format";

/**
 * Score de oportunidade na ficha do lote (RN-010).
 *
 * O número sozinho seria uma promessa; acompanhado das ressalvas, é uma
 * estimativa. Por isso a memória de cálculo e os avisos aparecem sempre, não
 * atrás de um "ver detalhes": quem lê "43% abaixo da FIPE" precisa ver, na
 * mesma tela, que o lance inicial é o piso do pregão e que a comissão já está
 * somada.
 */
export function OpportunityPanel({ opportunity }: { opportunity: Opportunity }) {
  const r = opportunity.reasons ?? {};
  const acimaDaReferencia = opportunity.discount_pct <= 0;

  return (
    <section className="portal-card p-4 md:p-5">
      <header className="mb-4 flex items-center gap-2">
        <TrendingDown size={16} className={acimaDaReferencia ? "text-red-400" : "text-accent"} />
        <h2 className="text-xs font-semibold uppercase tracking-wider text-radar-muted">
          Comparação com o mercado
        </h2>
      </header>

      {acimaDaReferencia ? (
        <div className="mb-4 flex items-start gap-2 rounded-lg bg-red-500/10 p-3 text-sm text-red-300 ring-1 ring-inset ring-red-500/20">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <span>
            O custo total já está <strong>{formatPercent(Math.abs(opportunity.discount_pct))} acima</strong> da
            referência de mercado.
          </span>
        </div>
      ) : (
        <div className="mb-4 flex items-baseline gap-3">
          <div className="text-3xl font-bold text-accent">
            {formatPercent(opportunity.discount_pct)}
          </div>
          <div className="text-sm text-radar-muted">abaixo da referência de mercado</div>
        </div>
      )}

      {/* Memória de cálculo: o que o arrematante realmente desembolsa. */}
      <dl className="space-y-1.5 text-sm">
        <Row label="Lance inicial" value={formatBRL(r.lance ?? null)} />
        {r.comissao != null && r.comissao > 0 && (
          <Row label={`Comissão do leiloeiro (${formatPercent(r.comissao_pct ?? 0, 0)})`} value={formatBRL(r.comissao)} />
        )}
        {r.despesas != null && r.despesas > 0 && <Row label="Despesas informadas" value={formatBRL(r.despesas)} />}
        <Row label="Custo total estimado" value={formatBRL(opportunity.total_cost)} strong />
        <div className="!mt-3 border-t border-radar-border pt-3">
          <Row label="Referência de mercado" value={formatBRL(opportunity.reference_value)} />
          {r.referencia_ajustada != null && r.fator_condicao != null && r.fator_condicao < 1 && (
            <Row
              label={`Ajustada pela condição (${Math.round(r.fator_condicao * 100)}%)`}
              value={formatBRL(r.referencia_ajustada)}
            />
          )}
        </div>
      </dl>

      {opportunity.reference_label && (
        <p className="mt-3 text-xs text-radar-muted">Fonte da referência: {opportunity.reference_label}</p>
      )}

      <div className="mt-4 space-y-2">
        {r.nota_preco && <Note icon={Info} text={r.nota_preco} />}
        {r.nota_condicao && <Note icon={HelpCircle} text={r.nota_condicao} warn />}
        {r.nota && <Note icon={Info} text={r.nota} />}
      </div>
    </section>
  );
}

function Row({ label, value, strong = false }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className={strong ? "text-radar-text" : "text-radar-muted"}>{label}</dt>
      <dd className={`tabular-nums ${strong ? "font-semibold text-radar-text" : "text-radar-muted"}`}>{value}</dd>
    </div>
  );
}

function Note({
  icon: Icon,
  text,
  warn = false,
}: {
  icon: typeof Info;
  text: string;
  warn?: boolean;
}) {
  return (
    <p
      className={`flex items-start gap-2 rounded-lg p-2.5 text-xs leading-relaxed ${
        warn ? "bg-amber-500/10 text-amber-200/90" : "bg-white/[0.03] text-radar-muted"
      }`}
    >
      <Icon size={13} className="mt-0.5 shrink-0" />
      <span>{text}</span>
    </p>
  );
}

/** Selo compacto para o card da vitrine. */
export function OpportunityBadge({ discount }: { discount: number }) {
  if (discount <= 0) return null;
  return (
    <span
      title="Desconto estimado sobre a referência de mercado, já somando comissão e despesas"
      className="inline-flex items-center gap-1 rounded-full bg-accent/15 px-2 py-0.5 text-[11px] font-semibold text-accent ring-1 ring-inset ring-accent/30"
    >
      <TrendingDown size={11} />
      {formatPercent(discount, 0)} abaixo da FIPE
    </span>
  );
}
