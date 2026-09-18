import { Clock, Lock, CheckCircle2, EyeOff, CircleDashed } from "lucide-react";
import { STATUS_LABELS, STATUS_LABELS_ADMIN } from "../../lib/labels";
import { Badge, BadgeVariant } from "../ui/Badge";

interface StatusBadgeProps {
  status: string;
  tone?: "portal" | "admin";
  size?: "sm" | "md";
}

const PORTAL_STYLES: Record<string, string> = {
  published: "bg-emerald-500/15 text-emerald-300 ring-emerald-400/30",
  auction_soon: "bg-accent/15 text-accent-300 ring-accent/40",
  closed: "bg-white/5 text-radar-muted ring-white/10",
  withdrawn: "bg-white/5 text-radar-muted ring-white/10",
  possibly_withdrawn: "bg-white/5 text-radar-muted ring-white/10",
  collected: "bg-sky-500/15 text-sky-300 ring-sky-400/30",
  review: "bg-purple-500/15 text-purple-300 ring-purple-400/30",
};

const ADMIN_VARIANTS: Record<string, BadgeVariant> = {
  collected: "info",
  review: "purple",
  published: "success",
  auction_soon: "warning",
  closed: "default",
  withdrawn: "danger",
  possibly_withdrawn: "danger",
};

function Icon({ status, size }: { status: string; size: number }) {
  switch (status) {
    case "auction_soon":
      return <Clock size={size} />;
    case "closed":
      return <Lock size={size} />;
    case "published":
      return <CheckCircle2 size={size} />;
    case "withdrawn":
    case "possibly_withdrawn":
      return <EyeOff size={size} />;
    default:
      return <CircleDashed size={size} />;
  }
}

export function StatusBadge({ status, tone = "portal", size = "sm" }: StatusBadgeProps) {
  if (tone === "admin") {
    return <Badge variant={ADMIN_VARIANTS[status] ?? "default"}>{STATUS_LABELS_ADMIN[status] ?? status}</Badge>;
  }
  const cls = PORTAL_STYLES[status] ?? "bg-white/5 text-radar-muted ring-white/10";
  const pad = size === "md" ? "px-3 py-1 text-xs" : "px-2 py-0.5 text-[11px]";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full font-semibold ring-1 ring-inset whitespace-nowrap ${pad} ${cls}`}
    >
      {status === "auction_soon" && (
        <span className="relative flex h-1.5 w-1.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-75" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-accent" />
        </span>
      )}
      <Icon status={status} size={size === "md" ? 13 : 11} />
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}
