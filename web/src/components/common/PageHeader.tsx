import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { useLanguage } from "@/providers/LanguageProvider";

export function PageHeader({
  title,
  description,
  actions,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  const { t } = useLanguage();
  const translatedTitle = typeof title === "string" ? t(title) : title;
  const translatedDescription = typeof description === "string" ? t(description) : description;

  return (
    <div className={cn("mb-4 flex flex-wrap items-start justify-between gap-3", className)}>
      <div className="min-w-0">
        <h1 className="text-20 font-semibold tracking-tight text-content">{translatedTitle}</h1>
        {translatedDescription && <p className="mt-0.5 text-13 text-content-dim">{translatedDescription}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}
