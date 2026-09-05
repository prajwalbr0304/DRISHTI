import type { SocioEconomicResponse } from "@/api/types";
import type { DashTile } from "@/components/dashboard/DashboardGrid";
import { CorrelationBars } from "@/components/charts/CorrelationBars";
import { IndicatorCrimeCard } from "@/components/dashboard/IndicatorCrimeCard";
import { SocioNarrativeCard } from "@/components/dashboard/SocioNarrativeCard";
import { NativeSelect } from "@/components/ui/native-select";
import { Widget } from "@/components/widget/Widget";
import { indicatorsByStrength } from "@/lib/socio";

/* ============================================================================
   The socio-economic band of a command board: a read-out tile plus ONE TILE PER
   INDICATOR, rather than a single tile with three panes crammed into it.

   Shared by the DGP and policymaker boards so the two never drift apart in
   layout or in the caveats they print.

   Every box is an independent DashTile, which means a chief can move, resize or
   dismiss the indicators they don't watch — a band of ten only works if it can
   be trimmed, and DashboardGrid's dismissal is always reversible.

   Geometry: two boxes per row on the 12-column board, three on the 24-column
   wide board. Tiles are keyed `socio-<indicator>`, and mergeLayouts keys saved
   arrangements by tile id, so a board someone already rearranged picks these up
   at their declared positions instead of having positions synthesised.
   ========================================================================== */

/** Tile height. The body holds a ~190px chart, the r line and the district
 *  standing strip; at h=6 the strip was the part that got scrolled away. */
const BOX_H = 7;
const BOX_W = 6; // 12-col: two per row
const XL_BOX_W = 8; // 24-col: three per row
/** Read-out holds the narrative beside a 10-row ranked bar chart (~290px). */
const READOUT_H = 8;

export function socioTiles({
  data,
  loading,
  error,
  onRefresh,
  category,
  onCategoryChange,
  stateWideChip,
  /** First grid row of the band on the 12-column board. */
  startY,
  /** First grid row of the band on the 24-column wide board. */
  xlStartY,
}: {
  data?: SocioEconomicResponse;
  loading?: boolean;
  error?: unknown;
  onRefresh?: () => void;
  /** Page-level default crime type; each box may override it. */
  category: string;
  onCategoryChange: (v: string) => void;
  stateWideChip?: string;
  startY: number;
  xlStartY: number;
}): DashTile[] {
  const indicators = data && category ? indicatorsByStrength(data, category) : [];

  const readout: DashTile = {
    key: "socio-readout",
    handle: "header",
    x: 0,
    y: startY,
    w: 12,
    h: READOUT_H,
    minW: 4,
    minH: 4,
    xl: { x: 0, y: xlStartY, w: 24, h: READOUT_H },
    el: (
      <Widget
        gridTile
        title="Socio-economic read-out"
        contextChip={stateWideChip}
        provenance={data?.result}
        loading={loading}
        error={error}
        empty={!loading && !error && !data}
        onRefresh={onRefresh}
        actions={
          <NativeSelect
            value={category}
            onChange={onCategoryChange}
            options={(data?.crime_categories ?? []).map((c) => ({ value: c, label: c }))}
            placeholder={category || "Crime type"}
            aria-label="Default crime type for every indicator box"
            className="w-52"
          />
        }
        info={
          <div className="space-y-2">
            <p>
              The strongest socio-economic association with crime this period in plain language, next
              to r for every indicator ranked by strength — the index for the per-indicator boxes
              below. Correlational, never causal.
            </p>
            <p>
              The crime type chosen here is the DEFAULT for those boxes; a box you set individually
              keeps its own selection. Geography comes from the district selector in the top bar,
              which rings that district inside each box rather than filtering to it.
            </p>
            <p>
              Rates are per 100,000 population, so the charts don't just redraw the population map.
              Districts below the k-anonymity threshold are omitted, not estimated.
            </p>
          </div>
        }
      >
        {data && (
          <div className="grid grid-cols-1 gap-x-5 gap-y-3 lg:grid-cols-12">
            {/* compact: the ranked top-5 list would restate the bars beside it. */}
            <div className="min-w-0 lg:col-span-4">
              <SocioNarrativeCard data={data} compact />
            </div>
            <div className="min-w-0 lg:col-span-8">
              {category && (
                <CorrelationBars cells={data.correlation_matrix} crimeCategory={category} />
              )}
            </div>
          </div>
        )}
      </Widget>
    ),
  };

  const boxes: DashTile[] = indicators.map((indicator, i) => ({
    key: `socio-${indicator}`,
    handle: "header",
    x: (i % 2) * BOX_W,
    y: startY + READOUT_H + Math.floor(i / 2) * BOX_H,
    w: BOX_W,
    h: BOX_H,
    minW: 3,
    minH: 5,
    xl: {
      x: (i % 3) * XL_BOX_W,
      y: xlStartY + READOUT_H + Math.floor(i / 3) * BOX_H,
      w: XL_BOX_W,
      h: BOX_H,
    },
    el: (
      <IndicatorCrimeCard
        gridTile
        data={data}
        indicator={indicator}
        defaultCrimeCategory={category}
        provenance={data?.result}
        loading={loading}
        error={error}
        onRefresh={onRefresh}
        chartHeight={190}
      />
    ),
  }));

  return [readout, ...boxes];
}
