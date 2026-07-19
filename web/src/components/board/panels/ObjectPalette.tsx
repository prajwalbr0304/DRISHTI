import { useState } from "react";
import { Frame, Plus, Search, StickyNote, Type, Waypoints } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { NODE_KIND_LEGEND } from "@/components/board/boardEncoding";
import { cn } from "@/lib/utils";

interface Props {
  filters: { evidence: boolean; hypothesis: boolean; search: string };
  setFilters: (f: { evidence: boolean; hypothesis: boolean; search: string }) => void;
  refTables: string[];
  readOnly: boolean;
  hasSelectedNode: boolean;
  onAddNote: () => void;
  onAddFrame: () => void;
  onAddObject: (refTable: string, refId: string) => void;
  onSearchAround: () => void;
}

export function ObjectPalette(props: Props) {
  const { filters, setFilters, refTables, readOnly } = props;
  const [refTable, setRefTable] = useState("");
  const [refId, setRefId] = useState("");

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-3 text-13">
      <section>
        <SectionTitle>Filter</SectionTitle>
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-content-dim" />
          <Input
            value={filters.search}
            onChange={(e) => setFilters({ ...filters, search: e.target.value })}
            placeholder="Filter objects…"
            className="h-8 pl-8 text-13"
          />
        </div>
        <div className="mt-2 flex gap-1">
          <Toggle active={filters.evidence} onClick={() => setFilters({ ...filters, evidence: !filters.evidence })}>
            <span className="mr-1 inline-block h-0.5 w-4 bg-primary align-middle" /> Evidence
          </Toggle>
          <Toggle active={filters.hypothesis} onClick={() => setFilters({ ...filters, hypothesis: !filters.hypothesis })}>
            <span className="mr-1 inline-block h-0.5 w-4 border-t-2 border-dashed border-content-dim align-middle" /> Hypothesis
          </Toggle>
        </div>
        <p className="mt-1 text-11 text-content-dim">Filters hide objects without deleting them.</p>
      </section>

      {!readOnly && (
        <section>
          <SectionTitle>Pin an object</SectionTitle>
          <NativeSelect
            value={refTable}
            onChange={setRefTable}
            options={refTables.map((t) => ({ value: t, label: t }))}
            placeholder="Object type…"
            aria-label="Object type"
          />
          <div className="mt-2 flex gap-1.5">
            <Input value={refId} onChange={(e) => setRefId(e.target.value)} placeholder="id" className="h-8 text-13" />
            <Button
              size="sm"
              disabled={!refTable || !refId.trim()}
              onClick={() => {
                props.onAddObject(refTable, refId.trim());
                setRefId("");
              }}
            >
              <Plus /> Pin
            </Button>
          </div>
          <p className="mt-1 text-11 text-content-dim">
            Pins a live reference (never a copy). The server hydrates its label + snapshot.
          </p>
        </section>
      )}

      {!readOnly && (
        <section>
          <SectionTitle>Add</SectionTitle>
          <div className="grid grid-cols-2 gap-1.5">
            <Button variant="outline" size="sm" onClick={props.onAddNote}><StickyNote /> Sticky</Button>
            <Button variant="outline" size="sm" onClick={props.onAddFrame}><Frame /> Frame</Button>
            <Button variant="outline" size="sm" onClick={props.onAddNote}><Type /> Text</Button>
            <Button variant="outline" size="sm" disabled={!props.hasSelectedNode} onClick={props.onSearchAround}
                    title={props.hasSelectedNode ? "Expand verified neighbours" : "Select a graph-backed node first"}>
              <Waypoints /> Search around
            </Button>
          </div>
        </section>
      )}

      <section>
        <SectionTitle>Legend</SectionTitle>
        <ul className="space-y-1">
          {NODE_KIND_LEGEND.map((l) => (
            <li key={l.kind} className="flex items-center gap-2 text-12 text-content-dim">
              <span className="size-2.5 rounded-full" style={{ background: l.color }} />
              {l.label}
            </li>
          ))}
        </ul>
        <div className="mt-2 space-y-1 text-11 text-content-dim">
          <div className="flex items-center gap-2"><span className="inline-block h-0.5 w-6 bg-primary" /> evidence (verified)</div>
          <div className="flex items-center gap-2"><span className="inline-block h-0 w-6 border-t-2 border-dashed border-content-dim" /> hypothesis (yours)</div>
        </div>
      </section>
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <div className="mb-1.5 text-11 font-semibold uppercase tracking-wide text-content-dim">{children}</div>;
}

function Toggle({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "flex-1 rounded-control border px-2 py-1 text-12 transition-colors",
        active ? "border-primary/50 bg-primary/10 text-content" : "border-hairline text-content-dim hover:text-content",
      )}
    >
      {children}
    </button>
  );
}
