import api from "./api";
import type {
  AdminAlert,
  AdminSavedFilter,
  PlanUpdateInput,
  UserAdmin,
  UserAdminUpdate,
  UsersPage,
  UsersSummary,
} from "./types";

export interface UsersParams {
  q?: string;
  plan?: string;
  page?: number;
  page_size?: number;
}

function clean<T extends object>(params: T): Record<string, string | number> {
  const out: Record<string, string | number> = {};
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    out[k] = v as string | number;
  }
  return out;
}

export const usersApi = {
  list: (params: UsersParams) => api.get<UsersPage>("/users", { params: clean(params) }).then((r) => r.data),
  summary: () => api.get<UsersSummary>("/users/summary").then((r) => r.data),
  update: (id: number, body: UserAdminUpdate) => api.patch<UserAdmin>(`/users/${id}`, body).then((r) => r.data),
  setPlan: (id: number, body: PlanUpdateInput) => api.put<UserAdmin>(`/users/${id}/plan`, body).then((r) => r.data),
  filters: (id: number) => api.get<AdminSavedFilter[]>(`/users/${id}/filters`).then((r) => r.data),
};

export interface AlertsParams {
  status?: string;
  user_id?: number;
  limit?: number;
}

export const alertsApi = {
  list: (params: AlertsParams) => api.get<AdminAlert[]>("/alerts", { params: clean(params) }).then((r) => r.data),
  retry: (id: number) => api.post<{ status: string; id: number }>(`/alerts/${id}/retry`).then((r) => r.data),
};
