import { useState } from "react";
import type { CaseNetworkResponse } from "@/api/types";
import { cn } from "@/lib/utils";

/* ============================================================================
   Embedded case node-link graph (doc 01 §4.2, doc 03 §2.7). A radial layout:
   the case at the centre, its accused and name-linked cases around it. Node
   colour encodes kind; edge style encodes relationship type. Lightweight SVG —
   the full canvas (sigma.js) is the Network destination (Phase 15d).
   ========================================================================== */

const W = 680;
const H = 460;
const CX = W / 2;
const CY = H / 2;
const R = 168;

export function CaseNetworkGraph({
  data,
  onOpenCase,
}: {
  data: CaseNetworkResponse;
  onOpenCase: (caseId: number) => void;
}) {
  const [hover, setHover] = useState<string | null>(null);
  const others = data.nodes.filter((n) => !n.root);
  const root = data.nodes.find((n) => n.root);
  const shown = others.slice(0, 20);

  const positioned = shown.map((n, i) => {
    const angle = (i / shown.length) * Math.PI * 2 - Math.PI / 2;
    return { node: n, x: CX + Math.cos(angle) * R, y: CY + Math.sin(angle) * R };
  });
  const posById = new Map(positioned.map((p) => [p.node.id, p]));

  return (
    <div>
      <div className="overflow-hidden rounded-card border border-hairline bg-surface-2/30">
        <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="Case network">
          {/* edges */}
          {data.edges.map((e, i) => {
            const p = posById.get(e.target === root?.id ? e.source : e.target);
            if (!p) return null;
            const shared = e.type === "shared-accused";
            const active = hover === p.node.id;
            return (
              <line
                key={i}
                x1={CX}
                y1={CY}
                x2={p.x}
                y2={p.y}
                stroke={active ? "var(--primary)" : "var(--border)"}
                strokeWidth={shared ? 2 : 1.2}
                strokeDasharray={shared ? "5 3" : undefined}
              />
            );
          })}

          {/* peripheral nodes */}
          {positioned.map(({ node, x, y }) => {
            const isCase = node.kind === "case";
            const active = hover === node.id;
            return (
              <g
                key={node.id}
                onMouseEnter={() => setHover(node.id)}
                onMouseLeave={() => setHover(null)}
                onClick={() => isCase && node.case_id && onOpenCase(node.case_id)}
                className={cn(isCase && node.case_id && "cursor-pointer")}
              >
                <title>{`${node.label ?? ""}${node.sub ? " · " + node.sub : ""}`}</title>
                <circle
                  cx={x}
                  cy={y}
                  r={active ? 11 : 9}
                  fill={isCase ? "var(--cat-3)" : "var(--accent)"}
                  fillOpacity={0.9}
                  stroke="var(--surface)"
                  strokeWidth={2}
                />
                <text
                  x={x}
                  y={y + (y > CY ? 22 : -14)}
                  textAnchor="middle"
                  className="fill-[var(--text-dim)] text-[10px]"
                >
                  {truncate(node.label ?? "", 16)}
                </text>
              </g>
            );
          })}

          {/* root */}
          <g>
            <circle cx={CX} cy={CY} r={26} fill="var(--primary)" stroke="var(--surface)" strokeWidth={3} />
            <text x={CX} y={CY + 4} textAnchor="middle" className="fill-white text-[11px] font-semibold">
              CASE
            </text>
            <text x={CX} y={CY + 44} textAnchor="middle" className="fill-[var(--text)] text-[11px] font-medium">
              {truncate(root?.label ?? "", 22)}
            </text>
          </g>
        </svg>
      </div>

      {/* legend + overflow note */}
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-12 text-content-dim">
        <LegendDot color="var(--primary)" label="This case" />
        <LegendDot color="var(--accent)" label="Accused" />
        <LegendDot color="var(--cat-3)" label="Linked case (shared accused)" />
        {others.length > shown.length && (
          <span className="tnum">+{others.length - shown.length} more not shown</span>
        )}
      </div>
    </div>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="size-2.5 rounded-full" style={{ background: color }} />
      {label}
    </span>
  );
}

function truncate(s: string, n: number) {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}
