import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "@/App";
import { QueryProvider } from "@/providers/QueryProvider";
import { RoleProvider } from "@/providers/RoleProvider";
import { ThemeProvider } from "@/providers/ThemeProvider";
import "@/index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryProvider>
      <RoleProvider>
        <ThemeProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </ThemeProvider>
      </RoleProvider>
    </QueryProvider>
  </StrictMode>,
);
