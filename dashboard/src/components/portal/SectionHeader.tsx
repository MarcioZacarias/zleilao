import { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";

interface SectionHeaderProps {
  title: string;
  subtitle?: string;
  to?: string;
  linkLabel?: string;
  right?: ReactNode;
  icon?: ReactNode;
}

export function SectionHeader({ title, subtitle, to, linkLabel = "Ver todos", right, icon }: SectionHeaderProps) {
  return (
    <div className="mb-4 flex items-end justify-between gap-4">
      <div className="min-w-0">
        <h2 className="flex items-center gap-2 text-lg font-bold text-radar-text md:text-xl">
          {icon}
          {title}
        </h2>
        {subtitle && <p className="mt-0.5 text-sm text-radar-muted">{subtitle}</p>}
      </div>
      {right}
      {to && (
        <Link to={to} className="inline-flex shrink-0 items-center gap-1 text-sm text-accent hover:underline">
          {linkLabel} <ArrowRight size={14} />
        </Link>
      )}
    </div>
  );
}
