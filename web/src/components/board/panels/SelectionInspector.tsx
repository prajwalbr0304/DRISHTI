import { useEffect, useState } from "react";
import { ExternalLink, GitCompareArrows, RefreshCw, ShieldCheck, Trash2 } from "lucide-react";
import type { BoardDetail, NodeDiff } from "@/api/endpoints/board";
import type { BoardSelection } from "@/components/board/BoardCanvas";
import { kindStyle } from "@/components/board/boardEncoding";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/common/EmptyState";
import { MousePointer2 } from "lucide-react";

interface Props {
  detail: BoardDetail;
  selection: BoardSelection;
  diffs: Record<number, NodeDiff>;
  readOnly: boolean;
  canPromote: boolean;
  onOpenSource: (path: string) => void;
  onDelete: (sel: BoardSelection) => void;
  onRefreshSnapshot: (nodeId: number) => void;
  onSaveRationale: (edgeId: number, rationale: string) => void;
  onPromote: (edgeId: number) => void;
}

export function SelectionInspector(props: Props) {
  const { detail, selection, diffs, readOnly, canPromote } = props;

  if (selection.kind === null || selection.id == null) {
    return (
      <div className="p-4">
        <EmptyState
          icon={MousePointer2}
          title="Nothing selected"
          description="Select an object or link on the canvas to see its properties, source and linked records here."
          className="min-h-[220px]"
        />
      </div>
    );
  }

  if (selection.kind === "node") {
    const n = detail.nodes.find((x) => x.board_node_id === selection.id);
    if (!n) return null;
    const ks = kindStyle(n.node_kind);
    const diff = diffs[n.board_node_id];
    const snap = n.snapshot || {};
    return (
      <div className="space-y-3 p-3 text-13">
        <Header color={ks.color} kind={ks.label} title={n.label || `Node ${n.board_node_id}`} />
        {diff && diff.status !== "live" && (
          <div className="flex items-start gap-2 rounded-control border border-severity-medium/40 bg-severity-medium/10 px-2.5 py-2 text-12">
            <GitCompareArrows className="mt-0.5 size-4 shrink-0 text-severity-medium" />
            <span>
              {diff.status === "changed" && `Source changed since pinned (${diff.changed_fields.join(", ") || "fields differ"}).`}
              {diff.status === "broken" && "The source object is no longer available (broken reference)."}
              {diff.status === "unavailable" && "Live source is currently unavailable."}
            </span>
          </div>
        )}
        <Field label="Reference">
          {n.ref_table ? `${n.ref_table}:${n.ref_id}` : "content node (no source)"}
        </Field>
        {n.source_version && <Field label="Source version">{n.source_version}</Field>}
        {n.source_hash && <Field label="Source hash" mono>{n.source_hash.slice(0, 16)}…</Field>}
        {Object.keys(snap).length > 0 && (
          <div>
            <div className="mb-1 text-11 font-medium uppercase tracking-wide text-content-dim">Pinned snapshot</div>
            <dl className="space-y-1 rounded-control border border-hairline bg-surface-2/40 p-2">
              {Object.entries(snap).slice(0, 12).map(([k, v]) => (
                <div key={k} className="flex justify-between gap-2 text-12">
                  <dt className="truncate text-content-dim">{k}</dt>
                  <dd className="tnum max-w-[55%] truncate text-content">{String(v ?? "")}</dd>
                </div>
              ))}
            </dl>
          </div>
        )}
        <div className="flex flex-wrap gap-2 pt-1">
          {n.open_in_source && (
            <Button variant="outline" size="sm" onClick={() => props.onOpenSource(n.open_in_source!)}>
              <ExternalLink /> Open in source
            </Button>
          )}
          {!readOnly && n.ref_table && (
            <Button variant="ghost" size="sm" onClick={() => props.onRefreshSnapshot(n.board_node_id)}>
              <RefreshCw /> Refresh snapshot
            </Button>
          )}
          {!readOnly && (
            <Button variant="ghost" size="sm" className="text-severity-critical"
                    onClick={() => props.onDelete(selection)}>
              <Trash2 /> Remove
            </Button>
          )}
        </div>
      </div>
    );
  }

  if (selection.kind === "edge") {
    const e = detail.edges.find((x) => x.board_edge_id === selection.id);
    if (!e) return null;
    const isHyp = e.edge_class === "hypothesis";
    return (
      <EdgeInspector
        key={e.board_edge_id}
        edgeId={e.board_edge_id}
        isHyp={isHyp}
        readOnly={readOnly}
        canPromote={canPromote}
        relationship={e.relationship_type}
        confidence={e.confidence}
        rationale={e.rationale}
        sourceRecord={e.source_record_id}
        promoted={e.promoted_status}
        onSaveRationale={props.onSaveRationale}
        onPromote={props.onPromote}
        onDelete={() => props.onDelete(selection)}
      />
    );
  }

  // annotation
  const a = detail.annotations.find((x) => x.board_annotation_id === selection.id);
  if (!a) return null;
  return (
    <div className="space-y-3 p-3 text-13">
      <Header color="#64748b" kind={`${a.kind} annotation`} title={a.content || a.kind} />
      {!readOnly && (
        <Button variant="ghost" size="sm" className="text-severity-critical"
                onClick={() => props.onDelete(selection)}>
          <Trash2 /> Delete annotation
        </Button>
      )}
    </div>
  );
}

