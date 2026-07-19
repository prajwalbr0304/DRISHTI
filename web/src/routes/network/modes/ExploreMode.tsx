import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Loader2, MousePointerClick, RotateCcw } from "lucide-react";
import { api } from "@/api";
import type { GraphEdge, GraphNode } from "@/api/types";
import { usePeekStore } from "@/stores/usePeekStore";
import { Button } from "@/components/ui/button";
import { EntitySearch } from "@/components/network/EntitySearch";
import { GraphCanvas, type GEdge, type GNode } from "@/components/network/GraphCanvas";
import { ModeLayout, CanvasLegend } from "@/components/network/ModeLayout";
import { ENTITY_LEGEND } from "@/components/network/graphEncoding";
import { EmptyState } from "@/components/common/EmptyState";
import { Network as NetworkIcon } from "lucide-react";
import { SendToBoard } from "@/components/board/SendToBoard";

/* Explore: drop an entity, expand neighbours hop-by-hop (never a hairball). */
export function ExploreMode({
  colorMode,
  initialEntity,
}: {
  colorMode: "type" | "community";
  initialEntity?: number | null;
}) {
  const push = usePeekStore((s) => s.push);
  const [seed, setSeed] = useState<{ id: number; label: string } | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [expanding, setExpanding] = useState(false);

  const nodesMap = useRef(new Map<string, GNode>());
  const edgesMap = useRef(new Map<string, GEdge>());
  const [version, setVersion] = useState(0);

  const mergeSubgraph = useCallback((nodes: GraphNode[], edges: GraphEdge[]) => {
    for (const n of nodes) {
      nodesMap.current.set(String(n.entity_id), {
        id: n.entity_id,
        label: n.label,
        entity_type: n.entity_type,
        pagerank: n.pagerank,
        betweenness: n.betweenness,
        community: n.community,
      });
    }
    for (const e of edges) {
      nodesMap.current.has(String(e.source)) &&
        nodesMap.current.has(String(e.target)) &&
        edgesMap.current.set(String(e.edge_id), {
          id: e.edge_id,
          source: e.source,
          target: e.target,
          relationship_type: e.relationship_type,
          weight: e.weight,
        });
    }
    setVersion((v) => v + 1);
  }, []);

  const loadSeed = useCallback(
    async (id: number, label: string) => {
      nodesMap.current.clear();
      edgesMap.current.clear();
      setSeed({ id, label });
      setSelected(String(id));
      setExpanding(true);
      try {
        const r = await api.graph.neighbourhood(id, 1, 15);
        mergeSubgraph(r.nodes, r.edges);
      } finally {
        setExpanding(false);
      }
    },
    [mergeSubgraph],
  );

  const expand = useCallback(
    async (id: string) => {
      setExpanding(true);
      try {
        const r = await api.graph.neighbourhood(Number(id), 1, 12);
        mergeSubgraph(r.nodes, r.edges);
      } finally {
        setExpanding(false);
      }
    },
    [mergeSubgraph],
  );

  const nodes = useMemo(() => [...nodesMap.current.values()], [version]);
  const edges = useMemo(() => [...edgesMap.current.values()], [version]);

  // Deep-link seed (e.g. from a peek "Open in Network Analysis").
  const loadedInitial = useRef<number | null>(null);
  useEffect(() => {
    if (initialEntity && loadedInitial.current !== initialEntity) {
      loadedInitial.current = initialEntity;
      loadSeed(initialEntity, `Entity ${initialEntity}`);
    }
  }, [initialEntity, loadSeed]);

  return (
    <ModeLayout
      panelTitle="Explore"
      panel={
        <div className="space-y-3">
          <EntitySearch
            placeholder="Search a starting entity…"
            selected={seed}
            onPick={(e) => loadSeed(e.entity_id, e.label)}
            onClear={() => {
              setSeed(null);
              nodesMap.current.clear();
              edgesMap.current.clear();
              setVersion((v) => v + 1);
            }}
          />
          {seed && (
            <>
              <div className="flex items-center gap-2 rounded-control bg-surface-2/60 px-2.5 py-2 text-12 text-content-dim">
                <MousePointerClick className="size-4 shrink-0 text-primary" />
                Double-click any node to expand its neighbours.
              </div>
              <div className="tnum text-12 text-content-dim">
                {nodes.length} nodes · {edges.length} edges {expanding && "· loading…"}
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => loadSeed(seed.id, seed.label)}
                className="w-full justify-center"
              >
                <RotateCcw /> Reset to seed
              </Button>
              {/* Send the focal (or selected) graph node to an Investigation Board. */}
              <SendToBoard
                className="w-full justify-center"
                target={{
                  refTable: "EntityGraph",
                  refId: selected ? Number(selected) : seed.id,
                  nodeKind: "entity",
                  label: selected ? nodesMap.current.get(selected)?.label ?? seed.label : seed.label,
                }}
              />
              <p className="text-11 text-content-dim">
                Sends the selected node (or seed) as a live reference; on the board,
                Search Around imports its verified neighbours as evidence.
              </p>
            </>
          )}
        </div>
      }
    >
      {!seed ? (
        <div className="grid h-full place-items-center p-6">
          <EmptyState
            icon={NetworkIcon}
            title="Start exploring"
            description="Search for a person, phone, vehicle or account to drop onto the canvas, then expand its network hop by hop."
          />
        </div>
      ) : (
        <>
          {expanding && (
            <div className="absolute right-3 top-3 z-10 inline-flex items-center gap-1.5 rounded-control border border-hairline bg-surface/90 px-2 py-1 text-12 text-content-dim backdrop-blur">
              <Loader2 className="size-3.5 animate-spin" /> expanding
            </div>
          )}
          <GraphCanvas
            nodes={nodes}
            edges={edges}
            colorMode={colorMode}
            selectedId={selected}
            onNodeClick={(id) => {
              setSelected(id);
              const n = nodesMap.current.get(id);
              push({ kind: "person", id: Number(id), label: n?.label ?? `Entity ${id}`, sublabel: n?.entity_type ?? undefined });
            }}
            onNodeDoubleClick={(id) => expand(id)}
          />
          <CanvasLegend items={colorMode === "type" ? ENTITY_LEGEND : [{ label: "Coloured by community", color: "#6366f1" }]} />
        </>
      )}
    </ModeLayout>
  );
}
