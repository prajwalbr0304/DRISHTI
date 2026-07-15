import { useState } from "react";
import { useLocation } from "react-router-dom";
import { Compass, ExternalLink } from "lucide-react";
import type { EntityKind } from "@/api/types";
import { destinationByPath } from "@/config/destinations";
import { usePeekStore } from "@/stores/usePeekStore";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/common/PageHeader";
import { EmptyState } from "@/components/common/EmptyState";

/* ============================================================================
   Generic destination placeholder. The destinations arrive in later Wave-C
   phases; for now each shows its purpose and — where it helps — a quick way to
   open a real record in the peek rail (exercising live data + peek).
   ========================================================================== */

const QUICK_OPEN: Record<string, { kind: EntityKind; noun: string }> = {
  cases: { kind: "case", noun: "case" },
  network: { kind: "person", noun: "entity" },
  money: { kind: "account", noun: "account" },
};

export function Placeholder() {
  const { pathname } = useLocation();
  const dest = destinationByPath(pathname);
  const push = usePeekStore((s) => s.push);
  const [value, setValue] = useState("");

  const Icon = dest?.icon ?? Compass;
  const quick = dest ? QUICK_OPEN[dest.id] : undefined;

  function open() {
    const id = Number(value.trim());
    if (!Number.isFinite(id) || id <= 0 || !quick) return;
    push({
      kind: quick.kind,
      id,
      label: `${quick.noun[0].toUpperCase()}${quick.noun.slice(1)} ${id}`,
      sublabel: quick.noun,
    });
  }

  return (
    <div>
      <PageHeader title={dest?.label ?? "Destination"} description={dest?.description} />
      <EmptyState
        icon={Icon}
        title="Being built in a later Wave-C phase"
        description={
          quick
            ? `The full ${dest?.label} workspace is on the way. In the meantime, open a ${quick.noun} in the peek rail to see live records.`
            : `The full ${dest?.label} workspace is on the way. The shell, navigation and data layer are ready for it.`
        }
        action={
          quick && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                open();
              }}
              className="flex items-center gap-2"
            >
              <Input
                value={value}
                onChange={(e) => setValue(e.target.value)}
                inputMode="numeric"
                placeholder={`${quick.noun} id`}
                className="w-40"
              />
              <Button type="submit" variant="secondary" disabled={!value.trim()}>
                Open in peek
                <ExternalLink />
              </Button>
            </form>
          )
        }
      />
    </div>
  );
}
