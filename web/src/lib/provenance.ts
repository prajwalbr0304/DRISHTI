import type { EntityKind, ObjectRef } from "@/api/types";

/* ============================================================================
   Provenance helpers. Source record ids from the AiResult contract look like
   "CaseMaster:123" / "AccusedMaster:45" / "ModelInference:9". We parse those
   into peekable ObjectRefs so an Evidence Trail record opens in the peek rail.
   ========================================================================== */

const TABLE_KIND: Record<string, EntityKind> = {
  case: "case",
  casemaster: "case",
  crime: "case",
  crimemaster: "case",
  fir: "case",
  aisummary: "case",
  accused: "person",
  accusedmaster: "person",
  person: "person",
  entity: "person",
  entitygraph: "person",
  victim: "person",
  complainant: "person",
  officer: "person",
  vehicle: "vehicle",
  vehiclemaster: "vehicle",
  phone: "phone",
  imei: "phone",
  mobile: "phone",
  account: "account",
  bankaccount: "account",
  transaction: "account",
  district: "location",
  location: "location",
  place: "location",
  ward: "location",
  station: "location",
  hotspot: "location",
  modelversion: "model",
  modelinference: "model",
  model: "model",
  crimeriskscore: "model",
  crimeprediction: "model",
  alerthistory: "alert",
  alert: "alert",
};

export interface ParsedRecord {
  raw: string;
  table: string;
  id: string;
  /** Peekable reference, when the table maps to a known object kind. */
  ref?: ObjectRef;
}

/** Split a "Table:Id" provenance token; produce a peek ref when we recognise it. */
export function parseSourceRecord(raw: string): ParsedRecord {
  const idx = raw.indexOf(":");
  if (idx === -1) return { raw, table: raw, id: "" };
  const table = raw.slice(0, idx);
  const id = raw.slice(idx + 1);
  const kind = TABLE_KIND[table.toLowerCase().replace(/[_\s]/g, "")];
  const numeric = /^\d+$/.test(id);
  const ref: ObjectRef | undefined =
    kind && numeric
      ? { kind, id: Number(id), label: `${prettyTable(table)} ${id}`, sublabel: prettyTable(table) }
      : undefined;
  return { raw, table, id, ref };
}

export function parseSourceRecords(raws: string[]): ParsedRecord[] {
  return raws.map(parseSourceRecord);
}

function prettyTable(t: string): string {
  // CaseMaster -> "Case", AccusedMaster -> "Accused", split camelCase
  return t
    .replace(/master$/i, "")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .trim();
}
