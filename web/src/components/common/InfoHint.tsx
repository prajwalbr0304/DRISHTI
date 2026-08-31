import type { ReactNode } from "react";
import { Info } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

/* ============================================================================
   The info affordance: a circled "i" that reveals help on hover.

   This is the SINGLE implementation used by every titled surface — page
   headers, dashboard widgets, KPI cards and the Emergency Response tiles — so
   it can never drift into "an icon on one card, a word on another, nothing on a
   third". It always renders, falling back to generic scope copy when a surface
   has no specific help text, because a missing affordance reads as a bug.

   The trigger is a real <button>, so the hint also opens on keyboard focus, not
   hover alone. Hover/focus only — it deliberately does not steal the click.
   ========================================================================== */

export function InfoHint({
  children,
  side = "top",
  label = "More information",
  className,
}: {
  /** hint body; a generic scope note is shown when omitted */
  children?: ReactNode;
  side?: "top" | "bottom" | "left" | "right";
  /** accessible name for the trigger */
  label?: string;
  className?: string;
}) {
  return (
    /* Self-contained provider: PageHeader renders this on every page, including
       pages mounted outside AppShell (tests, harnesses), and a bare Radix
       Tooltip throws without a provider ancestor. Nesting providers is
       supported; the delay matches the shell's. */
    <TooltipProvider delayDuration={200} skipDelayDuration={400}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            aria-label={label}
            // `no-drag` keeps this from starting a drag inside a grid tile.
            className={cn(
              "no-drag inline-grid shrink-0 place-items-center rounded-full text-content-dim transition-colors hover:text-primary focus-visible:text-primary",
              className,
            )}
          >
            <Info className="size-4" aria-hidden />
          </button>
        </TooltipTrigger>
        <TooltipContent side={side} className="max-w-[320px] whitespace-normal leading-5">
          {children ?? (
            <p>
              Live data from the DRISHTI services, scoped to your role and the current time
              window.
            </p>
          )}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
