import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "@/App";
import { AuthProvider } from "@/auth";
import { QueryProvider } from "@/providers/QueryProvider";
import { RoleProvider } from "@/providers/RoleProvider";
import { ThemeProvider } from "@/providers/ThemeProvider";
import "@/index.css";

// AuthProvider sits above RoleProvider so the active role is derived from the
// authenticated Catalyst identity. It provides context app-wide but does not
// gate — <RequireAuth> (in App) guards the app routes while "/" stays public.
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryProvider>
      <AuthProvider>
        <RoleProvider>
          <ThemeProvider>
            <BrowserRouter>
              <App />
            </BrowserRouter>
          </ThemeProvider>
        </RoleProvider>
      </AuthProvider>
    </QueryProvider>
  </StrictMode>,
);
