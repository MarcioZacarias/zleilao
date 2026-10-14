import { useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { Loader2, ArrowLeft } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useBranding } from "../hooks/useBranding";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import { Button } from "../components/ui/Button";
import { errorMessage } from "../services/api";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { login, token, loading: authLoading } = useAuth();
  const branding = useBranding();
  const navigate = useNavigate();
  const location = useLocation();
  useDocumentTitle("Entrar");

  const from = (location.state as { from?: string } | null)?.from;

  if (!authLoading && token) {
    return <Navigate to={from && from.startsWith("/admin") ? from : "/admin"} replace />;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
      navigate(from && from.startsWith("/admin") ? from : "/admin", { replace: true });
    } catch (err) {
      setError(errorMessage(err, "E-mail ou senha incorretos"));
    }
    setLoading(false);
  };

  return (
    <div className="portal flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <img src={branding.logo_dark} alt={branding.site_title} className="mx-auto h-20 w-auto object-contain" />
          <p className="mt-3 text-sm text-radar-muted">Acesso ao painel administrativo</p>
        </div>

        <form onSubmit={handleSubmit} className="portal-card space-y-4 p-6">
          <div>
            <label className="mb-1 block text-sm font-medium text-radar-text/90" htmlFor="email">
              E-mail
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoFocus
              autoComplete="username"
              className="portal-input"
              placeholder="voce@empresa.com.br"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-radar-text/90" htmlFor="password">
              Senha
            </label>
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
          </div>

          {error && (
            <div className="rounded-lg border border-red-400/30 bg-red-500/10 px-3 py-2 text-sm text-red-300" role="alert">
              {error}
            </div>
          )}

          <Button type="submit" variant="accent" className="w-full" size="lg" disabled={loading}>
            {loading ? <Loader2 size={18} className="animate-spin" /> : "Entrar"}
          </Button>
        </form>

        <div className="mt-6 text-center">
          <Link to="/" className="inline-flex items-center gap-1 text-sm text-radar-muted hover:text-radar-text">
            <ArrowLeft size={14} /> Voltar ao portal
          </Link>
        </div>
      </div>
    </div>
  );
}
