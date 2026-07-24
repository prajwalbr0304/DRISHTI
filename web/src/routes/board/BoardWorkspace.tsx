import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  ArrowLeft, Clock, Download, GitBranch, Loader2, Lock, ScrollText, Share2, Users, Workflow,
} from "lucide-react";
import { api } from "@/api";
import type { BoardSelection } from "@/components/board/BoardCanvas";
import type { ExportOut, NodeDiff } from "@/api/endpoints/board";
import { useRole } from "@/providers/RoleProvider";
import { BoardCanvas } from "@/components/board/BoardCanvas";
import { BoardGraphView } from "@/components/board/BoardGraphView";
import { ObjectPalette } from "@/components/board/panels/ObjectPalette";
import { SelectionInspector } from "@/components/board/panels/SelectionInspector";
import { HelperDrawer } from "@/components/board/panels/HelperDrawer";
import { RationaleDialog, type RationalePayload } from "@/components/board/dialogs/RationaleDialog";
import { SearchAroundDialog } from "@/components/board/dialogs/SearchAroundDialog";
import { EvidenceTrail } from "@/routes/board/EvidenceTrail";
import { BoardTimeline } from "@/routes/board/BoardTimeline";
import { useBoardActivityPoll, useBoardDetail, useBoardPresence, useInvalidateBoard } from "@/routes/board/useBoard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { EmptyState } from "@/components/common/EmptyState";
import { cn } from "@/lib/utils";

const SHARE_LOCK_ROLES = new Set(["supervisor", "super_admin"]);

