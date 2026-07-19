import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";
import ReactFlow, {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  MiniMap,
  Panel,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Connection,
  type Edge,
  type Node,
} from "reactflow";
import "reactflow/dist/style.css";
import {
  Crosshair, ExternalLink, LayoutGrid, Maximize2, Minimize2, Radius, Trash2,
  Waypoints, Workflow,
} from "lucide-react";
import type { BoardDetail, BoardEdgeT, BoardNodeT, NodeDiff } from "@/api/endpoints/board";
import { kindStyle } from "@/components/board/boardEncoding";
import { boardNodeTypes } from "@/components/board/nodes/BoardNodes";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/* Calm, Palantir-inspired edge styling: evidence = thin muted solid (label only
   when selected), hypothesis = dashed slate with a small label, selected = primary. */
function edgeVisual(e: BoardEdgeT, isSelected: boolean) {
  const isHyp = e.edge_class === "hypothesis";
  const stroke = isSelected ? "#6366f1" : isHyp ? "#94a3b8" : "rgba(120,134,156,0.45)";
  const width = isSelected ? 2.4 : isHyp ? 1.6 : 1.1;
  const showLabel = isSelected || isHyp;
  return {
    style: { stroke, strokeWidth: width, strokeDasharray: isHyp ? "6 4" : undefined },
    label: showLabel ? e.relationship_type || (isHyp ? "hypothesis" : undefined) : undefined,
    labelStyle: { fontSize: 9, fill: "#94a3b8" },
    labelShowBg: false,
    markerEnd: e.directed
      ? { type: MarkerType.ArrowClosed, color: stroke, width: 14, height: 14 }
      : undefined,
  };
}

interface ContextMenuState {
  x: number;
  y: number;
  nodeId: number;
  refTable?: string | null;
  openSrc?: string | null;
  label: string;
}

export interface BoardSelection {
  kind: "node" | "edge" | "annotation" | null;
  id: number | null;
}

interface Props {
  detail: BoardDetail;
  diffs: Record<number, NodeDiff["status"]>;
  filters: { evidence: boolean; hypothesis: boolean; search: string };
  scrubTime?: string | null;
  focusMode: boolean;
  readOnly: boolean;
  selection: BoardSelection;
  onSelect: (s: BoardSelection) => void;
  onMoveNode: (id: number, x: number, y: number) => void;
  onMoveAnnotation: (id: number, x: number, y: number) => void;
  onConnect: (source: number, target: number) => void;
  onOpenSource: (path: string) => void;
  onToggleFocus: () => void;
  onSearchAround: (nodeId: number) => void;
  onDeleteNode: (nodeId: number) => void;
}

type LayoutMode = "radial" | "force" | "hierarchical";

function computeLayout(
  ids: number[],
  edges: { s: number; t: number }[],
  mode: LayoutMode,
  cx = 480,
  cy = 320,
): Map<number, { x: number; y: number }> {
  const pos = new Map<number, { x: number; y: number }>();
  const n = ids.length || 1;
  if (mode === "radial") {
    const R = Math.max(180, n * 26);
    ids.forEach((id, i) => {
      const a = (2 * Math.PI * i) / n;
      pos.set(id, { x: cx + R * Math.cos(a), y: cy + R * Math.sin(a) });
    });
    return pos;
  }
  if (mode === "hierarchical") {
    // BFS layers from the highest-degree node
    const deg = new Map<number, number>();
    ids.forEach((id) => deg.set(id, 0));
    edges.forEach((e) => {
      deg.set(e.s, (deg.get(e.s) ?? 0) + 1);
      deg.set(e.t, (deg.get(e.t) ?? 0) + 1);
    });
    const root = [...ids].sort((a, b) => (deg.get(b) ?? 0) - (deg.get(a) ?? 0))[0];
    const adj = new Map<number, number[]>();
    edges.forEach((e) => {
      (adj.get(e.s) ?? adj.set(e.s, []).get(e.s)!).push(e.t);
      (adj.get(e.t) ?? adj.set(e.t, []).get(e.t)!).push(e.s);
    });
    const layer = new Map<number, number>([[root, 0]]);
    const q = [root];
    while (q.length) {
      const cur = q.shift()!;
      for (const nb of adj.get(cur) ?? []) {
        if (!layer.has(nb)) {
          layer.set(nb, (layer.get(cur) ?? 0) + 1);
          q.push(nb);
        }
      }
    }
    const byLayer = new Map<number, number[]>();
    ids.forEach((id) => {
      const l = layer.get(id) ?? 99;
      (byLayer.get(l) ?? byLayer.set(l, []).get(l)!).push(id);
    });
    [...byLayer.entries()].forEach(([l, arr]) => {
      arr.forEach((id, i) => pos.set(id, { x: 120 + i * 240, y: 120 + l * 170 }));
    });
    return pos;
  }
  // force: light repulsion + spring (few iterations)
  ids.forEach((id, i) => {
    const a = (2 * Math.PI * i) / n;
    pos.set(id, { x: cx + 200 * Math.cos(a), y: cy + 200 * Math.sin(a) });
  });
  for (let it = 0; it < 120; it++) {
    for (const a of ids) {
      let fx = 0;
      let fy = 0;
      const pa = pos.get(a)!;
      for (const b of ids) {
        if (a === b) continue;
        const pb = pos.get(b)!;
        const dx = pa.x - pb.x;
        const dy = pa.y - pb.y;
        const d2 = dx * dx + dy * dy + 0.01;
        const f = 9000 / d2;
        fx += dx * f;
        fy += dy * f;
      }
      pa.x += Math.max(-25, Math.min(25, fx));
      pa.y += Math.max(-25, Math.min(25, fy));
    }
    for (const e of edges) {
      const pa = pos.get(e.s);
      const pb = pos.get(e.t);
      if (!pa || !pb) continue;
      const dx = pb.x - pa.x;
      const dy = pb.y - pa.y;
      pa.x += dx * 0.02;
      pa.y += dy * 0.02;
      pb.x -= dx * 0.02;
      pb.y -= dy * 0.02;
    }
  }
  return pos;
}

