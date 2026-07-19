import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export interface RationalePayload {
  rationale: string;
  relationship_type?: string;
  confidence?: number;
  directed: boolean;
}

export function RationaleDialog({
  open,
  sourceLabel,
  targetLabel,
  onCancel,
  onCreate,
}: {
  open: boolean;
  sourceLabel?: string;
  targetLabel?: string;
  onCancel: () => void;
  onCreate: (p: RationalePayload) => void;
}) {
  const [rationale, setRationale] = useState("");
  const [rel, setRel] = useState("");
  const [confidence, setConfidence] = useState(60);
  const [directed, setDirected] = useState(false);

  useEffect(() => {
    if (open) {
      setRationale("");
      setRel("");
      setConfidence(60);
      setDirected(false);
    }
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onCancel()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Draw a hypothesis link</DialogTitle>
          <DialogDescription>
            Connecting <b>{sourceLabel}</b> → <b>{targetLabel}</b>. A hypothesis is your reasoning,
            not a fact — a rationale is required and it renders as a dashed link.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-12 font-medium text-content-dim">Rationale (required)</label>
            <textarea
              autoFocus
              value={rationale}
              onChange={(e) => setRationale(e.target.value)}
              rows={3}
              placeholder="e.g. Both used the same device IMEI in March; likely the same operator."
              className="w-full rounded-control border border-hairline bg-surface-2 p-2 text-13 text-content focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="mb-1 block text-12 font-medium text-content-dim">Relationship (optional)</label>
              <Input value={rel} onChange={(e) => setRel(e.target.value)} placeholder="directs / shares / funds…" className="h-8 text-13" />
            </div>
            <div>
              <label className="mb-1 block text-12 font-medium text-content-dim">Confidence: {confidence}%</label>
              <input type="range" min={0} max={100} value={confidence}
                     onChange={(e) => setConfidence(Number(e.target.value))} className="w-full" />
            </div>
          </div>
          <label className="flex items-center gap-2 text-12 text-content-dim">
            <input type="checkbox" checked={directed} onChange={(e) => setDirected(e.target.checked)} />
            Directed link (source → target)
          </label>
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onCancel}>Cancel</Button>
          <Button
            disabled={!rationale.trim()}
            onClick={() =>
              onCreate({
                rationale: rationale.trim(),
                relationship_type: rel.trim() || undefined,
                confidence: confidence / 100,
                directed,
              })
            }
          >
            Create hypothesis link
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
