import { ImgHTMLAttributes, useEffect, useState } from "react";
import { Car } from "lucide-react";

interface SafeImageProps extends Omit<ImgHTMLAttributes<HTMLImageElement>, "src" | "onError"> {
  src: string | null | undefined;
  fallbackClassName?: string;
  iconSize?: number;
}

/**
 * Imagem com lazy loading, sem referrer (fontes externas) e placeholder
 * quando a URL falha ou é nula.
 */
export function SafeImage({ src, alt = "", className = "", fallbackClassName = "", iconSize = 32, ...rest }: SafeImageProps) {
  const [failed, setFailed] = useState(!src);
  useEffect(() => setFailed(!src), [src]);

  if (failed || !src) {
    return (
      <div
        role="img"
        aria-label={alt || "Sem imagem"}
        className={`flex items-center justify-center bg-radar-surface2 text-radar-muted/60 ${className} ${fallbackClassName}`}
      >
        <Car size={iconSize} strokeWidth={1.5} />
      </div>
    );
  }
  return (
    <img
      src={src}
      alt={alt}
      loading="lazy"
      decoding="async"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
      className={className}
      {...rest}
    />
  );
}