function Inner(props: Props) {
  const {
    detail, diffs, filters, scrubTime, readOnly, selection, onSelect, onMoveNode,
    onMoveAnnotation, onConnect, onOpenSource, focusMode, onToggleFocus,
    onSearchAround, onDeleteNode,
  } = props;
  const rf = useReactFlow();
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [menu, setMenu] = useState<ContextMenuState | null>(null);

  const search = filters.search.trim().toLowerCase();

  // Live refs so the STRUCTURAL rebuild reads the latest overlay state without
  // being re-triggered by it (that re-trigger is what made dragged nodes snap
  // back on click). Overlay state is applied by a separate, position-preserving
  // effect below.
  const selRef = useRef(selection);
  const filtersRef = useRef(filters);
  const diffsRef = useRef(diffs);
  const scrubRef = useRef(scrubTime);
  const onOpenSourceRef = useRef(onOpenSource);
  selRef.current = selection;
  filtersRef.current = filters;
  diffsRef.current = diffs;
  scrubRef.current = scrubTime;
  onOpenSourceRef.current = onOpenSource;

  // build RF nodes/edges from the authoritative board detail
  // STRUCTURAL signature: only which objects exist (ids + kinds). Selection,
  // filter, diff and scrub are NOT here — they must never trigger a rebuild, or
  // a just-dragged node snaps back to the server position on the next click.
  const structuralSig = useMemo(
    () =>
      JSON.stringify({
        n: detail.nodes.map((n) => n.board_node_id).sort((a, b) => a - b),
        a: detail.annotations.map((a) => a.board_annotation_id).sort((a, b) => a - b),
        e: detail.edges.map((e) => `${e.board_edge_id}:${e.edge_class}`).sort(),
      }),
    [detail],
  );

  const matchesSearch = useCallback((n: BoardNodeT) => {
    const q = (filtersRef.current.search || "").trim().toLowerCase();
    if (!q) return true;
    return (n.label ?? "").toLowerCase().includes(q) || (n.node_kind ?? "").includes(q);
  }, []);

  const outOfWindow = useCallback((n: BoardNodeT) => {
    const s = scrubRef.current;
    return !!s && !!n.created_at && n.created_at > s;
  }, []);

  // FULL rebuild — runs only when objects are added/removed/imported. Positions
  // come from the (persisted) board detail; earlier drags were persisted, so
  // this never snaps a node back. Reads overlay state via refs (latest values).
  useEffect(() => {
    const sel = selRef.current;
    const rfNodes: Node[] = detail.nodes.map((n) => ({
      id: `n:${n.board_node_id}`,
      type: "object",
      position: { x: n.pos_x, y: n.pos_y },
      selected: sel.kind === "node" && sel.id === n.board_node_id,
      hidden: !matchesSearch(n),
      data: {
        obj: n, diffStatus: diffsRef.current[n.board_node_id], dimmed: outOfWindow(n),
        reviewedPoi: !!(n.style as { reviewed_poi?: boolean })?.reviewed_poi,
        onOpenSource: onOpenSourceRef.current,
      },
      draggable: !readOnly,
    }));
    for (const a of detail.annotations) {
      const g = (a.geometry || {}) as { x?: number; y?: number; w?: number; h?: number };
      rfNodes.push({
        id: `a:${a.board_annotation_id}`,
        type: a.kind === "frame" ? "frame" : "sticky",
        position: { x: g.x ?? 0, y: g.y ?? 0 },
        selected: sel.kind === "annotation" && sel.id === a.board_annotation_id,
        style: a.kind === "frame" ? { width: g.w ?? 320, height: g.h ?? 220, zIndex: -1 } : undefined,
        data: { ann: a, dimmed: false },
        draggable: !readOnly,
      });
    }
    setNodes(rfNodes);

    const f = filtersRef.current;
    setEdges(detail.edges.map((e) => {
      const isSel = sel.kind === "edge" && sel.id === e.board_edge_id;
      const hidden = e.edge_class === "evidence" ? !f.evidence : !f.hypothesis;
      return {
        id: `e:${e.board_edge_id}`,
        source: `n:${e.source_node_id}`,
        target: `n:${e.target_node_id}`,
        selected: isSel,
        hidden,
        ...edgeVisual(e, isSel),
        data: { edge: e },
      } as Edge;
    }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [structuralSig, readOnly]);

  // OVERLAY — selection / filter / diff / scrub / live label refresh applied to
  // the EXISTING react-flow items WITHOUT touching their positions.
  useEffect(() => {
    const nById = new Map(detail.nodes.map((n) => [n.board_node_id, n]));
    const aById = new Map(detail.annotations.map((a) => [a.board_annotation_id, a]));
    setNodes((prev) =>
      prev.map((rn) => {
        if (rn.id.startsWith("n:")) {
          const id = Number(rn.id.slice(2));
          const n = nById.get(id);
          if (!n) return rn;
          return {
            ...rn,
            selected: selection.kind === "node" && selection.id === id,
            hidden: !matchesSearch(n),
            data: {
              obj: n, diffStatus: diffs[id], dimmed: outOfWindow(n),
              reviewedPoi: !!(n.style as { reviewed_poi?: boolean })?.reviewed_poi,
              onOpenSource,
            },
          };
        }
        const id = Number(rn.id.slice(2));
        const a = aById.get(id);
        return {
          ...rn,
          selected: selection.kind === "annotation" && selection.id === id,
          data: { ann: a ?? (rn.data as { ann: unknown }).ann, dimmed: false },
        };
      }),
    );
    const eById = new Map(detail.edges.map((e) => [e.board_edge_id, e]));
    setEdges((prev) =>
      prev.map((re) => {
        const id = Number(re.id.slice(2));
        const e = eById.get(id);
        if (!e) return re;
        const isSel = selection.kind === "edge" && selection.id === id;
        const hidden = e.edge_class === "evidence" ? !filters.evidence : !filters.hypothesis;
        return { ...re, selected: isSel, hidden, ...edgeVisual(e, isSel), data: { edge: e } };
      }),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selection, filters, diffs, scrubTime, detail]);

  const handleConnect = useCallback(
    (c: Connection) => {
      if (readOnly || !c.source || !c.target) return;
      if (!c.source.startsWith("n:") || !c.target.startsWith("n:")) return;
      onConnect(Number(c.source.slice(2)), Number(c.target.slice(2)));
    },
    [onConnect, readOnly],
  );

  const handleDragStop = useCallback(
    (_e: unknown, node: Node) => {
      const [kind, idStr] = node.id.split(":");
      const id = Number(idStr);
      if (kind === "n") onMoveNode(id, Math.round(node.position.x), Math.round(node.position.y));
      else if (kind === "a") onMoveAnnotation(id, Math.round(node.position.x), Math.round(node.position.y));
    },
    [onMoveNode, onMoveAnnotation],
  );

  const tidy = useCallback(
    (mode: LayoutMode) => {
      const objIds = detail.nodes.map((n) => n.board_node_id);
      const eds = detail.edges.map((e) => ({ s: e.source_node_id, t: e.target_node_id }));
      const layout = computeLayout(objIds, eds, mode);
      setNodes((ns) =>
        ns.map((n) => {
          if (!n.id.startsWith("n:")) return n;
          const p = layout.get(Number(n.id.slice(2)));
          return p ? { ...n, position: p } : n;
        }),
      );
      // persist new positions (manual positions elsewhere are preserved: only
      // object nodes in the layout set move).
      layout.forEach((p, id) => onMoveNode(id, Math.round(p.x), Math.round(p.y)));
      setTimeout(() => rf.fitView({ padding: 0.2, duration: 400 }), 50);
    },
    [detail, onMoveNode, rf, setNodes],
  );

  const onSelChange = useCallback(
    (params: { nodes: Node[]; edges: Edge[] }) => {
      if (params.edges.length) {
        onSelect({ kind: "edge", id: Number(params.edges[0].id.slice(2)) });
      } else if (params.nodes.length) {
        const nd = params.nodes[0];
        const [k, idStr] = nd.id.split(":");
        onSelect({ kind: k === "a" ? "annotation" : "node", id: Number(idStr) });
      } else {
        onSelect({ kind: null, id: null });
      }
    },
    [onSelect],
  );

  const closeMenu = useCallback(() => setMenu(null), []);
  const onNodeContextMenu = useCallback(
    (e: ReactMouseEvent, node: Node) => {
      e.preventDefault();
      if (!node.id.startsWith("n:")) return;
      const id = Number(node.id.slice(2));
      const obj = (node.data as { obj?: BoardNodeT }).obj;
      onSelect({ kind: "node", id });
      setMenu({ x: e.clientX, y: e.clientY, nodeId: id, refTable: obj?.ref_table,
                openSrc: obj?.open_in_source, label: obj?.label || `Node ${id}` });
    },
    [onSelect],
  );

  return (
    <>
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={boardNodeTypes}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onConnect={handleConnect}
      onNodeDragStop={handleDragStop}
      onSelectionChange={onSelChange}
      onNodeContextMenu={onNodeContextMenu}
      onPaneClick={() => { closeMenu(); onSelect({ kind: null, id: null }); }}
      onMoveStart={closeMenu}
      nodesDraggable={!readOnly}
      nodesConnectable={!readOnly}
      elementsSelectable
      selectionOnDrag
      panOnDrag={[1, 2]}
      minZoom={0.15}
      maxZoom={2.5}
      fitView
      proOptions={{ hideAttribution: true }}
      className="bg-bg"
    >
      <Background variant={BackgroundVariant.Dots} gap={22} size={1} className="text-hairline" />
      <MiniMap
        pannable
        zoomable
        nodeColor={(n) => kindStyle((n.data as { obj?: { node_kind?: string } })?.obj?.node_kind).color}
        className="!bg-surface !border !border-hairline"
      />
      <Controls className="!border-hairline" />
      <Panel position="top-right" className="flex gap-1">
        <div className="flex overflow-hidden rounded-control border border-hairline bg-surface/90 backdrop-blur">
          <IconBtn label="Radial tidy" onClick={() => tidy("radial")}><Radius className="size-4" /></IconBtn>
          <IconBtn label="Force tidy" onClick={() => tidy("force")}><Workflow className="size-4" /></IconBtn>
          <IconBtn label="Hierarchical tidy" onClick={() => tidy("hierarchical")}><LayoutGrid className="size-4" /></IconBtn>
          <IconBtn label="Fit view" onClick={() => rf.fitView({ padding: 0.2, duration: 400 })}><Crosshair className="size-4" /></IconBtn>
          <IconBtn label={focusMode ? "Exit focus (F)" : "Projector focus (F)"} onClick={onToggleFocus}>
            {focusMode ? <Minimize2 className="size-4" /> : <Maximize2 className="size-4" />}
          </IconBtn>
        </div>
      </Panel>
    </ReactFlow>

    {menu && (
      <>
        <div className="fixed inset-0 z-40" onClick={closeMenu}
             onContextMenu={(e) => { e.preventDefault(); closeMenu(); }} />
        <div
          className="fixed z-50 min-w-[196px] rounded-card border border-hairline bg-surface p-1 text-13 shadow-pop"
          style={{ left: Math.min(menu.x, window.innerWidth - 210), top: Math.min(menu.y, window.innerHeight - 160) }}
        >
          <div className="truncate px-2 py-1 text-11 font-medium uppercase tracking-wide text-content-dim">
            {menu.label}
          </div>
          {menu.refTable === "EntityGraph" && (
            <MenuItem icon={Waypoints} onClick={() => { onSearchAround(menu.nodeId); closeMenu(); }}>
              Search around
            </MenuItem>
          )}
          {menu.openSrc && (
            <MenuItem icon={ExternalLink} onClick={() => { onOpenSource(menu.openSrc!); closeMenu(); }}>
              Open in source
            </MenuItem>
          )}
          {!readOnly && (
            <MenuItem icon={Trash2} danger onClick={() => { onDeleteNode(menu.nodeId); closeMenu(); }}>
              Remove from board
            </MenuItem>
          )}
        </div>
      </>
    )}
    </>
  );
}

function IconBtn({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <Button variant="ghost" size="icon-sm" onClick={onClick} aria-label={label} title={label}
            className={cn("rounded-none")}>
      {children}
    </Button>
  );
}

function MenuItem({
  icon: Icon, onClick, danger, children,
}: {
  icon: typeof Waypoints; onClick: () => void; danger?: boolean; children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-2 rounded-control px-2 py-1.5 text-left transition-colors hover:bg-surface-2",
        danger ? "text-severity-critical" : "text-content",
      )}
    >
      <Icon className="size-4 shrink-0" /> {children}
    </button>
  );
}

export function BoardCanvas(props: Props) {
  return (
    <ReactFlowProvider>
      <Inner {...props} />
    </ReactFlowProvider>
  );
}
