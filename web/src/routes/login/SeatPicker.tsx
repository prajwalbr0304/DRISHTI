import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Loader2, Search, UserCog } from "lucide-react";
import { api } from "@/api";
import type { SeatOut } from "@/api/endpoints/org";
import { RoleIcon } from "@/components/roles/RoleIcon";
import {
  SCOPE_TYPE_BLURBS, SCOPE_TYPE_LABELS, normalizeRole,
  type ScopeType,
} from "@/config/roles";
import { useSeatStore, type SelectedSeat } from "@/stores/useSeatStore";
import { cn } from "@/lib/utils";

/* ============================================================================
   Seat picker.

   The login screen used to be a grid of role cards, which worked when a role was
   a seat. It is not any more: there are ~11,825 provisioned seats and a role only
   says which BOARD renders. An SP of Mysuru and an SP of Belagavi share a role and
   command different districts, so a role card cannot pick between them.

   Two steps rather than one long list: choose the TIER (what kind of seat), then
   search within it. 1,000 SHO seats and ~10,700 IO seats cannot be browsed, but
   they can be searched — by station name, posting or officer name, which is how
   someone actually knows the seat they want.

   Selecting a seat sets a VIEW. The server resolves that seat's jurisdiction from
   its own record, so this cannot grant access to a district; it only says which
   seat to render for.
   ========================================================================== */

/** Tiers, in command order. Each maps to a scope_type the server can filter on. */
const TIERS: { scope: ScopeType; label: string }[] = [
  { scope: "state", label: "State Command" },
  { scope: "wing", label: "Functional Wing" },
  { scope: "range", label: "Range Command" },
  { scope: "commissionerate", label: "City Commissionerate" },
  { scope: "district", label: "District Command" },
  { scope: "station", label: "Station (SHO)" },
  { scope: "assigned_case", label: "Investigating Officer" },
  { scope: "platform", label: "Platform Admin" },
];

/** Tiers with few enough seats to list without searching. The rest need a query
 *  before anything is shown, so the picker never tries to render 10,700 rows. */
const BROWSABLE = new Set<ScopeType>([
  "state", "wing", "range", "commissionerate", "district", "platform",
]);

function toSelected(seat: SeatOut): SelectedSeat {
  return {
    username: seat.username,
    displayName: seat.display_name ?? null,
    role: normalizeRole(seat.role),
    scopeType: (seat.scope_type as ScopeType) ?? "unresolved",
    scopeLabel: seat.scope_label,
    postingLabel: seat.posting_label ?? null,
    rankLabel: seat.rank_label ?? null,
  };
}

