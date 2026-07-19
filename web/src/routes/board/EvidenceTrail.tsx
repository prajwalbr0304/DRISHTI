import { Download, FileJson } from "lucide-react";
import type { BoardDetail, ExportOut } from "@/api/endpoints/board";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { kindStyle } from "@/components/board/boardEncoding";

/**
 * Evidence Trail: every source record pinned to the board with its provenance,
 * plus the export preview. Evidence edges carry their source record; hypothesis
 * edges carry their rationale + author. Nothing here exposes raw evidence bytes.
 */
export function EvidenceTrail({
  detail,
  onExport,
  exportResult,
}: {
  detail: BoardDetail;
  onExport: () => void;
  exportResult: ExportOut | null;
}) {
  const sourced = detail.nodes.filter((n) => n.ref_table);
  const evidence = detail.edges.filter((e) => e.edge_class === "evidence");
  const hypotheses = detail.edges.filter((e) => e.edge_class === "hypothesis");

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-15 font-semibold text-content">Evidence Trail</h2>
          <p className="text-12 text-content-dim">Source inventory + provenance for board "{detail.board.title}" (v{detail.board.version}).</p>
        </div>
        <Button size="sm" onClick={onExport}><Download /> Export attributable snapshot</Button>
      </div>

      {exportResult && (
        <div className="flex items-center gap-3 rounded-control border border-primary/30 bg-primary/5 px-3 py-2 text-12">
          <FileJson className="size-4 text-primary" />
          <span>Export {exportResult.format.toUpperCase()} · hash {exportResult.sha256.slice(0, 16)}… · {exportResult.watermark}</span>
          <a href={exportResult.download_url} target="_blank" rel="noreferrer" className="ml-auto text-primary hover:underline">Download</a>
        </div>
      )}

      <Section title={`Pinned source objects (${sourced.length})`}>
        <table className="w-full text-12">
          <thead className="text-content-dim">
            <tr className="border-b border-hairline text-left">
              <th className="py-1">Kind</th><th className="py-1">Label</th><th className="py-1">Source</th><th className="py-1">Version</th><th className="py-1">Hash</th>
            </tr>
          </thead>
          <tbody>
            {sourced.map((n) => (
              <tr key={n.board_node_id} className="border-b border-hairline/50">
                <td className="py-1"><span className="inline-flex items-center gap-1.5"><span className="size-2 rounded-full" style={{ background: kindStyle(n.node_kind).color }} />{n.node_kind}</span></td>
                <td className="py-1">{n.label}</td>
                <td className="py-1 text-content-dim">{n.ref_table}:{n.ref_id}</td>
                <td className="py-1 tnum">{n.source_version ?? "—"}</td>
                <td className="py-1 font-mono text-11 text-content-dim">{n.source_hash ? `${n.source_hash.slice(0, 12)}…` : "—"}</td>
              </tr>
            ))}
            {sourced.length === 0 && <tr><td colSpan={5} className="py-3 text-center text-content-dim">No source-backed objects pinned yet.</td></tr>}
          </tbody>
        </table>
      </Section>

      <Section title={`Evidence links (${evidence.length}) — verified, read-only`}>
        <ul className="space-y-1 text-12">
          {evidence.map((e) => (
            <li key={e.board_edge_id} className="flex items-center gap-2 border-b border-hairline/50 py-1">
              <Badge variant="primary">evidence</Badge>
              <span>{e.relationship_type || "related"}</span>
              <span className="ml-auto font-mono text-11 text-content-dim">{e.source_record_id}</span>
            </li>
          ))}
          {evidence.length === 0 && <li className="text-content-dim">None imported.</li>}
        </ul>
      </Section>

      <Section title={`Hypothesis links (${hypotheses.length}) — reasoning + author`}>
        <ul className="space-y-1 text-12">
          {hypotheses.map((e) => (
            <li key={e.board_edge_id} className="border-b border-hairline/50 py-1">
              <div className="flex items-center gap-2">
                <Badge variant="medium">hypothesis</Badge>
                <span>{e.relationship_type || "link"}</span>
                {e.promoted_status === "proposed" && <Badge variant="high">proposed for review</Badge>}
                <span className="ml-auto text-content-dim">{e.created_by}</span>
              </div>
              {e.rationale && <p className="mt-0.5 pl-1 text-content-dim">“{e.rationale}”</p>}
            </li>
          ))}
          {hypotheses.length === 0 && <li className="text-content-dim">No hypotheses drawn yet.</li>}
        </ul>
      </Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="mb-2 text-12 font-semibold uppercase tracking-wide text-content-dim">{title}</h3>
      {children}
    </section>
  );
}
