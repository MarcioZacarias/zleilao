import { useEffect, useState } from "react";
import { portalApi } from "../services/portal";

export interface Branding {
  logo_dark: string;
  logo_light: string;
  favicon: string;
  site_title: string;
  tagline: string;
  disclaimer: string;
}

export const DEFAULT_BRANDING: Branding = {
  logo_dark: "/branding/logo-dark.svg",
  logo_light: "/branding/logo-light.svg",
  favicon: "/branding/favicon.svg",
  site_title: "ZConnect Leilão",
  tagline: "Todos os leilões de veículos do Brasil em um só radar",
  disclaimer: "",
};

let cache: Branding | null = null;
let inflight: Promise<Branding> | null = null;
const subscribers = new Set<(b: Branding) => void>();

async function fetchOnce(): Promise<Branding> {
  if (cache) return cache;
  if (inflight) return inflight;
  inflight = (async () => {
    try {
      const data = await portalApi.branding();
      cache = {
        logo_dark: data.logo_dark || DEFAULT_BRANDING.logo_dark,
        logo_light: data.logo_light || DEFAULT_BRANDING.logo_light,
        favicon: data.favicon || DEFAULT_BRANDING.favicon,
        site_title: data.site_title || DEFAULT_BRANDING.site_title,
        tagline: data.tagline ?? DEFAULT_BRANDING.tagline,
        disclaimer: data.disclaimer ?? "",
      };
    } catch {
      cache = DEFAULT_BRANDING;
    }
    subscribers.forEach((cb) => cb(cache!));
    inflight = null;
    return cache;
  })();
  return inflight;
}

/** Força nova busca (após upload no admin). */
export async function refreshBranding(): Promise<Branding> {
  cache = null;
  inflight = null;
  return fetchOnce();
}

export function useBranding(): Branding {
  const [branding, setBranding] = useState<Branding>(cache || DEFAULT_BRANDING);
  useEffect(() => {
    subscribers.add(setBranding);
    if (cache) setBranding(cache);
    else fetchOnce();
    return () => {
      subscribers.delete(setBranding);
    };
  }, []);
  return branding;
}

/** Aplica título e favicon do documento. Chamar uma vez na raiz (App). */
export function useApplyBranding() {
  const branding = useBranding();
  useEffect(() => {
    document.title = branding.site_title;
    let link = document.querySelector<HTMLLinkElement>("link[rel='icon']");
    if (!link) {
      link = document.createElement("link");
      link.rel = "icon";
      document.head.appendChild(link);
    }
    link.href = branding.favicon;
  }, [branding]);
}
