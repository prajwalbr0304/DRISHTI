import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { AlertTriangle, Loader2 } from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import { useRole } from "@/providers/RoleProvider";
import { EmptyState } from "@/components/common/EmptyState";
import { emptyPayload } from "@/routes/intake/useDraftEditor";

/** Creates a fresh draft then redirects to the wizard at its stable key. */
export function NewFir() {
  const navigate = useNavigate();
  const { role } = useRole();
  const [params] = useSearchParams();
  const kind = params.get("kind") || "fir_standard";
  const started = useRef(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    (async () => {
      try {
        const draft = await api.intake.createDraft({
          case_kind: kind,
          payload: emptyPayload(),
          parties: [],
          created_by_actor: role,
        });
        navigate(`/intake/fir/${draft.draft_key}`, { replace: true });
      } catch (e) {
        setError(errorMessage(e));
      }
    })();
  }, [kind, role, navigate]);

  if (error) {
    return (
      <EmptyState icon={AlertTriangle} title="Couldn't start a new FIR" description={error} />
    );
  }
  return (
    <div className="flex min-h-[300px] items-center justify-center text-13 text-content-dim">
      <Loader2 className="mr-2 size-4 animate-spin" /> Starting a new FIR draft…
    </div>
  );
}
