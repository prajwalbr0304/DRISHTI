import { useQuery } from "@tanstack/react-query";
import { api } from "@/api";
import type { SelectOption } from "@/components/ui/native-select";
import type { IntakeOptionItem } from "@/api/types";

/* Shared react-query hooks + option helpers for the intake wizard. All data is
   live from the FastAPI intake endpoints (browser -> API only). */

export function useIntakeStatus() {
  return useQuery({
    queryKey: ["intake", "status"],
    queryFn: ({ signal }) => api.intake.status(signal),
    staleTime: 60_000,
  });
}

export function useIntakeWorkflow() {
  return useQuery({
    queryKey: ["intake", "workflow"],
    queryFn: ({ signal }) => api.intake.workflow(signal),
    staleTime: 10 * 60_000,
  });
}

export function useIntakeLookups(unitId?: number) {
  return useQuery({
    queryKey: ["intake", "lookups", unitId ?? null],
    queryFn: ({ signal }) => api.intake.lookups(unitId, signal),
    staleTime: 10 * 60_000,
  });
}

/** {id,name}[] -> NativeSelect options. */
export function toOptions(items?: IntakeOptionItem[] | null): SelectOption[] {
  return (items ?? []).map((i) => ({ value: String(i.id), label: i.name ?? `#${i.id}` }));
}

/** Filter sub-heads to a chosen head. */
export function subHeadOptions(items: IntakeOptionItem[] | undefined, headId?: number | null): SelectOption[] {
  if (!headId) return toOptions(items);
  return toOptions((items ?? []).filter((i) => i.parent_id === headId));
}
