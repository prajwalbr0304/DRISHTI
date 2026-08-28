import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { AlertTriangle, ChevronLeft, ChevronRight, Lock, Map as MapIcon, Search, Table2 } from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import { cn, formatNumber } from "@/lib/utils";
import { roleCan } from "@/config/roles";
import { useRole } from "@/providers/RoleProvider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/common/PageHeader";
import { EmptyState } from "@/components/common/EmptyState";
import { CaseMap } from "@/components/cases/CaseMap";
import { CaseFilterRail, type CaseFilters } from "@/components/cases/CaseFilterRail";
import { CaseTable } from "@/components/cases/CaseTable";
import { MoSearchBar } from "@/components/cases/MoSearchBar";

const PAGE_SIZE = 25;

export function CaseExplorer() {
  const { role } = useRole();
  const navigate = useNavigate();

  const [filters, setFilters] = useState<CaseFilters>({});
  const [page, setPage] = useState(1);
  const [view, setView] = useState<"table" | "map">("table");
  const [qInput, setQInput] = useState("");

  // debounce keyword search into the filter set
  useEffect(() => {
    const t = setTimeout(
      () => setFilters((f) => ({ ...f, q: qInput.trim() || undefined })),
      400,
    );
    return () => clearTimeout(t);
  }, [qInput]);
  useEffect(() => setPage(1), [filters]);

  // Individual case files are PII-bearing, so entry is capability-gated (the
  // server enforces the same decision). INTERIM: every role holds `case_read`.
  const canReadCases = roleCan(role, "case_read");

  const optionsQ = useQuery({
    queryKey: ["cases", "filters"],
    queryFn: ({ signal }) => api.cases.filters(signal),
    enabled: canReadCases,
    staleTime: 10 * 60_000,
  });

  const listQ = useQuery({
    queryKey: ["cases", "list", filters, page],
    queryFn: ({ signal }) => api.cases.list({ ...filters, page, page_size: PAGE_SIZE }, signal),
    enabled: canReadCases,
    placeholderData: keepPreviousData,
  });

  const activeCount = useMemo(
    () => Object.values(filters).filter((v) => v !== undefined && v !== false && v !== "").length,
    [filters],
  );

  if (!canReadCases) {
    return (
      <div>
        <PageHeader title="Cases" />
        <EmptyState
          icon={Lock}
          title="Not available for this role"
          description="Individual case files contain personal data and are not accessible to this role, which works with aggregate views only. See the Command Center and Analytics."
        />
      </div>
    );
  }

  const total = listQ.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const items = listQ.data?.items ?? [];

  return (
    <div className="min-w-0 overflow-x-hidden">
      <PageHeader
        title="Case Explorer"
        description="A filterable index of FIRs — search by attributes or by modus operandi."
      />

      <div className="flex min-w-0 flex-col gap-4 min-[1680px]:flex-row">
        <CaseFilterRail
          filters={filters}
          options={optionsQ.data}
          onChange={(patch) => setFilters((f) => ({ ...f, ...patch }))}
          onClear={() => {
            setFilters({});
            setQInput("");
          }}
          activeCount={activeCount}
        />

        <div className="w-full min-w-0 flex-1 space-y-3">
          <MoSearchBar />

          {/* toolbar */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative min-w-0 basis-full sm:min-w-[220px] sm:flex-1 sm:basis-auto">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-content-dim" />
              <Input
                value={qInput}
                onChange={(e) => setQInput(e.target.value)}
                placeholder="Search case reference, person, alias, source, or facts…"
                className="h-8 pl-8"
              />
            </div>
            <div className="tnum text-13 text-content-dim">
              {listQ.isLoading ? "…" : `${formatNumber(total)} cases`}
            </div>
            <div className="flex overflow-hidden rounded-control border border-hairline">
              <ToggleBtn active={view === "table"} onClick={() => setView("table")} icon={<Table2 />} label="Table" />
              <ToggleBtn active={view === "map"} onClick={() => setView("map")} icon={<MapIcon />} label="Map" />
            </div>
          </div>

          {listQ.error ? (
            <EmptyState
              icon={AlertTriangle}
              title="Couldn't load cases"
              description={errorMessage(listQ.error)}
              action={
                <Button variant="outline" size="sm" onClick={() => listQ.refetch()}>
                  Retry
                </Button>
              }
            />
          ) : view === "table" ? (
            <>
              <CaseTable items={items} loading={listQ.isLoading} onRowClick={(id) => navigate(`/cases/${id}`)} />
              {!listQ.isLoading && items.length === 0 && (
                <p className="py-8 text-center text-13 text-content-dim">No cases match these filters.</p>
              )}
            </>
          ) : (
            <div className="rounded-card border border-hairline bg-surface p-3">
              <div className="mb-2 text-13 text-content-dim">
                Spatial view of this page's results. The full interactive map lives in{" "}
                <Link to="/map" className="text-primary hover:underline">Map &amp; Hotspots</Link>.
              </div>
              <CaseMap items={items} onSelect={(id) => navigate(`/cases/${id}`)} />
            </div>
          )}

          {/* pagination */}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="tnum text-12 text-content-dim">
              Page {page} of {formatNumber(totalPages)}
            </span>
            <div className="flex items-center gap-1.5">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1 || listQ.isFetching}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                <ChevronLeft /> Prev
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages || listQ.isFetching}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              >
                Next <ChevronRight />
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ToggleBtn({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex items-center gap-1.5 px-2.5 py-1.5 text-13 font-medium transition-colors [&_svg]:size-4",
        active ? "bg-primary text-primary-fg" : "bg-surface-2 text-content-dim hover:text-content",
      )}
    >
      {icon}
      {label}
    </button>
  );
}
