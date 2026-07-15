import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowUpRight,
  ChevronDown,
  Coins,
  GitBranch,
  Network as NetworkIcon,
  ShieldAlert,
} from "lucide-react";
import { api } from "@/api";
import { ApiError, errorMessage, type AiResult } from "@/api/contracts";
import type { EntityKind, GraphNode, ObjectRef } from "@/api/types";
import type { PeekEntry } from "@/stores/usePeekStore";
import { usePeekStore } from "@/stores/usePeekStore";
import { cn, formatNumber, formatPercent } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EvidenceTrail } from "@/components/widget/EvidenceTrail";

/* ============================================================================
   Peek content resolvers. Each opens a reference by calling a READ-ONLY Wave-B
   endpoint (no writes, no mocks). Related records inside a peek push a new peek
   (peek-within-peek). When no direct endpoint exists, we say so honestly and
   offer the destination that can show it.
   ========================================================================== */

export function PeekContent({ entry }: { entry: PeekEntry }) {
  switch (entry.kind) {
    case "person":
      return <PersonPeek id={Number(entry.id)} />;
    case "case":
      return <CasePeek id={Number(entry.id)} />;
    case "account":
      return <AccountPeek id={Number(entry.id)} />;
    case "model":
      return <ModelPeek id={Number(entry.id)} />;
    case "association":
      return <AssociationPeek id={Number(entry.id)} />;
    default:
      return <GenericPeek entry={entry} />;
  }
}

/* ------------------------------- Person ----------------------------------- */
function PersonPeek({ id }: { id: number }) {
  const navigate = useNavigate();
  const push = usePeekStore((s) => s.push);
  const risk = useQuery({
    queryKey: ["risk", "entity", id],
    queryFn: ({ signal }) => api.risk.byEntity(id, false, signal),
  });
  const nb = useQuery({
    queryKey: ["graph", "neighbourhood", id, 1],
    queryFn: ({ signal }) => api.graph.neighbourhood(id, 1, 10, signal),
  });

  return (
    <div className="space-y-4">
      <PeekSection title="Risk" icon={<ShieldAlert className="size-4" />}>
        {risk.isLoading ? (
          <Skeleton className="h-16 w-full" />
        ) : risk.error ? (
          <PeekError error={risk.error} onRetry={() => risk.refetch()} />
        ) : risk.data ? (
          <div className="space-y-2">
            <div className="flex items-baseline justify-between">
              <span className="text-13 text-content-dim">
                {risk.data.offender_name ?? `Entity ${id}`}
              </span>
              <Badge variant={riskBadge(risk.data.risk_level)} className="capitalize">
                {risk.data.risk_band}
              </Badge>
            </div>
            <Meter value={risk.data.risk_score} label="Risk score" />
            {risk.data.factors.slice(0, 3).map((f) => (
              <div key={f.feature} className="flex items-center justify-between text-12">
                <span className="truncate text-content-dim">{f.label}</span>
                <span className={cn("tnum font-medium", f.contribution >= 0 ? "text-severity-high" : "text-severity-low")}>
                  {f.contribution >= 0 ? "+" : ""}
                  {f.contribution.toFixed(2)}
                </span>
              </div>
            ))}
            <Provenance result={risk.data.result} />
          </div>
        ) : null}
      </PeekSection>

      <PeekSection title="Immediate network" icon={<NetworkIcon className="size-4" />}>
        {nb.isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : nb.error ? (
          <PeekError error={nb.error} onRetry={() => nb.refetch()} />
        ) : nb.data ? (
          <div className="space-y-1.5">
            <div className="text-12 text-content-dim tnum">
              {nb.data.node_count} entities · {nb.data.edge_count} links
            </div>
            {nb.data.nodes
              .filter((n) => n.entity_id !== id)
              .slice(0, 6)
              .map((n) => (
                <NeighbourRow key={n.entity_id} node={n} onOpen={() => push(nodeToRef(n))} />
              ))}
            <Provenance result={nb.data.result} />
          </div>
        ) : null}
      </PeekSection>

      <OpenIn label="Open full profile" onClick={() => navigate(`/people/${id}`)} />
    </div>
  );
}

function NeighbourRow({ node, onOpen }: { node: GraphNode; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-full items-center gap-2 rounded-control px-2 py-1.5 text-left text-13 transition-colors hover:bg-surface-2"
    >
      <span className="truncate text-content">{node.label ?? `Entity ${node.entity_id}`}</span>
      <Badge variant="neutral" className="ml-auto shrink-0 capitalize">
        {node.entity_type}
      </Badge>
      <ArrowUpRight className="size-3.5 shrink-0 text-content-dim" />
    </button>
  );
}

