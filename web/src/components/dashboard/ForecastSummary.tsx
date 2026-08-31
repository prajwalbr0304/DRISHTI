import type { ForecastMapResponse } from "@/api/types";
import { formatNumber, formatPercent } from "@/lib/utils";
import { useDistrictNamer } from "@/hooks/useDistricts";

/* ============================================================================
   District-aggregate forecast (doc 01 §4.5/§4.6, policymaker = district only).
   Reads fused forecast cells and rolls them up to district level — never a
   point map. Uncertainty is shown, not hidden: each bar's opacity encodes
   confidence and a % chip states it (doc 03 §2.15).
   ========================================================================== */

interface DistrictAgg {
  district_id: number;
  predicted: number;
  confidence: number;
  cells: number;
}

export function ForecastSummary({ data }: { data: ForecastMapResponse }) {
  // Forecast cells carry only district_id, so names are resolved here rather
  // than printing raw ids.
  const districtName = useDistrictNamer();
  const byDistrict = new Map<number, DistrictAgg>();
  let total = 0;
  let confWeighted = 0;

  for (const c of data.cells) {
    const pred = c.predicted_count ?? 0;
    const conf = c.confidence ?? 0;
    total += pred;
    confWeighted += conf;
    if (c.district_id == null) continue;
    const cur = byDistrict.get(c.district_id) ?? {
      district_id: c.district_id,
      predicted: 0,
      confidence: 0,
      cells: 0,
    };
    cur.predicted += pred;
    cur.confidence += conf;
    cur.cells += 1;
    byDistrict.set(c.district_id, cur);
  }

  const avgConf = data.cells.length ? confWeighted / data.cells.length : 0;
  const districts = [...byDistrict.values()]
    .map((d) => ({ ...d, confidence: d.confidence / Math.max(1, d.cells) }))
    .sort((a, b) => b.predicted - a.predicted)
    .slice(0, 6);
  const peak = Math.max(1, ...districts.map((d) => d.predicted));

  return (
    <div className="space-y-3">
      <div className="flex items-baseline gap-2">
        <span className="tnum text-28 font-semibold leading-none text-content">
          {formatNumber(Math.round(total))}
        </span>
        <span className="text-13 text-content-dim">predicted next period</span>
        <span className="tnum ml-auto text-13 text-content-dim">
          {formatPercent(avgConf, 0)} avg conf.
        </span>
      </div>

      {districts.length > 0 ? (
        <div className="space-y-1.5">
          {districts.map((d) => (
            <div key={d.district_id} className="flex items-center gap-3">
              <span
                className="w-32 shrink-0 truncate text-13 text-content"
                title={districtName(d.district_id)}
              >
                {districtName(d.district_id)}
              </span>
              <span className="relative h-2 flex-1 overflow-hidden rounded-full bg-surface-2">
                <span
                  className="absolute inset-y-0 left-0 rounded-full bg-primary"
                  style={{
                    width: `${(d.predicted / peak) * 100}%`,
                    // uncertainty: fade low-confidence forecasts
                    opacity: 0.35 + Math.min(1, d.confidence) * 0.65,
                  }}
                />
              </span>
              <span className="tnum w-10 shrink-0 text-right text-13 font-medium text-content">
                {formatNumber(Math.round(d.predicted))}
              </span>
              <span className="tnum w-10 shrink-0 text-right text-12 text-content-dim">
                {formatPercent(d.confidence, 0)}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-12 text-content-dim">
          Forecast cells carry no district rollup for this layer.
        </p>
      )}
    </div>
  );
}
