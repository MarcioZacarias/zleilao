import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Expand, X } from "lucide-react";
import { SafeImage } from "../ui/SafeImage";

interface GalleryProps {
  images: string[];
  alt: string;
}

/** Galeria com miniaturas, navegação por teclado e lightbox. */
export function Gallery({ images, alt }: GalleryProps) {
  const list = images.filter(Boolean);
  const [idx, setIdx] = useState(0);
  const [zoom, setZoom] = useState(false);

  useEffect(() => setIdx(0), [images]);

  const prev = () => setIdx((i) => (i - 1 + list.length) % list.length);
  const next = () => setIdx((i) => (i + 1) % list.length);

  useEffect(() => {
    if (!zoom) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setZoom(false);
      if (e.key === "ArrowLeft") prev();
      if (e.key === "ArrowRight") next();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zoom, list.length]);

  if (list.length === 0) {
    return (
      <div className="portal-card overflow-hidden">
        <SafeImage src={null} alt={alt} className="aspect-[4/3] w-full" iconSize={56} />
        <p className="px-4 py-2 text-center text-xs text-radar-muted">Imagem não informada pela fonte</p>
      </div>
    );
  }

  const current = list[Math.min(idx, list.length - 1)];

  return (
    <div className="space-y-2">
      <div className="portal-card group relative overflow-hidden">
        <SafeImage
          key={current}
          src={current}
          alt={`${alt} — imagem ${idx + 1} de ${list.length}`}
          className="aspect-[4/3] w-full object-contain bg-radar-surface2"
          fallbackClassName="aspect-[4/3] w-full"
          iconSize={56}
        />
        {list.length > 1 && (
          <>
            <button
              type="button"
              onClick={prev}
              className="absolute left-2 top-1/2 -translate-y-1/2 rounded-full bg-radar-bg/70 p-2 text-radar-text opacity-0 transition-opacity hover:bg-radar-bg group-hover:opacity-100 focus:opacity-100"
              aria-label="Imagem anterior"
            >
              <ChevronLeft size={18} />
            </button>
            <button
              type="button"
              onClick={next}
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full bg-radar-bg/70 p-2 text-radar-text opacity-0 transition-opacity hover:bg-radar-bg group-hover:opacity-100 focus:opacity-100"
              aria-label="Próxima imagem"
            >
              <ChevronRight size={18} />
            </button>
            <span className="absolute bottom-2 left-2 rounded-md bg-radar-bg/80 px-2 py-0.5 text-[11px] text-radar-text tabular-nums">
              {idx + 1} / {list.length}
            </span>
          </>
        )}
        <button
          type="button"
          onClick={() => setZoom(true)}
          className="absolute bottom-2 right-2 rounded-md bg-radar-bg/80 p-1.5 text-radar-text hover:bg-radar-bg"
          aria-label="Ampliar imagem"
        >
          <Expand size={14} />
        </button>
      </div>

      {list.length > 1 && (
        <div className="no-scrollbar flex gap-2 overflow-x-auto pb-1">
          {list.map((src, i) => (
            <button
              type="button"
              key={`${src}-${i}`}
              onClick={() => setIdx(i)}
              className={`shrink-0 overflow-hidden rounded-lg ring-2 transition ${
                i === idx ? "ring-accent" : "ring-transparent hover:ring-white/20"
              }`}
              aria-label={`Ver imagem ${i + 1}`}
            >
              <SafeImage src={src} alt="" className="h-16 w-20 object-cover" fallbackClassName="h-16 w-20" iconSize={18} />
            </button>
          ))}
        </div>
      )}

      {zoom && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 p-4" onClick={() => setZoom(false)}>
          <button
            type="button"
            className="absolute right-4 top-4 rounded-full bg-white/10 p-2 text-white hover:bg-white/20"
            aria-label="Fechar"
          >
            <X size={20} />
          </button>
          {list.length > 1 && (
            <>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  prev();
                }}
                className="absolute left-4 top-1/2 -translate-y-1/2 rounded-full bg-white/10 p-2 text-white hover:bg-white/20"
                aria-label="Imagem anterior"
              >
                <ChevronLeft size={22} />
              </button>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  next();
                }}
                className="absolute right-4 top-1/2 -translate-y-1/2 rounded-full bg-white/10 p-2 text-white hover:bg-white/20"
                aria-label="Próxima imagem"
              >
                <ChevronRight size={22} />
              </button>
            </>
          )}
          <img
            src={current}
            alt={alt}
            referrerPolicy="no-referrer"
            className="max-h-[90vh] max-w-full object-contain"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </div>
  );
}