export function SeatPicker({ onPick }: { onPick: (seat: SelectedSeat) => void }) {
  const [scope, setScope] = useState<ScopeType>("district");
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const current = useSeatStore((s) => s.seat);

  // Debounced so typing a station name does not fire a request per keystroke
  // against an 11,825-row directory.
  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 250);
    return () => clearTimeout(t);
  }, [q]);

  const browsable = BROWSABLE.has(scope);
  const enabled = browsable || debounced.length >= 2;

  const seats = useQuery({
    queryKey: ["org", "seats", scope, debounced],
    queryFn: ({ signal }) =>
      api.org.seats(
        { scope_type: scope, q: debounced || undefined, page_size: 60 },
        signal,
      ),
    enabled,
    staleTime: 60_000,
  });

  const counts = useQuery({
    queryKey: ["org", "seats", "counts"],
    queryFn: ({ signal }) => api.org.seats({ page_size: 1 }, signal),
    staleTime: 10 * 60_000,
  });

  const tierCounts = counts.data?.scope_type_counts ?? {};
  const items = seats.data?.items ?? [];

  const hint = useMemo(() => {
    if (browsable) return null;
    if (debounced.length >= 2) return null;
    const n = tierCounts[scope];
    return n
      ? `${n.toLocaleString()} seats. Type at least two characters to search by station, posting or officer name.`
      : "Type at least two characters to search.";
  }, [browsable, debounced, scope, tierCounts]);

  return (
    <div className="rounded-card border border-hairline bg-surface">
      {/* tier selector */}
      <div className="flex flex-wrap gap-1.5 border-b border-hairline p-3">
        {TIERS.map((t) => {
          const n = tierCounts[t.scope];
          const active = t.scope === scope;
          return (
            <button
              key={t.scope}
              type="button"
              onClick={() => { setScope(t.scope); setQ(""); }}
              aria-pressed={active}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-control border px-2.5 py-1.5 text-11 transition-colors",
                active
                  ? "border-primary/60 bg-primary/10 text-content"
                  : "border-hairline bg-surface-2 text-content-dim hover:border-primary/40 hover:text-content",
              )}
            >
              {t.label}
              {n != null && (
                <span className="text-10 text-content-dim">{n.toLocaleString()}</span>
              )}
            </button>
          );
        })}
      </div>

      {/* search */}
      <div className="border-b border-hairline p-3">
        <label htmlFor="seat-search" className="sr-only">
          Search seats within {SCOPE_TYPE_LABELS[scope]}
        </label>
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-content-dim" />
          <input
            id="seat-search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={
              browsable
                ? `Filter ${SCOPE_TYPE_LABELS[scope]} seats…`
                : "Search by station, posting or officer name…"
            }
            className="h-10 w-full rounded-control border border-hairline bg-surface-2 pl-8 pr-3 text-12 text-content outline-none transition-colors focus:border-primary"
          />
        </div>
        <p className="mt-1.5 text-11 text-content-dim">
          {SCOPE_TYPE_BLURBS[scope]}
          {seats.data?.total != null && enabled
            ? ` · ${seats.data.total.toLocaleString()} matching`
            : ""}
        </p>
      </div>

      {/* results */}
      <div className="max-h-[320px] overflow-y-auto p-2">
        {hint && <p className="px-2 py-6 text-center text-12 text-content-dim">{hint}</p>}

        {enabled && seats.isLoading && (
          <p className="flex items-center justify-center gap-2 px-2 py-6 text-12 text-content-dim">
            <Loader2 className="size-4 animate-spin text-primary" /> Loading seats…
          </p>
        )}

        {enabled && seats.error && (
          <p className="px-2 py-6 text-center text-12 text-severity-critical">
            Could not load the seat directory. Is the DRISHTI service running?
          </p>
        )}

        {enabled && !seats.isLoading && !seats.error && items.length === 0 && (
          <p className="px-2 py-6 text-center text-12 text-content-dim">
            No seats match. Postings look like “Jayanagar PS-1, Bengaluru City”.
          </p>
        )}

        <ul className="space-y-1">
          {items.map((seat) => {
            const isCurrent = current?.username === seat.username;
            return (
              <li key={seat.user_id}>
                <button
                  type="button"
                  onClick={() => onPick(toSelected(seat))}
                  className={cn(
                    "group flex w-full items-center gap-3 rounded-control border p-2.5 text-left transition-colors",
                    isCurrent
                      ? "border-primary/60 bg-primary/10"
                      : "border-transparent hover:border-primary/40 hover:bg-surface-2/60",
                  )}
                >
                  <span className="grid size-9 shrink-0 place-items-center rounded-control bg-primary/10 text-primary">
                    <RoleIcon
                      role={normalizeRole(seat.role)}
                      scope={seat.scope_type as ScopeType}
                      className="size-4"
                    />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-12 font-semibold text-content">
                      {seat.display_name || seat.username}
                    </span>
                    <span className="mt-0.5 flex min-w-0 items-center gap-1.5 text-11 text-content-dim">
                      <UserCog className="size-3 shrink-0" />
                      <span className="truncate">
                        {seat.rank_label ? `${seat.rank_label} · ` : ""}
                        {seat.posting_label || seat.scope_label}
                      </span>
                    </span>
                  </span>
                  {seat.is_lead_investigator && seat.scope_type === "assigned_case" && (
                    /* An IO seat that may be the officer OF RECORD, as opposed to
                       an assisting HC/PC seat. Both hold the same scope, so the
                       posting alone does not distinguish them. */
                    <span className="shrink-0 rounded-control bg-accent/15 px-1.5 py-0.5 text-10 text-accent">
                      Lead IO
                    </span>
                  )}
                  <ArrowRight className="size-3.5 shrink-0 text-content-dim opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100" />
                </button>
              </li>
            );
          })}
        </ul>
      </div>

      <p className="border-t border-hairline px-3 py-2 text-10 leading-relaxed text-content-dim">
        Choosing a seat selects a view. The server derives that seat’s jurisdiction
        from its own record and refuses anything outside it, so this cannot grant
        access to a district.
      </p>
    </div>
  );
}
