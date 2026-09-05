import { useMemo, useState } from "react";
import { Sparkles } from "lucide-react";
import type { SocioEconomicResponse } from "@/api/types";
import { CorrelationScatter } from "@/components/charts/CorrelationScatter";
import { NativeSelect } from "@/components/ui/native-select";
import { Widget } from "@/components/widget/Widget";
import { districtStanding, socioCell, socioSeries } from "@/lib/socio";
import { cn, formatNumber, humanizeKey } from "@/lib/utils";
import { useScopeStore } from "@/stores/useScopeStore";
import { useUIStore } from "@/stores/useUIStore";

/* ============================================================================
   ONE socio-economic indicator against crime — its own box, its own controls.

   The read-out used to be a single container holding a narrative, a ranked bar
   chart and one scatter, which meant nine of the ten indicators were only ever
   visible as a bar. Each indicator now gets a box it owns: pick the crime type and
   read the correlation for that pairing.

   GEOGRAPHY COMES FROM THE TOP-BAR SELECTOR, and it focuses rather than filters.

   There is no per-box district control: the workspace already has one district
   selector in the top bar, and a second one per box would be eleven controls
   competing to answer the same question. So these boxes read the global scope
   (useScopeStore), which useSeatScopeAnchor has already defaulted to the seat's
   own region — a state seat opens on every district, an SP or SHO on theirs.

   What the selection does here is EMPHASIS, not filtering. Pearson r is computed
   ACROSS districts — one dot per district, and the service requires at least six
   of them. Filtering to a single district would leave one point, which has no
   correlation at all; and there is no socio-economic or population data below
   district grain to correlate within a district instead. So the state-wide cloud
   stays intact and the selected district is ringed, with a strip showing where it
   actually sits: its indicator value against the state median, its rate, its
   distance from the fit, its rank. That is the honest answer to "how does my
   region compare", and it never implies a narrowing that was not performed.
   (Recorded as districtSupport.socio = "focus" in useScopeStore.)
   ========================================================================== */

export function IndicatorCrimeCard({
  data,
  indicator,
  defaultCrimeCategory,
  provenance,
  loading,
  error,
  onRefresh,
  gridTile,
  chartHeight = 210,
}: {
  data?: SocioEconomicResponse;
  /** Indicator key this box is about, e.g. "unemployment_rate". */
  indicator: string;
  /** Crime category to open on; the user can change it per box. */
  defaultCrimeCategory: string;
  provenance?: SocioEconomicResponse["result"] | null;
  loading?: boolean;
  error?: unknown;
  onRefresh?: () => void;
  gridTile?: boolean;
  chartHeight?: number;
}) {
  const askAbout = useUIStore((s) => s.askAbout);
  // The one district selector lives in the top bar; this box follows it.
  const focusDistrict = useScopeStore((s) => s.districtId);

  /* Crime type is UNSET until the user acts. `undefined` means "still following
     the page default", so a default arriving from the service after this box
     first rendered still takes effect. */
  const [categoryOverride, setCategoryOverride] = useState<string | undefined>(undefined);
  const category = categoryOverride || defaultCrimeCategory;

  const series = useMemo(
    () => (data && category ? socioSeries(data, indicator, category) : null),
    [data, indicator, category],
  );
  const cell = data && category ? socioCell(data, indicator, category) : undefined;
  const standing = series ? districtStanding(series, focusDistrict) : null;

  const label = humanizeKey(indicator);
  const hasPoints = (series?.points.length ?? 0) > 0;

  return (
    <Widget
      gridTile={gridTile}
      title={<span className="capitalize">{label}</span>}
      contextChip={cell?.r != null ? `r ${signed(cell.r)}` : "no fit"}
      provenance={provenance}
      loading={loading}
      error={error}
      empty={!loading && !error && !hasPoints}
      emptyLabel={`No district series for ${label} × ${category.toLowerCase()} — every cell was suppressed or too small to fit.`}
      onRefresh={onRefresh}
      actions={
        <NativeSelect
          value={category}
          onChange={(v) => setCategoryOverride(v || undefined)}
          options={(data?.crime_categories ?? []).map((c) => ({ value: c, label: c }))}
          placeholder={defaultCrimeCategory || "Crime type"}
          aria-label={`Crime type for ${label}`}
          className="w-44"
        />
      }
      menuItems={[
        {
          label: "Ask DRISHTI about this",
          icon: <Sparkles />,
          onSelect: () =>
            askAbout(
              `How does ${label} correlate with per-capita ${category.toLowerCase()} across ` +
                `Karnataka districts${standing ? `, and where does ${standing.districtName} sit` : ""}? ` +
                `Make clear this is correlational, not causal.`,
            ),
        },
      ]}
      info={
        <div className="space-y-2">
          <p>
            Every district plotted by its average {label} against its {category.toLowerCase()} rate
            per 100,000 people, with the linear fit. Rates are per capita so the chart doesn't just
            redraw the population map.
          </p>
          <p>
            The district selector in the top bar <strong>rings</strong> a district here rather than
            filtering to it. This correlation is measured across districts — one district alone has
            no correlation, and there is no socio-economic data below district level to compute one
            within a district. The strip under the chart shows where the selected district actually
            sits.
          </p>
          <p>
            Correlational, never causal. Districts whose count fell below the k-anonymity threshold
            (k≥{data?.k_threshold ?? "—"}) are omitted, not estimated.
          </p>
        </div>
      }
    >
      {series && hasPoints && (
        <div className="space-y-2">
          <CorrelationScatter
            series={series}
            height={chartHeight}
            highlightDistrictId={focusDistrict}
          />

          <CorrelationLine cell={cell} label={label} category={category} />

          {focusDistrict != null && <DistrictStandingStrip standing={standing} label={label} />}
        </div>
      )}
    </Widget>
  );
}

