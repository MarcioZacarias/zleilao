import { useEffect } from "react";
import { useBranding } from "./useBranding";

/** Título da aba: "<página> · <site>". */
export function useDocumentTitle(page?: string | null) {
  const { site_title } = useBranding();
  useEffect(() => {
    document.title = page ? `${page} · ${site_title}` : site_title;
    return () => {
      document.title = site_title;
    };
  }, [page, site_title]);
}
