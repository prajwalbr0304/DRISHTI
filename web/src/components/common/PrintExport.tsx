import { Printer } from "lucide-react";
import { cn } from "@/lib/utils";
import { useRole } from "@/providers/RoleProvider";
import { Button } from "@/components/ui/button";

/* ============================================================================
   "Export view → PDF" (doc 01 §4.7, Phase 5) for chart/analytics views. The
   button triggers the browser's print-to-PDF (print CSS isolates <main> and
   forces a light palette). It is hidden from the printed output; a print-only
   header (PrintHeader) carries the title, timestamp and the k-anonymity /
   role-scope note so any export is honest about what it shows.
   ========================================================================== */

export function ExportViewButton({ className }: { className?: string }) {
  return (
    <Button
      variant="outline"
      size="sm"
      onClick={() => window.print()}
      className={cn("print:hidden", className)}
    >
      <Printer /> Export view
    </Button>
  );
}

/** Print-only running header for a chart/analytics export (hidden on screen). */
export function PrintHeader({ title }: { title: string }) {
  const { def, role } = useRole();
  return (
    <div className="mb-4 hidden border-b border-hairline pb-2 print:block">
      <div className="text-16 font-semibold text-content">{title}</div>
      <div className="text-12 text-content-dim">
        DRISHTI · Karnataka State Police — CONFIDENTIAL · {def.label} ({role}) · {def.scope}
      </div>
      <div className="text-12 text-content-dim">
        Generated {new Date().toLocaleString()} · role-scoped view; aggregate figures are
        k-anonymity–suppressed at source.
      </div>
    </div>
  );
}