/** r, its strength and the district count it rests on — never r on its own. */
function CorrelationLine({
  cell,
  label,
  category,
}: {
  cell?: { r?: number | null; p_value?: number | null; n: number; strength?: string | null; direction?: string | null };
  label: string;
  category: string;
}) {
  if (!cell || cell.r == null) {
    return (
      <p className="text-12 text-content-dim">
        No correlation reported for {label} × {category.toLowerCase()}: too few districts cleared the
        suppression threshold to fit one.
      </p>
    );
  }
  return (
    <p className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-12 text-content-dim">
      <span className="tnum font-medium text-content">r {signed(cell.r)}</span>
      {cell.strength && (
        <span className="capitalize">
          {cell.strength} {cell.direction}
        </span>
      )}
      <span className="text-hairline">·</span>
      <span className="tnum">n = {cell.n} districts</span>
      {cell.p_value != null && (
        <>
          <span className="text-hairline">·</span>
          <span className="tnum">
            p {cell.p_value === 0 ? "< 0.00001" : `= ${cell.p_value.toFixed(3)}`}
          </span>
        </>
      )}
    </p>
  );
}

/** Where the selected district sits inside the state-wide cloud. */
function DistrictStandingStrip({
  standing,
  label,
}: {
  standing: ReturnType<typeof districtStanding>;
  label: string;
}) {
  if (!standing) {
    return (
      <p className="rounded-control bg-surface-2/50 px-2.5 py-1.5 text-12 text-content-dim">
        The selected district isn't in this series — its count was suppressed for k-anonymity, or the
        indicator is unmeasured there. It is withheld, not zero.
      </p>
    );
  }

  const { residualPct } = standing;
  return (
    <div className="space-y-1 rounded-control bg-surface-2/50 px-2.5 py-2">
      <p className="truncate text-12 font-medium text-content">{standing.districtName}</p>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 sm:grid-cols-4">
        <Stat
          term={label}
          value={formatNumber(round1(standing.indicatorValue))}
          sub={`state median ${formatNumber(round1(standing.indicatorMedian))}`}
        />
        <Stat
          term="Rate /100k"
          value={formatNumber(Math.round(standing.rate))}
          sub={`median ${formatNumber(Math.round(standing.rateMedian))}`}
        />
        <Stat
          term="vs the fit"
          value={residualPct == null ? "—" : `${residualPct >= 0 ? "+" : "−"}${Math.abs(residualPct).toFixed(0)}%`}
          sub={residualPct == null ? "no fit" : residualPct >= 0 ? "above expected" : "below expected"}
          tone={residualPct == null ? undefined : residualPct >= 0 ? "high" : "low"}
        />
        <Stat
          term="Rank by rate"
          value={`${standing.rateRank} of ${standing.outOf}`}
          sub="1 = highest"
        />
      </dl>
    </div>
  );
}

function Stat({
  term,
  value,
  sub,
  tone,
}: {
  term: string;
  value: string;
  sub?: string;
  tone?: "high" | "low";
}) {
  return (
    <div className="min-w-0">
      <dt className="truncate text-12 capitalize text-content-dim" title={term}>
        {term}
      </dt>
      <dd
        className={cn(
          "tnum truncate text-13 font-medium",
          tone === "high" ? "text-severity-high" : "text-content",
        )}
      >
        {value}
      </dd>
      {sub && <dd className="tnum truncate text-12 text-content-dim">{sub}</dd>}
    </div>
  );
}

/** Explicit sign so a positive r never reads as an unsigned magnitude. */
function signed(r: number): string {
  return `${r >= 0 ? "+" : "−"}${Math.abs(r).toFixed(2)}`;
}

function round1(n: number): number {
  return Math.round(n * 10) / 10;
}
