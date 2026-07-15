import { useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/api";
import { useAskStore } from "@/stores/useAskStore";

/* Load a past chat session's full (real, grounded) turns into the current
   thread. Cached via react-query so re-opening is instant. */
export function useLoadSession() {
  const qc = useQueryClient();
  const loadSession = useAskStore((s) => s.loadSession);
  const [loadingId, setLoadingId] = useState<number | null>(null);

  const open = useCallback(
    async (sessionId: number) => {
      setLoadingId(sessionId);
      try {
        const detail = await qc.fetchQuery({
          queryKey: ["chat", "session", sessionId],
          queryFn: ({ signal }) => api.chat.session(sessionId, signal),
        });
        loadSession(detail);
      } finally {
        setLoadingId(null);
      }
    },
    [qc, loadSession],
  );

  return { open, loadingId };
}
