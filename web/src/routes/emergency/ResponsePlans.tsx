import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Circle, CircleDot, Loader2, Plus } from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import type { ResponsePlan, ResponseTask } from "@/api/endpoints/disaster";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { PageHeader } from "@/components/common/PageHeader";
import { districtName } from "@/stores/useDisasterStore";
import { DistrictPicker, Panel, SyntheticNote, useErCapabilities } from "@/routes/emergency/erShared";

const HAZARDS = ["flood", "urban_flood", "landslide", "drought", "heatwave", "cyclone",
                 "forest_fire", "dam_breach", "lightning"];
const NEXT_TASK: Record<string, string> = { open: "in_progress", in_progress: "done", done: "open" };

export function ResponsePlans() {
  const qc = useQueryClient();
  const { canWrite, activeDistrict } = useErCapabilities();
  const d = activeDistrict ?? undefined;

  const plans = useQuery({ queryKey: ["er", "plans", d], queryFn: ({ signal }) => api.disaster.plans({ district_id: d }, signal) });
  const events = useQuery({ queryKey: ["er", "events", d], queryFn: ({ signal }) => api.disaster.events({ district_id: d }, signal) });

  const [hazard, setHazard] = useState("flood");
  const [title, setTitle] = useState("");
  const [eventId, setEventId] = useState("");

  const create = useMutation({
    mutationFn: () => api.disaster.createPlan({
      hazard_code: hazard, title: title.trim() || `${hazard} SOP`,
      hazard_event_id: eventId ? Number(eventId) : undefined,
      district_id: activeDistrict ?? undefined }),
    onSuccess: () => { setTitle(""); qc.invalidateQueries({ queryKey: ["er", "plans"] }); },
  });
  const patch = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      api.disaster.patchTask(id, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["er", "plans"] }),
  });

  return (
    <div className="space-y-4">
      <PageHeader title="Response Plans"
        description={`Per-hazard SOP checklists, task assignment and after-action — ${districtName(activeDistrict)}`}
        actions={<DistrictPicker />} />

      {canWrite && (
        <Panel title="Create SOP plan from template">
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-12 text-content-dim">
              Hazard
              <NativeSelect className="mt-1 w-44" aria-label="Hazard" value={hazard} onChange={setHazard}
                options={HAZARDS.map((h) => ({ value: h, label: h }))} />
            </label>
            <label className="text-12 text-content-dim">
              Event (optional)
              <NativeSelect className="mt-1 w-64" aria-label="Event" value={eventId} onChange={setEventId}
                options={(events.data?.events ?? []).map((e) => ({
                  value: String(e.hazard_event_id),
                  label: `#${e.hazard_event_id} ${e.hazard_code}` }))} placeholder="No event" />
            </label>
            <label className="flex-1 text-12 text-content-dim">
              Title
              <Input className="mt-1 h-8 text-13" value={title} onChange={(e) => setTitle(e.target.value)}
                placeholder={`${hazard} SOP`} />
            </label>
            <Button size="sm" disabled={create.isPending} onClick={() => create.mutate()}>
              {create.isPending ? <Loader2 className="animate-spin" /> : <Plus />} Create plan
            </Button>
          </div>
          {create.isError && <p className="mt-2 text-12 text-severity-critical">{errorMessage(create.error)}</p>}
        </Panel>
      )}

      {plans.isLoading && <Loader2 className="size-4 animate-spin text-content-dim" />}
      <div className="grid gap-4 lg:grid-cols-2">
        {plans.data?.plans.map((p) => (
          <PlanCard key={p.response_plan_id} plan={p} canWrite={canWrite}
            onToggle={(t) => patch.mutate({ id: t.response_task_id, status: NEXT_TASK[t.status] ?? "open" })}
            busy={patch.isPending} />
        ))}
        {plans.data && plans.data.plans.length === 0 &&
          <Panel><p className="text-12 text-content-dim">No response plans yet.</p></Panel>}
      </div>

      <SyntheticNote />
    </div>
  );
}

function PlanCard({ plan, canWrite, onToggle, busy }: {
  plan: ResponsePlan; canWrite: boolean; onToggle: (t: ResponseTask) => void; busy: boolean;
}) {
  const done = plan.tasks.filter((t) => t.status === "done").length;
  return (
    <Panel
      title={<span className="flex items-center gap-2">{plan.title}
        <Badge variant="neutral">{plan.hazard_code}</Badge></span>}
      actions={<Badge variant={done === plan.tasks.length ? "low" : "medium"}>{done}/{plan.tasks.length} done</Badge>}
    >
      <ul className="space-y-1">
        {plan.tasks.map((t) => {
          const Icon = t.status === "done" ? CheckCircle2 : t.status === "in_progress" ? CircleDot : Circle;
          const tone = t.status === "done" ? "text-severity-low"
            : t.status === "overdue" ? "text-severity-critical"
            : t.status === "in_progress" ? "text-primary" : "text-content-dim";
          return (
            <li key={t.response_task_id} className="flex items-center gap-2">
              <button type="button" disabled={!canWrite || busy} onClick={() => onToggle(t)}
                      className="shrink-0 disabled:opacity-60" aria-label={`Toggle ${t.title}`}>
                <Icon className={`size-4 ${tone}`} />
              </button>
              <span className={t.status === "done" ? "text-12 text-content-dim line-through" : "text-12 text-content"}>
                {t.sequence}. {t.title}
              </span>
              {t.status === "overdue" && <Badge variant="critical">overdue</Badge>}
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}
