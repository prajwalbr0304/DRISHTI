import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ShieldAlert, Sparkles, Users } from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import { cn, formatNumber } from "@/lib/utils";
import { useUIStore } from "@/stores/useUIStore";
import { usePeekStore } from "@/stores/usePeekStore";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/EmptyState";
import { GraphCanvas } from "@/components/network/GraphCanvas";
import { ModeLayout } from "@/components/network/ModeLayout";
import { communityColor } from "@/components/network/graphEncoding";

/* Communities: Louvain clusters coloured as groups, cross-referenced with
   known gangs (GangMembership) in a ranked side list. */
export function CommunitiesMode() {
  const push = usePeekStore((s) => s.push);
  const askAbout = useUIStore((s) => s.askAbout);
  const [selected, setSelected] = useState<number | null>(null);

  const listQ = useQuery({
    queryKey: ["communities", "list"],
    queryFn: ({ signal }) => api.graph.communitiesList(40, signal),
  });
  const sgQ = useQuery({
    queryKey: ["communities", "subgraph", selected],
    queryFn: ({ signal }) => api.graph.communitySubgraph(selected!, 80, signal),
    enabled: selected != null,
  });

  const nodes = useMemo(
    () =>
      (sgQ.data?.nodes ?? []).map((n) => ({
        id: n.entity_id,
        label: n.label,
        entity_type: n.entity_type,
        pagerank: n.pagerank,
        community: n.community,
      })),
    [sgQ.data],
  );
  const edges = useMemo(
    () =>
      (sgQ.data?.edges ?? []).map((e) => ({
        id: e.edge_id,
        source: e.source,
        target: e.target,
        relationship_type: e.relationship_type,
        weight: e.weight,
      })),
    [sgQ.data],
  );

  return (
    <ModeLayout
      panelTitle="Communities"
      panel={
        <div className="space-y-1.5">
          {listQ.isLoading &&
            Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}
          {listQ.error && <p className="text-12 text-content-dim">{errorMessage(listQ.error)}</p>}
          {listQ.data?.communities.map((c) => {
            const active = selected === c.community;
            return (
              <button
                key={c.community}
                type="button"
                onClick={() => setSelected(c.community)}
                className={cn(
                  "flex w-full items-center gap-2.5 rounded-control border px-2.5 py-2 text-left transition-colors",
                  active ? "border-primary/60 bg-surface-2" : "border-hairline hover:bg-surface-2",
                )}
              >
                <span className="size-3 shrink-0 rounded-full" style={{ background: communityColor(c.community) }} />
                <span className="min-w-0 flex-1">
                  <span className="block text-13 font-medium text-content">Community {c.community}</span>
                  <span className="tnum block text-12 text-content-dim">{formatNumber(c.size)} members</span>
                </span>
                {c.gang_members > 0 && (
                  <Badge variant="high" className="shrink-0 gap-1">
                    <ShieldAlert className="size-3" /> {c.gang_members}
                  </Badge>
                )}
              </button>
            );
          })}
        </div>
      }
    >
      {selected == null ? (
        <div className="grid h-full place-items-center p-6">
          <EmptyState icon={Users} title="Pick a community" description="Select a community from the list to render its members and internal links. Badges flag how many members are known gang affiliates." />
        </div>
      ) : (
        <>
          <div className="flex items-center justify-between border-b border-hairline bg-surface px-3 py-2">
            <span className="text-13 font-medium text-content">
              Community {selected}
              {sgQ.data && <span className="tnum ml-2 text-12 text-content-dim">{sgQ.data.node_count} shown · {sgQ.data.edge_count} links</span>}
            </span>
            <Button variant="ghost" size="sm" onClick={() => askAbout(`Explain community ${selected} in the entity network`)}>
              <Sparkles /> Explain
            </Button>
          </div>
          <div className="relative min-h-0 flex-1">
            {sgQ.isLoading ? (
              <div className="grid h-full place-items-center"><Skeleton className="h-40 w-40 rounded-full" /></div>
            ) : (
              <GraphCanvas
                nodes={nodes}
                edges={edges}
                colorMode="community"
                onNodeClick={(id) => {
                  const n = sgQ.data?.nodes.find((x) => String(x.entity_id) === id);
                  push({ kind: "person", id: Number(id), label: n?.label ?? `Entity ${id}`, sublabel: n?.entity_type ?? undefined });
                }}
              />
            )}
          </div>
        </>
      )}
    </ModeLayout>
  );
}
