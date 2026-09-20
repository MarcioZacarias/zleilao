import { useState } from "react";
import { MailWarning } from "lucide-react";
import { toast } from "sonner";
import { Button } from "../ui/Button";
import { publicAuthApi } from "../../services/account";
import { errorMessage } from "../../services/api";

/**
 * E-mail não verificado não recebe alerta nenhum (RN-006). Enquanto
 * `email_verified` for false o aviso fica fixo no topo da conta.
 */
export function EmailBanner({ email }: { email: string }) {
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);

  const resend = async () => {
    setSending(true);
    try {
      const r = await publicAuthApi.resendVerification(email);
      setSent(true);
      toast.success(r.detail ?? "Link de confirmação reenviado.");
    } catch (e) {
      toast.error(errorMessage(e, "Não foi possível reenviar agora."));
    }
    setSending(false);
  };

  return (
    <div className="mb-6 rounded-xl border border-accent/30 bg-accent/10 p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <MailWarning size={22} className="shrink-0 text-accent" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-accent-300">Confirme seu e-mail para receber alertas</p>
          <p className="mt-0.5 text-sm text-radar-muted">
            Enquanto <strong className="text-radar-text">{email}</strong> não for confirmado, seus filtros continuam
            salvos, mas <strong className="text-radar-text">nenhum aviso é enviado</strong>.
            {sent && " Reenviamos o link — confira a caixa de entrada e o spam."}
          </p>
        </div>
        <Button variant="accent" size="sm" className="shrink-0" onClick={resend} loading={sending}>
          Reenviar confirmação
        </Button>
      </div>
    </div>
  );
}
