import { useCallback } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  Banknote,
  BookOpen,
  FolderKanban,
  GitBranch,
  Lock,
  MapPin,
  Network,
  ShieldAlert,
  Users,
} from "lucide-react";
import { api } from "@/api";
import { ApiError, errorMessage } from "@/api/contracts";
import type { EntityDetailResponse, RiskResponse, SubgraphResponse } from "@/api/types";
import { cn, formatDate, formatNumber, formatPercent } from "@/lib/utils";
import { useRole } from "@/providers/RoleProvider";
import { usePeekStore } from "@/stores/usePeekStore";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/EmptyState";
import { PageHeader } from "@/components/common/PageHeader";
import { Widget } from "@/components/widget/Widget";
import { MiniDensity } from "@/components/dashboard/MiniDensity";
import { EvidenceTrail } from "@/components/widget/EvidenceTrail";

/* ============================================================================
   Entity Profile (doc 01 §4.3): AWS-style sub-nav with Identity, Criminal
   History, Network, Risk (gauge + factor bars), MO Cluster, Cases, Financial
   (permission-gated), Locations, Evidence Trail.
   ========================================================================== */

interface SubItem {
  key: string;
  label: string;
  icon: React.ElementType;
}

const SUB_NAV: SubItem[] = [
  { key: "identity", label: "Identity", icon: BookOpen },
  { key: "history", label: "Criminal History", icon: FolderKanban },
  { key: "network", label: "Network", icon: Network },
  { key: "risk", label: "Risk", icon: ShieldAlert },
  { key: "mo", label: "MO Cluster", icon: Users },
  { key: "cases", label: "Cases", icon: FolderKanban },
  { key: "financial", label: "Financial", icon: Banknote },
  { key: "locations", label: "Locations", icon: MapPin },
  { key: "trail", label: "Evidence Trail", icon: GitBranch },
];

export function EntityProfile() {
  const { role } = useRole();
  const navigate = useNavigate();
  const { entityId: rawId } = useParams<{ entityId: string }>();
  const entityId = Number(rawId);
  const [sp, setSp] = useSearchParams();
  const tab = sp.get("tab") ?? "identity";
  const goTo = useCallback((k: string) => setSp({ tab: k }, { replace: true }), [setSp]);

  if (role === "policymaker") {
    return (
      <div>
        <PageHeader title="Entity profile" />
        <EmptyState
          icon={Lock}
          title="Not available for this role"
          description="Individual entity profiles are not accessible to the policymaker role (aggregate-only)."
        />
      </div>
    );
  }

  const detailQ = useQuery({
    queryKey: ["entity", "detail", entityId],
    queryFn: ({ signal }) => api.graph.entityDetail(entityId, signal),
    enabled: Number.isFinite(entityId) && entityId > 0,
  });

  if (detailQ.error) {
    const is404 = detailQ.error instanceof ApiError && detailQ.error.status === 404;
    return (
      <EmptyState
        icon={is404 ? Users : AlertTriangle}
        title={is404 ? "Entity not found" : "Couldn't load entity"}
        description={errorMessage(detailQ.error)}
        action={<Button variant="outline" size="sm" onClick={() => navigate("/people")}>Back to explorer</Button>}
      />
    );
  }

  const detail = detailQ.data;

  return (
    <div className="flex gap-4">
      <aside className="hidden w-subnav shrink-0 md:block">
        <ScrollArea className="h-[calc(100vh-11rem)]">
          <nav className="space-y-0.5 pr-2">
            {SUB_NAV.map((s) => {
              const Icon = s.icon;
              const active = tab === s.key;
              return (
                <button
                  key={s.key}
                  type="button"
                  onClick={() => goTo(s.key)}
                  className={cn(
                    "flex w-full items-center gap-2.5 rounded-control px-2.5 py-2 text-13 font-medium transition-colors",
                    active ? "bg-surface-2 text-content" : "text-content-dim hover:bg-surface-2/60 hover:text-content",
                  )}
                >
                  <Icon className={cn("size-4 shrink-0", active && "text-primary")} />
                  <span className="truncate">{s.label}</span>
                </button>
              );
            })}
          </nav>
        </ScrollArea>
      </aside>

      <div className="min-w-0 flex-1">
        <PageHeader
          title={detailQ.isLoading ? <Skeleton className="h-6 w-48" /> : (detail?.label ?? `Entity ${entityId}`)}
          description={detail ? `${detail.entity_type} · Entity ${detail.entity_id}` : undefined}
        />
        {detailQ.isLoading ? (
          <div className="space-y-3"><Skeleton className="h-48 w-full" /><Skeleton className="h-24 w-full" /></div>
        ) : detail ? (
          <SubPage tab={tab} detail={detail} entityId={entityId} />
        ) : null}
      </div>
    </div>
  );
}

