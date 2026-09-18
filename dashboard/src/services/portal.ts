import api from "./api";
import type {
  Auction,
  BrandingResponse,
  Category,
  FacetValue,
  ItemCard,
  ItemDetail,
  ItemPage,
  PortalSearchParams,
  PortalStats,
} from "./types";

function clean<T extends object>(params: T): Record<string, string | number | boolean> {
  const out: Record<string, string | number | boolean> = {};
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    out[k] = v as string | number | boolean;
  }
  return out;
}

export const portalApi = {
  branding: () => api.get<BrandingResponse>("/portal/branding").then((r) => r.data),
  stats: () => api.get<PortalStats>("/portal/stats").then((r) => r.data),
  categories: () => api.get<Category[]>("/portal/categories").then((r) => r.data),
  items: (params: PortalSearchParams) =>
    api.get<ItemPage>("/portal/items", { params: clean(params) }).then((r) => r.data),
  item: (id: number | string) => api.get<ItemDetail>(`/portal/items/${id}`).then((r) => r.data),
  brands: (category?: string) =>
    api.get<FacetValue[]>("/portal/brands", { params: clean({ category }) }).then((r) => r.data),
  models: (brand: string) =>
    api.get<FacetValue[]>("/portal/models", { params: { brand } }).then((r) => r.data),
  upcomingAuctions: (days = 7, limit = 10) =>
    api.get<Auction[]>("/portal/auctions/upcoming", { params: { days, limit } }).then((r) => r.data),
  auction: (id: number | string) =>
    api.get<{ auction: Auction; items: ItemCard[] }>(`/portal/auctions/${id}`).then((r) => r.data),
  /** URL do redirect oficial (RN-001). Usar como href, nunca via XHR. */
  goUrl: (id: number) => `/api/portal/items/${id}/go`,
};
