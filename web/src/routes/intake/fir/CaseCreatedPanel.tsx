import { useNavigate } from "react-router-dom";
import { CheckCircle2, Clock, FileText, Paperclip, Users } from "lucide-react";
import { Button } from "@/components/ui/button";

/** Shown once a draft is approved into a case (DoD §E: after case creation offer
    Continue to Evidence / People / Timeline / Case file). */
export function CaseCreatedPanel({ caseId, crimeNo }: { caseId: number; crimeNo: string | null }) {
  const navigate = useNavigate();
  const go = (tab: string) => navigate(`/cases/${caseId}?tab=${tab}`);
  return (
    <div className="rounded-card border border-severity-low/40 bg-severity-low/5 p-4">
      <div className="flex items-center gap-2">
        <CheckCircle2 className="size-5 text-severity-low" />
        <div>
          <h3 className="text-14 font-semibold text-content">Case created</h3>
          <p className="text-12 text-content-dim">
            {crimeNo ? <>Crime No <span className="tnum">{crimeNo}</span></> : `Case #${caseId}`} is now on record.
          </p>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button size="sm" variant="outline" onClick={() => go("evidence")}><Paperclip /> Evidence</Button>
        <Button size="sm" variant="outline" onClick={() => go("accused")}><Users /> People</Button>
        <Button size="sm" variant="outline" onClick={() => go("timeline")}><Clock /> Timeline</Button>
        <Button size="sm" onClick={() => go("overview")}><FileText /> Open case file</Button>
      </div>
    </div>
  );
}
