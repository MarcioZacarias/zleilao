import { ReactNode } from "react";
import { Inbox, LucideIcon } from "lucide-react";

interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: ReactNode;
  tone?: "light" | "dark";
  compact?: boolean;
}

export function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,
  tone = "light",
  compact = false,
}: EmptyStateProps) {
  const dark = tone === "dark";
  return (
    <div
      className={`flex flex-col items-center justify-center text-center ${compact ? "py-8 px-4" : "py-16 px-6"} ${
        dark ? "text-radar-muted" : "text-gray-500"
      }`}
    >
      <div
        className={`mb-4 flex h-14 w-14 items-center justify-center rounded-2xl ${
          dark ? "bg-radar-surface2 text-accent" : "bg-gray-100 text-gray-400"
        }`}
      >
        <Icon size={26} />
      </div>
      <h3 className={`text-base font-semibold ${dark ? "text-radar-text" : "text-gray-900"}`}>{title}</h3>
      {description && <p className="mt-1 max-w-md text-sm">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
