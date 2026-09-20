import { FormEvent, useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { Button } from "../../components/ui/Button";
import { AuthError, AuthShell, Field, safeNext } from "../../components/portal/AuthShell";
import { errorMessage } from "../../services/api";

/** Login do assinante (o /login é a porta do administrador). */
export default function Entrar() {
  const [sp] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { login, token, user, loading: authLoading } = useAuth();
  const navigate = useNavigate();
  useDocumentTitle("Entrar");

  const next = safeNext(sp.get("next"));

  // Já logado: vai direto para o destino (ou para a área certa do papel).
  if (!authLoading && token && user) {
    return <Navigate to={next ?? (user.role === "admin" ? "/admin" : "/conta")} replace />;
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await login(email, password);
      navigate(next ?? (res.role === "admin" ? "/admin" : "/conta"), { replace: true });
    } catch (err) {
      setError(errorMessage(err, "E-mail ou senha incorretos"));
      setLoading(false);
    }
  };

  return (
    <AuthShell
      title="Entrar na sua conta"
      subtitle="Acompanhe seus filtros salvos e receba alertas dos lotes que interessam."
      footer={
        <>
          Ainda não tem conta?{" "}
          <Link
            to={`/cadastro${next ? `?next=${encodeURIComponent(next)}` : ""}`}
            className="font-medium text-accent hover:underline"
          >
            Criar conta gratuita
          </Link>
        </>
      }
    >
      <form onSubmit={submit} className="space-y-4">
        <Field id="email" label="E-mail">
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoFocus
            autoComplete="username"
            className="portal-input"
            placeholder="voce@email.com.br"
          />
        </Field>

        <Field id="password" label="Senha">
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
            className="portal-input"
            placeholder="••••••••"
          />
        </Field>

        <div className="flex justify-end">
          <Link to="/esqueci-senha" className="text-xs text-radar-muted hover:text-accent">
            Esqueci minha senha
          </Link>
        </div>

        {error && <AuthError>{error}</AuthError>}

        <Button type="submit" variant="accent" size="lg" className="w-full" loading={loading}>
          Entrar
        </Button>
      </form>
    </AuthShell>
  );
}
