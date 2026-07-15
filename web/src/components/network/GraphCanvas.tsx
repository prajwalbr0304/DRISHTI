import { useEffect, useMemo, useRef } from "react";
import Graph from "graphology";
import Sigma from "sigma";
import forceAtlas2 from "graphology-layout-forceatlas2";
import { useChartTheme } from "@/lib/chart-theme";
import {
  communityColor,
  entityColor,
  relationshipColor,
  scaleEdge,
  scaleSize,
} from "@/components/network/graphEncoding";

/* ============================================================================
   Full-canvas WebGL graph (sigma.js). Encodes the doc-03/04 contract: node
   size = centrality, colour = entity type or community, halo = high influence
   (sigma `highlighted`), edge width = strength, colour = relationship type.
   Never renders the whole graph — callers pass a bounded, expand-on-demand set.
   ========================================================================== */

export interface GNode {
  id: number | string;
  label?: string | null;
  entity_type?: string | null;
  pagerank?: number | null;
  betweenness?: number | null;
  community?: number | null;
  degree?: number | null;
}
export interface GEdge {
  id?: number | string;
  source: number | string;
  target: number | string;
  relationship_type?: string | null;
  weight?: number | null;
}

export function GraphCanvas({
  nodes,
  edges,
  colorMode = "type",
  selectedId,
  highlightNodeIds,
  highlightEdgeIds,
  influentialTopN = 5,
  onNodeClick,
  onNodeDoubleClick,
  height = "100%",
}: {
  nodes: GNode[];
  edges: GEdge[];
  colorMode?: "type" | "community";
  selectedId?: string | number | null;
  highlightNodeIds?: (string | number)[];
  highlightEdgeIds?: (string | number)[];
  influentialTopN?: number;
  onNodeClick?: (id: string) => void;
  onNodeDoubleClick?: (id: string) => void;
  height?: number | string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const sigmaRef = useRef<Sigma | null>(null);
  const theme = useChartTheme();

  // live refs for reducers (avoid rebuilding sigma on selection/highlight change)
  const selRef = useRef<string | null>(null);
  selRef.current = selectedId != null ? String(selectedId) : null;
  const hlNodesRef = useRef<Set<string>>(new Set());
  const hlEdgesRef = useRef<Set<string>>(new Set());
  hlNodesRef.current = new Set((highlightNodeIds ?? []).map(String));
  hlEdgesRef.current = new Set((highlightEdgeIds ?? []).map(String));
  const cbRef = useRef({ onNodeClick, onNodeDoubleClick });
  cbRef.current = { onNodeClick, onNodeDoubleClick };

  // Build a stable signature so we only rebuild when the graph actually changes.
  const signature = useMemo(
    () =>
      `${colorMode}|${nodes.length}|${edges.length}|${nodes.map((n) => n.id).join(",")}`,
    [nodes, edges, colorMode],
  );

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const graph = new Graph({ multi: true, type: "undirected" });

    // centrality extent for sizing
    const cents = nodes.map((n) => n.pagerank ?? n.degree ?? 0);
    const minC = Math.min(...cents, 0);
    const maxC = Math.max(...cents, 0.0001);
    // top-N influential -> halo
    const influential = new Set(
      [...nodes]
        .sort((a, b) => (b.pagerank ?? b.degree ?? 0) - (a.pagerank ?? a.degree ?? 0))
        .slice(0, influentialTopN)
        .map((n) => String(n.id)),
    );

    for (const n of nodes) {
      const id = String(n.id);
      if (graph.hasNode(id)) continue;
      graph.addNode(id, {
        label: n.label ?? id,
        x: Math.random(),
        y: Math.random(),
        size: scaleSize(n.pagerank ?? n.degree ?? 0, minC, maxC),
        color: colorMode === "community" ? communityColor(n.community) : entityColor(n.entity_type),
        highlighted: influential.has(id),
        entityType: n.entity_type ?? "",
      });
    }

    for (const e of edges) {
      const s = String(e.source);
      const t = String(e.target);
      if (!graph.hasNode(s) || !graph.hasNode(t)) continue;
      const key = String(e.id ?? `${s}__${t}`);
      if (graph.hasEdge(key)) continue;
      try {
        graph.addEdgeWithKey(key, s, t, {
          size: scaleEdge(e.weight),
          color: relationshipColor(e.relationship_type),
        });
      } catch {
        /* parallel/duplicate — ignore */
      }
    }

    if (graph.order > 0) {
      const iterations = graph.order > 250 ? 60 : 180;
      try {
        forceAtlas2.assign(graph, {
          iterations,
          settings: {
            ...forceAtlas2.inferSettings(graph),
            gravity: 1.2,
            scalingRatio: 12,
            adjustSizes: true,
            barnesHutOptimize: graph.order > 150,
          },
        });
      } catch {
        /* layout best-effort */
      }
    }

    const renderer = new Sigma(graph, container, {
      allowInvalidContainer: true,
      renderLabels: true,
      labelColor: { color: theme.textDim },
      labelSize: 11,
      labelFont: theme.fontFamily,
      labelWeight: "500",
      defaultEdgeColor: theme.grid,
      nodeReducer: (node, data) => {
        const res: Record<string, unknown> = { ...data };
        const sel = selRef.current === node;
        const hl = hlNodesRef.current;
        if (hl.size > 0 && !hl.has(node) && !sel) {
          res.color = theme.grid;
          res.label = "";
          res.highlighted = false;
        }
        if (sel) {
          res.highlighted = true;
          res.zIndex = 3;
        }
        return res;
      },
      edgeReducer: (edge, data) => {
        const res: Record<string, unknown> = { ...data };
        const hl = hlEdgesRef.current;
        if (hl.size > 0) {
          if (hl.has(edge)) {
            res.color = theme.primary;
            res.size = Math.max(Number(data.size) || 1, 3);
            res.zIndex = 3;
          } else {
            res.color = theme.grid;
            res.size = 0.5;
          }
        }
        return res;
      },
    });

    renderer.on("clickNode", ({ node }) => cbRef.current.onNodeClick?.(node));
    renderer.on("doubleClickNode", (e) => {
      // prevent sigma's default zoom on double-click (API varies across builds)
      const payload = e as unknown as {
        preventSigmaDefault?: () => void;
        event?: { preventSigmaDefault?: () => void };
      };
      payload.preventSigmaDefault?.();
      payload.event?.preventSigmaDefault?.();
      cbRef.current.onNodeDoubleClick?.(e.node);
    });

    sigmaRef.current = renderer;
    return () => {
      renderer.kill();
      sigmaRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature, theme.text, theme.textDim, theme.grid, theme.primary]);

  // Re-run reducers when selection / highlight changes (no rebuild).
  useEffect(() => {
    sigmaRef.current?.refresh();
  }, [selectedId, highlightNodeIds, highlightEdgeIds]);

  return <div ref={containerRef} style={{ height }} className="w-full" />;
}
