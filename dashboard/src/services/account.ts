import api from "./api";
import type {
  AccountMe,
  AccountUpdate,
  FilterPreview,
  MyAlert,
  RegisterResponse,
  ResetPasswordResponse,
  SavedFilter,
  SavedFilterInput,
  SavedFilterList,
  SimpleStatus,
  VerifyEmailResponse,
} from "./types";

/** Rotas públicas de conta: cadastro, verificação e recuperação de senha. */
export const publicAuthApi = {
  register: (body: { name: string; email: string; password: string; phone?: string | null }) =>
    api.post<RegisterResponse>("/auth/register", body).then((r) => r.data),
  /** O backend recebe o token como query string, não no corpo. */
  verifyEmail: (token: string) =>
    api.post<VerifyEmailResponse>("/auth/verify-email", null, { params: { token } }).then((r) => r.data),
  resendVerification: (email: string) =>
    api.post<SimpleStatus>("/auth/resend-verification", { email }).then((r) => r.data),
  forgotPassword: (email: string) =>
    api.post<SimpleStatus>("/auth/forgot-password", { email }).then((r) => r.data),
  resetPassword: (token: string, new_password: string) =>
    api.post<ResetPasswordResponse>("/auth/reset-password", { token, new_password }).then((r) => r.data),
};

/** Conta do assinante (exige token de qualquer papel). */
export const accountApi = {
  me: () => api.get<AccountMe>("/me").then((r) => r.data),
  update: (body: AccountUpdate) => api.patch<AccountMe>("/me", body).then((r) => r.data),
  changePassword: (current_password: string, new_password: string) =>
    api.post<SimpleStatus>("/me/change-password", { current_password, new_password }).then((r) => r.data),

  filters: () => api.get<SavedFilterList>("/me/filters").then((r) => r.data),
  createFilter: (body: SavedFilterInput) => api.post<SavedFilter>("/me/filters", body).then((r) => r.data),
  updateFilter: (id: number, body: SavedFilterInput) =>
    api.put<SavedFilter>(`/me/filters/${id}`, body).then((r) => r.data),
  deleteFilter: (id: number) => api.delete<SimpleStatus>(`/me/filters/${id}`).then((r) => r.data),
  previewFilter: (id: number, limit = 6) =>
    api.get<FilterPreview>(`/me/filters/${id}/preview`, { params: { limit } }).then((r) => r.data),

  alerts: (limit = 50) => api.get<MyAlert[]>("/me/alerts", { params: { limit } }).then((r) => r.data),
};
