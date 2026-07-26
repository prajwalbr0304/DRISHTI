import { RotateCcw } from "lucide-react";
import type { CaseListParams } from "@/api/endpoints/cases";
import type { FilterOptionsResponse } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect, type SelectOption } from "@/components/ui/native-select";

export type CaseFilters = Omit<CaseListParams, "page" | "page_size">;

function opts(items?: { id: number; name?: string | null }[]): SelectOption[] {
  return (items ?? []).map((o) => ({ value: String(o.id), label: o.name ?? String(o.id) }));
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="block text-12 font-medium text-content-dim">{label}</label>
      {children}
    </div>
  );
}

/* Left filter rail for the Case Explorer (doc 01 §4.2). Filters compose into a
   view; all option lists are real reference lookups. */
export function CaseFilterRail({
  filters,
  options,
  onChange,
  onClear,
  activeCount,
}: {
  filters: CaseFilters;
  options?: FilterOptionsResponse;
  onChange: (patch: Partial<CaseFilters>) => void;
  onClear: () => void;
  activeCount: number;
}) {
  const num = (v: string) => (v ? Number(v) : undefined);
  return (
    <aside className="w-full shrink-0 space-y-3 min-[1680px]:w-56">
      <div className="flex items-center justify-between">
        <span className="text-13 font-semibold text-content">Filters</span>
        {activeCount > 0 && (
          <Button variant="ghost" size="sm" onClick={onClear} className="h-6 gap-1 px-1.5 text-12">
            <RotateCcw className="size-3" /> Clear ({activeCount})
          </Button>
        )}
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 min-[1680px]:grid-cols-1">
        <Field label="District">
          <NativeSelect
            aria-label="District"
            value={filters.district_id?.toString() ?? ""}
            onChange={(v) => onChange({ district_id: num(v) })}
            options={opts(options?.districts)}
          />
        </Field>
        <Field label="Station">
          <NativeSelect
            aria-label="Station"
            value={filters.station_id?.toString() ?? ""}
            onChange={(v) => onChange({ station_id: num(v) })}
            options={opts(options?.stations)}
          />
        </Field>
        <Field label="Crime head">
          <NativeSelect
            aria-label="Crime head"
            value={filters.major_head_id?.toString() ?? ""}
            onChange={(v) => onChange({ major_head_id: num(v) })}
            options={opts(options?.crime_heads)}
          />
        </Field>
        <Field label="Sub-head">
          <NativeSelect
            aria-label="Sub-head"
            value={filters.minor_head_id?.toString() ?? ""}
            onChange={(v) => onChange({ minor_head_id: num(v) })}
            options={opts(options?.sub_heads)}
          />
        </Field>
        <Field label="Status">
          <NativeSelect
            aria-label="Status"
            value={filters.status_id?.toString() ?? ""}
            onChange={(v) => onChange({ status_id: num(v) })}
            options={opts(options?.statuses)}
          />
        </Field>
        <Field label="Gravity">
          <NativeSelect
            aria-label="Gravity"
            value={filters.gravity_id?.toString() ?? ""}
            onChange={(v) => onChange({ gravity_id: num(v) })}
            options={opts(options?.gravities)}
          />
        </Field>
        <Field label="From">
          <Input
            type="date"
            value={filters.date_from ?? ""}
            onChange={(e) => onChange({ date_from: e.target.value || undefined })}
            className="h-8 text-12"
          />
        </Field>
        <Field label="To">
          <Input
            type="date"
            value={filters.date_to ?? ""}
            onChange={(e) => onChange({ date_to: e.target.value || undefined })}
            className="h-8 text-12"
          />
        </Field>
        <div className="flex flex-wrap content-end gap-x-4 gap-y-2 pb-1 min-[1680px]:space-y-1.5 min-[1680px]:pt-1">
          <Check
            label="Has arrest"
            checked={!!filters.has_arrest}
            onChange={(v) => onChange({ has_arrest: v || undefined })}
          />
          <Check
            label="Has chargesheet"
            checked={!!filters.has_chargesheet}
            onChange={(v) => onChange({ has_chargesheet: v || undefined })}
          />
        </div>
      </div>
    </aside>
  );
}

function Check({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-13 text-content">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="size-3.5 accent-[var(--primary)]"
      />
      {label}
    </label>
  );
}
