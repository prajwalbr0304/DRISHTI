import * as React from "react";
import {
  AlertTriangle,
  ChevronDown,
  GripVertical,
  Maximize2,
  MoreVertical,
  RefreshCw,
} from "lucide-react";
import type { AiResult } from "@/api/contracts";
import { errorMessage } from "@/api/contracts";
import { cn, confidenceBand, formatPercent } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { SimpleTooltip } from "@/components/ui/tooltip";
import { Skeleton } from "@/components/ui/skeleton";
import { EvidenceTrail } from "@/components/widget/EvidenceTrail";

/* ============================================================================
   The universal widget frame (doc 01 §8.5), laid out like an AWS console board
   item so the two read identically:

     ⣿ drag grip · title (heading-l, bold) · Info link · context chip … ⋮ menu

   The six-dot grip on the left is the ONLY drag surface (matching Cloudscape's
   board item). Every secondary action — refresh, expand, widget-specific items —
   lives behind the single vertical-ellipsis menu on the right, so the header
   never grows a row of icons. The ⌄ provenance strip expands an Evidence Trail
   bound to the AiResult contract. Standard live-data states (loading / error /
   empty) are built in.
   ========================================================================== */

export interface WidgetMenuItem {
  label: string;
  icon?: React.ReactNode;
  onSelect: () => void;
  danger?: boolean;
}

export interface WidgetProps {
  title: React.ReactNode;
  /** small chip after the title, e.g. scope "Bengaluru City · 30d" */
  contextChip?: React.ReactNode;
  /** ⓘ content explaining what this widget shows / how to read it */
  info?: React.ReactNode;
  /** ⋯ overflow menu items */
  menuItems?: WidgetMenuItem[];
  /** provenance for the strip + Evidence Trail (an endpoint envelope's `result`) */
  provenance?: AiResult | null;
  /** extra header controls (rendered before ⓘ) */
  actions?: React.ReactNode;
  onRefresh?: () => void;
  loading?: boolean;
  error?: unknown;
  /** show the empty state instead of children */
  empty?: boolean;
  emptyLabel?: string;
  className?: string;
  bodyClassName?: string;
  /** remove body padding (for edge-to-edge maps / tables) */
  flush?: boolean;
  /** rendered as a tile in a DashboardGrid: fills the cell height, shows the
   *  six-dot drag grip in the header, and the body scrolls if content exceeds
   *  the cell. */
  gridTile?: boolean;
  children?: React.ReactNode;
}

