import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon?: LucideIcon;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex min-h-[320px] flex-col items-center justify-center rounded-card border border-dashed border-hairline bg-surface/50 p-10 text-center",
        className,
      )}
    >
      {Icon && (
        <div className="mb-3 grid size-11 place-items-center rounded-card bg-surface-2 text-content-dim">
          <Icon className="size-5" />
        </div>
      )}
      <h3 className="text-14 font-semibold text-content">{title}</h3>
      {description && <p className="mt-1 max-w-md text-13 text-content-dim">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
