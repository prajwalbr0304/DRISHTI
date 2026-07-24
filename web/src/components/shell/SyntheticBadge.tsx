import { useQuery } from "@tanstack/react-query";
import { FlaskConical } from "lucide-react";
import { api } from "@/api";
import { runtime } from "@/config/runtime";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

/* Persistent "Synthetic Hackathon Demo" badge (Global Contract §18). Prefers the
   server's intake status (the live hackathon posture) and falls back to the
   build-time VITE_DEMO_BADGE label when the server hasn't answered yet. */
export function SyntheticBadge() {
  const q = useQuery({
    queryKey: ["intake", "status"],
    queryFn: ({ signal }) => api.intake.status(signal),
    staleTime: 5 * 60_000,
    retry: false,
  });
  const label = q.data?.environment_label ?? runtime.demoBadge;
  return (
    <TooltipProvider delayDuration={200}>
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full border border-severity-medium/40 bg-severity-medium/10 px-2 py-0.5 text-11 font-medium text-severity-medium">
          <FlaskConical className="size-3 shrink-0" />
          <span className="hidden sm:inline">{label}</span>
          <span className="hidden text-content-dim xl:inline">· Not for Operational Use</span>
        </span>
      </TooltipTrigger>
      <TooltipContent>
        {label} — Not for Operational Use. Synthetic data only; all reads/writes go
        through the DRISHTI API (the browser never touches the database directly).
      </TooltipContent>
    </Tooltip>
    </TooltipProvider>
  );
}
