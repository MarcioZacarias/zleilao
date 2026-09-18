import { ReactNode, useEffect } from "react";
import { X } from "lucide-react";

interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  subtitle?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  side?: "left" | "right";
  width?: string;
  tone?: "light" | "dark";
}

export function Drawer({
  open,
  onClose,
  title,
  subtitle,
  children,
  footer,
  side = "right",
  width = "max-w-2xl",
  tone = "light",
}: DrawerProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  const dark = tone === "dark";
  const panel = dark
    ? "bg-radar-surface text-radar-text border-radar-border"
    : "bg-white text-gray-900 border-gray-200";
  const header = dark ? "border-radar-border" : "border-gray-100";

  return (
    <div
      className={`fixed inset-0 z-50 transition-opacity duration-200 ${
        open ? "pointer-events-auto opacity-100" : "pointer-events-none opacity-0"
      }`}
      aria-hidden={!open}
    >
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <aside
        role="dialog"
        aria-modal="true"
        className={`absolute inset-y-0 ${side === "right" ? "right-0" : "left-0"} flex w-full ${width} flex-col border-l shadow-2xl transition-transform duration-200 ${panel} ${
          open ? "translate-x-0" : side === "right" ? "translate-x-full" : "-translate-x-full"
        }`}
      >
        <div className={`flex items-start justify-between gap-3 border-b px-4 py-3 md:px-6 ${header}`}>
          <div className="min-w-0">
            {title && <h2 className="truncate text-base font-semibold">{title}</h2>}
            {subtitle && (
              <div className={`mt-0.5 text-xs ${dark ? "text-radar-muted" : "text-gray-500"}`}>{subtitle}</div>
            )}
          </div>
          <button
            onClick={onClose}
            className={`shrink-0 rounded-lg p-1.5 transition-colors ${
              dark ? "hover:bg-white/10 text-radar-muted" : "hover:bg-gray-100 text-gray-500"
            }`}
            aria-label="Fechar"
          >
            <X size={18} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-4 md:px-6">{children}</div>
        {footer && <div className={`border-t px-4 py-3 md:px-6 ${header}`}>{footer}</div>}
      </aside>
    </div>
  );
}
