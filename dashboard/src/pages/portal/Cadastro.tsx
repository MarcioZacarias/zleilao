import { FormEvent, useState } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";
import { MailCheck } from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { Button } from "../../components/ui/Button";
import { AuthError, AuthNotice, AuthShell, Field, safeNext } from "../../components/portal/AuthShell";
import { errorMessage, httpStatus } from "../../services/api";
import { publicAuthApi } from "../../services/account";
import { isValidPhone, maskPhone, phoneDigits } from "../../lib/format";
import type { RegisterResponse } from "../../services/types";

const MIN_PASSWORD = 8;

export default function Cadastro() {
  const [sp] = useSearchParams();
  const { token, loading: authLoading } = useAuth();
  useDocumentTitle("Criar conta");

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState<RegisterResponse | null>(null);
  const [resending, setResending] = useState(false);
  const [resent, setResent] = useState("");

  const next = safeNext(sp.get("next"));

  if (!authLoading && token && !done) {
    return <Navigate to="/conta" replace />;
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    if (password.length < MIN_PASSWORD) {
      setError(`A senha precisa ter ao menos ${MIN_PASSWORD} caracteres.`);
      return;
    }
    if (phone && !isValidPhone(phone)) {
      setError("Telefone inválido. Informe DDD + número.");
      return;
    }
    setLoading(true);
    try {
      const res = await publicAuthApi.register({
        name: name.trim(),
        email: email.trim(),
        password,
        phone: phone ? phoneDigits(phone) : null,
      });
      setDone(res);
    } catch (err) {
      // 409 não confirma nem nega o cadastro: mensagem neutra (RN-006).
      if (httpStatus(err) === 409) {
        setError(
          errorMessage(err, "Não foi possível criar a conta com esse e-mail") +
            ". Se a conta já existe, entre ou recupere a senha."
        );
      } else {
        setError(errorMessage(err, "Não foi possível criar a conta agora"));
      }
      setLoading(false);
    }
  };

  const resend = async () => {
    setResending(true);
    setResent("");
    try {
      const r = await publicAuthApi.resendVerification(email.trim());
      setResent(r.detail ?? "Se houver uma conta com esse e-mail, enviamos o link.");
    } catch (err) {
      setResent(errorMessage(err, "Não foi possível reenviar agora."));
    }
    setResending(false);
  };

  if (done) {
    return (
      <AuthShell
        title="Conta criada"
        subtitle="Falta só confirmar o seu e-mail."
        footer={
          <Link to={`/entrar${next ? `?next=${encodeURIComponent(next)}` : ""}`} className="font-medium text-accent hover:underline">
            Ir para o login
          </Link>
        }
      >
        <div className="space-y-4">
          <div className="flex items-start gap-3 rounded-lg bg-radar-surface2/60 px-3 py-3">
            <MailCheck size={20} className="mt-0.5 shrink-0 text-accent" />
            <p className="text-sm text-radar-text/90">{done.detail}</p>
          </div>

          {done.verification_required && (
            <p className="text-sm text-radar-muted">
              Enquanto o e-mail <strong className="text-radar-text">{email}</strong> não for confirmado, a conta funciona
              normalmente, mas <strong className="text-radar-text">nenhum alerta é enviado</strong>. Abra o link que
              enviamos para liberar os avisos.
            </p>
          )}

          {done.verification_required && (
            <div className="space-y-2">
              <Button variant="outline-dark" className="w-full" onClick={resend} loading={resending}>
                Reenviar confirmação
              </Button>
              {resent && <AuthNotice tone="info">{resent}</AuthNotice>}
            </div>
          )}
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Criar conta gratuita"
      subtitle="Salve buscas e receba um aviso quando aparecer o lote que você procura."
      footer={
        <>
          Já tem conta?{" "}
          <Link
            to={`/entrar${next ? `?next=${encodeURIComponent(next)}` : ""}`}
            className="font-medium text-accent hover:underline"
          >
            Entrar
          </Link>
        </>
      }
    >
      <form onSubmit={submit} className="space-y-4">
        <Field id="name" label="Nome">
          <input
            id="name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            minLength={2}
            autoFocus
            autoComplete="name"
            className="portal-input"
            placeholder="Como devemos te chamar"
          />
        </Field>

        <Field id="email" label="E-mail">
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
            className="portal-input"
            placeholder="voce@email.com.br"
          />
        </Field>

        <Field id="password" label="Senha" hint={`Mínimo de ${MIN_PASSWORD} caracteres.`}>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={MIN_PASSWORD}
            autoComplete="new-password"
            className="portal-input"
            placeholder="••••••••"
          />
        </Field>

        <Field
          id="phone"
          label="Telefone (opcional)"
          hint="Só é usado se você ativar alertas por WhatsApp na sua conta."
        >
          <input
            id="phone"
            type="tel"
            inputMode="numeric"
            value={phone}
            onChange={(e) => setPhone(maskPhone(e.target.value))}
            autoComplete="tel"
            className="portal-input"
            placeholder="(11) 98765-4321"
          />
        </Field>

        {error && <AuthError>{error}</AuthError>}

        <Button type="submit" variant="accent" size="lg" className="w-full" loading={loading}>
          Criar conta
        </Button>

        <p className="text-center text-xs leading-relaxed text-radar-muted/80">
          Somos um agregador: não realizamos leilões nem intermediamos lances. Os alertas apontam sempre para a fonte
          oficial do lote.
        </p>
      </form>
    </AuthShell>
  );
}
