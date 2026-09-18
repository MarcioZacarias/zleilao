import { createContext, useContext, useState, useEffect, ReactNode, useCallback } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { TOKEN_KEY, UNAUTHORIZED_EVENT, setAuthToken } from "../services/api";
import { authApi } from "../services/auth";

interface AuthUser {
  email: string;
  name: string | null;
  role: string | null;
}

interface AuthContextType {
  user: AuthUser | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  token: null,
  loading: true,
  login: async () => {},
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

  // 401 vindo do interceptor: só o admin sofre logout + redirect.
  useEffect(() => {
    const handler = () => {
      setToken(null);
      setUser(null);
      if (window.location.pathname.startsWith("/admin")) {
        navigate("/login", { replace: true, state: { from: window.location.pathname } });
      }
    };
    window.addEventListener(UNAUTHORIZED_EVENT, handler);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handler);
  }, [navigate, location.pathname]);

  const login = async (email: string, password: string) => {
    const res = await authApi.login(email, password);
    setAuthToken(res.access_token);
    setToken(res.access_token);
    setUser({ email: res.user_email, name: res.user_name, role: res.role });
  };

  return (
    <AuthContext.Provider value={{ user, token, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
