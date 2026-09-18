import { ReactNode } from "react";

export type BadgeVariant = "default" | "success" | "warning" | "danger" | "info" | "purple";

interface BadgeProps {
  children: ReactNode;
  variant?: BadgeVariant;
  className?: string;
  title?: string;
}

const variants: Record<BadgeVariant, string> = {
  default: "bg-gray-100 text-gray-700",
  success: "bg-green-100 text-green-700",
  warning: "bg-yellow-100 text-yellow-700",
  danger: "bg-red-100 text-red-700",
  info: "bg-blue-100 text-blue-700",
  purple: "bg-purple-100 text-purple-700",
};

export function Badge({ children, variant = "default", className = "", title }: BadgeProps) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium whitespace-nowrap ${variants[variant]} ${className}`}
    >
      {children}
    </span>
  );
}
