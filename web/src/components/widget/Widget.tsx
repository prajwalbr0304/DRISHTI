import * as React from "react";
import {
  AlertTriangle,
  ChevronDown,
  Info,
  Maximize2,
  MoreHorizontal,
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
   The universal widget frame (doc 01 §8.5):
     title · context chip · ⓘ · ⋯ · ⤢ · provenance strip
   The ⌄ provenance strip expands an Evidence Trail bound to the AiResult
   contract. Standard live-data states (loading / error / empty) are built in.
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
  /** rendered as a tile in a DashboardGrid: fills the cell height, the header is
   *  the drag handle, and the body scrolls if content exceeds the cell. */
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
      {/* Header */}
      <header
        className={cn(
          "flex items-center gap-2 px-4 py-2.5",
          gridTile && "dash-drag cursor-move select-none",
        )}
      >
        <div className="flex min-w-0 items-center gap-2">
          <h3 className="truncate text-14 font-semibold text-content">{title}</h3>
          {contextChip != null && (
            <Badge variant="neutral" className="shrink-0">
              {contextChip}
            </Badge>
          )}
        </div>

        <div className={cn("ml-auto flex shrink-0 items-center gap-0.5", gridTile && "no-drag cursor-default")}>
          {actions}
          {onRefresh && (
            <SimpleTooltip label="Refresh">
              <Button variant="ghost" size="icon-sm" onClick={onRefresh} aria-label="Refresh">
                <RefreshCw className={cn(loading && "animate-spin")} />
              </Button>
            </SimpleTooltip>
          )}

          {/* ⓘ info */}
          <Popover>
            <SimpleTooltip label="About this widget">
              <PopoverTrigger asChild>
                <Button variant="ghost" size="icon-sm" aria-label="About this widget">
                  <Info />
                </Button>
              </PopoverTrigger>
            </SimpleTooltip>
            <PopoverContent align="end" className="text-13 text-content">
              {info ?? (
                <p className="text-content-dim">
                  Live data from the DRISHTI services. Expand the provenance strip to see the
                  evidence behind these figures.
                </p>
              )}
            </PopoverContent>
          </Popover>

          {/* ⋯ overflow */}
          <DropdownMenu>
            <SimpleTooltip label="More">
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon-sm" aria-label="More actions">
                  <MoreHorizontal />
                </Button>
              </DropdownMenuTrigger>
            </SimpleTooltip>
            <DropdownMenuContent align="end">
              {onRefresh && (
                <DropdownMenuItem onSelect={onRefresh}>
                  <RefreshCw /> Refresh
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

          {/* ⤢ maximize */}
          <SimpleTooltip label="Expand">
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => setMaximized(true)}
              aria-label="Expand widget"
            >
              <Maximize2 />
            </Button>
          </SimpleTooltip>
        </div>
      </header>

      {/* Body */}
      <div className={cn("min-h-0 flex-1", gridTile && "overflow-auto", !flush && "px-4 pb-3", bodyClassName)}>
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
            <DialogTitle className="flex items-center gap-2">
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
        <p className="text-13 font-medium text-content">Couldn't load this widget</p>
        <p className="max-w-sm text-12 text-content-dim">{errorMessage(error)}</p>
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
      <div className="flex items-center justify-center py-8 text-center text-13 text-content-dim">
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
        className="flex w-full items-center gap-2 px-4 py-1.5 text-12 text-content-dim transition-colors hover:bg-surface-2/50"
      >
        <span
          className={cn("size-1.5 rounded-full", band === "low" ? "bg-content-dim" : "bg-primary")}
          aria-hidden
        />
        <span className="tnum font-medium text-content">{formatPercent(result.confidence, 0)}</span>
        <span>confidence</span>
        <span className="text-hairline">·</span>
        <span className="tnum">{count} sources</span>
        <code className="ml-auto hidden truncate rounded bg-surface-2 px-1.5 py-0.5 text-12 text-content-dim sm:inline">
          {result.model_version}
        </code>
        <ChevronDown className={cn("size-3.5 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="border-t border-hairline bg-surface-2/30 px-4 py-3">
          <EvidenceTrail result={result} />
        </div>
      )}
    </div>
  );
}
