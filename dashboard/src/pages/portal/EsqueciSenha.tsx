import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { MailCheck } from "lucide-react";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { Button } from "../../components/ui/Button";
import { AuthError, AuthShell, Field } from "../../components/portal/AuthShell";
import { publicAuthApi } from "../../services/account";
import { errorMessage } from "../../services/api";

export default function EsqueciSenha() {
  useDocumentTitle("Recuperar senha");
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState("");
  const [error, setError] = useState("");

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const r = await publicAuthApi.forgotPassword(email.trim());
      // A resposta é sempre a mesma: não revela se a conta existe.
      setSent(r.detail ?? "Se houver uma conta com esse e-mail, enviamos o link.");
    } catch (err) {
      setError(errorMessage(err, "Não foi possível processar o pedido agora."));
    }
    setLoading(false);
  };

  return (
    <AuthShell
      title="Recuperar senha"
      subtitle="Informe o e-mail da conta e enviaremos um link para criar uma nova senha."
      footer={
        <>
          Lembrou a senha?{" "}
          <Link to="/entrar" className="font-medium text-accent hover:underline">
            Voltar ao login
          </Link>
        </>
      }
    >
      {sent ? (
        <div className="space-y-4">
          <div className="flex items-start gap-3 rounded-lg bg-radar-surface2/60 px-3 py-3">
            <MailCheck size={20} className="mt-0.5 shrink-0 text-accent" />
            <p className="text-sm text-radar-text/90">{sent}</p>
          </div>
          <p className="text-sm text-radar-muted">
            O link vale por tempo limitado e só pode ser usado uma vez. Confira também a caixa de spam.
          </p>
          <Button variant="outline-dark" className="w-full" onClick={() => setSent("")}>
            Usar outro e-mail
          </Button>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <Field id="email" label="E-mail da conta">
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoFocus
              autoComplete="email"
              className="portal-input"
              placeholder="voce@email.com.br"
            />
          </Field>

          {error && <AuthError>{error}</AuthError>}

          <Button type="submit" variant="accent" size="lg" className="w-full" loading={loading}>
            Enviar link de recuperação
          </Button>
        </form>
      )}
    </AuthShell>
  );
}
