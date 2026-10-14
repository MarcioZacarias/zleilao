import api from "./api";
import type { LlmTestResult, SettingsResponse, TestSendResult } from "./types";

export type BrandingKey = "logo_dark" | "logo_light" | "favicon";

export const settingsApi = {
  list: () => api.get<SettingsResponse>("/settings").then((r) => r.data),
  save: (settings: Record<string, string>) =>
    api.put<{ status: string; updated: number }>("/settings", { settings }).then((r) => r.data),
  testLlm: () => api.post<LlmTestResult>("/settings/test-llm", null, { timeout: 60000 }).then((r) => r.data),
  /** Envia uma mensagem real para o destinatário informado. */
  testEmail: (to: string) =>
    api.post<TestSendResult>("/settings/test-email", { to }, { timeout: 60000 }).then((r) => r.data),
  /** `to` é o telefone com DDD. */
  testWhatsapp: (to: string) =>
    api.post<TestSendResult>("/settings/test-whatsapp", { to }, { timeout: 60000 }).then((r) => r.data),
};

export const brandingApi = {
  upload: (key: BrandingKey, file: File) => {
    const form = new FormData();
    form.append("key", key);
    form.append("file", file);
    return api
      .post<{ key: string; mimetype: string; size: number; url: string }>("/branding/upload", form, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      .then((r) => r.data);
  },
  remove: (key: BrandingKey) => api.delete(`/branding/${key}`).then((r) => r.data),
  /** URL pública do asset, na mesma origem da API: o nginx local ou o Worker. */
  url: (key: BrandingKey, bust = true) =>
    `${api.defaults.baseURL ?? "/api"}/branding/${key}${bust ? `?t=${Date.now()}` : ""}`,
};
