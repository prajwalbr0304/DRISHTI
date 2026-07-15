import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError } from "@/api/contracts";

/* ============================================================================
   react-query setup. Tuned for an operations tool hitting live services:
   - one retry, and never retry 4xx (a 404/409 is a real, final answer)
   - no refetch-on-focus thrash; explicit, visible staleness instead
   ========================================================================== */

export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60_000,
            gcTime: 5 * 60_000,
            refetchOnWindowFocus: false,
            retry: (failureCount, error) => {
              if (error instanceof ApiError && error.status >= 400 && error.status < 500)
                return false;
              return failureCount < 1;
            },
          },
        },
      }),
  );

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
