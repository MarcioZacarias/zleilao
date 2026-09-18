import api from "./api";
import type { ParserInfo, Source, SourceInput, SourceTestResult } from "./types";

export const sourcesApi = {
  list: () => api.get<Source[]>("/sources").then((r) => r.data),
  parsers: () => api.get<ParserInfo[]>("/sources/parsers").then((r) => r.data),
  get: (id: number) => api.get<Source>(`/sources/${id}`).then((r) => r.data),
  create: (body: SourceInput) => api.post<Source>("/sources", body).then((r) => r.data),
  update: (id: number, body: Partial<SourceInput>) =>
    api.put<Source>(`/sources/${id}`, body).then((r) => r.data),
  remove: (id: number) => api.delete(`/sources/${id}`).then((r) => r.data),
  run: (id: number) => api.post<{ status: string }>(`/sources/${id}/run`).then((r) => r.data),
  test: (id: number) =>
    api.post<SourceTestResult>(`/sources/${id}/test`, null, { timeout: 120000 }).then((r) => r.data),
  reactivate: (id: number) => api.post<Source>(`/sources/${id}/reactivate`).then((r) => r.data),
};
