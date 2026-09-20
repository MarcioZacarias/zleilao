import { FormEvent, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "../../context/AuthContext";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { Button } from "../../components/ui/Button";
import { AuthError, AuthShell, Field } from "../../components/portal/AuthShell";
import { publicAuthApi } from "../../services/account";
import { errorMessage } from "../../services/api";

const MIN_PASSWORD = 8;

export default function RedefinirSenha() {
  const [sp] = useSearchParams();
  const token = sp.get("token");
  const { applySession } = useAuth();
  const navigate = useNavigate();
  useDocumentTitle("Nova senha");

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    if (!token) {
      setError("Link sem token. Peça um novo e-mail de recuperação.");
      return;
    }
    if (password.length < MIN_PASSWORD) {
      setError(`A senha precisa ter ao menos ${MIN_PASSWORD} caracteres.`);
      return;
    }
    if (password !== confirm) {
      setError("As senhas não conferem.");
      return;
    }
    setLoading(true);
    try {
      // A API devolve o token de acesso: o usuário já entra logado.
      const res = await publicAuthApi.resetPassword(token, password);
      applySession(res);
      toast.success("Senha alterada. Você já está conectado.");
      navigate(res.role === "admin" ? "/admin" : "/conta", { replace: true });
    } catch (err) {
      setError(errorMessage(err, "Link inválido ou expirado. Peça um novo."));
      setLoading(false);
    }
  };

  return (
    <AuthShell
      title="Criar nova senha"
      subtitle="Escolha uma senha nova para a sua conta."
      footer={
        <>
          Link expirado?{" "}
          <Link to="/esqueci-senha" className="font-medium text-accent hover:underline">
            Pedir outro e-mail
          </Link>
        </>
      }
    >
      <form onSubmit={submit} className="space-y-4">
        {!token && <AuthError>Link sem token. Peça um novo e-mail de recuperação.</AuthError>}

        <Field id="password" label="Nova senha" hint={`Mínimo de ${MIN_PASSWORD} caracteres.`}>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={MIN_PASSWORD}
            autoFocus
            autoComplete="new-password"
            className="portal-input"
            placeholder="••••••••"
          />
        </Field>

        <Field id="confirm" label="Repita a nova senha">
          <input
            id="confirm"
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
            minLength={MIN_PASSWORD}
            autoComplete="new-password"
            className="portal-input"
            placeholder="••••••••"
          />
        </Field>

        {error && <AuthError>{error}</AuthError>}

        <Button type="submit" variant="accent" size="lg" className="w-full" loading={loading} disabled={!token}>
          Salvar e entrar
        </Button>
      </form>
    </AuthShell>
  );
}
