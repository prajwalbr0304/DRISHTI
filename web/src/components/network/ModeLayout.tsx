import type { ReactNode } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";

/* Shared Network Analysis layout: left contextual rail + full canvas area. */
export function ModeLayout({
  panelTitle,
  panel,
  children,
}: {
  panelTitle?: ReactNode;
  panel: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex h-[calc(100vh-13.5rem)] min-h-[420px] gap-4">
      <aside className="flex w-80 shrink-0 flex-col overflow-hidden rounded-card border border-hairline bg-surface">
        {panelTitle && (
          <div className="shrink-0 border-b border-hairline px-3 py-2 text-13 font-semibold text-content">
            {panelTitle}
          </div>
        )}
        <ScrollArea className="min-h-0 flex-1">
          <div className="p-3">{panel}</div>
        </ScrollArea>
      </aside>
      <div className="relative flex min-w-0 flex-1 flex-col overflow-hidden rounded-card border border-hairline bg-surface-2/20">
        {children}
      </div>
    </div>
  );
}

/* Small legend strip shown over the canvas. */
export function CanvasLegend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <div className="pointer-events-none absolute bottom-3 left-3 z-10 flex flex-wrap gap-x-3 gap-y-1 rounded-control border border-hairline bg-surface/90 px-2.5 py-1.5 text-12 text-content-dim backdrop-blur">
      {items.map((it) => (
        <span key={it.label} className="inline-flex items-center gap-1.5">
          <span className="size-2.5 rounded-full" style={{ background: it.color }} />
          {it.label}
        </span>
      ))}
    </div>
  );
}
