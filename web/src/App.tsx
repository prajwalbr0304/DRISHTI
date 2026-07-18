import { Navigate, Route, Routes } from "react-router-dom";
import { useRole } from "@/providers/RoleProvider";
import { RequireAuth } from "@/auth";
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
import { IntakeInbox } from "@/routes/intake/IntakeInbox";
import { NewFir } from "@/routes/intake/fir/NewFir";
import { FirWizard } from "@/routes/intake/fir/FirWizard";
import { IntakeImports } from "@/routes/intake/imports/IntakeImports";
import { ImportsWorkspace } from "@/routes/imports/ImportsWorkspace";
import { QualityReview } from "@/routes/review/quality/QualityReview";
import { EntityResolution } from "@/routes/review/entities/EntityResolution";
import { JurisdictionReview } from "@/routes/review/jurisdiction/JurisdictionReview";
import { CanonicalProfile } from "@/routes/entities/CanonicalProfile";
import { GovernanceRegistry } from "@/routes/governance/GovernanceRegistry";
import { NotFound } from "@/routes/NotFound";
import { LandingPage } from "@/routes/landing/LandingPage";

/** Guards the Admin destination — only super_admin may enter, even by URL. */
function AdminOnly({ children }: { children: React.ReactNode }) {
  const { isAdmin } = useRole();
  return isAdmin ? <>{children}</> : <Navigate to="/command" replace />;
}

export default function App() {
  return (
    <Routes>
      {/* Public marketing page. */}
      <Route path="/" element={<LandingPage />} />
      {/* Legacy /app/* path from the Catalyst embedded-auth SDK redirect (it
          targets the deprecated Web Client path). Slate serves from "/", so send
          these back to root instead of 404ing. */}
      <Route path="/app" element={<Navigate to="/" replace />} />
      <Route path="/app/*" element={<Navigate to="/" replace />} />
      {/* Everything below requires a Catalyst session. */}
      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
        <Route path="/command" element={<CommandCenter />} />
        <Route path="/cases" element={<CaseExplorer />} />
        <Route path="/cases/:caseId" element={<CaseFile />} />
        <Route path="/intake" element={<IntakeInbox />} />
        <Route path="/intake/fir/new" element={<NewFir />} />
        <Route path="/intake/fir/:draftKey" element={<FirWizard />} />
        <Route path="/intake/imports" element={<IntakeImports />} />
        <Route path="/imports" element={<ImportsWorkspace />} />
        <Route path="/review/quality" element={<QualityReview />} />
        <Route path="/review/entities" element={<EntityResolution />} />
        <Route path="/review/jurisdiction" element={<JurisdictionReview />} />
        <Route path="/people" element={<EntityExplorer />} />
        <Route path="/people/canonical/:cpid" element={<CanonicalProfile />} />
        <Route path="/people/:entityId" element={<EntityProfile />} />
        <Route path="/network" element={<NetworkAnalysis />} />
        <Route path="/map" element={<MapHotspots />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/governance" element={<GovernanceRegistry />} />
        <Route path="/ask" element={<AskDrishti />} />
        {/* Folded into other destinations per doc 01 §4 — keep old links alive */}
        <Route path="/money" element={<Navigate to="/network?mode=money" replace />} />
        <Route path="/forecast" element={<Navigate to="/analytics" replace />} />
        <Route
          path="/admin"
          element={
            <AdminOnly>
              <GovernanceRegistry />
            </AdminOnly>
          }
        />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Route>
    </Routes>
  );
}