/* -------------------------------- Case ------------------------------------ */
function CasePeek({ id }: { id: number }) {
  const navigate = useNavigate();
  const push = usePeekStore((s) => s.push);
  const sim = useQuery({
    queryKey: ["cases", "similar", id],
    queryFn: ({ signal }) => api.cases.similar(id, 5, signal),
  });

  return (
    <div className="space-y-4">
      <PeekSection title="Similar cases" icon={<GitBranch className="size-4" />}>
        {sim.isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : sim.error ? (
          <PeekError error={sim.error} onRetry={() => sim.refetch()} />
        ) : sim.data ? (
          <div className="space-y-1.5">
            <div className="text-12 text-content-dim tnum">
              corpus {formatNumber(sim.data.corpus_size)} cases
            </div>
            {sim.data.results.map((c) => (
              <button
                key={c.case_id}
                type="button"
                onClick={() =>
                  push({ kind: "case", id: c.case_id, label: c.crime_no ?? `Case ${c.case_id}`, sublabel: c.crime_group ?? "Case" })
                }
                className="flex w-full items-center gap-2 rounded-control px-2 py-1.5 text-left transition-colors hover:bg-surface-2"
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-13 text-content">
                    {c.crime_no ?? `Case ${c.case_id}`}
                  </span>
                  <span className="block truncate text-12 text-content-dim">
                    {[c.crime_group, c.district].filter(Boolean).join(" · ")}
                  </span>
                </span>
                <span className="tnum shrink-0 text-12 font-medium text-primary">
                  {formatPercent(c.similarity, 0)}
                </span>
              </button>
            ))}
            <Provenance result={sim.data.result} />
          </div>
        ) : null}
      </PeekSection>

      <OpenIn label="Open in Cases" onClick={() => navigate(`/cases?case=${id}`)} />
    </div>
  );
}

/* ------------------------------- Account ---------------------------------- */
function AccountPeek({ id }: { id: number }) {
  const navigate = useNavigate();
  const push = usePeekStore((s) => s.push);
  const trace = useQuery({
    queryKey: ["money", "trace", id],
    queryFn: ({ signal }) => api.money.trace(id, 3, signal),
  });

  const forbidden = trace.error instanceof ApiError && trace.error.status === 403;

  return (
    <div className="space-y-4">
      <PeekSection title="Money trace" icon={<Coins className="size-4" />}>
        {trace.isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : forbidden ? (
          <p className="text-12 text-content-dim">
            Money-trail access is restricted for your current role.
          </p>
        ) : trace.error ? (
          <PeekError error={trace.error} onRetry={() => trace.refetch()} />
        ) : trace.data ? (
          <div className="space-y-1.5">
            <div className="flex items-baseline justify-between">
              <span className="text-12 text-content-dim">Total traced</span>
              <span className="tnum font-semibold text-content">
                ₹{formatNumber(Math.round(trace.data.total_traced_amount))}
              </span>
            </div>
            <div className="text-12 text-content-dim tnum">
              {trace.data.node_count} accounts · {trace.data.edge_count} transfers
            </div>
            {trace.data.nodes
              .filter((n) => n.account_id !== id)
              .slice(0, 6)
              .map((n) => (
                <button
                  key={n.account_id}
                  type="button"
                  onClick={() =>
                    push({ kind: "account", id: n.account_id, label: n.label ?? `Account ${n.account_id}`, sublabel: n.bank ?? "Account" })
                  }
                  className="flex w-full items-center gap-2 rounded-control px-2 py-1.5 text-left text-13 transition-colors hover:bg-surface-2"
                >
                  <span className="truncate text-content">{n.label ?? `Account ${n.account_id}`}</span>
                  {n.is_flagged && <Badge variant="high" className="ml-auto shrink-0">flagged</Badge>}
                </button>
              ))}
            <Provenance result={trace.data.result} />
          </div>
        ) : null}
      </PeekSection>

      <OpenIn label="Open in Money Trail" onClick={() => navigate(`/network?mode=money&account=${id}`)} />
    </div>
  );
}

/* -------------------------------- Model ----------------------------------- */
function ModelPeek({ id }: { id: number }) {
  const navigate = useNavigate();
  const md = useQuery({
    queryKey: ["explain", "model", id],
    queryFn: ({ signal }) => api.explain.modelDetail(id, signal),
  });

  return (
    <div className="space-y-4">
      <PeekSection title="Model" icon={<GitBranch className="size-4" />}>
        {md.isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : md.error ? (
          <PeekError error={md.error} onRetry={() => md.refetch()} />
        ) : md.data ? (
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <span className="text-13 font-medium text-content">{md.data.model.model_name}</span>
              <code className="tnum rounded bg-surface-2 px-1.5 py-0.5 text-12 text-content-dim">
                v{md.data.model.version}
              </code>
            </div>
            <div className="text-12 text-content-dim">
              {[md.data.model.model_type, md.data.model.status].filter(Boolean).join(" · ")}
            </div>
            <div className="flex items-center justify-between text-12">
              <span className="text-content-dim">Drift</span>
              <span className="capitalize text-content">{md.data.drift_flag.replace(/_/g, " ")}</span>
            </div>
            {md.data.notes && <p className="text-12 text-content-dim">{md.data.notes}</p>}
            <Provenance result={md.data.result} />
          </div>
        ) : null}
      </PeekSection>

      <OpenIn label="Open in Admin" onClick={() => navigate(`/admin?model=${id}`)} />
    </div>
  );
}

