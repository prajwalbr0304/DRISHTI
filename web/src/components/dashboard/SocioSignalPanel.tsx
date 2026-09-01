import type { SocioEconomicResponse } from "@/api/types";
import { CorrelationBars } from "@/components/charts/CorrelationBars";
import { CorrelationScatter } from "@/components/charts/CorrelationScatter";
import { SocioNarrativeCard } from "@/components/dashboard/SocioNarrativeCard";
import { humanizeKey } from "@/lib/utils";

/* ============================================================================
   Command Center socio-economic signal (doc 01 §4.1, doc 03 §2.10).

   The read-out used to be text plus a ranked list; this puts the numbers on
   axes. Three panes, left to right, following how the claim is actually made:

     1  the narrative  — what the correlation says, in words, with the
                         k-anonymity count and the causation disclaimer
     2  ranked bars    — r against every indicator for the selected category,
                         so the reader sees which signal is strongest AND how
                         much stronger it is than the rest
     3  district scatter — the underlying points behind the headline number,
                         with the linear fit, so a single outlier district
                         cannot hide inside a summary statistic

   Aggregate-only by construction: one dot is a district, never a person.
   ========================================================================== */

export function SocioSignalPanel({
  data,
  crimeCategory,
  focusIndicator,
  onSelectIndicator,
}: {
  data: SocioEconomicResponse;
  /** Crime category driving both charts. */
  crimeCategory: string;
  /** Indicator the scatter is plotted against (server-selected unless overridden). */
  focusIndicator: string;
  /** Clicking a bar re-focuses the scatter. */
  onSelectIndicator?: (indicator: string) => void;
}) {
  const series = data.scatter.find((s) => s.crime_category === crimeCategory) ?? null;

  return (
    <div className="grid grid-cols-1 gap-x-5 gap-y-4 md:grid-cols-2 xl:grid-cols-12">
      {/* 1 — narrative + honesty footer */}
      <div className="min-w-0 xl:col-span-3">
        <SocioNarrativeCard data={data} compact />
      </div>

      {/* 2 — correlation strength by indicator */}
      <section className="min-w-0 xl:col-span-4">
        <PaneHead title="Correlation by indicator" sub={crimeCategory} />
        <CorrelationBars
          cells={data.correlation_matrix}
          crimeCategory={crimeCategory}
          focusIndicator={focusIndicator}
          onSelectIndicator={onSelectIndicator}
        />
      </section>

      {/* 3 — the districts behind the number */}
      <section className="min-w-0 md:col-span-2 xl:col-span-5">
        <PaneHead
          title="Districts: crime rate vs indicator"
          sub={focusIndicator ? humanizeKey(focusIndicator) : undefined}
        />
        {series && series.points.length > 0 ? (
          <CorrelationScatter series={series} height={230} />
        ) : (
          <p className="py-6 text-center text-13 text-content-dim">
            No district-level series for this pairing — every cell was suppressed or too small to fit.
          </p>
        )}
      </section>
    </div>
  );
}

function PaneHead({ title, sub }: { title: string; sub?: string }) {
  return (
    <div className="mb-1.5 flex min-w-0 items-baseline gap-2">
      <h3 className="truncate text-13 font-medium text-content">{title}</h3>
      {sub && <span className="truncate text-12 text-content-dim">{sub}</span>}
    </div>
  );
}
