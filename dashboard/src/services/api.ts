import axios from "axios";

export const TOKEN_KEY = "zleilao_token";
export const UNAUTHORIZED_EVENT = "zleilao:unauthorized";

/**
 * Onde fica a API.
 *
 * No Docker o nginx do container faz o proxy de `/api` para o backend, e o
 * padrão relativo serve. Publicado no Cloudflare Pages não há nginx: o build
 * recebe a URL do Worker em `VITE_API_URL` e fala direto com ela.
 */
const BASE = import.meta.env.VITE_API_URL || "/api";

/**
 * Verdadeiro no build publicado na Cloudflare. O painel usa para esconder o
 * que só existe no backend local (ver `Sidebar`).
 */
export const NA_BORDA = Boolean(import.meta.env.VITE_API_URL);

const api = axios.create({
  baseURL: BASE,
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

// Rotas que nunca derrubam a sessão: a vitrine e todo o fluxo público de
// conta (login, cadastro, verificação de e-mail, recuperação de senha).
// `/auth/me` e `/auth/change-password` ficam de fora de propósito — ali um
// 401 significa mesmo token inválido.
const PUBLIC_PREFIXES = [
  "/portal",
  "/auth/login",
  "/auth/register",
  "/auth/verify-email",
  "/auth/resend-verification",
  "/auth/forgot-password",
  "/auth/reset-password",
];

// 401 global: sessão expirada/invalidada. O AuthContext escuta o evento e
// redireciona conforme a área. 403 NÃO desloga: é falta de permissão
// (assinante tentando rota de operação), e a tela mostra "acesso restrito".
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status: number | undefined = error?.response?.status;
    const url: string = error?.config?.url ?? "";
    const isPublic = PUBLIC_PREFIXES.some((p) => url.startsWith(p));
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
    if (err.response?.status === 403) return "Acesso restrito";
    if (err.response?.status === 404) return "Não encontrado";
    if (err.response?.status === 409) return "Conflito: operação não permitida";
    if (err.response?.status === 503) return "Serviço indisponível";
    if (err.message) return err.message;
  }
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

/** Status HTTP de um erro axios, quando houver resposta. */
export function httpStatus(err: unknown): number | undefined {
  return axios.isAxiosError(err) ? err.response?.status : undefined;
}

/** 403 = acesso restrito / limite de plano. Nunca desloga. */
export function isForbidden(err: unknown): boolean {
  return httpStatus(err) === 403;
}

export default api;
