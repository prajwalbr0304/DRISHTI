import { AlertTriangle, CheckCircle2, Eye, PencilLine } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { cn } from "@/lib/utils";
import { SectionCard } from "@/routes/intake/components";
import {
  confidenceBand, fieldLabel, formatPercent,
} from "@/routes/intake/scan/scanQueries";
import type { IntakeScanField, IntakeScanUnresolved } from "@/api/types";

/* ============================================================================
   The correction surface for a scanned FIR.

   Two things this deliberately makes impossible to miss:
     1. which values a machine read (and how confident the parser was), and
     2. which values the server refused to guess.

   Low-confidence rows are visually separated rather than mixed in, because the
   whole safety argument for OCR prefill rests on the officer actually checking
   them. A field the server could not resolve shows candidate choices, never a
   silently-picked "best" match.
   ========================================================================== */

export type FieldEdit = { path: string; value: string };

function BandBadge({ confidence, threshold }: { confidence: number; threshold: number }) {
  const band = confidenceBand(confidence, threshold);
  const variant = band === "high" ? "low" : band === "medium" ? "medium" : "high";
  const label = band === "high" ? "Clear" : band === "medium" ? "Check" : "Unclear";
  return (
    <Badge variant={variant} className="tnum">
      {label} · {formatPercent(confidence)}
    </Badge>
  );
}

