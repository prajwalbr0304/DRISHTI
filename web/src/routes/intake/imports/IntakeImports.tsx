import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, FileUp, Loader2, Lock, PlayCircle, UploadCloud } from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import { useRole } from "@/providers/RoleProvider";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/common/PageHeader";
import { EmptyState } from "@/components/common/EmptyState";
import { SectionCard } from "@/routes/intake/components";
import { emptyPayload } from "@/routes/intake/useDraftEditor";
import { IMPORT_COLUMNS, parseCsv, parseJson } from "@/routes/intake/imports/parse";
import type { IntakeCreateDraftRequest } from "@/api/types";

type Row = Record<string, unknown>;
type RowCheck = { row: Row; errors: string[] };

const KINDS = new Set(["fir_standard", "zero_fir", "udr", "ncr", "par", "missing_person"]);

export function checkRow(r: Row): string[] {
  const e: string[] = [];
  const kind = String(r.case_kind ?? "fir_standard");
  if (!KINDS.has(kind)) e.push(`invalid case_kind '${kind}'`);
  if (!r.registration_date) e.push("registration_date required");
  if (!r.station_id) e.push("station_id required");
  if (!r.registering_officer_id) e.push("registering_officer_id required");
  if (!r.major_head_id) e.push("major_head_id required");
  if (!r.brief_facts) e.push("brief_facts required");
  if (!r.complainant_name) e.push("complainant_name required (reporter)");
  return e;
}

export function toRequest(r: Row): IntakeCreateDraftRequest {
  const p = emptyPayload();
  p.registration.registration_date = r.registration_date ? String(r.registration_date) : null;
  p.registration.station_id = r.station_id ? Number(r.station_id) : null;
  p.registration.registering_officer_id = r.registering_officer_id ? Number(r.registering_officer_id) : null;
  p.classification.major_head_id = r.major_head_id ? Number(r.major_head_id) : null;
  p.incident.latitude = r.latitude ? Number(r.latitude) : null;
  p.incident.longitude = r.longitude ? Number(r.longitude) : null;
  p.narrative.brief_facts = r.brief_facts ? String(r.brief_facts) : null;
  p.source.source_system_code = "CSV_IMPORT";
  p.source.external_source_id = r.external_source_id ? String(r.external_source_id) : null;
  return {
    case_kind: String(r.case_kind ?? "fir_standard"),
    payload: p,
    parties: [{ role_type: "complainant", party_nature: "person", is_unknown: false,
      display_name: String(r.complainant_name ?? "Unknown"), attributes: {} }],
  };
}

export function IntakeImports() {
  const { role } = useRole();
  const navigate = useNavigate();
  const [rows, setRows] = useState<Row[]>([]);
  const [fileName, setFileName] = useState<string>("");
  const [parseErr, setParseErr] = useState<string | null>(null);
  const [committing, setCommitting] = useState(false);
  const [result, setResult] = useState<{ created: number; failed: number; keys: string[] } | null>(null);

  const checks: RowCheck[] = useMemo(() => rows.map((r) => ({ row: r, errors: checkRow(r) })), [rows]);
  const validCount = checks.filter((c) => c.errors.length === 0).length;

  if (role === "policymaker") {
    return (
      <div><PageHeader title="Bulk import" />
        <EmptyState icon={Lock} title="Not available for this role"
          description="Case intake is not accessible to the policymaker role." /></div>
    );
  }

  const onFile = async (file: File) => {
    setParseErr(null); setResult(null);
    try {
      const text = await file.text();
      const parsed = file.name.endsWith(".json") ? parseJson(text) : parseCsv(text);
      setRows(parsed as Row[]); setFileName(file.name);
    } catch (e) { setParseErr(errorMessage(e)); setRows([]); }
  };

  const commit = async () => {
    setCommitting(true);
    const keys: string[] = []; let failed = 0;
    for (const c of checks) {
      if (c.errors.length) { failed++; continue; }
      try { const d = await api.intake.createDraft(toRequest(c.row)); keys.push(d.draft_key); }
      catch { failed++; }
    }
    setResult({ created: keys.length, failed, keys });
    setCommitting(false);
  };

  return (
    <div>
      <PageHeader title="Bulk import"
        description="Structured CSV/JSON case import with a dry-run preview. Imported rows become drafts in the review inbox."
        actions={<Button size="sm" variant="outline" onClick={() => navigate("/intake")}>Back to inbox</Button>} />

      <div className="space-y-4">
        <SectionCard title="Upload" description={`Expected columns: ${IMPORT_COLUMNS.join(", ")}`}>
          <label className="flex cursor-pointer items-center gap-2 rounded-control border border-dashed border-hairline bg-surface-2 px-4 py-6 text-13 text-content-dim hover:bg-surface-2/70">
            <UploadCloud className="size-5" />
            <span>{fileName || "Choose a .csv or .json file"}</span>
            <input type="file" accept=".csv,.json" className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) void onFile(f); }} />
          </label>
          {parseErr && <p className="mt-2 flex items-center gap-1 text-12 text-severity-high"><AlertTriangle className="size-3" />{parseErr}</p>}
        </SectionCard>

        {rows.length > 0 && (
          <SectionCard title={`Dry run — ${rows.length} rows (${validCount} valid, ${rows.length - validCount} with errors)`}>
            <div className="max-h-80 overflow-auto rounded-control border border-hairline">
              <table className="w-full text-12">
                <thead className="sticky top-0 bg-surface-2 text-content-dim">
                  <tr><th className="px-2 py-1.5 text-left">#</th><th className="px-2 py-1.5 text-left">Kind</th>
                    <th className="px-2 py-1.5 text-left">Brief facts</th><th className="px-2 py-1.5 text-left">Validation</th></tr>
                </thead>
                <tbody className="divide-y divide-hairline">
                  {checks.map((c, i) => (
                    <tr key={i}>
                      <td className="px-2 py-1.5 tnum text-content-dim">{i + 1}</td>
                      <td className="px-2 py-1.5 text-content-dim">{String(c.row.case_kind ?? "fir_standard")}</td>
                      <td className="px-2 py-1.5 max-w-[18rem] truncate text-content">{String(c.row.brief_facts ?? "—")}</td>
                      <td className="px-2 py-1.5">
                        {c.errors.length === 0 ? <Badge variant="low">valid</Badge>
                          : <span className="text-severity-high">{c.errors.join("; ")}</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-3 flex items-center gap-2">
              <Button size="sm" onClick={commit} disabled={committing || validCount === 0}>
                {committing ? <Loader2 className="animate-spin" /> : <PlayCircle />} Create {validCount} draft(s)
              </Button>
              {result && (
                <span className="text-12 text-content-dim">
                  Created {result.created}, failed {result.failed}.{" "}
                  {result.created > 0 && <button className="text-primary hover:underline" onClick={() => navigate("/intake")}>View in inbox</button>}
                </span>
              )}
            </div>
          </SectionCard>
        )}

        {rows.length === 0 && !parseErr && (
          <EmptyState icon={FileUp} title="No file loaded" description="Upload a CSV or JSON file to preview and import rows." />
        )}
      </div>
    </div>
  );
}
