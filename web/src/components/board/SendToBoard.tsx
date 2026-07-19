import { useState } from "react";
import { Check, Loader2, Plus, Workflow } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "@/api";
import type { BoardSummary } from "@/api/endpoints/board";
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

  if (role === "policymaker") return null; // no board access for this role

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
  const [done, setDone] = useState<{ boardId: number } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState("");

  // lazy-load boards on first open
  if (boards === null && !busy) {
    setBusy(true);
    api.board.list()
      .then((r) => setBoards(r.items.filter((b) => !b.is_locked && b.my_role !== "viewer")))
      .catch((e) => setErr(e instanceof Error ? e.message : "Could not load boards"))
      .finally(() => setBusy(false));
  }

  const pin = async (boardId: number) => {
    setBusy(true);
    setErr(null);
    try {
      await api.board.addNode(boardId, {
        node_kind: target.nodeKind ?? "entity",
        ref_table: target.refTable,
        ref_id: String(target.refId),
        label: target.label,
      });
      setDone({ boardId });
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
      await api.board.addNode(b.board.board_id, {
        node_kind: target.nodeKind ?? "entity",
        ref_table: target.refTable, ref_id: String(target.refId), label: target.label,
      });
      setDone({ boardId: b.board.board_id });
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Create failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Workflow className="size-4" /> Send to board</DialogTitle>
          <DialogDescription>
            Pin <b>{target.label ?? `${target.refTable}:${target.refId}`}</b> as a live reference.
            {target.unverified && " This is unverified open-source material and stays labelled as such."}
          </DialogDescription>
        </DialogHeader>

        {done ? (
          <div className="space-y-3">
            <div className="flex items-center gap-2 rounded-control border border-primary/30 bg-primary/10 px-3 py-2 text-13">
              <Check className="size-4 text-primary" /> Pinned to the board.
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={onClose}>Close</Button>
              <Button onClick={() => navigate(`/board/${done.boardId}`)}>Open board</Button>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            {err && <p className="text-12 text-severity-critical">{err}</p>}
            <div className="max-h-56 space-y-1 overflow-auto">
              {busy && !boards && <div className="grid h-20 place-items-center"><Loader2 className="size-5 animate-spin text-content-dim" /></div>}
              {boards?.map((b) => (
                <button key={b.board_id} type="button" disabled={busy} onClick={() => pin(b.board_id)}
                  className={cn("flex w-full items-center gap-2 rounded-control border border-hairline px-3 py-2 text-left text-13",
                    "transition-colors hover:border-primary/50 hover:bg-surface-2/50 disabled:opacity-50")}>
                  <span className="truncate font-medium text-content">{b.title}</span>
                  <span className="ml-auto text-11 text-content-dim">{b.node_count} nodes</span>
                </button>
              ))}
              {boards && boards.length === 0 && <p className="px-1 py-2 text-12 text-content-dim">No editable boards yet — create one below.</p>}
            </div>
            <div className="flex items-end gap-2 border-t border-hairline pt-3">
              <div className="flex-1">
                <label className="mb-1 block text-12 text-content-dim">New board</label>
                <Input value={newTitle} onChange={(e) => setNewTitle(e.target.value)} placeholder={`Board · ${target.label ?? target.refTable}`} className="h-8 text-13" />
              </div>
              <Button size="sm" disabled={busy} onClick={createAndPin}><Plus /> Create & pin</Button>
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
