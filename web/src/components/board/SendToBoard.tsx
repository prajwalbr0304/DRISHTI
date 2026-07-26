import { useEffect, useState } from "react";
import { Check, Loader2, Plus, Workflow } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "@/api";
import type { BoardSummary } from "@/api/endpoints/board";
import { roleCan } from "@/config/roles";
import { useRole } from "@/providers/RoleProvider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

/* ============================================================================
   Send to Board — the connective-tissue affordance. It opens a board picker
   and creates an OBJECT REFERENCE on the chosen board through the API. The
   whole record is never serialised into the URL or frontend state — only its
   {ref_table, ref_id} reference travels.
   ========================================================================== */

export interface SendTarget {
  refTable: string;
  refId: string | number;
  nodeKind?: string;
  label?: string;
  /** For a governed OSINT/news object — carried through as an unverified label. */
  unverified?: boolean;
}

export function SendToBoard({
  target,
  variant = "outline",
  size = "sm",
  className,
  label = "Send to Board",
}: {
  target: SendTarget;
  variant?: "outline" | "ghost" | "secondary" | "primary";
  size?: "sm" | "md" | "icon-sm";
  className?: string;
  label?: string;
}) {
  const { role } = useRole();
  const [open, setOpen] = useState(false);

  if (!roleCan(role, "board_use")) return null; // no board capability for this role

  return (
    <>
      <Button variant={variant} size={size} className={className} onClick={() => setOpen(true)}
              title="Pin this object to an investigation board">
        <Workflow /> {size !== "icon-sm" && label}
      </Button>
      {open && <BoardPickerDialog target={target} onClose={() => setOpen(false)} />}
    </>
  );
}

function BoardPickerDialog({ target, onClose }: { target: SendTarget; onClose: () => void }) {
  const navigate = useNavigate();
  const [boards, setBoards] = useState<BoardSummary[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<{ boardId: number; detail?: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState("");

  useEffect(() => {
    let alive = true;
    setBusy(true);
    api.board.list()
      .then((r) => {
        if (alive) setBoards(r.items.filter((b) => !b.is_locked && b.my_role !== "viewer"));
      })
      .catch((e) => {
        if (alive) setErr(e instanceof Error ? e.message : "Could not load boards");
      })
      .finally(() => {
        if (alive) setBusy(false);
      });
    return () => { alive = false; };
  }, []);

  // Seed a subgraph, not a lone node: a case brings its governed operational
  // records and an entity brings its verified neighbourhood. Falls back to a
  // single pin server-side.
  const seedBody = () => ({
    ref_table: target.refTable,
    ref_id: String(target.refId),
    node_kind: target.nodeKind,
    label: target.label,
    expand: true,
  });

  const pin = async (boardId: number) => {
    setBusy(true);
    setErr(null);
    try {
      const r = await api.board.seed(boardId, seedBody());
      setDone({ boardId, detail: r.detail });
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Pin failed");
    } finally {
      setBusy(false);
    }
  };

  const createAndPin = async () => {
    setBusy(true);
    setErr(null);
    try {
      const b = await api.board.create({ title: newTitle.trim() || `Board · ${target.label ?? target.refTable}` });
      const r = await api.board.seed(b.board.board_id, seedBody());
      setDone({ boardId: b.board.board_id, detail: r.detail });
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Create failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="w-[calc(100vw-2rem)] max-w-lg overflow-hidden">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Workflow className="size-4" /> Send to board</DialogTitle>
          <DialogDescription>
            Add <b>{target.label ?? `${target.refTable}:${target.refId}`}</b> and its governed
            network. A case brings people, legal sections, evidence, statements, property,
            digital/financial links and lifecycle records; an entity brings its verified links.
            {target.unverified && " This is unverified open-source material and stays labelled as such."}
          </DialogDescription>
        </DialogHeader>

        {done ? (
          <div className="space-y-3">
            <div className="flex items-center gap-2 rounded-control border border-primary/30 bg-primary/10 px-3 py-2 text-13">
              <Check className="size-4 text-primary" /> {done.detail || "Added to the board."}
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={onClose}>Close</Button>
              <Button onClick={() => navigate(`/board/${done.boardId}`)}>Open board</Button>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            {err && <p className="text-12 text-severity-critical">{err}</p>}
            <div className="max-h-56 min-w-0 space-y-1 overflow-y-auto overflow-x-hidden">
              {busy && !boards && <div className="grid h-20 place-items-center"><Loader2 className="size-5 animate-spin text-content-dim" /></div>}
              {boards?.map((b) => (
                <button key={b.board_id} type="button" disabled={busy} onClick={() => pin(b.board_id)}
                  className={cn("flex w-full min-w-0 items-center gap-2 rounded-control border border-hairline px-3 py-2 text-left text-13",
                    "transition-colors hover:border-primary/50 hover:bg-surface-2/50 disabled:opacity-50")}>
                  <span className="min-w-0 flex-1 truncate font-medium text-content" title={b.title}>{b.title}</span>
                  <span className="shrink-0 text-11 text-content-dim">{b.node_count} nodes</span>
                </button>
              ))}
              {boards && boards.length === 0 && <p className="px-1 py-2 text-12 text-content-dim">No editable boards yet — create one below.</p>}
            </div>
            <div className="grid min-w-0 grid-cols-1 gap-2 border-t border-hairline pt-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
              <div className="min-w-0">
                <label className="mb-1 block text-12 text-content-dim">New board</label>
                <Input value={newTitle} onChange={(e) => setNewTitle(e.target.value)} placeholder={`Board · ${target.label ?? target.refTable}`} className="h-8 text-13" />
              </div>
              <Button className="w-full sm:w-auto" size="sm" disabled={busy} onClick={createAndPin}><Plus /> Create & pin</Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

/** Map a peek ObjectRef kind to a board reference target (best-effort). */
export function peekKindToTarget(kind: string, id: string | number, label?: string): SendTarget | null {
  switch (kind) {
    case "case":
      return { refTable: "CaseMaster", refId: id, nodeKind: "case", label };
    case "person":
      return { refTable: "EntityGraph", refId: id, nodeKind: "entity", label };
    case "vehicle":
      return { refTable: "EntityGraph", refId: id, nodeKind: "vehicle", label };
    case "phone":
      return { refTable: "EntityGraph", refId: id, nodeKind: "phone", label };
    case "account":
      return { refTable: "EntityGraph", refId: id, nodeKind: "account", label };
    case "location":
      return { refTable: "EntityGraph", refId: id, nodeKind: "location", label };
    case "organisation":
      return { refTable: "EntityGraph", refId: id, nodeKind: "entity", label };
    default:
      return null; // association/model/alert are not single pinnable objects
  }
}
