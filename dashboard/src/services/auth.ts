import api from "./api";
import type { LoginResponse, MeResponse } from "./types";

export const authApi = {
  login: (email: string, password: string) =>
    api.post<LoginResponse>("/auth/login", { email, password }).then((r) => r.data),
  me: () => api.get<MeResponse>("/auth/me").then((r) => r.data),
  changePassword: (current_password: string, new_password: string) =>
    api
      .post<{ status: string }>("/auth/change-password", { current_password, new_password })
      .then((r) => r.data),
};