/* ----------------------------- Association -------------------------------- */
function AssociationPeek({ id }: { id: number }) {
  const navigate = useNavigate();
  const push = usePeekStore((s) => s.push);
  const pp = useQuery({
    queryKey: ["graph", "proof", id],
    queryFn: ({ signal }) => api.graph.proofPath(id, signal),
  });

  return (
    <div className="space-y-4">
      <PeekSection title="Hidden association" icon={<NetworkIcon className="size-4" />}>
        {pp.isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : pp.error ? (
          <PeekError error={pp.error} onRetry={() => pp.refetch()} />
        ) : pp.data ? (
          <div className="space-y-1.5">
            <div className="flex flex-wrap gap-1">
              {pp.data.link_kinds.map((k) => (
                <Badge key={k} variant="primary">
                  {k}
                </Badge>
              ))}
            </div>
            {pp.data.nodes.slice(0, 6).map((n) => (
              <NeighbourRow key={n.entity_id} node={n} onOpen={() => push(nodeToRef(n))} />
            ))}
            <Provenance result={pp.data.result} />
          </div>
        ) : null}
      </PeekSection>
      <OpenIn label="Open in Network Analysis" onClick={() => navigate(`/network?mode=hidden&association=${id}`)} />
    </div>
  );
}

/* ------------------------------- Generic ---------------------------------- */
function GenericPeek({ entry }: { entry: ObjectRef }) {
  const navigate = useNavigate();
  const target = kindDestination(entry.kind);
  return (
    <div className="space-y-4">
      <PeekSection title="Reference">
        <p className="text-13 text-content">{entry.label}</p>
        {entry.sublabel && <p className="text-12 text-content-dim">{entry.sublabel}</p>}
        <p className="mt-2 text-12 text-content-dim">
          No standalone detail endpoint for a {entry.kind} yet — open the destination that shows it.
        </p>
      </PeekSection>
      {target && <OpenIn label={`Open in ${target.label}`} onClick={() => navigate(target.path)} />}
    </div>
  );
}

/* ------------------------------- helpers ---------------------------------- */
function PeekSection({
  title,
  icon,
  children,
}: {
  title: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h4 className="mb-2 flex items-center gap-1.5 text-12 font-semibold uppercase tracking-wide text-content-dim">
        {icon}
        {title}
      </h4>
      {children}
    </section>
  );
}

function Meter({ value, label }: { value: number; label: string }) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-12">
        <span className="text-content-dim">{label}</span>
        <span className="tnum font-semibold text-content">{formatPercent(value, 0)}</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
        <div className="h-full rounded-full bg-primary" style={{ width: `${Math.round(value * 100)}%` }} />
      </div>
    </div>
  );
}

function Provenance({ result }: { result: AiResult }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2 border-t border-hairline pt-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 text-12 text-content-dim transition-colors hover:text-content"
        aria-expanded={open}
      >
        <span className="tnum font-medium text-content">{formatPercent(result.confidence, 0)}</span>
        <span>confidence · evidence</span>
        <ChevronDown className={cn("ml-auto size-3.5 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="mt-2">
          <EvidenceTrail result={result} />
        </div>
      )}
    </div>
  );
}

function PeekError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  return (
    <div className="flex items-start gap-2 rounded-control border border-hairline bg-surface-2/40 p-2.5">
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-severity-high" />
      <div className="min-w-0">
        <p className="text-12 text-content-dim">{errorMessage(error)}</p>
        <Button variant="link" size="sm" onClick={onRetry} className="h-auto px-0 text-12">
          Retry
        </Button>
      </div>
    </div>
  );
}

function OpenIn({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <Button variant="outline" size="sm" onClick={onClick} className="w-full justify-between">
      {label}
      <ArrowUpRight />
    </Button>
  );
}

function riskBadge(level: string): "critical" | "high" | "medium" | "low" | "neutral" {
  switch (level.toLowerCase()) {
    case "critical":
      return "critical";
    case "high":
      return "high";
    case "medium":
      return "medium";
    case "low":
      return "low";
    default:
      return "neutral";
  }
}

const KIND_BY_ENTITY_TYPE: Record<string, EntityKind> = {
  person: "person",
  accused: "person",
  victim: "person",
  vehicle: "vehicle",
  phone: "phone",
  account: "account",
  location: "location",
  organisation: "organisation",
};

function nodeToRef(n: GraphNode): ObjectRef {
  const kind = KIND_BY_ENTITY_TYPE[n.entity_type?.toLowerCase()] ?? "person";
  return { kind, id: n.entity_id, label: n.label ?? `Entity ${n.entity_id}`, sublabel: n.entity_type };
}

function kindDestination(kind: EntityKind): { label: string; path: string } | null {
  switch (kind) {
    case "vehicle":
    case "phone":
    case "organisation":
      return { label: "Network Analysis", path: "/network" };
    case "location":
      return { label: "Map & Hotspots", path: "/map" };
    case "alert":
      return { label: "Map & Hotspots", path: "/map" };
    default:
      return null;
  }
}
