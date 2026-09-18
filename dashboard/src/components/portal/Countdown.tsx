import { useEffect, useState } from "react";
import { toEpoch } from "../../lib/format";

interface CountdownProps {
  target: string | null | undefined;
  size?: "sm" | "md" | "lg";
  /** Texto quando o alvo já passou. */
  pastLabel?: string;
  className?: string;
}

interface Parts {
  d: number;
  h: number;
  m: number;
  s: number;
  past: boolean;
}

function split(ms: number): Parts {
  const past = ms <= 0;
  const t = Math.max(0, Math.floor(Math.abs(ms) / 1000));
  return {
    d: Math.floor(t / 86400),
    h: Math.floor((t % 86400) / 3600),
    m: Math.floor((t % 3600) / 60),
    s: t % 60,
    past,
  };
}

function useCountdown(target: string | null | undefined): Parts | null {
  const epoch = toEpoch(target);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (epoch === null) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [epoch]);
  if (epoch === null) return null;
  return split(epoch - now);
}

const pad = (n: number) => String(n).padStart(2, "0");

/** Contagem regressiva ao vivo até `next_session_at` (RN-005). */
export function Countdown({ target, size = "md", pastLabel = "Sessão iniciada", className = "" }: CountdownProps) {
  const parts = useCountdown(target);
  if (!parts) return null;

  if (parts.past) {
    return <span className={`text-radar-muted ${className}`}>{pastLabel}</span>;
  }

  if (size === "sm") {
    const text =
      parts.d > 0
        ? `${parts.d}d ${pad(parts.h)}h ${pad(parts.m)}m`
        : `${pad(parts.h)}:${pad(parts.m)}:${pad(parts.s)}`;
    return <span className={`font-semibold tabular-nums text-accent ${className}`}>{text}</span>;
  }

  const cells: { v: number; l: string }[] = [
    { v: parts.d, l: "dias" },
    { v: parts.h, l: "horas" },
    { v: parts.m, l: "min" },
    { v: parts.s, l: "seg" },
  ];
  const box = size === "lg" ? "min-w-[64px] px-3 py-2" : "min-w-[52px] px-2 py-1.5";
  const num = size === "lg" ? "text-2xl md:text-3xl" : "text-lg";

  return (
    <div className={`flex items-center gap-2 ${className}`} role="timer" aria-live="off">
      {cells.map((c) => (
        <div key={c.l} className={`rounded-lg bg-radar-surface2 ring-1 ring-inset ring-white/10 text-center ${box}`}>
          <div className={`${num} font-bold tabular-nums leading-none text-accent`}>{pad(c.v)}</div>
          <div className="mt-1 text-[10px] uppercase tracking-wider text-radar-muted">{c.l}</div>
        </div>
      ))}
    </div>
  );
}
