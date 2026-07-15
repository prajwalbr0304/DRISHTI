import { Navigate, Route, Routes } from "react-router-dom";
import { useRole } from "@/providers/RoleProvider";
import { AppShell } from "@/components/shell/AppShell";
import { CommandCenter } from "@/routes/CommandCenter";
import { CaseExplorer } from "@/routes/cases/CaseExplorer";
import { CaseFile } from "@/routes/cases/CaseFile";
import { EntityExplorer } from "@/routes/entities/EntityExplorer";
import { EntityProfile } from "@/routes/entities/EntityProfile";
import { NetworkAnalysis } from "@/routes/network/NetworkAnalysis";
import { MapHotspots } from "@/routes/map/MapHotspots";
import { Analytics } from "@/routes/analytics/Analytics";
import { AskDrishti } from "@/routes/ask/AskDrishti";
import { Placeholder } from "@/routes/Placeholder";
import { NotFound } from "@/routes/NotFound";

/** Guards the Admin destination — only super_admin may enter, even by URL. */
function AdminOnly({ children }: { children: React.ReactNode }) {
  const { isAdmin } = useRole();
  return isAdmin ? <>{children}</> : <Navigate to="/" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<CommandCenter />} />
        <Route path="/cases" element={<CaseExplorer />} />
        <Route path="/cases/:caseId" element={<CaseFile />} />
        <Route path="/people" element={<EntityExplorer />} />
        <Route path="/people/:entityId" element={<EntityProfile />} />
        <Route path="/network" element={<NetworkAnalysis />} />
        <Route path="/map" element={<MapHotspots />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/ask" element={<AskDrishti />} />
        {/* Folded into other destinations per doc 01 §4 — keep old links alive */}
        <Route path="/money" element={<Navigate to="/network?mode=money" replace />} />
        <Route path="/forecast" element={<Navigate to="/analytics" replace />} />
        <Route
          path="/admin"
          element={
            <AdminOnly>
              <Placeholder />
            </AdminOnly>
          }
        />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
