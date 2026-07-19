import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { FilePlus2, FolderOpen, Loader2, Lock, Plus, Share2, Workflow } from "lucide-react";
import type { BoardSummary, CreateBoardBody } from "@/api/endpoints/board";
import { useBoards, useCreateBoard } from "@/routes/board/useBoard";
import { PageHeader } from "@/components/common/PageHeader";
import { EmptyState } from "@/components/common/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { timeAgo } from "@/lib/utils";

type Template = "blank" | "case" | "network";

export function MyBoards() {
  const navigate = useNavigate();
  const { data, isLoading } = useBoards();
  const [open, setOpen] = useState<Template | null>(null);

  return (
    <div>
      <PageHeader
        title="Investigation Board"
        description="Assemble live case objects on a shared canvas. Evidence is imported and read-only; hypotheses are yours, attributed and dashed."
        actions={<Button onClick={() => setOpen("blank")}><Plus /> New board</Button>}
      />

      <div className="mb-5 grid gap-3 sm:grid-cols-3">
        <Template icon={FilePlus2} title="Blank board" desc="Start empty and pin objects as you go." onClick={() => setOpen("blank")} />
        <Template icon={FolderOpen} title="From a case" desc="Scope a board to a case / FIR." onClick={() => setOpen("case")} />
        <Template icon={Share2} title="From a network selection" desc="Seed with a verified subgraph around an entity." onClick={() => setOpen("network")} />
      </div>

      <h2 className="mb-2 text-13 font-semibold text-content-dim">My boards & shared with me</h2>
      {isLoading ? (
        <div className="grid h-40 place-items-center text-content-dim"><Loader2 className="size-5 animate-spin" /></div>
      ) : !data || data.items.length === 0 ? (
        <EmptyState icon={Workflow} title="No boards yet"
          description="Create a board, or use Send to Board from a case, entity, network node, map feature or prediction." />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {data.items.map((bd) => <BoardCard key={bd.board_id} board={bd} onOpen={() => navigate(`/board/${bd.board_id}`)} />)}
        </div>
      )}

      <NewBoardDialog template={open} onClose={() => setOpen(null)} />
    </div>
  );
}

function Template({ icon: Icon, title, desc, onClick }: { icon: typeof Plus; title: string; desc: string; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick}
      className="flex items-start gap-3 rounded-card border border-hairline bg-surface p-3 text-left transition-colors hover:border-primary/50 hover:bg-surface-2/50">
      <span className="grid size-9 shrink-0 place-items-center rounded-control bg-primary/10 text-primary"><Icon className="size-4" /></span>
      <span className="min-w-0">
        <span className="block text-13 font-medium text-content">{title}</span>
        <span className="block text-12 text-content-dim">{desc}</span>
      </span>
    </button>
  );
}

function BoardCard({ board, onOpen }: { board: BoardSummary; onOpen: () => void }) {
  return (
    <button type="button" onClick={onOpen}
      className="flex flex-col gap-2 rounded-card border border-hairline bg-surface p-3 text-left transition-colors hover:border-primary/50">
      <div className="flex items-center gap-2">
        <span className="truncate text-14 font-semibold text-content">{board.title}</span>
        {board.is_locked && <Lock className="size-3.5 text-severity-high" />}
      </div>
      {board.description && <p className="line-clamp-2 text-12 text-content-dim">{board.description}</p>}
      <div className="mt-auto flex flex-wrap items-center gap-1.5 text-11">
        <Badge variant="neutral">{board.node_count} nodes</Badge>
        <Badge variant="neutral">{board.edge_count} links</Badge>
        <Badge variant={board.visibility === "private" ? "neutral" : "primary"}>{board.visibility}</Badge>
        {board.my_role && <Badge variant="outline">{board.my_role}</Badge>}
        {board.updated_at && <span className="ml-auto text-content-dim">{timeAgo(board.updated_at)}</span>}
      </div>
    </button>
  );
}

function NewBoardDialog({ template, onClose }: { template: Template | null; onClose: () => void }) {
  const navigate = useNavigate();
  const create = useCreateBoard();
  const [title, setTitle] = useState("");
  const [visibility, setVisibility] = useState("private");
  const [caseId, setCaseId] = useState("");
  const [entityId, setEntityId] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    setErr(null);
    const body: CreateBoardBody = { title: title.trim() || "Untitled board", visibility: visibility as CreateBoardBody["visibility"] };
    if (template === "case" && caseId.trim()) body.case_master_id = Number(caseId);
    if (template === "network" && entityId.trim()) { body.seed_entity_id = Number(entityId); body.seed_hops = 1; }
    try {
      const b = await create.mutateAsync(body);
      onClose();
      navigate(`/board/${b.board.board_id}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Create failed");
    }
  };

  return (
    <Dialog open={template != null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>New investigation board</DialogTitle>
          <DialogDescription>
            {template === "case" && "Scope this board to a case / FIR."}
            {template === "network" && "Seed with a capped, verified subgraph around an entity."}
            {template === "blank" && "A blank analytical canvas."}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-12 text-content-dim">Title</label>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Operation Nightfall" />
          </div>
          {template === "case" && (
            <div>
              <label className="mb-1 block text-12 text-content-dim">Case (CaseMasterID)</label>
              <Input value={caseId} onChange={(e) => setCaseId(e.target.value)} placeholder="e.g. 1024" />
            </div>
          )}
          {template === "network" && (
            <div>
              <label className="mb-1 block text-12 text-content-dim">Seed entity (EntityID)</label>
              <Input value={entityId} onChange={(e) => setEntityId(e.target.value)} placeholder="e.g. 5012" />
            </div>
          )}
          <div>
            <label className="mb-1 block text-12 text-content-dim">Visibility</label>
            <NativeSelect value={visibility} onChange={setVisibility}
              options={[{ value: "private", label: "Private" }, { value: "shared", label: "Shared" }, { value: "unit", label: "Unit" }]}
              placeholder="Visibility" />
          </div>
          {err && <p className="text-12 text-severity-critical">{err}</p>}
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button disabled={create.isPending} onClick={submit}>
            {create.isPending ? <Loader2 className="animate-spin" /> : null} Create board
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
