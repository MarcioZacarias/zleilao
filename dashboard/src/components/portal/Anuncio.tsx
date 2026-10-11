import { useEffect, useRef, useState } from "react";
import { portalApi } from "../../services/portal";
import type { AdsConfig } from "../../services/types";

/**
 * Bloco de publicidade da vitrine.
 *
 * Três regras que valem mais que o espaço vendido:
 *
 * 1. **É sempre rotulado.** Anúncio disfarçado de lote faz o visitante clicar
 *    achando que é resultado de busca. Isso rende um clique e perde a pessoa.
 * 2. **Ocupa altura fixa desde o início.** Se o bloco aparecer depois e
 *    empurrar a lista, o usuário clica no lote errado — e a culpa é nossa.
 * 3. **Some sozinho quando não há o que mostrar.** Sem anúncio configurado,
 *    não sobra moldura nem "espaço reservado" na tela.
 *
 * O AdSense exige aprovação e costuma recusar subdomínio de plataforma; o
 * modo `proprio` serve para vender direto ao leiloeiro, sem depender disso.
 */

let configCache: Promise<AdsConfig> | null = null;

/** Uma consulta por sessão: a configuração não muda entre telas. */
function lerConfig(): Promise<AdsConfig> {
  if (!configCache) {
    configCache = portalApi.ads().catch(
      () => ({ enabled: false, provider: "proprio", adsense_client: "", intervalo_cards: 12,
               posicoes: { busca: null, ficha: null } }) as AdsConfig,
    );
  }
  return configCache;
}

/** Injeta o script do AdSense uma única vez por página. */
function carregarAdsense(client: string): void {
  if (!client || document.querySelector("script[data-adsense]")) return;
  const s = document.createElement("script");
  s.async = true;
  s.src = `https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${encodeURIComponent(client)}`;
  s.crossOrigin = "anonymous";
  s.dataset.adsense = "1";
  document.head.appendChild(s);
}

interface Props {
  posicao: "busca" | "ficha";
  className?: string;
}

export function Anuncio({ posicao, className = "" }: Props) {
  const [cfg, setCfg] = useState<AdsConfig | null>(null);
  const caixa = useRef<HTMLDivElement>(null);
  const contou = useRef(false);

  useEffect(() => {
    let vivo = true;
    lerConfig().then((c) => vivo && setCfg(c));
    return () => {
      vivo = false;
    };
  }, []);

  const peca = cfg?.enabled ? cfg.posicoes[posicao] : null;

  // Impressão só quando o bloco entra na tela de fato: contar na montagem
  // infla o número com anúncio que ninguém chegou a ver.
  useEffect(() => {
    if (!peca || !caixa.current || contou.current) return;
    const obs = new IntersectionObserver(
      (entradas) => {
        if (entradas.some((e) => e.isIntersecting) && !contou.current) {
          contou.current = true;
          portalApi.adEvent(posicao, "impressao").catch(() => {});
          obs.disconnect();
        }
      },
      { threshold: 0.5 },
    );
    obs.observe(caixa.current);
    return () => obs.disconnect();
  }, [peca, posicao]);

  useEffect(() => {
    if (cfg?.enabled && cfg.provider === "adsense" && cfg.adsense_client) {
      carregarAdsense(cfg.adsense_client);
      try {
        // A fila do AdSense é global; empurrar sinaliza "renderize este bloco".
        ((window as unknown as { adsbygoogle?: unknown[] }).adsbygoogle ||= []).push({});
      } catch {
        /* bloqueador de anúncio: silêncio é o comportamento correto */
      }
    }
  }, [cfg, peca]);

  if (!peca) return null;

  const rotulo = (
    <span className="mb-1 block text-[10px] uppercase tracking-wider text-radar-muted/70">
      Publicidade
    </span>
  );

  if (cfg?.provider === "adsense" && "slot" in peca) {
    return (
      <div ref={caixa} className={`portal-card min-h-[280px] p-3 ${className}`}>
        {rotulo}
        <ins
          className="adsbygoogle block"
          style={{ display: "block", minHeight: 250 }}
          data-ad-client={cfg.adsense_client}
          data-ad-slot={peca.slot}
          data-ad-format="auto"
          data-full-width-responsive="true"
        />
      </div>
    );
  }

  if ("imagem" in peca) {
    return (
      <a
        ref={caixa as unknown as React.RefObject<HTMLAnchorElement>}
        href={peca.alvo}
        target="_blank"
        // `sponsored` diz ao buscador que o link é pago; sem isso o site
        // pode ser penalizado por link comprado não declarado.
        rel="sponsored noopener noreferrer"
        onClick={() => portalApi.adEvent(posicao, "clique").catch(() => {})}
        className={`portal-card group block overflow-hidden p-3 transition-shadow hover:shadow-lg ${className}`}
      >
        {rotulo}
        <img
          src={peca.imagem}
          alt={peca.texto || "Anúncio"}
          loading="lazy"
          className="w-full rounded-lg object-cover"
        />
        {peca.texto && <p className="mt-2 text-xs text-radar-muted">{peca.texto}</p>}
      </a>
    );
  }

  return null;
}
