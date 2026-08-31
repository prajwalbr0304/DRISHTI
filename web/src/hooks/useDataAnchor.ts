import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api";
import { useTimeStore } from "@/stores/useTimeStore";

/* ============================================================================
   Anchor the global time window to the latest data date.

   The operational dataset is historical, so the wall clock can sit months past
   the last record — anchoring "now" to the machine clock would put every preset
   window after the data ends and every widget would read "No data".

   This MUST be mounted somewhere that renders on every route (AppShell). It used
   to live inside TimeScrubber and worked only because the top bar was always on
   screen; once the scrubber moved into the Command Center header that became a
   latent bug, so it is hoisted here deliberately.
   ========================================================================== */

export function useDataAnchor() {
  const setAnchor = useTimeStore((s) => s.setAnchor);
  const { data } = useQuery({
    queryKey: ["geo", "coverage"],
    queryFn: ({ signal }) => api.geo.coverage(signal),
    staleTime: Infinity,
    retry: false,
  });
  useEffect(() => {
    if (data?.max_date) setAnchor(data.max_date);
  }, [data?.max_date, setAnchor]);
}
