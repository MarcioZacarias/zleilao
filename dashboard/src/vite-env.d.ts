/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** E-mail do suporte. A ativação do plano pago é manual (não há gateway):
   *  quando definido, a conta oferece um `mailto:` já preenchido. */
  readonly VITE_SUPPORT_EMAIL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
