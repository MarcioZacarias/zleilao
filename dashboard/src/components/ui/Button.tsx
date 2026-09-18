import { ButtonHTMLAttributes } from "react";
import { Loader2 } from "lucide-react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "danger" | "ghost" | "accent" | "outline-dark";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
}

const variantClasses: Record<NonNullable<ButtonProps["variant"]>, string> = {
  primary: "bg-primary-600 text-white hover:bg-primary-700 shadow-sm focus:ring-primary-500",
  secondary: "bg-white text-gray-700 border border-gray-300 hover:bg-gray-50 focus:ring-primary-500",
  danger: "bg-red-600 text-white hover:bg-red-700 focus:ring-red-500",
  ghost: "text-gray-600 hover:bg-gray-100 focus:ring-primary-500",
  // Portal
  accent: "bg-accent text-[#0b1020] hover:bg-accent-400 shadow-sm focus:ring-accent/50 focus:ring-offset-radar-bg font-semibold",
  "outline-dark":
    "bg-transparent text-radar-text border border-white/15 hover:border-white/30 hover:bg-white/5 focus:ring-accent/40 focus:ring-offset-radar-bg",
};

const sizeClasses = {
  sm: "px-3 py-1.5 text-xs",
  md: "px-4 py-2 text-sm",
  lg: "px-6 py-3 text-base",
};

export function Button({
  variant = "primary",
  size = "md",
  className = "",
  disabled,
  loading = false,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed ${variantClasses[variant]} ${sizeClasses[size]} ${className}`}
      disabled={disabled || loading}
      {...props}
    >
      {loading && <Loader2 size={14} className="animate-spin" />}
      {children}
    </button>
  );
}
