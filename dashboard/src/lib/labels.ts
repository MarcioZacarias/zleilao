// Rótulos pt-BR para os enums do contrato (docs/API.md).

export const STATUS_LABELS: Record<string, string> = {
  collected: "Coletado",
  review: "Em revisão",
  published: "Aberto",
  auction_soon: "Pregão em breve",
  closed: "Encerrado",
  withdrawn: "Retirado",
  possibly_withdrawn: "Possivelmente retirado",
};

/** Rótulos técnicos para o admin (published = "Publicado"). */
export const STATUS_LABELS_ADMIN: Record<string, string> = {
  ...STATUS_LABELS,
  published: "Publicado",
};

export const EXTRACTION_LABELS: Record<string, string> = {
  pending: "Pendente",
  done: "Concluída",
  failed: "Falhou",
  review: "Revisão",
  skipped: "Ignorada",
};

export const PRICE_KIND_LABELS: Record<string, string> = {
  lance_inicial: "Lance inicial",
  lance_atual: "Lance atual",
  avaliacao: "Avaliação",
  preco_pedido: "Preço pedido",
};

export const CONDITION_LABELS: Record<string, string> = {
  normal: "Normal",
  sinistro_recuperavel: "Sinistro recuperável",
  sinistro_media_monta: "Sinistro média monta",
  sinistro_grande_monta: "Sinistro grande monta",
  sucata: "Sucata",
  nao_informado: "Não informado",
};

export const SESSION_KIND_LABELS: Record<string, string> = {
  "1a_praca": "1ª praça",
  "2a_praca": "2ª praça",
  unica: "Sessão única",
  repasse: "Repasse",
  condicional: "Condicional",
};

export const AUCTION_TYPE_LABELS: Record<string, string> = {
  judicial: "Judicial",
  extrajudicial: "Extrajudicial",
};

export const MODALITY_LABELS: Record<string, string> = {
  online: "Online",
  presencial: "Presencial",
  hibrido: "Híbrido",
};

/**
 * Valores de enum dos campos dinâmicos (items.attributes), usados onde não há
 * o field_def à mão — como nos chips do card da vitrine.
 */
export const ENUM_VALUE_LABELS: Record<string, string> = {
  ...CONDITION_LABELS,
  // origem
  financeira: "Financeira",
  seguradora: "Seguradora",
  judicial: "Judicial",
  frota: "Frota",
  locadora: "Locadora",
  particular: "Particular",
  // combustível
  gasolina: "Gasolina",
  etanol: "Etanol",
  flex: "Flex",
  diesel: "Diesel",
  gnv: "GNV",
  eletrico: "Elétrico",
  hibrido: "Híbrido",
  // câmbio
  manual: "Manual",
  automatico: "Automático",
  automatizado: "Automatizado",
  cvt: "CVT",
  // documento
  crlv_disponivel: "CRLV disponível",
  sem_documento: "Sem documento",
  documento_pendente: "Documento pendente",
  // laudo
  aprovado: "Laudo aprovado",
  reprovado: "Laudo reprovado",
};

export const HEALTH_LABELS: Record<string, string> = {
  ok: "Saudável",
  suspended: "Suspensa",
  unknown: "Desconhecido",
};

export const INCIDENT_KIND_LABELS: Record<string, string> = {
  zero_items: "Zero itens",
  abnormal_variation: "Variação anormal",
  parser_error: "Erro de parser",
  http_error: "Erro HTTP",
  robots_disallowed: "Bloqueado por robots.txt",
  scraping_not_allowed: "Coleta não permitida",
};

export const INCIDENT_STATUS_LABELS: Record<string, string> = {
  open: "Aberto",
  acknowledged: "Reconhecido",
  resolved: "Resolvido",
};

export const DUPLICATE_STATUS_LABELS: Record<string, string> = {
  suspected: "Suspeito",
  confirmed: "Confirmado",
  rejected: "Rejeitado",
};

export const JOB_TYPE_LABELS: Record<string, string> = {
  scrape: "Coleta",
  scrape_tick: "Coleta",
  normalize: "Normalização",
  lifecycle: "Ciclo de vida",
  dedup: "Deduplicação",
  cleanup: "Limpeza",
  match: "Casamento de filtros",
  dispatch: "Envio de alertas",
};

export const JOB_STATUS_LABELS: Record<string, string> = {
  running: "Executando",
  success: "Sucesso",
  failed: "Falhou",
  skipped: "Ignorado",
};

export const FIELD_TYPE_LABELS: Record<string, string> = {
  string: "Texto",
  int: "Inteiro",
  decimal: "Decimal",
  bool: "Sim/Não",
  enum: "Lista",
  date: "Data",
};

export const SOURCE_KIND_LABELS: Record<string, string> = {
  auction: "Leilão",
  marketplace: "Marketplace",
};

export const SORT_LABELS: Record<string, string> = {
  relevance: "Relevância",
  newest: "Mais recentes",
  session_asc: "Pregão mais próximo",
  price_asc: "Menor preço",
  price_desc: "Maior preço",
};

export const ADMIN_SORT_LABELS: Record<string, string> = {
  updated_desc: "Atualização recente",
  first_seen_desc: "Coleta recente",
  session_asc: "Pregão mais próximo",
  price_desc: "Maior preço",
};

export const ROBOTS_LABELS: Record<string, string> = {
  allowed: "Permitido",
  disallowed: "Bloqueado",
  unknown: "Não verificado",
  error: "Erro",
};

export function label(map: Record<string, string>, value: string | null | undefined, fallback = "—"): string {
  if (!value) return fallback;
  return map[value] ?? value;
}

export const ALERT_CONDITIONS = new Set([
  "sinistro_recuperavel",
  "sinistro_media_monta",
  "sinistro_grande_monta",
  "sucata",
]);

export function isAlertCondition(condition: string | null | undefined): boolean {
  return !!condition && ALERT_CONDITIONS.has(condition);
}

export const UF_LIST = [
  "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA",
  "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
];

/* ───────── Onda 2: contas, filtros salvos e alertas ───────── */

export const ALERT_REASON_LABELS: Record<string, string> = {
  new: "Novo lote",
  price_drop: "Queda de lance",
  new_session: "Nova sessão",
};

export const ALERT_STATUS_LABELS: Record<string, string> = {
  pending: "Na fila",
  sent: "Enviado",
  failed: "Falhou",
  skipped: "Ignorado",
};

export const ALERT_CHANNEL_LABELS: Record<string, string> = {
  email: "E-mail",
  whatsapp: "WhatsApp",
};

export const PLAN_LABELS: Record<string, string> = {
  free: "Gratuito",
  pro: "Pago",
};

export const PLAN_STATUS_LABELS: Record<string, string> = {
  active: "Ativo",
  canceled: "Cancelado",
  expired: "Vencido",
};

export const ROLE_LABELS: Record<string, string> = {
  user: "Assinante",
  admin: "Administrador",
};

/** Rótulo de cada chave do `criteria` do filtro salvo. */
export const CRITERIA_LABELS: Record<string, string> = {
  q: "Busca",
  category: "Categoria",
  brand: "Marca",
  model: "Modelo",
  year_min: "Ano a partir de",
  year_max: "Ano até",
  price_min: "Preço a partir de",
  price_max: "Preço até",
  state: "UF",
  city: "Cidade",
  source: "Fonte",
  condition: "Condição",
  auction_type: "Tipo de leilão",
};
