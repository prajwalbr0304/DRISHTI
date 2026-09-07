import * as React from "react";
import { ArrowDownRight, ArrowUpRight, Minus, X } from "lucide-react";
import { cn, formatCompact, formatNumber } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { InfoHint } from "@/components/common/InfoHint";
import { useDashTile } from "@/components/dashboard/dashTile";
import { errorMessage } from "@/api/contracts";

/* ============================================================================
   KPI stat card (doc 03 §2.1): big tabular number + label + signed delta vs.
   prior period + 12-point sparkline. Delta shows an ARROW and a SIGN, never
   colour alone. Supports loading / error / and an honest "awaiting API" state.

   FOUR OUTCOMES, FOUR APPEARANCES. They are different facts and must not render
   alike:

     loading      a skeleton — the measurement is still in flight;
     pending      "— awaiting API" — no endpoint serves this card yet;
     error        "— unavailable" + the server's reason — the source was asked
                  and it refused or failed;
     null value   a bare "—" — the source answered and has no number.

   The error case used to draw the same bare em-dash as a null value, which made
   a 503 indistinguishable from "measured nothing". That is the one confusion
   this card must never create: an unavailable source is a fault to chase, an
   empty measurement is not. `docs/production-role-dashboard-plan.md` §3.3 states
   the rule ("Unavailable: the source or calculation is not ready; never
   substitute zero") and its acceptance test 16 requires the states stay
   distinct.
   ========================================================================== */

export interface KpiCardProps {
  icon?: React.ReactNode;
  label: string;
  value?: number | null;
  unit?: string;
  /** signed percent change vs. prior period */
  delta?: number | null;
  /** What the delta is measured against. Defaults to the prior period of equal
   *  length; a card comparing against the same period LAST YEAR must say so,
   *  because "+3% vs. prior" and "+3% vs. last year" are different claims. */
  deltaLabel?: string;
  /** when true, a downward move is the good direction (e.g. crime counts) */
  improveWhenDown?: boolean;
  /** recent values for the sparkline */
  spark?: number[];
  loading?: boolean;
  error?: unknown;
  /** endpoint not built yet — show honestly rather than fabricate */
  pending?: boolean;
  pendingNote?: string;
  hint?: React.ReactNode;
  className?: string;
}

export function KpiCard({
  icon,
  label,
  value,
  unit,
  delta,
  deltaLabel = "vs. prior",
  improveWhenDown = true,
  spark,
  loading,
  error,
  pending,
  pendingNote,
  hint,
  className,
}: KpiCardProps) {
  return (
    <div className={cn("group flex flex-col rounded-card border border-hairline bg-surface p-5 shadow-card", className)}>
      {/* Label row — the ⓘ hint is the same affordance the widget headers and
          page headers use, and it always renders so no card looks half-built.
          The remove control sits directly beside it, so the two card-level
          affordances live in one place. */}
      <div className="flex items-center gap-1.5 text-body-s text-content-dim">
        {icon && <span className="[&_svg]:size-4">{icon}</span>}
        <span className="truncate">{label}</span>
        {/* The hint carries the REASON when there is one. A card reading
            "unavailable" with no way to find out why sends the reader to the
            network tab; the server already said what was wrong, so repeat it
            here alongside what the card would have measured. */}
        <InfoHint>
          {error ? (
            <span>
              <strong>Unavailable.</strong> {errorMessage(error)}
              {hint ? <> <span className="block pt-1.5">{hint}</span></> : null}
            </span>
          ) : pending ? (
            (pendingNote ?? "Awaiting a Wave-B endpoint.")
          ) : (
            hint
          )}
        </InfoHint>
        <RemoveTile label={label} />
      </div>

      {/* The metric row absorbs the card's remaining height (`flex-1`) and
          centres in it. On a tall card that keeps the number optically with its
          label instead of stranding it at the bottom edge, and gives the
          sparkline real vertical space to grow into. */}
      <div className="mt-2 flex flex-1 items-center justify-between gap-3">
        <div className="min-w-0">
          {loading ? (
            <Skeleton className="h-8 w-24" />
          ) : pending ? (
            <div className="flex items-baseline gap-2">
              <span className="text-28 font-bold leading-none text-content-dim">—</span>
              <span className="rounded-badge bg-surface-2 px-1.5 py-0.5 text-body-s text-content-dim">
                awaiting API
              </span>
            </div>
          ) : error ? (
            /* Same shape as the pending state so the band stays visually even,
               but in the warning tone: this source was asked and it failed,
               which is a fault to chase rather than a card yet to be built. */
            <div className="flex items-baseline gap-2">
              <span className="text-28 font-bold leading-none text-content-dim">—</span>
              <span className="rounded-badge bg-surface-2 px-1.5 py-0.5 text-body-s text-severity-high">
                unavailable
              </span>
            </div>
          ) : (
            <span className="tnum text-28 font-bold leading-none text-content">
              {value == null ? "—" : value >= 100000 ? formatCompact(value) : formatNumber(value)}
              {/* A unit belongs to a number. "—%" would read as a percentage
                  that was measured and came back empty, which is a different
                  claim from "there is no measurement". */}
              {unit && value != null && (
                <span className="ml-0.5 text-heading-s font-bold text-content-dim">{unit}</span>
              )}
            </span>
          )}
          {!loading && !pending && !error && delta != null && (
            <Delta pct={delta} label={deltaLabel} improveWhenDown={improveWhenDown} />
          )}
        </div>

        {!pending && spark && spark.length > 1 && <Sparkline values={spark} />}
      </div>
    </div>
  );
}

