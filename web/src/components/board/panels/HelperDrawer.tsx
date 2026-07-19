import { useState } from "react";
import { ChevronDown, ChevronUp, Clock, History as HistoryIcon, Table2 } from "lucide-react";
import type { BoardActivityT, BoardDetail } from "@/api/endpoints/board";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn, timeAgo } from "@/lib/utils";

type Tab = "table" | "history" | "stats";

export function HelperDrawer({
  detail,
  activity,
  open,
  onToggle,
}: {
  detail: BoardDetail;
  activity: BoardActivityT[];
  open: boolean;
  onToggle: () => void;
}) {
  const [tab, setTab] = useState<Tab>("table");
  const evidence = detail.edges.filter((e) => e.edge_class === "evidence");
  const hypotheses = detail.edges.filter((e) => e.edge_class === "hypothesis");

  return (
    <div className="border-t border-hairline bg-surface">
      <div className="flex items-center gap-1 px-2 py-1">
        <TabBtn active={tab === "table" && open} onClick={() => { setTab("table"); if (!open) onToggle(); }}>
          <Table2 className="size-3.5" /> Table
        </TabBtn>
        <TabBtn active={tab === "history" && open} onClick={() => { setTab("history"); if (!open) onToggle(); }}>
          <HistoryIcon className="size-3.5" /> History
        </TabBtn>
        <TabBtn active={tab === "stats" && open} onClick={() => { setTab("stats"); if (!open) onToggle(); }}>
          <Clock className="size-3.5" /> Statistics
        </TabBtn>
        <Button variant="ghost" size="icon-sm" className="ml-auto" onClick={onToggle}
                aria-label={open ? "Collapse helper drawer" : "Expand helper drawer"}>
          {open ? <ChevronDown className="size-4" /> : <ChevronUp className="size-4" />}
        </Button>
      </div>

      {open && (
        <div className="h-52 overflow-auto border-t border-hairline px-3 py-2 text-12">
          {tab === "table" && (
            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="mb-1 font-medium text-content-dim">Nodes ({detail.nodes.length})</div>
                <table className="w-full">
                  <tbody>
                    {detail.nodes.map((n) => (
                      <tr key={n.board_node_id} className="border-b border-hairline/50">
                        <td className="py-0.5 pr-2 text-content-dim">{n.node_kind}</td>
                        <td className="truncate py-0.5">{n.label}</td>
                        <td className="py-0.5 text-right text-content-dim">{n.ref_table ? `${n.ref_table}:${n.ref_id}` : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div>
                <div className="mb-1 font-medium text-content-dim">Edges ({detail.edges.length})</div>
                <table className="w-full">
                  <tbody>
                    {detail.edges.map((e) => (
                      <tr key={e.board_edge_id} className="border-b border-hairline/50">
                        <td className="py-0.5 pr-2">
                          <Badge variant={e.edge_class === "evidence" ? "primary" : "medium"}>{e.edge_class}</Badge>
                        </td>
                        <td className="truncate py-0.5">{e.relationship_type || e.label || "—"}</td>
                        <td className="truncate py-0.5 text-right text-content-dim">{e.rationale || e.source_record_id || ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {tab === "history" && (
            <ul className="space-y-1">
              {[...activity].reverse().map((a) => (
                <li key={a.board_activity_id} className="flex items-center gap-2 border-b border-hairline/50 py-1">
                  <span className="tnum w-8 text-content-dim">#{a.board_activity_id}</span>
                  <span className="font-medium text-content">{a.actor}</span>
                  <Badge variant="neutral">{a.action}</Badge>
                  <span className="text-content-dim">{a.target_type} {a.target_id}</span>
                  <span className="ml-auto text-content-dim">{a.created_at ? timeAgo(a.created_at) : ""}</span>
                </li>
              ))}
              {activity.length === 0 && <li className="text-content-dim">No activity yet.</li>}
            </ul>
          )}

          {tab === "stats" && (
            <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
              <Stat label="Nodes" value={detail.nodes.length} />
              <Stat label="Evidence edges" value={evidence.length} />
              <Stat label="Hypotheses" value={hypotheses.length} />
              <Stat label="Annotations" value={detail.annotations.length} />
              <Stat label="Collaborators" value={detail.collaborators.length} />
              <Stat label="Version" value={detail.board.version} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function TabBtn({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-control px-2.5 py-1 text-12 font-medium transition-colors",
        active ? "bg-surface-2 text-content" : "text-content-dim hover:text-content",
      )}
    >
      {children}
    </button>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-control border border-hairline bg-surface-2/40 p-2 text-center">
      <div className="tnum text-18 font-semibold text-content">{value}</div>
      <div className="text-11 text-content-dim">{label}</div>
    </div>
  );
}
