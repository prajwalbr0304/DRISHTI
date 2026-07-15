import { cn } from "@/lib/utils";

/** Loading placeholder for live data fetches. */
export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("animate-pulse rounded-control bg-surface-2", className)}
      {...props}
    />
  );
}
