import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ArrowDown, Play, Route as RouteIcon } from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import type { EntityListItem, PathResponse } from "@/api/types";
import { usePeekStore } from "@/stores/usePeekStore";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/common/EmptyState";
import { EntitySearch } from "@/components/network/EntitySearch";
import { GraphCanvas } from "@/components/network/GraphCanvas";
import { ModeLayout } from "@/components/network/ModeLayout";

type Picked = { id: number; label: string } | null;

/* Path Finder: shortest path between two entities, revealed with a short
   step-by-step animation. */
export function PathMode() {
  const push = usePeekStore((s) => s.push);
  const [a, setA] = useState<Picked>(null);
  const [b, setB] = useState<Picked>(null);
  const [revealed, setRevealed] = useState(0);
  const timer = useRef<number | null>(null);

  const mut = useMutation({
    mutationFn: ({ s, t }: { s: number; t: number }) => api.graph.path(s, t),
    onSuccess: () => setRevealed(0),
  });
  const path: PathResponse | undefined = mut.data;

  const nodes = useMemo(
    () => (path?.nodes ?? []).map((n) => ({ id: n.entity_id, label: n.label, entity_type: n.entity_type, pagerank: n.pagerank })),
    [path],
  );
  const edges = useMemo(
    () => (path?.edges ?? []).map((e) => ({ id: e.edge_id, source: e.source, target: e.target, relationship_type: e.relationship_type, weight: e.weight })),
    [path],
  );

  // Step-by-step reveal of the path edges.
  useEffect(() => {
    if (timer.current) window.clearInterval(timer.current);
    if (!path?.found || edges.length === 0) return;
    timer.current = window.setInterval(() => {
      setRevealed((r) => {
        if (r >= edges.length) {
          if (timer.current) window.clearInterval(timer.current);
          return r;
        }
        return r + 1;
      });
    }, 550);
    return () => {
      if (timer.current) window.clearInterval(timer.current);
    };
  }, [path, edges.length]);

  const revealedEdgeIds = edges.slice(0, revealed).map((e) => e.id!);

  const pick = (setter: (p: Picked) => void) => (e: EntityListItem) => setter({ id: e.entity_id, label: e.label });

  return (
    <ModeLayout
      panelTitle="Path Finder"
      panel={
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-12 text-content-dim">From (A)</label>
            <EntitySearch selected={a} onPick={pick(setA)} onClear={() => setA(null)} placeholder="Entity A…" />
          </div>
          <div className="flex justify-center text-content-dim"><ArrowDown className="size-4" /></div>
          <div>
            <label className="mb-1 block text-12 text-content-dim">To (B)</label>
            <EntitySearch selected={b} onPick={pick(setB)} onClear={() => setB(null)} placeholder="Entity B…" />
          </div>
          <Button
            className="w-full justify-center"
            disabled={!a || !b || mut.isPending}
            onClick={() => a && b && mut.mutate({ s: a.id, t: b.id })}
          >
            <RouteIcon /> {mut.isPending ? "Finding…" : "Find path"}
          </Button>

          {path && !path.found && (
            <div className="rounded-control border border-hairline bg-surface-2/60 px-2.5 py-2 text-12 text-content-dim">
              No path found within the hop limit.
            </div>
          )}
          {path?.found && (
            <div className="space-y-2 rounded-control border border-hairline bg-surface-2/60 px-2.5 py-2">
              <div className="flex items-center gap-2 text-13 text-content">
                <Badge variant="primary" className="tnum">{path.hops} hops</Badge>
                <span className="text-12 text-content-dim">{path.method}</span>
              </div>
              <Button variant="outline" size="sm" className="w-full justify-center" onClick={() => setRevealed(0)}>
                <Play /> Replay
              </Button>
            </div>
          )}
          {mut.error && <p className="text-12 text-content-dim">{errorMessage(mut.error)}</p>}
        </div>
      }
    >
      {!path ? (
        <div className="grid h-full place-items-center p-6">
          <EmptyState icon={RouteIcon} title="Connect two entities" description="Pick entity A and entity B to reveal the shortest chain of relationships between them." />
        </div>
      ) : path.found ? (
        <GraphCanvas
          nodes={nodes}
          edges={edges}
          colorMode="type"
          highlightNodeIds={nodes.map((n) => n.id)}
          highlightEdgeIds={revealedEdgeIds}
          onNodeClick={(id) => {
            const n = path.nodes.find((x) => String(x.entity_id) === id);
            push({ kind: "person", id: Number(id), label: n?.label ?? `Entity ${id}`, sublabel: n?.entity_type ?? undefined });
          }}
        />
      ) : (
        <div className="grid h-full place-items-center p-6">
          <EmptyState icon={RouteIcon} title="No path" description="These two entities are not connected within the search depth." />
        </div>
      )}
    </ModeLayout>
  );
}