export function Widget({
  title,
  contextChip,
  info,
  menuItems,
  provenance,
  actions,
  onRefresh,
  loading,
  error,
  empty,
  emptyLabel = "No data for the current scope.",
  className,
  bodyClassName,
  flush,
  gridTile,
  children,
}: WidgetProps) {
  const [trailOpen, setTrailOpen] = React.useState(false);
  const [maximized, setMaximized] = React.useState(false);

  const body = (
    <WidgetBody loading={loading} error={error} empty={empty} emptyLabel={emptyLabel} onRefresh={onRefresh}>
      {children}
    </WidgetBody>
  );

  return (
    <section
      className={cn(
        "flex min-w-0 flex-col rounded-card border border-hairline bg-surface shadow-card",
        gridTile && "h-full overflow-hidden",
        className,
      )}
    >
      {/* Header — grip · title · Info · chip … ⋮ (Cloudscape container header:
          20px content gutter, 56px tall, no divider rule) */}
      <header className={cn("flex min-h-14 items-center gap-2 py-3 pr-2", gridTile ? "pl-2" : "pl-5")}>
        {gridTile && (
          <span
            className="dash-drag grid size-8 shrink-0 select-none place-items-center rounded-control text-content-dim transition-colors hover:bg-surface-2 hover:text-content"
            title="Drag to move"
            aria-hidden
          >
            <GripVertical className="size-4" />
          </span>
        )}

        <div className="flex min-w-0 items-center gap-2">
          <h2 className="truncate text-heading-l font-bold text-content">{title}</h2>

          {/* Info — an AWS-style text link, not an icon button */}
          <Popover>
            <PopoverTrigger asChild>
              <button
                type="button"
                className="no-drag shrink-0 rounded text-body-s font-normal text-primary underline-offset-2 hover:underline"
              >
                Info
              </button>
            </PopoverTrigger>
            <PopoverContent align="start" className="text-body-m text-content">
              {info ?? (
                <p className="text-content-dim">
                  Live data from the DRISHTI services. Expand the provenance strip to see the
                  evidence behind these figures.
                </p>
              )}
            </PopoverContent>
          </Popover>

          {contextChip != null && (
            <Badge variant="neutral" className="shrink-0">
              {contextChip}
            </Badge>
          )}
        </div>

        <div className="no-drag ml-auto flex shrink-0 items-center gap-1">
          {actions}

          {/* ⋮ the single overflow menu */}
          <DropdownMenu>
            <SimpleTooltip label="Widget options">
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon-sm" className="size-8" aria-label="Widget options">
                  <MoreVertical />
                </Button>
              </DropdownMenuTrigger>
            </SimpleTooltip>
            <DropdownMenuContent align="end">
              {onRefresh && (
                <DropdownMenuItem onSelect={onRefresh}>
                  <RefreshCw className={cn(loading && "animate-spin")} /> Refresh
                </DropdownMenuItem>
              )}
              <DropdownMenuItem onSelect={() => setMaximized(true)}>
                <Maximize2 /> Expand
              </DropdownMenuItem>
              {menuItems?.length ? <DropdownMenuSeparator /> : null}
              {menuItems?.map((m) => (
                <DropdownMenuItem
                  key={m.label}
                  onSelect={m.onSelect}
                  className={m.danger ? "text-severity-critical focus:text-severity-critical" : undefined}
                >
                  {m.icon}
                  {m.label}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>

      {/* Body — 20px Cloudscape content gutter */}
      <div className={cn("min-h-0 flex-1", gridTile && "overflow-auto", !flush && "px-5 pb-5", bodyClassName)}>
        {body}
      </div>

      {/* Provenance strip */}
      {provenance && (
        <ProvenanceStrip
          result={provenance}
          open={trailOpen}
          onToggle={() => setTrailOpen((v) => !v)}
        />
      )}

      {/* ⤢ maximized view */}
      <Dialog open={maximized} onOpenChange={setMaximized}>
        <DialogContent className="max-w-5xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-heading-l font-bold">
              {title}
              {contextChip != null && <Badge variant="neutral">{contextChip}</Badge>}
            </DialogTitle>
          </DialogHeader>
          <div className="max-h-[70vh] overflow-auto">{body}</div>
          {provenance && (
            <div className="rounded-card border border-hairline bg-surface-2/50 p-3">
              <EvidenceTrail result={provenance} />
            </div>
          )}
        </DialogContent>
      </Dialog>
    </section>
  );
}

/* ------------------------------- Body states ------------------------------ */
function WidgetBody({
  loading,
  error,
  empty,
  emptyLabel,
  onRefresh,
  children,
}: {
  loading?: boolean;
  error?: unknown;
  empty?: boolean;
  emptyLabel: string;
  onRefresh?: () => void;
  children?: React.ReactNode;
}) {
  if (loading) {
    return (
      <div className="space-y-2 py-1">
        <Skeleton className="h-4 w-2/3" />
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 py-8 text-center">
        <AlertTriangle className="size-5 text-severity-high" />
        <p className="text-heading-xs font-bold text-content">Couldn't load this widget</p>
        <p className="max-w-sm text-body-s text-content-dim">{errorMessage(error)}</p>
        {onRefresh && (
          <Button variant="outline" size="sm" onClick={onRefresh} className="mt-1">
            <RefreshCw /> Retry
          </Button>
        )}
      </div>
    );
  }
  if (empty) {
    return (
      <div className="flex items-center justify-center py-8 text-center text-body-m text-content-dim">
        {emptyLabel}
      </div>
    );
  }
  return <>{children}</>;
}

/* ---------------------------- Provenance strip ---------------------------- */
function ProvenanceStrip({
  result,
  open,
  onToggle,
}: {
  result: AiResult;
  open: boolean;
  onToggle: () => void;
}) {
  const band = confidenceBand(result.confidence);
  const count = result.source_record_ids?.length ?? 0;
  return (
    <div className="border-t border-hairline">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-5 py-2 text-body-s text-content-dim transition-colors hover:bg-surface-2/50"
      >
        <span
          className={cn("size-1.5 rounded-full", band === "low" ? "bg-content-dim" : "bg-primary")}
          aria-hidden
        />
        <span className="tnum font-medium text-content">{formatPercent(result.confidence, 0)}</span>
        <span>confidence</span>
        <span className="text-hairline">·</span>
        <span className="tnum">{count} sources</span>
        <code className="ml-auto hidden truncate rounded-badge bg-surface-2 px-1.5 py-0.5 font-mono text-body-s text-content-dim sm:inline">
          {result.model_version}
        </code>
        <ChevronDown className={cn("size-3.5 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="border-t border-hairline bg-surface-2/30 px-5 py-4">
          <EvidenceTrail result={result} />
        </div>
      )}
    </div>
  );
}
