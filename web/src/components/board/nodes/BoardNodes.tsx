import { memo } from "react";
import { Handle, Position, type NodeProps } from "reactflow";
import { AlertTriangle, ExternalLink, GitCompareArrows } from "lucide-react";
import { cn } from "@/lib/utils";
import type { BoardAnnotationT, BoardNodeT } from "@/api/endpoints/board";
import { kindStyle, tint } from "@/components/board/boardEncoding";

export interface ObjectNodeData {
  obj: BoardNodeT;
  diffStatus?: "live" | "changed" | "broken" | "unavailable";
  dimmed?: boolean;
  reviewedPoi?: boolean;
  onOpenSource?: (path: string) => void;
}

export interface StickyNodeData {
  ann: BoardAnnotationT;
  dimmed?: boolean;
}

// Person-like kinds render an avatar (initials) like a Palantir photo node.
const PERSON_KINDS = new Set(["entity", "accused", "victim", "complainant", "organisation", "gang"]);

function initials(label?: string | null): string {
  const parts = (label ?? "").trim().split(/\s+/).filter(Boolean).slice(0, 2);
  const s = parts.map((p) => p[0]?.toUpperCase() ?? "").join("");
  return s || "•";
}

/* --- object node: a clean icon/name object (details live in the Inspector) -- */
export const ObjectNode = memo(function ObjectNode({ data, selected }: NodeProps<ObjectNodeData>) {
  const { obj, diffStatus, dimmed, reviewedPoi, onOpenSource } = data;
  const ks = kindStyle(obj.node_kind);
  const Icon = ks.icon;
  const isPerson = PERSON_KINDS.has(obj.node_kind);
  const name = obj.label || `${ks.label} ${obj.ref_id ?? obj.board_node_id}`;

  return (
    <div
      className={cn(
        "group relative w-[172px] rounded-card border bg-surface shadow-card transition-all",
        selected ? "border-primary ring-2 ring-primary/40" : "border-hairline hover:border-content-dim/40",
        dimmed && "opacity-30",
      )}
    >
      <Handle type="target" position={Position.Left} className="!size-2 !border-0 !bg-content-dim/50" />
      <Handle type="source" position={Position.Right} className="!size-2 !border-0 !bg-content-dim/50" />

      {reviewedPoi && (
        <span className="pointer-events-none absolute -inset-1 rounded-card ring-2 ring-severity-high/70"
              aria-label="Reviewed person of interest" />
      )}

      <div className="flex items-center gap-2.5 p-2.5">
        {/* avatar / icon chip */}
        {isPerson ? (
          <span className="grid size-9 shrink-0 place-items-center rounded-full text-12 font-semibold"
                style={{ background: tint(ks.color, 0.18), color: ks.color, boxShadow: `inset 0 0 0 1.5px ${ks.color}` }}>
            {initials(obj.label)}
          </span>
        ) : (
          <span className="grid size-9 shrink-0 place-items-center rounded-card"
                style={{ background: tint(ks.color, 0.16), color: ks.color }}>
            <Icon className="size-4" />
          </span>
        )}

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1">
            <span className="truncate text-10 font-medium uppercase tracking-wide" style={{ color: ks.color }}>
              {ks.label}
            </span>
            {diffStatus === "changed" && (
              <GitCompareArrows className="size-3 text-severity-medium" aria-label="Source changed since pinned" />
            )}
            {diffStatus === "broken" && (
              <AlertTriangle className="size-3 text-severity-critical" aria-label="Source reference broken" />
            )}
          </div>
          <div className="truncate text-13 font-semibold leading-tight text-content" title={name}>
            {name}
          </div>
        </div>
      </div>

      {/* thin provenance footer — only for object-backed nodes */}
      {obj.ref_table && (
        <div className="flex items-center gap-1 border-t border-hairline/60 px-2.5 py-1 text-10 text-content-dim">
          <span className="truncate" title={`${obj.ref_table}:${obj.ref_id}`}>
            {obj.ref_table}{obj.source_version ? ` · v${obj.source_version}` : ""}
          </span>
          {obj.open_in_source && (
            <button
              type="button"
              className="ml-auto opacity-0 transition-opacity group-hover:opacity-100 hover:text-primary"
              onClick={(e) => { e.stopPropagation(); onOpenSource?.(obj.open_in_source!); }}
              aria-label="Open in source"
              title="Open in source"
            >
              <ExternalLink className="size-3" />
            </button>
          )}
        </div>
      )}
    </div>
  );
});

/* --- sticky / text annotation ------------------------------------------- */
export const StickyNode = memo(function StickyNode({ data, selected }: NodeProps<StickyNodeData>) {
  const { ann, dimmed } = data;
  const style = (ann.style || {}) as { color?: string };
  const isText = ann.kind === "text";
  return (
    <div
      className={cn(
        "w-[190px] rounded-card p-2.5 text-12 shadow-card transition-opacity",
        isText ? "bg-transparent text-content" : "text-amber-950",
        selected && "ring-2 ring-primary/50",
        dimmed && "opacity-30",
      )}
      style={{ background: isText ? undefined : style.color || "#fde68a" }}
    >
      <Handle type="target" position={Position.Left} className="!size-1.5 !border-0 !bg-transparent" />
      <div className="whitespace-pre-wrap break-words leading-snug">{ann.content || (isText ? "Text" : "Sticky note")}</div>
      <Handle type="source" position={Position.Right} className="!size-1.5 !border-0 !bg-transparent" />
    </div>
  );
});

/* --- frame (grouping rectangle) ----------------------------------------- */
export const FrameNode = memo(function FrameNode({ data, selected }: NodeProps<StickyNodeData>) {
  const { ann, dimmed } = data;
  return (
    <div
      className={cn(
        "h-full w-full rounded-card border-2 border-dashed border-content-dim/35 bg-surface-2/10",
        selected && "border-primary/60",
        dimmed && "opacity-30",
      )}
    >
      <div className="inline-block rounded-br-card bg-surface-2/60 px-2 py-1 text-11 font-medium uppercase tracking-wide text-content-dim">
        {ann.content || "Frame"}
      </div>
    </div>
  );
});

export const boardNodeTypes = {
  object: ObjectNode,
  sticky: StickyNode,
  frame: FrameNode,
};
