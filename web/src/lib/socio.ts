import type {
  CorrelationCell,
  ScatterPoint,
  ScatterSeries,
  SocioEconomicResponse,
} from "@/api/types";

/* ============================================================================
   Building socio-economic scatter series on the client.

   /analytics/socioeconomic publishes the raw district PANEL it computed from
   (each district's averaged indicators + its per-100k rates) plus a fitted
   regression line on every correlation cell. So any indicator x crime-category
   pairing can be assembled here, which is what lets a grid of one-chart-per-
   indicator load from a single request instead of one request per chart.

   Two honesty rules the helpers below enforce:

     A suppressed cell is ABSENT from `rates`, never zero. Missing means
     "withheld for k-anonymity", so those districts are dropped from the series
     rather than plotted at the origin — a suppressed district must not read as a
     district with no crime.

     r and the fit come from the SERVER cell, never recomputed here. Re-deriving
     them in the browser would let the chart and the stated correlation drift
     apart, and the server already applied the minimum-district gate.
   ========================================================================== */

/** The server's cell for one indicator x crime-category pairing. */
export function socioCell(
  data: SocioEconomicResponse,
  indicator: string,
  crimeCategory: string,
): CorrelationCell | undefined {
  return data.correlation_matrix.find(
    (c) => c.indicator === indicator && c.crime_category === crimeCategory,
  );
}

/** Assemble the district scatter for one indicator x crime-category pairing. */
export function socioSeries(
  data: SocioEconomicResponse,
  indicator: string,
  crimeCategory: string,
): ScatterSeries {
  const cell = socioCell(data, indicator, crimeCategory);
  const points: ScatterPoint[] = [];

  for (const d of data.districts) {
    const x = d.indicators[indicator];
    const y = d.rates[crimeCategory];
    // Absent = suppressed or unmeasured. Skip; never substitute a zero.
    if (x == null || y == null) continue;
    points.push({
      district_id: d.district_id,
      district_name: d.district_name,
      x,
      y,
      crime_count: d.counts[crimeCategory] ?? 0,
      population: d.population,
    });
  }

  return {
    crime_category: crimeCategory,
    indicator,
    r: cell?.r ?? null,
    fit_slope: cell?.fit_slope ?? null,
    fit_intercept: cell?.fit_intercept ?? null,
    points,
  };
}

/** Where one district sits inside a series — the read-out a district commander
 *  wants when the correlation itself is state-wide and cannot be narrowed. */
export interface DistrictStanding {
  districtId: number;
  districtName: string;
  /** this district's indicator value */
  indicatorValue: number;
  /** this district's crime rate per 100k */
  rate: number;
  crimeCount: number;
  /** median indicator value across the plotted districts */
  indicatorMedian: number;
  /** median rate across the plotted districts */
  rateMedian: number;
  /** rate the fit predicts at this indicator value; null without a fit */
  expectedRate: number | null;
  /** signed % this district sits above/below the fit; null without a usable fit */
  residualPct: number | null;
  /** 1 = highest rate in the series */
  rateRank: number;
  /** districts in the series (the rank denominator) */
  outOf: number;
}

export function districtStanding(
  series: ScatterSeries,
  districtId: number | null | undefined,
): DistrictStanding | null {
  if (districtId == null) return null;
  const point = series.points.find((p) => p.district_id === districtId);
  if (!point) return null;

  const expectedRate =
    series.fit_slope != null && series.fit_intercept != null
      ? series.fit_intercept + series.fit_slope * point.x
      : null;

  return {
    districtId,
    districtName: point.district_name,
    indicatorValue: point.x,
    rate: point.y,
    crimeCount: point.crime_count,
    indicatorMedian: median(series.points.map((p) => p.x)),
    rateMedian: median(series.points.map((p) => p.y)),
    expectedRate,
    // Guard a non-positive expectation: a percentage against it would be
    // meaningless (or a divide-by-zero), so report no residual instead.
    residualPct:
      expectedRate != null && expectedRate > 0
        ? ((point.y - expectedRate) / expectedRate) * 100
        : null,
    rateRank: series.points.filter((p) => p.y > point.y).length + 1,
    outOf: series.points.length,
  };
}

function median(values: number[]): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

/** Indicators ordered by how strongly they correlate with `crimeCategory`, so a
 *  grid of per-indicator charts leads with the ones that actually say something.
 *  Indicators with no usable r keep their declared order at the end. */
export function indicatorsByStrength(
  data: SocioEconomicResponse,
  crimeCategory: string,
): string[] {
  const strength = new Map<string, number>();
  for (const c of data.correlation_matrix) {
    if (c.crime_category === crimeCategory && c.r != null) {
      strength.set(c.indicator, Math.abs(c.r));
    }
  }
  return [...data.indicators].sort((a, b) => {
    const sa = strength.get(a);
    const sb = strength.get(b);
    if (sa == null && sb == null) return 0;
    if (sa == null) return 1;
    if (sb == null) return -1;
    return sb - sa;
  });
}

/** The crime category a view should open on: the one the server's narrative is
 *  about, else the first real category ("All Crime" is a synthetic total). */
export function defaultCrimeCategory(data: SocioEconomicResponse): string {
  return (
    data.narrative.crime_category ||
    data.crime_categories.find((c) => c !== "All Crime") ||
    data.crime_categories[0] ||
    ""
  );
}
