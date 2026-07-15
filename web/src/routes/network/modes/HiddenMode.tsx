import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { EyeOff, Link2, RefreshCw } from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import { cn } from "@/lib/utils";
import { usePeekStore } from "@/stores/usePeekStore";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/EmptyState";
import { GraphCanvas } from "@/components/network/GraphCanvas";
import { ModeLayout } from "@/components/network/ModeLayout";
import { EvidenceTrail } from "@/components/widget/EvidenceTrail";

/* Hidden Associations: ranked association cards; clicking one draws the proof
   path on the canvas and exposes its Evidence Trail. */
export function HiddenMode({ initialAssociation }: { initialAssociation?: number | null }) {
  const push = usePeekStore((s) => s.push);
  const [selected, setSelected] = useState<number | null>(initialAssociation ?? null);
  const [refresh, setRefresh] = useState(false);

  useEffect(() => {
    if (initialAssociation) setSelected(initialAssociation);
  }, [initialAssociation]);

  const feedQ = useQuery({
    queryKey: ["hidden", "feed", refresh],
    queryFn: ({ signal }) => api.graph.hiddenAssociations({ page: 1, page_size: 40, refresh }, signal),
  });
  const proofQ = useQuery({
    queryKey: ["hidden", "proof", selected],
    queryFn: ({ signal }) => api.graph.proofPath(selected!, signal),
    enabled: selected != null,
  });

  const nodes = useMemo(
    () => (proofQ.data?.nodes ?? []).map((n) => ({ id: n.entity_id, label: n.label, entity_type: n.entity_type, pagerank: n.pagerank, community: n.community })),
    [proofQ.data],
  );
  const edges = useMemo(
    () => (proofQ.data?.edges ?? []).map((e) => ({ id: e.edge_id, source: e.source, target: e.target, relationship_type: e.relationship_type, weight: e.weight })),
    [proofQ.data],
  );
  const items = feedQ.data?.items ?? [];

  return (
    <ModeLayout
      panelTitle={
        <div className="flex items-center justify-between">
          <span>Hidden associations {feedQ.data ? `(${feedQ.data.total})` : ""}</span>
          <Button variant="ghost" size="icon-sm" onClick={() => setRefresh(true)} aria-label="Recompute" title="Recompute">
            <RefreshCw className={cn(feedQ.isFetching && "animate-spin")} />
          </Button>
        </div>
      }
      panel={
        <div className="space-y-2">
          {feedQ.isLoading && Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-20 w-full" />)}
          {feedQ.error && <p className="text-12 text-content-dim">{errorMessage(feedQ.error)}</p>}
          {feedQ.data && items.length === 0 && (
            <EmptyState icon={EyeOff} title="Nothing materialised" description="Recompute to build the hidden-association feed." />
          )}
          {items.map((a) => {
            const active = selected === a.association_id;
            return (
              <button
                key={a.association_id}
                type="button"
                onClick={() => setSelected(a.association_id)}
                className={cn(
                  "w-full rounded-card border px-3 py-2.5 text-left transition-colors",
                  active ? "border-primary/60 bg-surface-2" : "border-hairline hover:bg-surface-2",
                )}
              >
                <div className="flex items-center gap-1.5 text-13 text-content">
                  <span className="truncate font-medium">{a.label_a ?? `#${a.entity_a}`}</span>
                  <Link2 className="size-3.5 shrink-0 text-primary" />
                  <span className="truncate font-medium">{a.label_b ?? `#${a.entity_b}`}</span>
                </div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {a.link_kinds.map((k) => (
                    <Badge key={k} variant="primary" className="capitalize">{k.replace(/_/g, " ")}</Badge>
                  ))}
                </div>
                <div className="mt-1 text-12 text-content-dim tnum">
                  {a.independent_links} independent links · 0 shared FIRs · score {a.score.toFixed(2)}
                </div>
              </button>
            );
          })}
        </div>
      }
    >
      {selected == null ? (
        <div className="grid h-full place-items-center p-6">
          <EmptyState icon={Link2} title="Select an association" description="Pick a card to draw the proof path — the shared intermediaries that connect two entities who never appear in the same FIR." />
        </div>
      ) : (
        <div className="flex h-full min-h-0 flex-col">
          <div className="relative min-h-0 flex-1">
            {proofQ.isLoading ? (
              <div className="grid h-full place-items-center"><Skeleton className="h-40 w-64" /></div>
            ) : (
              <GraphCanvas
                nodes={nodes}
                edges={edges}
                colorMode="type"
                highlightNodeIds={nodes.map((n) => n.id)}
                onNodeClick={(id) => {
                  const n = proofQ.data?.nodes.find((x) => String(x.entity_id) === id);
                  push({ kind: "person", id: Number(id), label: n?.label ?? `Entity ${id}`, sublabel: n?.entity_type ?? undefined });
                }}
              />
            )}
          </div>
          {proofQ.data && (
            <div className="max-h-56 shrink-0 overflow-auto border-t border-hairline bg-surface p-3">
              <div className="mb-2 text-12 font-semibold uppercase tracking-wide text-content-dim">Evidence trail</div>
              <EvidenceTrail result={proofQ.data.result} />
            </div>
          )}
        </div>
      )}
    </ModeLayout>
  );
}
