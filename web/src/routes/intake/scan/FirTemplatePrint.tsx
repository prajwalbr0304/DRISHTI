import { AlertTriangle, Info, Printer } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/EmptyState";
import { PageHeader } from "@/components/common/PageHeader";
import { errorMessage } from "@/api/contracts";
import { useScanTemplate } from "@/routes/intake/scan/scanQueries";
import type { IntakeScanTemplateLine } from "@/api/types";

/* ============================================================================
   The printable FIR intake form.

   Every line comes from GET /intake/scan/template, which the server generates
   from the same field table its parser reads. So a field can never appear on the
   printed page that the parser does not know how to read back.

   Why character cells matter: Zia recognises handwriting only when it is close to
   a standard character shape. One character per box gets far closer to that than
   joined writing, which is why dates, times and numbers are boxed and only the
   narrative is a free ruled area.
   ========================================================================== */

const CELLS: Record<string, number> = {
  date: 8,       // DDMMYYYY
  time: 4,       // HHMM
  datetime: 12,  // DDMMYYYYHHMM
  phone: 10,
  int: 3,
};

function Boxes({ count }: { count: number }) {
  return (
    <span className="inline-flex gap-[2px] align-middle print:gap-[1px]">
      {Array.from({ length: count }).map((_, i) => (
        <span
          key={i}
          className="inline-block h-[22px] w-[18px] border border-content/40 print:h-[20px] print:w-[16px]"
        />
      ))}
    </span>
  );
}

function TemplateRow({ line }: { line: IntakeScanTemplateLine }) {
  const cellCount = CELLS[line.kind] ?? 0;
  return (
    <tr className="align-top">
      <td className="w-8 py-2 pr-1 text-12 text-content-dim print:py-1.5">{line.index}.</td>
      <td className="w-[15rem] py-2 pr-2 print:py-1.5">
        <div className="text-12 font-medium text-content">{line.label_en}</div>
        {line.label_kn && (
          <div lang="kn" className="text-12 text-content-dim">
            {line.label_kn}
          </div>
        )}
        {line.format_hint && (
          <div className="text-11 text-content-dim">{line.format_hint}</div>
        )}
      </td>
      <td className="py-2 print:py-1.5">
        <span className="mr-1.5 text-content-dim">:</span>
        {line.boxed && cellCount ? (
          <Boxes count={cellCount} />
        ) : line.multiline ? (
          <span className="block space-y-3.5 pt-1">
            <span className="block border-b border-content/30" />
            <span className="block border-b border-content/30" />
            <span className="block border-b border-content/30" />
          </span>
        ) : (
          <span className="inline-block h-[22px] w-full border-b border-content/30 align-middle" />
        )}
      </td>
    </tr>
  );
}

export function FirTemplatePrint() {
  const q = useScanTemplate();

  if (q.isLoading) {
    return (
      <div className="space-y-4">
        <PageHeader title="Printable FIR form" description="The form officers write on." />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (q.error || !q.data) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title="Couldn't load the form"
        description={q.error ? errorMessage(q.error) : "The template is unavailable."}
      />
    );
  }

  const t = q.data;

  return (
    <div className="space-y-4">
      <div className="print:hidden">
        <PageHeader
          title="Printable FIR form"
          description="Print this, write on it, then photograph it to fill the FIR automatically."
          actions={
            <Button size="sm" onClick={() => window.print()}>
              <Printer /> Print
            </Button>
          }
        />
        <div className="mb-4 flex items-start gap-2 rounded-card border border-primary/30 bg-primary/5 p-3 text-13">
          <Info className="mt-0.5 size-4 shrink-0 text-primary" />
          <div>
            <p className="text-content">{t.notice_en}</p>
            <p className="mt-1 text-12 text-content-dim">
              Form {t.template_code}. Writing on this exact layout is what makes the
              reading reliable — a free-form page will read far worse.
            </p>
          </div>
        </div>
      </div>

      {/* The printable sheet itself. */}
      <div className="rounded-card border border-hairline bg-surface p-6 shadow-card print:border-0 print:p-0 print:shadow-none">
        <header className="mb-4 border-b border-content/30 pb-3">
          <h2 className="text-heading-m font-bold text-content">
            First Information Report — intake form
          </h2>
          <p lang="kn" className="text-13 text-content-dim">
            ಪ್ರಥಮ ವರ್ತಮಾನ ವರದಿ — ನಮೂನೆ
          </p>
          <p className="mt-1 text-11 text-content-dim">
            Synthetic demonstration form · {t.template_code}
          </p>
        </header>

        <table className="w-full border-collapse">
          <tbody>
            {t.lines.map((line) => (
              <TemplateRow key={line.field} line={line} />
            ))}
          </tbody>
        </table>

        <section className="mt-5 border-t border-content/30 pt-3">
          <h3 className="mb-1.5 text-12 font-semibold text-content">
            How to fill this in
          </h3>
          <ol className="ml-4 list-decimal space-y-0.5 text-11 text-content-dim">
            {t.guidance_en.map((g, i) => (
              <li key={i}>{g}</li>
            ))}
          </ol>
          {t.guidance_kn.length > 0 && (
            <ol lang="kn" className="ml-4 mt-2 list-decimal space-y-0.5 text-11 text-content-dim">
              {t.guidance_kn.map((g, i) => (
                <li key={i}>{g}</li>
              ))}
            </ol>
          )}
        </section>

        <footer className="mt-5 grid grid-cols-2 gap-6 border-t border-content/30 pt-4 text-11 text-content-dim">
          <div>
            <div className="mb-6">Signature of complainant</div>
            <div className="border-b border-content/30" />
          </div>
          <div>
            <div className="mb-6">Signature of registering officer</div>
            <div className="border-b border-content/30" />
          </div>
        </footer>
      </div>
    </div>
  );
}
