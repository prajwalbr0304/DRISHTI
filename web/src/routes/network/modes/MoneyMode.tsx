import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ResponsiveContainer, Sankey, Tooltip } from "recharts";
import { AlertTriangle, Banknote, Lock, Search } from "lucide-react";
import { api } from "@/api";
import { ApiError, errorMessage } from "@/api/contracts";
import { cn, formatNumber } from "@/lib/utils";
import { useRole } from "@/providers/RoleProvider";
import { useChartTheme } from "@/lib/chart-theme";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/EmptyState";
import { ModeLayout } from "@/components/network/ModeLayout";

/* Money Trail: a Sankey of traced fund flows (forward DAG) + a structuring /
   laundering flags panel. Server-gated on the money_trail permission. */
export function MoneyMode({ initialAccount }: { initialAccount?: number | null }) {
  const { role } = useRole();
  const theme = useChartTheme();
  const [input, setInput] = useState(initialAccount ? String(initialAccount) : "");
  const [account, setAccount] = useState<number | null>(initialAccount ?? null);

  const flaggedQ = useQuery({
    queryKey: ["money", "flagged", "feed"],
    queryFn: ({ signal }) => api.money.flagged({ page: 1, page_size: 20 }, signal),
    retry: false,
  });
  const traceQ = useQuery({
    queryKey: ["money", "trace", account],
    queryFn: ({ signal }) => api.money.trace(account!, 4, signal),
    enabled: account != null,
    retry: false,
  });

  const permissionDenied =
    (flaggedQ.error instanceof ApiError && flaggedQ.error.status === 403) ||
    (traceQ.error instanceof ApiError && traceQ.error.status === 403);

  // Build a cycle-free Sankey (forward hops only) from the trace.
  const sankey = useMemo(() => {
    if (!traceQ.data) return null;
    const hop = new Map(traceQ.data.nodes.map((n) => [n.account_id, n.hop]));
    const index = new Map<number, number>();
    const nodes = traceQ.data.nodes.map((n, i) => {
      index.set(n.account_id, i);
      return { name: n.label ?? `Acct ${n.account_id}` };
    });
    const links = traceQ.data.edges
      .filter((e) => (hop.get(e.target_account) ?? 0) > (hop.get(e.source_account) ?? 0))
      .filter((e) => index.has(e.source_account) && index.has(e.target_account) && e.amount > 0)
      .map((e) => ({
        source: index.get(e.source_account)!,
        target: index.get(e.target_account)!,
        value: Math.max(1, Math.round(e.amount)),
      }));
    return links.length ? { nodes, links } : null;
  }, [traceQ.data]);

  const flags = (traceQ.data?.edges ?? []).filter((e) => e.is_flagged);

  if (permissionDenied) {
    return (
      <ModeLayout panelTitle="Money Trail" panel={<p className="text-12 text-content-dim">Restricted.</p>}>
        <div className="grid h-full place-items-center p-6">
          <EmptyState icon={Lock} title="Financial data restricted" description={`The '${role}' role does not have the money_trail permission. Ask an administrator for access.`} />
        </div>
      </ModeLayout>
    );
  }

  return (
    <ModeLayout
      panelTitle="Money Trail"
      panel={
        <div className="space-y-3">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const id = Number(input.trim());
              if (Number.isFinite(id) && id > 0) setAccount(id);
            }}
            className="flex items-center gap-2"
          >
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-content-dim" />
              <Input value={input} onChange={(e) => setInput(e.target.value)} inputMode="numeric" placeholder="account id…" className="h-8 pl-8" />
            </div>
            <Button type="submit" size="sm" disabled={!input.trim()}>Trace</Button>
          </form>

          <div className="flex items-center justify-between">
            <span className="text-12 font-semibold text-content-dim">Flagged accounts</span>
            {flaggedQ.data && flaggedQ.data.total > 0 && (
              <Badge variant="high" className="shrink-0">{formatNumber(flaggedQ.data.total)}</Badge>
            )}
          </div>
          {flaggedQ.isLoading && <Skeleton className="h-24 w-full" />}
          {flaggedQ.data && flaggedQ.data.total === 0 && (
            <p className="rounded-control border border-hairline bg-surface-2/50 px-2.5 py-2 text-12 text-content-dim">
              No flagged transactions yet. Run the money-laundering detection job to surface
              structuring, layering and circular-flow patterns here.
            </p>
          )}
          {flaggedQ.data && flaggedQ.data.total > 0 && (
            <div className="flex flex-wrap gap-1">
              {Object.entries(flaggedQ.data.by_reason).map(([reason, n]) => (
                <span key={reason} className="rounded-full bg-surface-2 px-2 py-0.5 text-11 capitalize text-content-dim">
                  {reason} · <span className="tnum">{formatNumber(n)}</span>
                </span>
              ))}
            </div>
          )}
          {flaggedQ.data?.items.slice(0, 15).map((f) => (
            <button
              key={f.transaction_id}
              type="button"
              onClick={() => {
                setInput(String(f.source_account));
                setAccount(f.source_account);
              }}
              className="flex w-full items-center gap-2 rounded-control border border-hairline px-2.5 py-1.5 text-left transition-colors hover:bg-surface-2"
            >
              <AlertTriangle className="size-3.5 shrink-0 text-severity-high" />
              <span className="min-w-0 flex-1">
                <span className="tnum block truncate text-13 text-content">#{f.source_account} → #{f.destination_account}</span>
                <span className="block truncate text-12 text-content-dim">{f.flag_reason ?? "flagged"}</span>
              </span>
              <span className="tnum shrink-0 text-12 text-content-dim">₹{formatNumber(Math.round(f.amount))}</span>
            </button>
          ))}
        </div>
      }
    >
      {account == null ? (
        <div className="grid h-full place-items-center p-6">
          <EmptyState icon={Banknote} title="Trace the money" description="Enter an account id or pick a flagged account to trace fund flows and structuring patterns." />
        </div>
      ) : traceQ.isLoading ? (
        <div className="grid h-full place-items-center"><Skeleton className="h-48 w-3/4" /></div>
      ) : traceQ.error ? (
        <div className="grid h-full place-items-center p-6">
          <EmptyState icon={AlertTriangle} title="Couldn't trace" description={errorMessage(traceQ.error)} />
        </div>
      ) : (
        <div className="flex h-full min-h-0 flex-col">
          <div className="flex items-center gap-3 border-b border-hairline bg-surface px-3 py-2 text-12 text-content-dim">
            <span className="tnum text-content">₹{formatNumber(Math.round(traceQ.data!.total_traced_amount))}</span> traced
            <span>· {traceQ.data!.node_count} accounts · {traceQ.data!.edge_count} transfers</span>
            {flags.length > 0 && <Badge variant="high" className="ml-auto">{flags.length} flagged</Badge>}
          </div>
          <div className="min-h-0 flex-1 p-2">
            {sankey ? (
              <ResponsiveContainer width="100%" height="100%">
                <Sankey
                  data={sankey}
                  nodePadding={22}
                  nodeWidth={12}
                  link={{ stroke: theme.primary, strokeOpacity: 0.25 }}
                  node={{ fill: theme.primary, stroke: theme.surface }}
                  margin={{ top: 12, right: 120, bottom: 12, left: 12 }}
                >
                  <Tooltip
                    contentStyle={{ background: theme.tooltipBg, border: `1px solid ${theme.tooltipBorder}`, borderRadius: 10, fontSize: 12, color: theme.text }}
                    formatter={(v: number) => [`₹${formatNumber(v)}`, "amount"]}
                  />
                </Sankey>
              </ResponsiveContainer>
            ) : (
              <div className="grid h-full place-items-center text-13 text-content-dim">No forward flow to chart for this account.</div>
            )}
          </div>
          {flags.length > 0 && (
            <div className="max-h-40 shrink-0 overflow-auto border-t border-hairline bg-surface p-3">
              <div className="mb-2 flex items-center gap-1.5 text-12 font-semibold uppercase tracking-wide text-content-dim">
                <AlertTriangle className="size-3.5 text-severity-high" /> Structuring / laundering flags
              </div>
              <div className="space-y-1">
                {flags.map((f, i) => (
                  <div key={i} className="flex items-center gap-2 text-12">
                    <span className="tnum text-content">#{f.source_account} → #{f.target_account}</span>
                    <span className="text-content-dim">{f.flag_reasons.join(", ")}</span>
                    <span className="tnum ml-auto text-content-dim">₹{formatNumber(Math.round(f.amount))}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </ModeLayout>
  );
}
