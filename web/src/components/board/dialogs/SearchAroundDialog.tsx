import { useState } from "react";
import { Loader2, Waypoints } from "lucide-react";
import { api } from "@/api";
import type { SearchAroundNeighbor, SearchAroundResult } from "@/api/endpoints/board";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

/**
 * Search Around with hop/type/time caps and preview-before-add. Imported
 * relationships arrive as read-only evidence edges; candidate/unverified ones
 * are labelled and never called facts.
 */
export function SearchAroundDialog({
  open,
  boardId,
  nodeId,
  focalLabel,
  onClose,
  onImported,
}: {
  open: boolean;
  boardId: number;
  nodeId: number | null;
  focalLabel?: string;
  onClose: () => void;
  onImported: () => void;
}) {
  const [hops, setHops] = useState(1);
  const [maxNeighbors, setMaxNeighbors] = useState(15);
  const [preview, setPreview] = useState<SearchAroundResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const runPreview = async () => {
    if (nodeId == null) return;
    setLoading(true);
    setErr(null);
    try {
      const r = await api.board.searchAround(boardId, { node_id: nodeId, hops, max_neighbors: maxNeighbors, preview: true });
      setPreview(r);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Search Around failed");
    } finally {
      setLoading(false);
    }
  };

  const runImport = async () => {
    if (nodeId == null) return;
    setImporting(true);
    setErr(null);
    try {
      await api.board.importSubgraph(boardId, { node_id: nodeId, hops, max_neighbors: maxNeighbors });
      onImported();
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Import failed");
    } finally {
      setImporting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Waypoints className="size-4" /> Search Around {focalLabel}</DialogTitle>
          <DialogDescription>
            Expand verified relationships from the canonical graph (capped, id-based — never name matching).
            Preview first, then import as read-only evidence links.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-wrap items-end gap-3">
          <label className="text-12 text-content-dim">
            Hops (max 3)
            <select value={hops} onChange={(e) => setHops(Number(e.target.value))}
                    className="ml-2 h-8 rounded-control border border-hairline bg-surface-2 px-2 text-13 text-content">
              {[1, 2, 3].map((h) => <option key={h} value={h}>{h}</option>)}
            </select>
          </label>
          <label className="text-12 text-content-dim">
            Max neighbours
            <select value={maxNeighbors} onChange={(e) => setMaxNeighbors(Number(e.target.value))}
                    className="ml-2 h-8 rounded-control border border-hairline bg-surface-2 px-2 text-13 text-content">
              {[5, 10, 15, 25, 50].map((h) => <option key={h} value={h}>{h}</option>)}
            </select>
          </label>
          <Button variant="outline" size="sm" onClick={runPreview} disabled={loading || nodeId == null}>
            {loading ? <Loader2 className="animate-spin" /> : null} Preview
          </Button>
        </div>

        {err && <p className="text-12 text-severity-critical">{err}</p>}

        {preview && (
          <div className="max-h-64 overflow-auto rounded-control border border-hairline">
            <div className="flex items-center justify-between border-b border-hairline bg-surface-2/50 px-3 py-1.5 text-12">
              <span>{preview.neighbors.length} neighbour(s) · {preview.node_count} nodes / {preview.edge_count} edges</span>
              <span className="text-content-dim">{preview.latency_ms} ms{preview.cached ? " · cached" : ""}</span>
            </div>
            <ul className="divide-y divide-hairline/60">
              {preview.neighbors.map((n: SearchAroundNeighbor) => (
                <li key={n.entity_id} className="flex items-center gap-2 px-3 py-1.5 text-12">
                  <span className="truncate font-medium text-content">{n.label || `Entity ${n.entity_id}`}</span>
                  <span className="text-content-dim">{n.entity_type}</span>
                  {n.relationship_type && <Badge variant="neutral">{n.relationship_type}</Badge>}
                  <span className="ml-auto flex items-center gap-1.5">
                    {n.verified ? <Badge variant="primary">verified</Badge> : <Badge variant="medium">candidate</Badge>}
                    {n.already_on_board && <Badge variant="neutral">on board</Badge>}
                  </span>
                </li>
              ))}
              {preview.neighbors.length === 0 && (
                <li className="px-3 py-3 text-center text-12 text-content-dim">No neighbours within the cap.</li>
              )}
            </ul>
          </div>
        )}

        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button disabled={!preview || preview.neighbors.length === 0 || importing} onClick={runImport}>
            {importing ? <Loader2 className="animate-spin" /> : null} Add to board as evidence
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
