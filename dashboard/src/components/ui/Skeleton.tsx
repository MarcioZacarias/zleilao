interface SkeletonProps {
  className?: string;
  tone?: "light" | "dark";
  rounded?: string;
}

export function Skeleton({ className = "h-4 w-full", tone = "light", rounded = "rounded-md" }: SkeletonProps) {
  return (
    <div
      aria-hidden
      className={`${tone === "dark" ? "skeleton-dark" : "skeleton-light"} ${rounded} ${className}`}
    />
  );
}

export function SkeletonText({ lines = 3, tone = "light" }: { lines?: number; tone?: "light" | "dark" }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} tone={tone} className={`h-3 ${i === lines - 1 ? "w-2/3" : "w-full"}`} />
      ))}
    </div>
  );
}

/** Skeleton no formato de um ItemCard do portal. */
export function ItemCardSkeleton() {
  return (
    <div className="portal-card overflow-hidden">
      <Skeleton tone="dark" className="aspect-[4/3] w-full" rounded="rounded-none" />
      <div className="p-4 space-y-3">
        <Skeleton tone="dark" className="h-3 w-1/3" />
        <Skeleton tone="dark" className="h-4 w-full" />
        <Skeleton tone="dark" className="h-4 w-3/4" />
        <Skeleton tone="dark" className="h-6 w-1/2" />
        <Skeleton tone="dark" className="h-3 w-2/3" />
      </div>
    </div>
  );
}

export function TableSkeleton({ rows = 6, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div className="divide-y divide-gray-100">
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-4 px-4 py-3">
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} className={`h-4 ${c === 0 ? "w-1/3" : "w-1/6"}`} />
          ))}
        </div>
      ))}
    </div>
  );
}
