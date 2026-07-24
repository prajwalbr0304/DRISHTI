import { useMemo } from "react";
import { GraphCanvas, type GEdge, type GNode } from "@/components/network/GraphCanvas";
import type { BoardDetail } from "@/api/endpoints/board";
import type { BoardSelection } from "@/components/board/BoardCanvas";

/* ============================================================================
   Read-only WebGL (sigma.js / forceAtlas2) force-graph view of the board — the
   SAME data as the React Flow canvas, rendered for dense boards where the
   hand-laid canvas becomes a hairball. Node size = degree, colour = kind,
   hover-to-focus + influence halos come from the shared network renderer.
   Click selects (drives the inspector); double-click expands an entity's
   verified neighbours. Editing (drag/connect/annotate) stays on the Flow view.
   ========================================================================== */

// Board node kinds -> the network renderer's entity-type colour buckets.
const KIND_TO_ETYPE: Record<string, string> = {
  entity: "person", accused: "person", victim: "person", complainant: "person",
  vehicle: "vehicle", phone: "phone", account: "account", location: "location",
  hotspot: "location", organisation: "organisation", gang: "gang",
};

export function BoardGraphView({
  detail,
  selection,
  onSelect,
  onExpandNode,
  colorMode = "type",
}: {
  detail: BoardDetail;
  selection: BoardSelection;
  onSelect: (s: BoardSelection) => void;
  onExpandNode?: (nodeId: number) => void;
  colorMode?: "type" | "community";
}) {
  const nodes = useMemo<GNode[]>(() => {
    const degree = new Map<number, number>();
    for (const e of detail.edges) {
      degree.set(e.source_node_id, (degree.get(e.source_node_id) ?? 0) + 1);
      degree.set(e.target_node_id, (degree.get(e.target_node_id) ?? 0) + 1);
    }
    // object-backed nodes only (sticky/frame annotations are not graph nodes)
    return detail.nodes.map((n) => ({
      id: n.board_node_id,
      label: n.label ?? n.node_kind,
      entity_type: KIND_TO_ETYPE[n.node_kind] ?? n.node_kind,
      degree: degree.get(n.board_node_id) ?? 0,
    }));
  }, [detail.nodes, detail.edges]);

  const edges = useMemo<GEdge[]>(
    () =>
      detail.edges.map((e) => ({
        id: e.board_edge_id,
        source: e.source_node_id,
        target: e.target_node_id,
        relationship_type: e.relationship_type ?? undefined,
        weight: (e.style as { weight?: number })?.weight ?? 1,
      })),
    [detail.edges],
  );

  if (nodes.length === 0) {
    return (
      <div className="grid h-full place-items-center text-12 text-content-dim">
        Nothing to render yet — pin or seed an object first.
      </div>
    );
  }

  return (
    <div className="h-full w-full">
      <GraphCanvas
        nodes={nodes}
        edges={edges}
        colorMode={colorMode}
        selectedId={selection.kind === "node" ? selection.id ?? undefined : undefined}
        onNodeClick={(id) => onSelect({ kind: "node", id: Number(id) })}
        onNodeDoubleClick={(id) => onExpandNode?.(Number(id))}
        height="100%"
      />
    </div>
  );
}
