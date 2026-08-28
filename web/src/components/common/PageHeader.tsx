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
    /* AWS console page header: heading-xl title (24/30 bold) with a body-m
       description, 20px below, actions right-aligned on the title line. */
    <div className={cn("mb-5 flex flex-wrap items-start justify-between gap-3", className)}>
      <div className="min-w-0">
        <h1 className="text-heading-xl font-bold text-content">{translatedTitle}</h1>
        {translatedDescription && (
          <p className="mt-1 text-body-m text-content-dim">{translatedDescription}</p>
        )}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}
