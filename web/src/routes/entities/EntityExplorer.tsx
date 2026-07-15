import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { AlertTriangle, ChevronLeft, ChevronRight, Lock, Search, Users } from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import type { EntityListItem } from "@/api/types";
import { cn, formatNumber } from "@/lib/utils";
import { useRole } from "@/providers/RoleProvider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/common/PageHeader";
import { EmptyState } from "@/components/common/EmptyState";

const PAGE_SIZE = 25;
const TYPE_OPTIONS = [
  { value: "person", label: "Person" },
  { value: "phone", label: "Phone" },
  { value: "vehicle", label: "Vehicle" },
  { value: "location", label: "Location" },
  { value: "bank_account", label: "Bank account" },
  { value: "gang", label: "Gang" },
];

export function EntityExplorer() {
  const { role } = useRole();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [entityType, setEntityType] = useState("");
  const [hasRisk, setHasRisk] = useState(false);
  const [gangAffiliated, setGangAffiliated] = useState(false);
  const [page, setPage] = useState(1);

  useEffect(() => {
    const t = setTimeout(() => setSearch(q.trim()), 400);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => setPage(1), [search, entityType, hasRisk, gangAffiliated]);

  if (role === "policymaker") {
    return (
      <div>
        <PageHeader title="People & Entities" />
        <EmptyState
          icon={Lock}
          title="Not available for this role"
          description="Individual entity profiles are not accessible to the policymaker role, which works with aggregate views only."
        />
      </div>
    );
  }

  const listQ = useQuery({
    queryKey: ["entities", "list", search, entityType, hasRisk, gangAffiliated, page],
    queryFn: ({ signal }) =>
      api.graph.entities(
        {
          q: search || undefined,
          entity_type: entityType || undefined,
          has_risk: hasRisk || undefined,
          gang_affiliated: gangAffiliated || undefined,
          page,
          page_size: PAGE_SIZE,
        },
        signal,
      ),
    placeholderData: keepPreviousData,
  });

  const items = listQ.data?.items ?? [];
  const total = listQ.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div>
      <PageHeader
        title="People & Entities"
        description="Search and browse persons, phones, vehicles, gangs and accounts in the intelligence graph."
      />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative min-w-[240px] flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-content-dim" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search label…"
            className="h-8 pl-8"
          />
        </div>
        <NativeSelect
          value={entityType}
          onChange={setEntityType}
          options={TYPE_OPTIONS}
          placeholder="All types"
          className="w-40"
          aria-label="Entity type"
        />
        <label className="flex cursor-pointer items-center gap-1.5 text-13 text-content">
          <input type="checkbox" checked={hasRisk} onChange={(e) => setHasRisk(e.target.checked)} className="size-3.5 accent-[var(--primary)]" />
          Has risk score
        </label>
        <label className="flex cursor-pointer items-center gap-1.5 text-13 text-content">
          <input type="checkbox" checked={gangAffiliated} onChange={(e) => setGangAffiliated(e.target.checked)} className="size-3.5 accent-[var(--primary)]" />
          Gang affiliated
        </label>
        <span className="tnum text-13 text-content-dim">{listQ.isLoading ? "…" : `${formatNumber(total)} entities`}</span>
      </div>

      {listQ.error ? (
        <EmptyState icon={AlertTriangle} title="Couldn't load entities" description={errorMessage(listQ.error)} />
      ) : (
        <div className="overflow-x-auto rounded-card border border-hairline">
          <table className="w-full border-collapse text-13">
            <thead className="sticky top-0 z-10 bg-surface-2">
              <tr className="border-b border-hairline">
                <th className="px-3 py-2 text-left text-12 font-semibold text-content-dim">Label</th>
                <th className="px-3 py-2 text-left text-12 font-semibold text-content-dim">Type</th>
                <th className="px-3 py-2 text-left text-12 font-semibold text-content-dim">Source</th>
                <th className="px-3 py-2 text-right text-12 font-semibold text-content-dim">PageRank</th>
                <th className="px-3 py-2 text-right text-12 font-semibold text-content-dim">Community</th>
              </tr>
            </thead>
            <tbody>
              {listQ.isLoading &&
                Array.from({ length: 10 }).map((_, i) => (
                  <tr key={i} className="border-b border-hairline">
                    <td className="px-3 py-2" colSpan={5}><Skeleton className="h-5 w-full" /></td>
                  </tr>
                ))}
              {!listQ.isLoading && items.map((e) => (
                <tr
                  key={e.entity_id}
                  onClick={() => navigate(`/people/${e.entity_id}`)}
                  className="cursor-pointer border-b border-hairline transition-colors hover:bg-surface-2"
                >
                  <td className="px-3 py-2 font-medium text-content">{e.label}</td>
                  <td className="px-3 py-2">
                    <Badge variant="neutral" className="capitalize">{e.entity_type.replace(/_/g, " ")}</Badge>
                  </td>
                  <td className="px-3 py-2 text-content-dim">{e.ref_table ?? "—"}</td>
                  <td className="tnum px-3 py-2 text-right text-content-dim">{e.pagerank?.toFixed(5) ?? "—"}</td>
                  <td className="tnum px-3 py-2 text-right text-content-dim">{e.community ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!listQ.isLoading && items.length === 0 && !listQ.error && (
        <p className="py-8 text-center text-13 text-content-dim">No entities match these filters.</p>
      )}

      <div className="mt-3 flex items-center justify-between">
        <span className="tnum text-12 text-content-dim">Page {page} of {formatNumber(totalPages)}</span>
        <div className="flex items-center gap-1.5">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            <ChevronLeft /> Prev
          </Button>
          <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
            Next <ChevronRight />
          </Button>
        </div>
      </div>
    </div>
  );
}
