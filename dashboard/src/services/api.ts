import axios from "axios";

export const TOKEN_KEY = "zleilao_token";
export const UNAUTHORIZED_EVENT = "zleilao:unauthorized";

const api = axios.create({
  baseURL: "/api",
  timeout: 30000,
  headers: {
    "Content-Type": "application/json",
  },
});

const saved = localStorage.getItem(TOKEN_KEY);
if (saved) {
  api.defaults.headers.common["Authorization"] = `Bearer ${saved}`;
}

export function setAuthToken(token: string | null) {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
    api.defaults.headers.common["Authorization"] = `Bearer ${token}`;
  } else {
    localStorage.removeItem(TOKEN_KEY);
    delete api.defaults.headers.common["Authorization"];
  }
}

// 401 global: só interessa ao admin. Rotas públicas (/portal, /auth/login)
// nunca disparam logout; o AuthContext escuta o evento e redireciona.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status: number | undefined = error?.response?.status;
    const url: string = error?.config?.url ?? "";
    const isPublic = url.startsWith("/portal") || url.startsWith("/auth/login");
    if (status === 401 && !isPublic) {
      setAuthToken(null);
      window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT));
    }
    return Promise.reject(error);
  }
);

/** Extrai uma mensagem legível de um erro axios/HTTP. */
export function errorMessage(err: unknown, fallback = "Ocorreu um erro inesperado"): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d: { msg?: string; loc?: unknown[] }) => d.msg ?? JSON.stringify(d))
        .join("; ");
    }
    if (err.response?.status === 404) return "Não encontrado";
    if (err.response?.status === 409) return "Conflito: operação não permitida";
    if (err.response?.status === 503) return "Serviço indisponível";
    if (err.message) return err.message;
  }
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

export default api;
