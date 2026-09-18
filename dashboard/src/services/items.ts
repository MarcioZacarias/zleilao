import api from "./api";
import type { AdminItemsParams, ItemAdmin, ItemAdminPage, ItemsSummary, ItemUpdate } from "./types";

function clean<T extends object>(params: T): Record<string, string | number> {
  const out: Record<string, string | number> = {};
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    out[k] = v as string | number;
  }
  return out;
}

export const itemsApi = {
  list: (params: AdminItemsParams) =>
    api.get<ItemAdminPage>("/items", { params: clean(params) }).then((r) => r.data),
  summary: () => api.get<ItemsSummary>("/items/summary").then((r) => r.data),
  get: (id: number) => api.get<ItemAdmin>(`/items/${id}`).then((r) => r.data),
  update: (id: number, body: ItemUpdate) => api.patch<ItemAdmin>(`/items/${id}`, body).then((r) => r.data),
  remove: (id: number) => api.delete(`/items/${id}`).then((r) => r.data),
  renormalize: (id: number) =>
    api.post<ItemAdmin>(`/items/${id}/renormalize`, null, { timeout: 120000 }).then((r) => r.data),
  publish: (id: number) => api.post<ItemAdmin>(`/items/${id}/publish`).then((r) => r.data),
  hide: (id: number) => api.post<ItemAdmin>(`/items/${id}/hide`).then((r) => r.data),
};