/* ------------------------------- Sub-pages -------------------------------- */
function SubPage({ tab, detail, entityId }: { tab: string; detail: EntityDetailResponse; entityId: number }) {
  switch (tab) {
    case "identity": return <IdentityTab detail={detail} />;
    case "history": return <HistoryTab detail={detail} />;
    case "network": return <NetworkTab entityId={entityId} />;
    case "risk": return <RiskTab entityId={entityId} />;
    case "mo": return <MoTab detail={detail} />;
    case "cases": return <CasesTab detail={detail} />;
    case "financial": return <FinancialTab entityId={entityId} />;
    case "locations": return <LocationsTab detail={detail} />;
    case "trail": return <TrailTab entityId={entityId} />;
    default: return <IdentityTab detail={detail} />;
  }
}

/* Identity */
function IdentityTab({ detail }: { detail: EntityDetailResponse }) {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <div className="rounded-card border border-hairline bg-surface p-4 space-y-3">
        <Fact label="Label" value={detail.label} />
        <Fact label="Type" value={detail.entity_type} />
        <Fact label="Source table" value={detail.ref_table} />
        <Fact label="Source ID" value={detail.ref_id} />
        {detail.accused_master_id && <Fact label="AccusedMasterID" value={String(detail.accused_master_id)} mono />}
        <Fact label="District" value={detail.district} />
        {detail.created_at && <Fact label="First seen" value={formatDate(detail.created_at)} />}
      </div>
      <div className="rounded-card border border-hairline bg-surface p-4 space-y-3">
        <Fact label="PageRank" value={detail.pagerank?.toFixed(5)} mono />
        <Fact label="Betweenness" value={detail.betweenness?.toFixed(5)} mono />
        <Fact label="Community" value={detail.community != null ? String(detail.community) : null} mono />
        {detail.gangs.length > 0 && (
          <div>
            <span className="text-12 text-content-dim">Gang affiliations</span>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {detail.gangs.map((g) => <Badge key={g.gang_id} variant="high">{g.gang_name ?? `Gang ${g.gang_id}`}</Badge>)}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* Criminal History */
function HistoryTab({ detail }: { detail: EntityDetailResponse }) {
  const navigate = useNavigate();
  if (!detail.cases.length) return <EmptyState icon={FolderKanban} title="No linked cases" description="No FIRs are linked to this entity." />;
  return (
    <div className="space-y-1.5">
      {detail.cases.map((c) => (
        <button
          key={c.case_id}
          type="button"
          onClick={() => navigate(`/cases/${c.case_id}`)}
          className="flex w-full items-center gap-3 rounded-control border border-hairline bg-surface px-4 py-2.5 text-left transition-colors hover:bg-surface-2"
        >
          <span className="min-w-0 flex-1">
            <span className="block truncate text-13 font-medium text-content">{c.crime_no ?? `Case ${c.case_id}`}</span>
            <span className="block truncate text-12 text-content-dim">{[c.crime_group, c.status].filter(Boolean).join(" · ")}</span>
          </span>
          <Badge variant="neutral" className="shrink-0 capitalize">{c.role}</Badge>
          <span className="tnum shrink-0 text-12 text-content-dim">{c.registered_date ? formatDate(c.registered_date) : ""}</span>
        </button>
      ))}
    </div>
  );
}

/* Network */
function NetworkTab({ entityId }: { entityId: number }) {
  const push = usePeekStore((s) => s.push);
  const q = useQuery({
    queryKey: ["graph", "neighbourhood", entityId, 2, 15],
    queryFn: ({ signal }) => api.graph.neighbourhood(entityId, 2, 15, signal),
  });
  return (
    <Widget title="Network" provenance={q.data?.result} loading={q.isLoading} error={q.error}
      empty={!q.isLoading && !q.error && (q.data?.node_count ?? 0) <= 1}
      emptyLabel="No connections found." onRefresh={() => q.refetch()}>
      {q.data && q.data.nodes.length > 1 && (
        <div className="space-y-1">
          <div className="text-12 text-content-dim tnum">{q.data.node_count} nodes · {q.data.edge_count} edges</div>
          {q.data.nodes.filter((n) => n.entity_id !== entityId).slice(0, 20).map((n) => (
            <button key={n.entity_id} type="button"
              onClick={() => push({ kind: "person", id: n.entity_id, label: n.label ?? `Entity ${n.entity_id}`, sublabel: n.entity_type })}
              className="flex w-full items-center gap-2 rounded-control px-2 py-1.5 text-left transition-colors hover:bg-surface-2">
              <span className="truncate text-13 text-content">{n.label ?? n.entity_id}</span>
              <Badge variant="neutral" className="ml-auto shrink-0 capitalize">{n.entity_type}</Badge>
            </button>
          ))}
        </div>
      )}
    </Widget>
  );
}

/* Risk (gauge + signed factor bars) */
function RiskTab({ entityId }: { entityId: number }) {
  const q = useQuery({
    queryKey: ["risk", "entity", entityId],
    queryFn: ({ signal }) => api.risk.byEntity(entityId, false, signal),
  });
  const is404 = q.error instanceof ApiError && (q.error as ApiError).status === 404;
  if (is404) return <EmptyState icon={ShieldAlert} title="No risk score" description="This entity has not been scored yet. Run the risk batch or rescore=true." />;
  return (
    <Widget title="Risk score" provenance={q.data?.result} loading={q.isLoading} error={q.error} onRefresh={() => q.refetch()}>
      {q.data && <RiskGauge data={q.data} />}
    </Widget>
  );
}

function RiskGauge({ data }: { data: RiskResponse }) {
  const pct = Math.round(data.risk_score * 100);
  return (
    <div className="space-y-4">
      <div className="flex items-baseline gap-3">
        <span className="tnum text-36 font-bold text-content">{pct}%</span>
        <Badge variant={data.risk_level === "critical" ? "critical" : data.risk_level === "high" ? "high" : data.risk_level === "medium" ? "medium" : "low"} className="capitalize">
          {data.risk_band}
        </Badge>
      </div>
      {/* Gauge bar */}
      <div className="h-2 w-full overflow-hidden rounded-full bg-surface-2">
        <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
      </div>
      {/* Signed factor bars */}
      <div className="space-y-2">
        {data.factors.map((f) => (
          <div key={f.feature} className="flex items-center gap-3">
            <span className="w-40 shrink-0 truncate text-13 text-content-dim" title={f.label}>{f.label}</span>
            <span className="relative h-2 flex-1 overflow-hidden rounded-full bg-surface-2">
              <span
                className={cn("absolute inset-y-0 rounded-full", f.contribution >= 0 ? "left-1/2 bg-severity-high" : "right-1/2 bg-severity-low")}
                style={{ width: `${Math.min(50, Math.abs(f.contribution) * 100)}%` }}
              />
            </span>
            <span className={cn("tnum w-12 shrink-0 text-right text-12 font-medium", f.contribution >= 0 ? "text-severity-high" : "text-severity-low")}>
              {f.contribution >= 0 ? "+" : ""}{f.contribution.toFixed(2)}
            </span>
          </div>
        ))}
      </div>
      <p className="text-12 text-content-dim capitalize">{data.factors[0]?.direction ?? ""} risk direction</p>
    </div>
  );
}

/* MO Cluster */
function MoTab({ detail }: { detail: EntityDetailResponse }) {
  const cluster = detail.community;
  if (cluster == null) return <EmptyState icon={Users} title="No MO cluster" description="Community detection hasn't assigned this entity yet." />;
  return (
    <div className="rounded-card border border-hairline bg-surface p-4">
      <div className="text-13 text-content">This entity belongs to community <span className="tnum font-semibold text-primary">#{cluster}</span>.</div>
      <p className="mt-2 text-12 text-content-dim">Louvain community labels are written by the graph batch job. Explore co-members in the Network tab or the full Network Analysis canvas.</p>
    </div>
  );
}

/* Cases */
function CasesTab({ detail }: { detail: EntityDetailResponse }) {
  return <HistoryTab detail={detail} />;
}

/* Financial (permission-gated via X-Role) */
function FinancialTab({ entityId }: { entityId: number }) {
  const { role } = useRole();
  const q = useQuery({
    queryKey: ["money", "unified", entityId],
    queryFn: ({ signal }) => api.money.unified({ entity_id: entityId }, 2, signal),
    retry: false,
  });
  const is403 = q.error instanceof ApiError && (q.error as ApiError).status === 403;
  if (is403) return <EmptyState icon={Lock} title="Financial data restricted" description={`The '${role}' role does not have the money_trail permission.`} />;
  return (
    <Widget title="Financial links" provenance={q.data?.result} loading={q.isLoading} error={q.error}
      empty={!q.isLoading && !q.error && (q.data?.node_count ?? 0) === 0} emptyLabel="No financial links." onRefresh={() => q.refetch()}>
      {q.data && (
        <div className="space-y-1.5">
          <div className="text-12 text-content-dim tnum">{q.data.node_count} accounts/entities · {q.data.edge_count} links</div>
          {q.data.nodes.slice(0, 12).map((n) => (
            <div key={n.id} className="flex items-center gap-2 rounded-control px-2 py-1 text-13">
              <span className="truncate text-content">{n.label ?? n.id}</span>
              <Badge variant={n.is_flagged ? "high" : "neutral"} className="ml-auto shrink-0 capitalize">{n.kind}</Badge>
            </div>
          ))}
        </div>
      )}
    </Widget>
  );
}

/* Locations */
function LocationsTab({ detail }: { detail: EntityDetailResponse }) {
  const points = detail.latitude != null && detail.longitude != null
    ? [{ lon: detail.longitude, lat: detail.latitude, weight: 0.8 }]
    : [];
  if (!points.length) return <EmptyState icon={MapPin} title="No location" description="This entity has no geo-location." />;
  return (
    <div className="rounded-card border border-hairline bg-surface p-4">
      <MiniDensity points={points} />
      <div className="mt-2 tnum text-12 text-content-dim">{detail.latitude?.toFixed(6)}, {detail.longitude?.toFixed(6)}</div>
    </div>
  );
}

/* Evidence Trail */
function TrailTab({ entityId }: { entityId: number }) {
  const q = useQuery({
    queryKey: ["risk", "entity", entityId],
    queryFn: ({ signal }) => api.risk.byEntity(entityId, false, signal),
    retry: false,
  });
  const is404 = q.error instanceof ApiError && (q.error as ApiError).status === 404;
  if (is404 || (!q.isLoading && !q.data)) return <EmptyState icon={GitBranch} title="No evidence trail" description="No AI result is available to trace for this entity. Risk score and network provenance drive the Evidence Trail." />;
  return (
    <Widget title="Evidence Trail" loading={q.isLoading} error={q.error}>
      {q.data && <EvidenceTrail result={q.data.result} />}
    </Widget>
  );
}

/* Helper */
function Fact({ label, value, mono }: { label: string; value?: string | null; mono?: boolean }) {
  return (
    <div>
      <div className="text-12 text-content-dim">{label}</div>
      <div className={cn("text-13 text-content", mono && "tnum")}>{value ?? "—"}</div>
    </div>
  );
}
