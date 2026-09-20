import { createContext, useContext, useState, useEffect, ReactNode, useCallback } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { TOKEN_KEY, UNAUTHORIZED_EVENT, setAuthToken } from "../services/api";
import { authApi } from "../services/auth";
import type { LoginResponse } from "../services/types";

interface AuthUser {
  email: string;
  name: string | null;
  role: string | null;
}

interface AuthContextType {
  user: AuthUser | null;
  token: string | null;
  loading: boolean;
  /** true quando o token pertence a um administrador. */
  isAdmin: boolean;
  /** Devolve a resposta do login para quem precisa rotear pelo papel. */
  login: (email: string, password: string) => Promise<LoginResponse>;
  /** Abre sessão a partir de um token já emitido (ex.: redefinir senha). */
  applySession: (res: LoginResponse) => void;
  /** Atualiza nome/papel depois de o assinante editar o perfil. */
  patchUser: (patch: Partial<AuthUser>) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  token: null,
  loading: true,
  isAdmin: false,
  login: async () => {
    throw new Error("AuthProvider ausente");
  },
  applySession: () => {},
  patchUser: () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));
  const [loading, setLoading] = useState(!!localStorage.getItem(TOKEN_KEY));
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    const saved = localStorage.getItem(TOKEN_KEY);
    if (!saved) {
      setLoading(false);
      return;
    }
    setAuthToken(saved);
    authApi
      .me()
      .then((me) => setUser({ email: me.email, name: me.name, role: me.role }))
      .catch(() => {
        setAuthToken(null);
        setToken(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const logout = useCallback(() => {
    setAuthToken(null);
    setToken(null);
    setUser(null);
  }, []);

  // 401 vindo do interceptor: derruba a sessão e devolve cada área ao seu
  // login — o admin para /login, o assinante para /entrar.
  useEffect(() => {
    const handler = () => {
      setToken(null);
      setUser(null);
      const path = window.location.pathname;
      if (path.startsWith("/admin")) {
        navigate("/login", { replace: true, state: { from: path } });
      } else if (path.startsWith("/conta")) {
        navigate(`/entrar?next=${encodeURIComponent(path + window.location.search)}`, { replace: true });
      }
    };
    window.addEventListener(UNAUTHORIZED_EVENT, handler);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handler);
  }, [navigate, location.pathname]);

  const applySession = useCallback((res: LoginResponse) => {
    setAuthToken(res.access_token);
    setToken(res.access_token);
    setUser({ email: res.user_email, name: res.user_name, role: res.role });
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const res = await authApi.login(email, password);
      applySession(res);
      return res;
    },
    [applySession]
  );

  const patchUser = useCallback((patch: Partial<AuthUser>) => {
    setUser((u) => (u ? { ...u, ...patch } : u));
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        loading,
        isAdmin: user?.role === "admin",
        login,
        applySession,
        patchUser,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
