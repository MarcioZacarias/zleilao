import { FormEvent, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { Button } from "../../components/ui/Button";
import { AuthError, AuthNotice, AuthShell, Field } from "../../components/portal/AuthShell";
import { publicAuthApi } from "../../services/account";
import { errorMessage } from "../../services/api";

type State = "checking" | "ok" | "error" | "missing";

export default function VerificarEmail() {
  const [sp] = useSearchParams();
  const token = sp.get("token");
  const { token: session } = useAuth();
  useDocumentTitle("Confirmar e-mail");

  const [state, setState] = useState<State>(token ? "checking" : "missing");
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [resendEmail, setResendEmail] = useState("");
  const [resending, setResending] = useState(false);
  const [resent, setResent] = useState("");
  // StrictMode monta duas vezes em dev e o token é de uso único: a segunda
  // chamada devolveria 400 e a tela mostraria "link inválido" sem motivo.
  const fired = useRef(false);

  useEffect(() => {
    if (!token || fired.current) return;
    fired.current = true;
    publicAuthApi
      .verifyEmail(token)
      .then((r) => {
        setEmail(r.email);
        setState("ok");
      })
      .catch((err) => {
        setError(errorMessage(err, "Link inválido ou expirado. Peça um novo."));
        setState("error");
      });
  }, [token]);

  const resend = async (e: FormEvent) => {
    e.preventDefault();
    setResending(true);
    setResent("");
    try {
      const r = await publicAuthApi.resendVerification(resendEmail.trim());
      setResent(r.detail ?? "Se houver uma conta com esse e-mail, enviamos o link.");
    } catch (err) {
      setResent(errorMessage(err, "Não foi possível reenviar agora."));
    }
    setResending(false);
  };

  return (
    <AuthShell
      title="Confirmação de e-mail"
      footer={
        state === "ok" ? (
          <Link to={session ? "/conta" : "/entrar"} className="font-medium text-accent hover:underline">
            {session ? "Ir para minha conta" : "Entrar na conta"}
          </Link>
        ) : (
          <Link to="/entrar" className="font-medium text-accent hover:underline">
            Voltar ao login
          </Link>
        )
      }
    >
      {state === "checking" && (
        <div className="flex items-center justify-center gap-3 py-6 text-sm text-radar-muted">
          <Loader2 size={18} className="animate-spin text-accent" /> Confirmando seu e-mail…
        </div>
      )}

      {state === "ok" && (
        <div className="space-y-4 text-center">
          <CheckCircle2 size={44} className="mx-auto text-emerald-400" />
          <div>
            <p className="font-semibold text-radar-text">E-mail confirmado</p>
            <p className="mt-1 text-sm text-radar-muted">
              {email ? (
                <>
                  <strong className="text-radar-text">{email}</strong> está verificado. A partir de agora seus filtros
                  salvos podem enviar alertas.
                </>
              ) : (
                "Sua conta está verificada e já pode receber alertas."
              )}
            </p>
          </div>
          <Link to={session ? "/conta" : "/entrar"}>
            <Button variant="accent" className="w-full">
              {session ? "Ir para minha conta" : "Entrar na conta"}
            </Button>
          </Link>
        </div>
      )}

      {(state === "error" || state === "missing") && (
        <div className="space-y-4">
          <div className="text-center">
            <XCircle size={40} className="mx-auto text-red-400" />
            <p className="mt-3 font-semibold text-radar-text">
              {state === "missing" ? "Link sem token" : "Não foi possível confirmar"}
            </p>
          </div>
          <AuthError>
            {state === "missing"
              ? "Abra o link exatamente como ele chegou no e-mail, ou peça um novo abaixo."
              : error}
          </AuthError>

          <form onSubmit={resend} className="space-y-3 border-t border-radar-border pt-4">
            <Field id="resend-email" label="Reenviar a confirmação para">
              <input
                id="resend-email"
                type="email"
                value={resendEmail}
                onChange={(e) => setResendEmail(e.target.value)}
                required
                className="portal-input"
                placeholder="voce@email.com.br"
              />
            </Field>
            <Button type="submit" variant="outline-dark" className="w-full" loading={resending}>
              Reenviar confirmação
            </Button>
            {resent && <AuthNotice tone="info">{resent}</AuthNotice>}
          </form>
        </div>
      )}
    </AuthShell>
  );
}
