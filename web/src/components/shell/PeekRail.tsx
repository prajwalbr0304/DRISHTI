import { ChevronLeft, X } from "lucide-react";
import type { EntityKind } from "@/api/types";
import { cn } from "@/lib/utils";
import { usePeekStore } from "@/stores/usePeekStore";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { SimpleTooltip } from "@/components/ui/tooltip";
import { PeekContent } from "@/components/peek/PeekContent";
import { SendToBoard, peekKindToTarget } from "@/components/board/SendToBoard";

/* ============================================================================
   The PEEK RAIL — opens any object reference beside the workspace without
   navigating away. Supports peek-within-peek via a reference stack shown as a
   back-trail in the header.
   ========================================================================== */

const KIND_LABEL: Record<EntityKind, string> = {
  person: "Person",
  case: "Case",
  vehicle: "Vehicle",
  phone: "Phone",
  account: "Account",
  location: "Location",
  organisation: "Organisation",
  association: "Association",
  model: "Model",
  alert: "Alert",
};

export function PeekRail() {
  const { stack, isOpen } = usePeekStore();
  const pop = usePeekStore((s) => s.pop);
  const popTo = usePeekStore((s) => s.popTo);
  const close = usePeekStore((s) => s.close);

  if (!isOpen || stack.length === 0) return null;
  const top = stack[stack.length - 1];
  const depth = stack.length;

  return (
    <aside className="flex h-full w-peek shrink-0 animate-slide-in-right flex-col border-l border-hairline bg-surface shadow-peek">
      {/* Header */}
      <div className="flex h-topbar shrink-0 items-center gap-2 border-b border-hairline px-3">
        {depth > 1 && (
          <SimpleTooltip label="Back">
            <Button variant="ghost" size="icon-sm" onClick={pop} aria-label="Back">
              <ChevronLeft />
            </Button>
          </SimpleTooltip>
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <Badge variant="neutral" className="shrink-0">
              {KIND_LABEL[top.kind]}
            </Badge>
            <span className="truncate text-14 font-semibold text-content">{top.label}</span>
          </div>
          {top.sublabel && <div className="truncate text-12 text-content-dim">{top.sublabel}</div>}
        </div>
        {/* Send to Board — the universal object affordance (cases, people,
            vehicles, phones, accounts, locations, organisations). */}
        {(() => {
          const target = peekKindToTarget(top.kind, top.id, top.label);
          return target ? <SendToBoard target={target} size="icon-sm" variant="ghost" /> : null;
        })()}
        <SimpleTooltip label="Close peek">
          <Button variant="ghost" size="icon-sm" onClick={close} aria-label="Close peek">
            <X />
          </Button>
        </SimpleTooltip>
      </div>

      {/* Peek-within-peek trail */}
      {depth > 1 && (
        <div className="flex items-center gap-1 overflow-x-auto border-b border-hairline px-3 py-1.5 no-scrollbar">
          {stack.map((e, i) => {
            const last = i === stack.length - 1;
            return (
              <div key={e._key} className="flex shrink-0 items-center gap-1">
                {i > 0 && <span className="text-content-dim/60">/</span>}
                <button
                  type="button"
                  onClick={() => popTo(i)}
                  className={cn(
                    "max-w-[9rem] truncate rounded px-1 py-0.5 text-12 transition-colors",
                    last ? "font-medium text-content" : "text-content-dim hover:text-content",
                  )}
                >
                  {e.label}
                </button>
              </div>
            );
          })}
        </div>
      )}

      {/* Body — resolves the top reference to real data */}
      <ScrollArea className="min-h-0 flex-1">
        <div className="p-4">
          {/* key by stack entry so state/queries reset per reference */}
          <PeekContent key={top._key} entry={top} />
        </div>
      </ScrollArea>
    </aside>
  );
}
