import type { ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useLanguage } from "@/providers/LanguageProvider";
import { InfoHint } from "@/components/common/InfoHint";
import { destinationByPath } from "@/config/destinations";

/* ============================================================================
   Page header, laid out like an AWS console page header:

     Title  Info                                    [ actions ]
     Description

   Title is heading-xl (24/30 bold); the Info link sits on the title baseline and
   is the same affordance used by widget headers and KPI cards. Actions are
   right-aligned on the title line.
   ========================================================================== */

export function PageHeader({
  title,
  description,
  /** help content for the AWS-style "Info" link beside the title */
  info,
  actions,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  info?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  const { t } = useLanguage();
  const { pathname } = useLocation();
  const translatedTitle = typeof title === "string" ? t(title) : title;
  const translatedDescription = typeof description === "string" ? t(description) : description;

  // The ⓘ hint ALWAYS renders — a title that has it on one page and not the
  // next reads as a bug. Pages may pass their own copy; otherwise we fall back
  // to the destination's curated description from config/destinations.
  const destination = destinationByPath(pathname);
  const infoBody = info ?? (destination ? <p>{t(destination.description)}</p> : undefined);

  return (
    <div className={cn("mb-5 flex flex-wrap items-start justify-between gap-3", className)}>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-heading-xl font-bold text-content">{translatedTitle}</h1>
          <InfoHint>{infoBody}</InfoHint>
        </div>
        {translatedDescription && (
          <p className="mt-1 text-body-m text-content-dim">{translatedDescription}</p>
        )}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}