export function BoardWorkspace() {
  const { boardId: boardIdParam } = useParams();
  const boardId = boardIdParam ? Number(boardIdParam) : null;
  const navigate = useNavigate();
  const { role } = useRole();
  const [sp, setSp] = useSearchParams();
  const tab = (sp.get("tab") as "canvas" | "timeline" | "evidence") ?? "canvas";

  const { data: detail, isLoading, error } = useBoardDetail(boardId);
  const invalidate = useInvalidateBoard(boardId);
  const { newestNotice } = useBoardActivityPoll(boardId, detail);

  const [selection, setSelection] = useState<BoardSelection>({ kind: null, id: null });
  const presence = useBoardPresence(boardId, selection);
  const [filters, setFilters] = useState<{ evidence: boolean; hypothesis: boolean; search: string; hiddenKinds: string[] }>(
    { evidence: true, hypothesis: true, search: "", hiddenKinds: [] });
  const [renderMode, setRenderMode] = useState<"flow" | "graph">("flow");
  const [focusMode, setFocusMode] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [banner, setBanner] = useState<{ kind: "info" | "error"; msg: string } | null>(null);
  const [pendingConnect, setPendingConnect] = useState<{ s: number; t: number } | null>(null);
  const [searchAroundOpen, setSearchAroundOpen] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const [exportResult, setExportResult] = useState<ExportOut | null>(null);
  const [diffs, setDiffs] = useState<Record<number, NodeDiff>>({});
  const [scrubTime, setScrubTime] = useState<string | null>(null);
  const [spawn, setSpawn] = useState(0);
  // Latest selection/readOnly/delete for the (mount-once) keyboard handler.
  const kbd = useRef<{ selection: BoardSelection; readOnly: boolean; del: (s: BoardSelection) => void }>({
    selection: { kind: null, id: null }, readOnly: false, del: () => {},
  });

  const readOnly = !!detail?.board.is_locked || detail?.board.my_role === "viewer";
  const canShareLock = SHARE_LOCK_ROLES.has(role);
  const refTables = useMemo(() => detail ? Array.from(new Set([
    "CaseMaster", "CanonicalPerson", "CanonicalEntity", "EntityGraph",
    "FinancialAccount", "EvidenceItem", "CrimeHotspot",
  ])) : [], [detail]);
  const presentKinds = useMemo(
    () => (detail ? Array.from(new Set(detail.nodes.map((n) => n.node_kind))).sort() : []),
    [detail],
  );

  // live-vs-snapshot diffs (best-effort)
  useEffect(() => {
    if (!boardId || !detail) return;
    let alive = true;
    api.board.diffs(boardId).then((rows) => {
      if (!alive) return;
      const m: Record<number, NodeDiff> = {};
      rows.forEach((d) => (m[d.board_node_id] = d));
      setDiffs(m);
    }).catch(() => undefined);
    return () => { alive = false; };
  }, [boardId, detail]);

  // 'F' toggles projector focus mode (never while typing).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable)) return;
      if (e.key === "f" || e.key === "F") {
        e.preventDefault();
        setFocusMode((v) => !v);
      } else if (e.key === "Escape") {
        setFocusMode(false);
      } else if ((e.key === "Delete" || e.key === "Backspace")
                 && kbd.current.selection.id != null && !kbd.current.readOnly) {
        e.preventDefault();
        kbd.current.del(kbd.current.selection);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const run = useCallback(
    async (fn: () => Promise<unknown>, okMsg?: string) => {
      setBusy(true);
      setBanner(null);
      try {
        await fn();
        invalidate();
        if (okMsg) setBanner({ kind: "info", msg: okMsg });
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Action failed";
        setBanner({ kind: "error", msg });
      } finally {
        setBusy(false);
      }
    },
    [invalidate],
  );

  const nextPos = useCallback(() => {
    const p = { x: 120 + (spawn % 6) * 60, y: 120 + (spawn % 6) * 40 };
    setSpawn((s) => s + 1);
    return p;
  }, [spawn]);

  if (boardId == null) return null;
  if (isLoading) {
    return <div className="grid h-[70vh] place-items-center text-content-dim"><Loader2 className="size-6 animate-spin" /></div>;
  }
  if (error || !detail) {
    return (
      <div className="p-6">
        <EmptyState icon={Workflow} title="Board unavailable"
          description={error instanceof Error ? error.message : "You may not have access to this board."}
          action={<Button variant="outline" onClick={() => navigate("/board")}><ArrowLeft /> Back to boards</Button>} />
      </div>
    );
  }

  const b = detail.board;
  const selectedNode = selection.kind === "node"
    ? detail.nodes.find((n) => n.board_node_id === selection.id) : undefined;
  const canSearchAround = !!selectedNode &&
    (selectedNode.ref_table === "EntityGraph" || selectedNode.canonical_entity_id != null);

  // handlers -----------------------------------------------------------------
  const addObject = (refTable: string, refId: string) => {
    const p = nextPos();
    run(() => api.board.addNode(boardId, { node_kind: "entity", ref_table: refTable, ref_id: refId, pos_x: p.x, pos_y: p.y }),
      "Object pinned.");
  };
  const addNote = () => {
    const p = nextPos();
    run(() => api.board.addAnnotation(boardId, { kind: "sticky", content: "New note", geometry: { x: p.x, y: p.y } }));
  };
  const addFrame = () => {
    const p = nextPos();
    run(() => api.board.addAnnotation(boardId, { kind: "frame", content: "Frame", geometry: { x: p.x, y: p.y, w: 340, h: 240 } }));
  };
  const moveNode = (id: number, x: number, y: number) => {
    api.board.patchNode(boardId, id, { pos_x: x, pos_y: y, is_move_only: true }).catch(() => undefined);
  };
  const moveAnnotation = (id: number, x: number, y: number) => {
    const a = detail.annotations.find((z) => z.board_annotation_id === id);
    const g = { ...(a?.geometry || {}), x, y };
    api.board.patchAnnotation(boardId, id, { geometry: g }).catch(() => undefined);
  };
  const createEdge = (p: RationalePayload) => {
    if (!pendingConnect) return;
    const { s, t } = pendingConnect;
    setPendingConnect(null);
    run(() => api.board.addEdge(boardId, {
      source_node_id: s, target_node_id: t, rationale: p.rationale,
      relationship_type: p.relationship_type, confidence: p.confidence, directed: p.directed,
    }), "Hypothesis link added.");
  };
  const deleteSelection = (sel: BoardSelection) => {
    if (sel.id == null) return;
    if (sel.kind === "node") run(() => api.board.deleteNode(boardId, sel.id!), "Node removed.");
    else if (sel.kind === "edge") run(() => api.board.deleteEdge(boardId, sel.id!), "Link removed.");
    else if (sel.kind === "annotation") run(() => api.board.deleteAnnotation(boardId, sel.id!), "Annotation removed.");
    setSelection({ kind: null, id: null });
  };
  const refreshSnapshot = (nodeId: number) =>
    run(() => api.board.patchNode(boardId, nodeId, { refresh_snapshot: true }), "Snapshot re-pinned to the live object.");
  const saveRationale = (edgeId: number, rationale: string) =>
    run(() => api.board.patchEdge(boardId, edgeId, { rationale }), "Rationale saved.");
  const promote = (edgeId: number) =>
    run(() => api.board.promoteEdge(boardId, edgeId), "Hypothesis proposed for review (no confirmed edge created).");
  // Double-click / instant expand: pull the node's verified 1-hop neighbourhood.
  const expandNode = (nodeId: number) =>
    run(() => api.board.importSubgraph(boardId, { node_id: nodeId, hops: 1, max_neighbors: 12 }),
      "Expanded verified neighbours.");
  // Path Finder: shortest associative path between two entity nodes (imported as evidence).
  const findPath = async (a: number, c: number) => {
    setBusy(true);
    setBanner(null);
    try {
      const r = await api.board.findPath(boardId, a, c);
      invalidate();
      setBanner({
        kind: "info",
        msg: r.found
          ? `Path found — ${r.hops} hop(s); added ${r.nodes_added} node(s) + ${r.edges_added} link(s).`
          : (r.result?.answer || "No path found between the two selected nodes."),
      });
    } catch (e) {
      setBanner({ kind: "error", msg: e instanceof Error ? e.message : "Path Finder failed" });
    } finally {
      setBusy(false);
    }
  };
  const doLock = () =>
    run(() => api.board.lock(boardId), "Board locked for filing.");
  const doBranch = async () => {
    setBusy(true);
    try {
      const nb = await api.board.branch(boardId);
      navigate(`/board/${nb.board.board_id}`);
    } catch (e) {
      setBanner({ kind: "error", msg: e instanceof Error ? e.message : "Branch failed" });
    } finally { setBusy(false); }
  };
  const doExport = async () => {
    setBusy(true);
    try {
      const r = await api.board.export(boardId, "json");
      setExportResult(r);
    } catch (e) {
      setBanner({ kind: "error", msg: e instanceof Error ? e.message : "Export failed" });
    } finally { setBusy(false); }
  };
  const openSource = (path: string) => navigate(path);

  // keep the mount-once keyboard handler pointed at the latest state/handlers
  kbd.current = { selection, readOnly, del: deleteSelection };

  return (
    <div className={cn("flex flex-col", focusMode ? "fixed inset-0 z-50 bg-bg p-2" : "h-[calc(100vh-8rem)]")}>
      {/* toolbar */}
      <div className="mb-2 flex flex-wrap items-center gap-2">
        {!focusMode && (
          <Button variant="ghost" size="icon-sm" onClick={() => navigate("/board")} aria-label="Back to boards">
            <ArrowLeft className="size-4" />
          </Button>
        )}
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="truncate text-16 font-semibold text-content">{b.title}</h1>
            <Badge variant="neutral">v{b.version}</Badge>
            {b.is_locked && <Badge variant="high"><Lock className="size-3" /> locked</Badge>}
            <Badge variant={b.visibility === "private" ? "neutral" : "primary"}>{b.visibility}</Badge>
            <span className="hidden text-11 text-content-dim tnum sm:inline" title="Objects and links on this board">
              {detail.nodes.length} obj · {detail.edges.length} links
            </span>
          </div>
        </div>
        <div className="ml-auto flex items-center gap-1.5">
          {presence.count > 1 && (
            <span className="inline-flex items-center gap-1 rounded-full border border-hairline bg-surface-2/60 px-2 py-0.5 text-11 text-content-dim"
                  title={presence.actors.join(", ")}>
              <Users className="size-3" /> {presence.count} here
            </span>
          )}
          <div className="mr-1 flex overflow-hidden rounded-control border border-hairline">
            <TabBtn active={tab === "canvas"} onClick={() => setSp({ tab: "canvas" }, { replace: true })}><Workflow className="size-3.5" /> Canvas</TabBtn>
            <TabBtn active={tab === "timeline"} onClick={() => setSp({ tab: "timeline" }, { replace: true })}><Clock className="size-3.5" /> Timeline</TabBtn>
            <TabBtn active={tab === "evidence"} onClick={() => setSp({ tab: "evidence" }, { replace: true })}><ScrollText className="size-3.5" /> Evidence Trail</TabBtn>
          </div>
          {canShareLock && !b.is_locked && (
            <Button variant="ghost" size="sm" onClick={() => setShareOpen(true)}><Share2 /> Share</Button>
          )}
          {canShareLock && !b.is_locked && (
            <Button variant="ghost" size="sm" disabled={busy} onClick={doLock}><Lock /> Lock</Button>
          )}
          {b.is_locked && canShareLock && (
            <Button variant="secondary" size="sm" disabled={busy} onClick={doBranch}><GitBranch /> Branch</Button>
          )}
          <Button variant="ghost" size="sm" disabled={busy} onClick={doExport}><Download /> Export</Button>
        </div>
      </div>

      {banner && (
        <div className={cn("mb-2 rounded-control border px-3 py-1.5 text-12",
          banner.kind === "error" ? "border-severity-critical/40 bg-severity-critical/10 text-severity-critical"
            : "border-primary/30 bg-primary/10 text-content")}>
          {banner.msg}
        </div>
      )}
      {newestNotice.current && (
        <div className="mb-2 rounded-control border border-hairline bg-surface-2/50 px-3 py-1 text-11 text-content-dim">
          Synced a committed change from {newestNotice.current.actor} ({newestNotice.current.action}). No local edits were lost.
        </div>
      )}

      {/* body — focus mode always shows the canvas (projector view) */}
      {(tab === "canvas" || focusMode) && (
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-card border border-hairline">
          <div className="flex min-h-0 flex-1">
            {!focusMode && (
              <div className="w-60 shrink-0 border-r border-hairline bg-surface">
                <ObjectPalette
                  filters={filters}
                  setFilters={setFilters}
                  refTables={refTables}
                  kinds={presentKinds}
                  readOnly={readOnly}
                  hasSelectedNode={canSearchAround}
                  onAddNote={addNote}
                  onAddFrame={addFrame}
                  onAddObject={addObject}
                  onSearchAround={() => setSearchAroundOpen(true)}
                />
              </div>
            )}
            <div className="relative min-w-0 flex-1">
              {renderMode === "flow" ? (
              <BoardCanvas
                detail={detail}
                diffs={Object.fromEntries(Object.entries(diffs).map(([k, v]) => [k, v.status]))}
                filters={filters}
                scrubTime={scrubTime}
                focusMode={focusMode}
                readOnly={readOnly}
                selection={selection}
                onSelect={setSelection}
                onMoveNode={moveNode}
                onMoveAnnotation={moveAnnotation}
                onConnect={(s, t) => setPendingConnect({ s, t })}
                onOpenSource={openSource}
                onToggleFocus={() => setFocusMode((v) => !v)}
                onSearchAround={(nodeId) => { setSelection({ kind: "node", id: nodeId }); setSearchAroundOpen(true); }}
                onDeleteNode={(nodeId) => deleteSelection({ kind: "node", id: nodeId })}
                onExpandNode={expandNode}
                onFindPath={findPath}
              />
              ) : (
                <BoardGraphView
                  detail={detail}
                  selection={selection}
                  onSelect={setSelection}
                  onExpandNode={expandNode}
                />
              )}
              <div className="absolute left-2 top-2 z-10 flex overflow-hidden rounded-control border border-hairline bg-surface/90 backdrop-blur">
                <RenderBtn active={renderMode === "flow"} onClick={() => setRenderMode("flow")} title="Editable link canvas">Flow</RenderBtn>
                <RenderBtn active={renderMode === "graph"} onClick={() => setRenderMode("graph")} title="Force-directed network (read-only)">Network</RenderBtn>
              </div>
              {detail.nodes.length === 0 && detail.annotations.length === 0 && (
                <div className="pointer-events-none absolute inset-0 grid place-items-center p-6">
                  <EmptyState icon={Workflow} title="Empty board"
                    description="Pin an object from the palette, or use Send to Board from a case, entity, network node, map feature or prediction." />
                </div>
              )}
            </div>
            {!focusMode && (
              <div className="w-72 shrink-0 overflow-y-auto border-l border-hairline bg-surface">
                <SelectionInspector
                  detail={detail}
                  selection={selection}
                  diffs={diffs}
                  readOnly={readOnly}
                  canPromote={canShareLock}
                  onOpenSource={openSource}
                  onDelete={deleteSelection}
                  onRefreshSnapshot={refreshSnapshot}
                  onSaveRationale={saveRationale}
                  onPromote={promote}
                />
              </div>
            )}
          </div>
          {!focusMode && (
            <HelperDrawer detail={detail} activity={[]} open={drawerOpen} onToggle={() => setDrawerOpen((v) => !v)} />
          )}
        </div>
      )}

      {tab === "timeline" && !focusMode && (
        <div className="min-h-0 flex-1 overflow-auto rounded-card border border-hairline bg-surface p-4">
          <BoardTimeline boardId={boardId} onScrub={setScrubTime} scrubTime={scrubTime} />
        </div>
      )}

      {tab === "evidence" && !focusMode && (
        <div className="min-h-0 flex-1 overflow-auto rounded-card border border-hairline bg-surface p-4">
          <EvidenceTrail detail={detail} onExport={doExport} exportResult={exportResult} />
        </div>
      )}

      {/* dialogs */}
      <RationaleDialog
        open={!!pendingConnect}
        sourceLabel={detail.nodes.find((n) => n.board_node_id === pendingConnect?.s)?.label ?? undefined}
        targetLabel={detail.nodes.find((n) => n.board_node_id === pendingConnect?.t)?.label ?? undefined}
        onCancel={() => setPendingConnect(null)}
        onCreate={createEdge}
      />
      <SearchAroundDialog
        open={searchAroundOpen}
        boardId={boardId}
        nodeId={selectedNode?.board_node_id ?? null}
        focalLabel={selectedNode?.label ?? undefined}
        onClose={() => setSearchAroundOpen(false)}
        onImported={() => { invalidate(); setBanner({ kind: "info", msg: "Verified subgraph imported as evidence." }); }}
      />
      <ShareDialog open={shareOpen} boardId={boardId} onClose={() => setShareOpen(false)}
        onDone={() => { invalidate(); setShareOpen(false); }}
        onError={(m) => setBanner({ kind: "error", msg: m })} />
      <ExportDialog result={exportResult} onClose={() => setExportResult(null)} />
    </div>
  );
}

function TabBtn({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick}
      className={cn("inline-flex items-center gap-1.5 px-2.5 py-1.5 text-12 font-medium transition-colors",
        active ? "bg-surface-2 text-content" : "text-content-dim hover:text-content")}>
      {children}
    </button>
  );
}