function displayValue(value: unknown): string {
  if (value == null) return "";
  if (Array.isArray(value)) {
    return value
      .map((v) =>
        v && typeof v === "object"
          ? [
              (v as { act_code?: string }).act_code,
              (v as { section_code?: string }).section_code,
            ]
              .filter(Boolean)
              .join(" ")
          : String(v),
      )
      .filter(Boolean)
      .join(", ");
  }
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/** A field row: what OCR read, what it became, and an editable accepted value. */
function FieldRow({
  field, threshold, edited, onEdit, readOnly,
}: {
  field: IntakeScanField;
  threshold: number;
  edited?: string;
  onEdit: (path: string, value: string) => void;
  readOnly?: boolean;
}) {
  const current = edited ?? displayValue(field.value);
  const isEdited = edited !== undefined && edited !== displayValue(field.value);
  // Complex values (section lists) are corrected in the wizard, not inline —
  // showing a JSON blob in a text box invites worse data than it fixes.
  const editableInline = !Array.isArray(field.value) && typeof field.value !== "object";

  return (
    <div
      className={cn(
        "grid gap-2 border-t border-hairline py-2.5 sm:grid-cols-[minmax(0,11rem)_minmax(0,1fr)_auto]",
        field.requires_review && "bg-severity-medium/5",
      )}
    >
      <div className="min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-13 font-medium text-content">{fieldLabel(field.field)}</span>
          {isEdited && (
            <span title="You changed this value">
              <PencilLine className="size-3 text-primary" aria-label="Edited" />
            </span>
          )}
        </div>
        {field.raw_text && (
          <p className="mt-0.5 truncate text-12 text-content-dim" title={field.raw_text}>
            read: “{field.raw_text}”
          </p>
        )}
      </div>

      <div className="min-w-0">
        {editableInline && !readOnly ? (
          <Input
            value={current}
            onChange={(e) => onEdit(field.field, e.target.value)}
            className="h-8"
            aria-label={`${fieldLabel(field.field)} value`}
            placeholder={field.value == null ? "Not read — type it in" : undefined}
          />
        ) : (
          <span className="block truncate py-1.5 text-13 text-content">
            {current || <span className="text-content-dim">Not read</span>}
          </span>
        )}
        {field.note && (
          <p className="mt-0.5 flex items-start gap-1 text-12 text-severity-medium">
            <AlertTriangle className="mt-0.5 size-3 shrink-0" />
            {field.note}
          </p>
        )}
      </div>

      <div className="flex items-start justify-end pt-1">
        <BandBadge confidence={field.confidence} threshold={threshold} />
      </div>
    </div>
  );
}

/** A reference value the server refused to resolve — the officer picks. */
function UnresolvedRow({
  item, chosen, onChoose,
}: {
  item: IntakeScanUnresolved;
  chosen?: string;
  onChoose: (path: string, value: string) => void;
}) {
  const options = (item.candidates ?? [])
    .filter((c) => c.id != null)
    .map((c) => ({ value: String(c.id), label: c.name ?? `#${c.id}` }));

  return (
    <div className="grid gap-2 border-t border-hairline py-2.5 sm:grid-cols-[minmax(0,11rem)_minmax(0,1fr)]">
      <div className="min-w-0">
        <span className="text-13 font-medium text-content">{fieldLabel(item.field)}</span>
        {item.raw_text && (
          <p className="mt-0.5 truncate text-12 text-content-dim" title={item.raw_text}>
            read: “{item.raw_text}”
          </p>
        )}
      </div>
      <div className="min-w-0">
        {options.length ? (
          <NativeSelect
            value={chosen ?? ""}
            onChange={(v) => onChoose(item.field, v)}
            options={options}
            placeholder="Choose the correct one"
            aria-label={`${fieldLabel(item.field)} choice`}
          />
        ) : (
          <p className="py-1.5 text-13 text-content-dim">
            No close match — set this in the form after continuing.
          </p>
        )}
        <p className="mt-0.5 text-12 text-severity-medium">{item.reason}</p>
      </div>
    </div>
  );
}

export function ScanFieldTable({
  fields, unresolved, threshold, edits, onEdit, readOnly,
}: {
  fields: IntakeScanField[];
  unresolved: IntakeScanUnresolved[];
  threshold: number;
  edits: Record<string, string>;
  onEdit: (path: string, value: string) => void;
  readOnly?: boolean;
}) {
  const needsAttention = fields.filter((f) => f.requires_review);
  const clear = fields.filter((f) => !f.requires_review);

  return (
    <div className="space-y-4">
      {unresolved.length > 0 && (
        <SectionCard
          title={`${unresolved.length} value${unresolved.length > 1 ? "s" : ""} need your decision`}
          description="These were read from the page but matched no single record, so nothing was filled in. Picking the wrong station or section would mis-file the case, so the choice is yours."
        >
          <div className="-mt-2">
            {unresolved.map((u) => (
              <UnresolvedRow
                key={u.field}
                item={u}
                chosen={edits[u.field]}
                onChoose={onEdit}
              />
            ))}
          </div>
        </SectionCard>
      )}

      {needsAttention.length > 0 && (
        <SectionCard
          title={`${needsAttention.length} field${needsAttention.length > 1 ? "s" : ""} to check`}
          description="Read with low confidence. Compare each against the page before you continue."
        >
          <div className="-mt-2">
            {needsAttention.map((f) => (
              <FieldRow
                key={f.field}
                field={f}
                threshold={threshold}
                edited={edits[f.field]}
                onEdit={onEdit}
                readOnly={readOnly}
              />
            ))}
          </div>
        </SectionCard>
      )}

      {clear.length > 0 && (
        <SectionCard
          title={`${clear.length} field${clear.length > 1 ? "s" : ""} read clearly`}
          description="Still worth a glance — you are accountable for the FIR, not the recogniser."
        >
          <div className="-mt-2">
            {clear.map((f) => (
              <FieldRow
                key={f.field}
                field={f}
                threshold={threshold}
                edited={edits[f.field]}
                onEdit={onEdit}
                readOnly={readOnly}
              />
            ))}
          </div>
        </SectionCard>
      )}

      {!fields.length && !unresolved.length && (
        <div className="flex items-center gap-2 rounded-card border border-hairline bg-surface-2 p-4 text-13 text-content-dim">
          <Eye className="size-4" />
          Nothing was recognised on this page. Enter the FIR manually.
        </div>
      )}
    </div>
  );
}

/** Small summary strip used above the table. */
export function ScanSummary({
  language, ocrConfidence, templateMatched, needingReview, total, lowConfidence,
}: {
  language?: string | null;
  ocrConfidence?: number | null;
  templateMatched: boolean;
  needingReview: number;
  total: number;
  lowConfidence: boolean;
}) {
  const langLabel = language === "kn" ? "Kannada" : language === "mixed" ? "Kannada + English" : "English";
  return (
    <div className="flex flex-wrap items-center gap-2 text-12">
      <Badge variant="neutral">{langLabel}</Badge>
      <Badge variant={lowConfidence ? "high" : "low"} className="tnum">
        Recogniser {formatPercent(ocrConfidence)}
      </Badge>
      <Badge variant={templateMatched ? "low" : "medium"}>
        {templateMatched ? "DRISHTI form recognised" : "Form layout not recognised"}
      </Badge>
      {needingReview > 0 ? (
        <Badge variant="medium" className="tnum">
          <AlertTriangle className="size-3" /> {needingReview} of {total} need checking
        </Badge>
      ) : (
        <Badge variant="low" className="tnum">
          <CheckCircle2 className="size-3" /> {total} field{total === 1 ? "" : "s"} read
        </Badge>
      )}
    </div>
  );
}
