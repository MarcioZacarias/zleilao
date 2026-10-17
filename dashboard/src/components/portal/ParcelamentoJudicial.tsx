import { CreditCard, Scale } from "lucide-react";

/**
 * Parcelamento em leilão judicial (CPC, art. 895).
 *
 * A regra é da lei, não do anúncio: em leilão judicial de bem penhorado o
 * interessado pode propor, por escrito e antes do pregão, pagar pelo menos
 * 25% à vista e o restante em até 30 meses, com garantia. Por isso o site
 * sinaliza em todo lote judicial sem precisar coletar nada — e sempre com
 * a ressalva de que o edital e o juiz mandam, porque falência e recuperação
 * judicial seguem regras próprias e lance à vista tem preferência.
 */

export const PARCELAMENTO_RESUMO =
  "Leilão judicial: o CPC (art. 895) admite proposta de pagamento parcelado — pelo menos 25% à vista e o restante em até 30 meses. Depende do edital e do juiz.";

/** Selo curto, para o card da vitrine. */
export function ParcelamentoBadge() {
  return (
    <span
      title={PARCELAMENTO_RESUMO}
      className="inline-flex items-center gap-1 rounded-full bg-sky-500/10 px-2 py-0.5 text-[11px] font-medium text-sky-200 ring-1 ring-inset ring-sky-400/25"
    >
      <CreditCard size={11} /> pode parcelar
    </span>
  );
}

/** Aviso completo, para a ficha do lote. */
export function ParcelamentoAviso() {
  return (
    <div className="rounded-xl border border-sky-400/25 bg-sky-500/10 p-4 text-sm">
      <div className="mb-2 flex items-center gap-2 font-semibold text-sky-200">
        <Scale size={16} /> Leilão judicial: pode admitir proposta parcelada
      </div>
      <p className="text-radar-text/90">
        Pelo art. 895 do CPC, o interessado pode apresentar por escrito, antes do pregão, proposta de compra
        parcelada: pelo menos <strong>25% à vista</strong> e o restante em <strong>até 30 meses</strong>, com
        garantia (em veículos, em geral o próprio bem). Pelo valor da avaliação, a proposta vale até o 1º leilão;
        no 2º, por valor que não seja vil. Lance à vista tem preferência, e quem decide é o juiz.
      </p>
      <p className="mt-2 text-xs text-radar-muted">
        Confira o edital na fonte oficial: leilões de falência e recuperação judicial seguem regras próprias, e o
        edital pode restringir o parcelamento. A proposta é feita no juízo ou com o leiloeiro; não intermediamos.
      </p>
    </div>
  );
}