function RenderBtn({ active, onClick, title, children }: {
  active: boolean; onClick: () => void; title?: string; children: React.ReactNode;
}) {
  return (
    <button type="button" onClick={onClick} title={title}
      className={cn("px-2.5 py-1 text-11 font-medium transition-colors",
        active ? "bg-primary text-primary-fg" : "text-content-dim hover:text-content")}>
      {children}
    </button>
  );
}

function ShareDialog({ open, boardId, onClose, onDone, onError }: {
  open: boolean; boardId: number; onClose: () => void; onDone: () => void; onError: (m: string) => void;
}) {
  const [actor, setActor] = useState("");
  const [role, setRole] = useState("viewer");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      await api.board.addCollaborator(boardId, { actor: actor.trim(), role });
      onDone();
      setActor("");
    } catch (e) {
      onError(e instanceof Error ? e.message : "Share failed");
    } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Users className="size-4" /> Share board</DialogTitle>
          <DialogDescription>Grant a demo actor editor/viewer access. Sharing beyond the case/unit scope is warned and audited.</DialogDescription>
        </DialogHeader>
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <label className="mb-1 block text-12 text-content-dim">Actor</label>
            <Input value={actor} onChange={(e) => setActor(e.target.value)} placeholder="demo.analyst" className="h-8 text-13" />
          </div>
          <NativeSelect value={role} onChange={setRole} className="w-28"
            options={[{ value: "viewer", label: "viewer" }, { value: "editor", label: "editor" }]} placeholder="role" />
          <Button size="sm" disabled={!actor.trim() || busy} onClick={submit}>Add</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function ExportDialog({ result, onClose }: { result: ExportOut | null; onClose: () => void }) {
  return (
    <Dialog open={!!result} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Download className="size-4" /> Export ready</DialogTitle>
          <DialogDescription>Source-linked, synthetic-watermarked export to private Stratus with a short-lived URL.</DialogDescription>
        </DialogHeader>
        {result && (
          <div className="space-y-2 text-12">
            <Row k="Format">{result.format.toUpperCase()}</Row>
            <Row k="Object hash">{result.sha256.slice(0, 24)}…</Row>
            <Row k="Expires in">{result.expires_in_s}s</Row>
            <Row k="Watermark">{result.watermark}</Row>
            <a href={result.download_url} target="_blank" rel="noreferrer"
              className="inline-flex items-center gap-1.5 rounded-control bg-primary px-3 py-1.5 text-primary-fg">
              <Download className="size-4" /> Download
            </a>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function Row({ k, children }: { k: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-3 border-b border-hairline/60 pb-1">
      <span className="text-content-dim">{k}</span>
      <span className="max-w-[60%] truncate text-content">{children}</span>
    </div>
  );
}
