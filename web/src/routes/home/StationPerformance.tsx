import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Clock, FileCheck2, Layers, Users } from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import { Badge } from "@/components/ui/badge";

/* Prompt 20 Part C — real station & officer performance (replaces the
   "Awaiting the performance API" placeholder). Aggregate, explainable metrics
   with denominators, time window, data-freshness and limitations. No punitive
   per-officer ranking; officer load is an aggregate distribution. */

const num = (v: number | undefined | null) =>
  v == null ? "—" : v.toLocaleString();

function Stat({ icon, label, value, sub }: {
  icon: React.ReactNode; label: string; value: React.ReactNode; sub?: string;
}) {
  return (
    <div className="rounded-card border border-hairline p-2.5">
      <div className="flex items-center gap-1.5 text-11 text-content-dim">
        <span className="[&_svg]:size-3.5">{icon}</span>
        {label}
      </div>
      <div className="tnum mt-0.5 text-20 font-semibold text-content">{value}</div>
      {sub && <div className="text-11 text-content-dim">{sub}</div>}
    </div>
  );
}

export function StationPerformance({ districtId, unitId }: { districtId?: number; unitId?: number }) {
  const q = useQuery({
    queryKey: ["performance", "overview", districtId ?? null, unitId ?? null],
    queryFn: ({ signal }) =>
      api.performance.overview({ district_id: districtId, unit_id: unitId, window_days: 90 }, signal),
  });

  if (q.isLoading) return <p className="p-2 text-12 text-content-dim">Loading performance…</p>;
  if (q.error) {
    return (
      <p className="flex items-center gap-1 p-2 text-12 text-severity-high">
        <AlertTriangle className="size-3.5" /> {errorMessage(q.error)}
      </p>
    );
  }
  const d = q.data;
  if (!d) return null;
  if (d.empty) {
    return (
      <div className="p-2 text-12 text-content-dim">
        No cases in the current scope. {d.limitations?.slice(-1)[0]}
      </div>
    );
  }

  const t = d.totals;
  const cs = d.chargesheet;
  const off = d.officers;
  const bal = d.workload_balance;
  const maxAge = Math.max(1, ...d.ageing.map((a) => a.count));

  return (
    <div className="space-y-3">
      {/* freshness / window */}
      <div className="flex flex-wrap items-center gap-2 text-11">
        <Badge variant="neutral">as of {d.as_of}</Badge>
        <Badge variant="neutral">window {d.window_days}d</Badge>
        {d.stale && (
          <Badge variant="medium">
            data {d.data_age_days}d old (synthetic 2021–2025)
          </Badge>
        )}
        <span className="text-content-dim">
          {t.stations_in_scope} stations · {t.officers_in_scope} officers
        </span>
      </div>

      {/* headline stats */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat icon={<Layers />} label="Active workload" value={num(t.active_workload)}
          sub={`of ${num(t.total_cases)} total`} />
        <Stat icon={<Clock />} label="New (window)" value={num(t.new_cases_in_window)}
          sub={`last ${d.window_days}d`} />
        <Stat icon={<AlertTriangle />} label="Overdue reviews" value={num(t.overdue_reviews)}
          sub={`open > ${t.overdue_threshold_days}d`} />
        <Stat icon={<FileCheck2 />} label="Chargesheet rate"
          value={cs.throughput_ratio != null ? `${Math.round(cs.throughput_ratio * 100)}%` : "—"}
          sub={`${cs.filed_in_window}/${cs.new_cases_in_window} filed/new`} />
      </div>

      {/* ageing + disposal + officer load */}
      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-card border border-hairline p-2.5">
          <div className="mb-1.5 text-12 font-medium text-content">Open-case ageing</div>
          <div className="space-y-1">
            {d.ageing.map((a) => (
              <div key={a.bucket} className="flex items-center gap-2 text-11">
                <span className="w-16 text-content-dim">{a.bucket}</span>
                <div className="h-2 flex-1 overflow-hidden rounded bg-surface-2">
                  <div className="h-full bg-primary" style={{ width: `${(a.count / maxAge) * 100}%` }} />
                </div>
                <span className="tnum w-12 text-right text-content">{a.count}</span>
              </div>
            ))}
          </div>
          <p className="mt-1.5 text-11 text-content-dim">
            Median time to chargesheet: {cs.median_days_to_chargesheet ?? "—"}d
            {cs.avg_days_to_chargesheet != null ? ` (avg ${cs.avg_days_to_chargesheet}d)` : ""}
          </p>
        </div>

        <div className="rounded-card border border-hairline p-2.5">
          <div className="mb-1.5 flex items-center gap-1.5 text-12 font-medium text-content">
            <Users className="size-3.5" /> Officer load & balance
          </div>
          <div className="grid grid-cols-3 gap-2 text-11">
            <div><div className="text-content-dim">median</div><div className="tnum text-content">{off.median_open_per_officer}</div></div>
            <div><div className="text-content-dim">p90</div><div className="tnum text-content">{off.p90_open_per_officer}</div></div>
            <div><div className="text-content-dim">max</div><div className="tnum text-content">{off.max_open_per_officer}</div></div>
          </div>
          <p className="mt-1.5 text-11 text-content-dim">
            {off.heavy_load_officers} officer(s) hold &gt; {off.heavy_load_threshold} open cases.
            Station imbalance (busiest/median): {bal.imbalance_ratio_max_over_median ?? "—"}×.
          </p>
        </div>
      </div>

      {/* per-station table */}
      {d.stations.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-11">
            <thead className="text-content-dim">
              <tr className="border-b border-hairline text-left">
                <th className="py-1 pr-2 font-medium">Station</th>
                <th className="py-1 pr-2 font-medium">Open</th>
                <th className="py-1 pr-2 font-medium">New</th>
                <th className="py-1 pr-2 font-medium">Overdue</th>
              </tr>
            </thead>
            <tbody>
              {d.stations.slice(0, 8).map((s) => (
                <tr key={s.unit_id} className="border-b border-hairline/60">
                  <td className="py-1 pr-2 text-content">{s.unit_name}</td>
                  <td className="tnum py-1 pr-2">{s.open_cases}</td>
                  <td className="tnum py-1 pr-2">{s.new_cases}</td>
                  <td className="tnum py-1 pr-2">{s.overdue}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-11 text-content-dim">{off.note} {d.limitations?.[2]}</p>
    </div>
  );
}