function EdgeInspector({
  edgeId, isHyp, readOnly, canPromote, relationship, confidence, rationale,
  sourceRecord, promoted, onSaveRationale, onPromote, onDelete,
}: {
  edgeId: number; isHyp: boolean; readOnly: boolean; canPromote: boolean;
  relationship?: string | null; confidence?: number | null; rationale?: string | null;
  sourceRecord?: string | null; promoted?: string | null;
  onSaveRationale: (id: number, r: string) => void; onPromote: (id: number) => void;
  onDelete: () => void;
}) {
  const [draft, setDraft] = useState(rationale ?? "");
  useEffect(() => setDraft(rationale ?? ""), [rationale]);

  return (
    <div className="space-y-3 p-3 text-13">
      <div className="flex items-center gap-2">
        <Badge variant={isHyp ? "medium" : "primary"}>
          {isHyp ? "Hypothesis (dashed)" : "Evidence (solid, read-only)"}
        </Badge>
        {promoted === "proposed" && <Badge variant="high">proposed for review</Badge>}
      </div>
      <Field label="Relationship">{relationship || "—"}</Field>
      <Field label="Confidence">{confidence != null ? `${Math.round(confidence * 100)}%` : "not stated"}</Field>
      {sourceRecord && <Field label="Source record" mono>{sourceRecord}</Field>}

      {isHyp ? (
        <div>
          <div className="mb-1 text-11 font-medium uppercase tracking-wide text-content-dim">Rationale (the officer's why)</div>
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            disabled={readOnly}
            rows={4}
            className="w-full rounded-control border border-hairline bg-surface-2 p-2 text-12 text-content focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60 disabled:opacity-60"
          />
          {!readOnly && (
            <div className="mt-2 flex flex-wrap gap-2">
              <Button variant="outline" size="sm" disabled={!draft.trim() || draft === rationale}
                      onClick={() => onSaveRationale(edgeId, draft.trim())}>
                Save rationale
              </Button>
              {canPromote && promoted !== "proposed" && (
                <Button variant="secondary" size="sm" disabled={!draft.trim()}
                        onClick={() => onPromote(edgeId)}>
                  <ShieldCheck /> Promote for review
                </Button>
              )}
              <Button variant="ghost" size="sm" className="text-severity-critical" onClick={onDelete}>
                <Trash2 /> Delete
              </Button>
            </div>
          )}
        </div>
      ) : (
        <p className="rounded-control bg-surface-2/50 p-2 text-12 text-content-dim">
          Evidence edges are imported from verified source data and are read-only on the board.
          {!readOnly && " You can remove it from the board without altering the source."}
        </p>
      )}
      {!readOnly && !isHyp && (
        <Button variant="ghost" size="sm" className="text-severity-critical" onClick={onDelete}>
          <Trash2 /> Remove from board
        </Button>
      )}
    </div>
  );
}

function Header({ color, kind, title }: { color: string; kind: string; title: string }) {
  return (
    <div className="border-b border-hairline pb-2">
      <div className="text-11 font-medium uppercase tracking-wide" style={{ color }}>{kind}</div>
      <div className="mt-0.5 text-15 font-semibold text-content">{title}</div>
    </div>
  );
}

function Field({ label, children, mono }: { label: string; children: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-3">
      <span className="text-content-dim">{label}</span>
      <span className={mono ? "font-mono text-12 text-content" : "text-content"}>{children}</span>
    </div>
  );
}
