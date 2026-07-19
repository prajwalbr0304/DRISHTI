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
  const graphRef = useRef<Graph | null>(null);
  const theme = useChartTheme();

  // live refs for reducers (avoid rebuilding sigma on selection/highlight change)
  const selRef = useRef<string | null>(null);
  selRef.current = selectedId != null ? String(selectedId) : null;
  const hlNodesRef = useRef<Set<string>>(new Set());
  const hlEdgesRef = useRef<Set<string>>(new Set());
  hlNodesRef.current = new Set((highlightNodeIds ?? []).map(String));
  hlEdgesRef.current = new Set((highlightEdgeIds ?? []).map(String));
  // Hover-to-focus: the hovered node + its immediate neighbours stay lit, the
  // rest of a dense community fades back so the local structure is legible.
  const hoverRef = useRef<string | null>(null);
  const hoverNeighboursRef = useRef<Set<string>>(new Set());
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
      const iterations = graph.order > 250 ? 80 : 260;
      try {
        forceAtlas2.assign(graph, {
          iterations,
          settings: {
            ...forceAtlas2.inferSettings(graph),
            // More spread + hub separation so a dense clique reads as a shape,
            // not a hairball: stronger repulsion, gravity that still keeps it on
            // screen, and outbound-attraction so high-degree hubs push apart.
            gravity: 0.6,
            scalingRatio: 30,
            adjustSizes: true,
            outboundAttractionDistribution: true,
            barnesHutOptimize: graph.order > 150,
          },
        });
      } catch {
        /* layout best-effort */
      }
    }
    graphRef.current = graph;

    const renderer = new Sigma(graph, container, {
      allowInvalidContainer: true,
      renderLabels: true,
      labelColor: { color: theme.text },
      labelSize: 12,
      labelFont: theme.fontFamily,
      labelWeight: "600",
      // Only the more central nodes label by default -> far less text clutter;
      // hovering any node reveals its (and its neighbours') labels.
      labelRenderedSizeThreshold: 7,
      defaultEdgeColor: theme.grid,
      // Thin edges by default so nodes/labels dominate the dense view.
      edgeReducer: (edge, data) => {
        const res: Record<string, unknown> = { ...data };
        const hlE = hlEdgesRef.current;
        const hov = hoverRef.current;
        // explicit edge highlight (Path Finder reveal) takes precedence
        if (hlE.size > 0) {
          if (hlE.has(edge)) {
            res.color = theme.primary;
            res.size = Math.max(Number(data.size) || 1, 3);
            res.zIndex = 3;
          } else {
            res.color = theme.grid;
            res.size = 0.4;
          }
          return res;
        }
        res.size = Math.max(0.5, (Number(data.size) || 1) * 0.6);
        if (hov && graphRef.current) {
          const g = graphRef.current;
          const touches = g.hasExtremity?.(edge, hov);
          if (touches) {
            res.size = Math.max(Number(res.size) || 1, 2.4);
            res.zIndex = 3;
          } else {
            res.color = theme.grid;
            res.hidden = true; // fully fade unrelated edges on hover
          }
        }
        return res;
      },
      nodeReducer: (node, data) => {
        const res: Record<string, unknown> = { ...data };
        const sel = selRef.current === node;
        const hlN = hlNodesRef.current;
        const hov = hoverRef.current;
        // explicit node highlight (Path Finder) takes precedence
        if (hlN.size > 0 && !hlN.has(node) && !sel) {
          res.color = theme.grid;
          res.label = "";
          res.highlighted = false;
        }
        // hover focus: dim everything except the hovered node + its neighbours
        if (hov) {
          const isFocus = node === hov || hoverNeighboursRef.current.has(node);
          if (isFocus) {
            res.forceLabel = true;
            if (node === hov) {
              res.highlighted = true;
              res.zIndex = 4;
            }
          } else {
            res.color = theme.grid;
            res.label = "";
            res.highlighted = false;
          }
        }
        if (sel) {
          res.highlighted = true;
          res.zIndex = 3;
          res.forceLabel = true;
        }
        return res;
      },
    });

    renderer.on("clickNode", ({ node }) => cbRef.current.onNodeClick?.(node));
    renderer.on("enterNode", ({ node }) => {
      hoverRef.current = node;
      const g = graphRef.current;
      hoverNeighboursRef.current = g ? new Set(g.neighbors(node)) : new Set();
      renderer.refresh();
      if (container) container.style.cursor = "pointer";
    });
    renderer.on("leaveNode", () => {
      hoverRef.current = null;
      hoverNeighboursRef.current = new Set();
      renderer.refresh();
      if (container) container.style.cursor = "default";
    });
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
      graphRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature, theme.text, theme.textDim, theme.grid, theme.primary]);

  // Re-run reducers when selection / highlight changes (no rebuild).
  useEffect(() => {
    sigmaRef.current?.refresh();
  }, [selectedId, highlightNodeIds, highlightEdgeIds]);

  return <div ref={containerRef} style={{ height }} className="w-full" />;
}