/* Dismiss this card. Present only inside a DashboardGrid, which supplies the
   tile handle — a KpiCard rendered standalone has no board to be removed from,
   so the control is simply absent rather than inert.

   Revealed on card hover and on keyboard focus. It stays mounted either way so
   the control is reachable by Tab rather than by pointer alone; `opacity` hides
   it visually without removing it from the tab order. `no-drag` keeps the click
   from starting a tile drag, since a stat card is its own drag handle. */
function RemoveTile({ label }: { label: string }) {
  const tile = useDashTile();
  if (!tile) return null;
  return (
    <button
      type="button"
      onClick={tile.remove}
      aria-label={`Remove the ${label} card`}
      title={`Remove the ${label} card`}
      className={cn(
        "no-drag ml-auto inline-grid shrink-0 place-items-center rounded-full text-content-dim",
        "opacity-0 transition-opacity hover:text-severity-high focus-visible:opacity-100",
        "group-hover:opacity-100 group-focus-within:opacity-100",
      )}
    >
      <X className="size-4" aria-hidden />
    </button>
  );
}

function Delta({
  pct,
  label,
  improveWhenDown,
}: {
  pct: number;
  label: string;
  improveWhenDown: boolean;
}) {
  const flat = Math.abs(pct) < 0.05;
  const up = pct > 0;
  const good = flat ? false : improveWhenDown ? !up : up;
  const Icon = flat ? Minus : up ? ArrowUpRight : ArrowDownRight;
  return (
    /* `flex` + `max-w-full`, not `inline-flex`: an inline-flex row sizes to its
       content and pushes past the card edge, which is what a long delta label
       ("vs. same period last year") did next to a sparkline. The arrow and the
       percentage are `shrink-0` so the measurement is never the thing that gets
       cut; only the comparison label truncates, and it is stated in full in the
       ⓘ hint. */
    <div
      className={cn(
        "mt-1.5 flex max-w-full items-center gap-0.5 text-body-s font-bold tnum",
        flat ? "text-content-dim" : good ? "text-severity-low" : "text-severity-high",
      )}
    >
      <Icon className="size-3.5 shrink-0" />
      <span className="shrink-0">
        {up ? "+" : ""}
        {pct.toFixed(1)}%
      </span>
      <span className="ml-1 min-w-0 truncate font-normal text-content-dim">{label}</span>
    </div>
  );
}

/** 12-point sparkline (doc 03 §2.1). Single hue, no axes.
 *
 *  Self-measuring: on a wide card a fixed 88px sparkline left a large gap
 *  between the metric and the card edge, so it grows into whatever width the
 *  card gives it. The path is recomputed at the real pixel width rather than
 *  stretched with a viewBox, which would distort the stroke and the end dot. */
export function Sparkline({
  values,
  width,
  height,
}: {
  values: number[];
  /** fixed size; omit either to fill the available space in that axis */
  width?: number;
  height?: number;
}) {
  const hostRef = React.useRef<HTMLDivElement>(null);
  const [box, setBox] = React.useState({ w: 0, h: 0 });

  React.useEffect(() => {
    const el = hostRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver((entries) => {
      const r = entries[0]?.contentRect;
      if (r?.width) setBox({ w: r.width, h: r.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const w = width ?? box.w;
  const h = height ?? (box.h || 32);

  /* `flex-1` absorbs the card's spare width and `h-full` its spare height, both
     capped so a very large card does not turn a sparkline into a feature chart.
     Until measured the slot is held open at its minimum so nothing reflows. */
  const slot = "h-full min-h-8 max-h-16 min-w-[88px] max-w-[240px] flex-1";

  if (!w) return <div ref={hostRef} className={slot} aria-hidden />;

  return (
    <div ref={hostRef} className={slot}>
      <SparklinePath values={values} width={w} height={h} />
    </div>
  );
}

function SparklinePath({
  values,
  width,
  height,
}: {
  values: number[];
  width: number;
  height: number;
}) {
  const pts = values.slice(-12);
  const min = Math.min(...pts);
  const max = Math.max(...pts);
  const span = max - min || 1;
  const step = pts.length > 1 ? width / (pts.length - 1) : width;
  const d = pts
    .map((v, i) => {
      const x = i * step;
      const y = height - ((v - min) / span) * (height - 4) - 2;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const lastX = (pts.length - 1) * step;
  const lastY = height - ((pts[pts.length - 1] - min) / span) * (height - 4) - 2;

  return (
    <svg width={width} height={height} className="shrink-0 overflow-visible" aria-hidden>
      <path d={d} fill="none" stroke="var(--primary)" strokeWidth={1.5} strokeLinejoin="round" />
      <circle cx={lastX} cy={lastY} r={2} fill="var(--primary)" />
    </svg>
  );
}
