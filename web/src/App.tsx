import { Navigate, Route, Routes } from "react-router-dom";
import { useRole } from "@/providers/RoleProvider";
import { RequireAuth } from "@/auth";
import { useAuth } from "@/auth/AuthProvider";
import { ROLES } from "@/config/roles";
import { AppShell } from "@/components/shell/AppShell";
import { CommandCenter } from "@/routes/CommandCenter";
import { CaseExplorer } from "@/routes/cases/CaseExplorer";
import { CaseFile } from "@/routes/cases/CaseFile";
import { EntityExplorer } from "@/routes/entities/EntityExplorer";
import { EntityProfile } from "@/routes/entities/EntityProfile";
import { NetworkAnalysis } from "@/routes/network/NetworkAnalysis";
import { MyBoards } from "@/routes/board/MyBoards";
import { BoardWorkspace } from "@/routes/board/BoardWorkspace";
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
import { AdminConsole } from "@/routes/admin/AdminConsole";
import { LoginPage } from "@/routes/login/LoginPage";
import { SituationOverview } from "@/routes/emergency/SituationOverview";
import { LiveSituation } from "@/routes/emergency/LiveSituation";
import { ForecastRisk } from "@/routes/emergency/ForecastRisk";
import { Resources as ErResources } from "@/routes/emergency/Resources";
import { ResponsePlans } from "@/routes/emergency/ResponsePlans";
import { NotFound } from "@/routes/NotFound";
import { LandingPage } from "@/routes/landing/LandingPage";

/** Guards the Admin destination — only super_admin may enter, even by URL. */
function AdminOnly({ children }: { children: React.ReactNode }) {
  const { isAdmin } = useRole();
  return isAdmin ? <>{children}</> : <Navigate to="/command" replace />;
}

/** Public marketing page at "/". Once authenticated (incl. the full-page reload
    the Catalyst SDK does after sign-in, which lands back on "/"), forward
    straight to the role home so there is no second "Enter platform" click. */
function PublicLanding() {
  const { status, user } = useAuth();
  if (status === "authenticated") {
    const home = user?.demoRole ? ROLES[user.demoRole].home : "/command";
    return <Navigate to={home} replace />;
  }
  return <LandingPage />;
}

/** Boards hold sensitive investigative material — the policymaker role is
    denied even by direct URL (matches the Catalyst-authenticated API gate). */
function BoardGate({ children }: { children: React.ReactNode }) {
  const { role } = useRole();
  return role === "policymaker" ? <Navigate to="/analytics" replace /> : <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      {/* Public marketing page (forwards authenticated users to their home). */}
      <Route path="/" element={<PublicLanding />} />
      {/* Public sign-in / demo-identity picker. */}
      <Route path="/login" element={<LoginPage />} />
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
        <Route path="/board" element={<BoardGate><MyBoards /></BoardGate>} />
        <Route path="/board/:boardId" element={<BoardGate><BoardWorkspace /></BoardGate>} />
        <Route path="/map" element={<MapHotspots />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/governance" element={<GovernanceRegistry />} />
        <Route path="/ask" element={<AskDrishti />} />
        {/* Emergency Response context (Prompt 17) — separate workspace. */}
        <Route path="/er" element={<SituationOverview />} />
        <Route path="/er/live" element={<LiveSituation />} />
        <Route path="/er/forecast" element={<ForecastRisk />} />
        <Route path="/er/resources" element={<ErResources />} />
        <Route path="/er/plans" element={<ResponsePlans />} />
        {/* Folded into other destinations per doc 01 §4 — keep old links alive */}
        <Route path="/money" element={<Navigate to="/network?mode=money" replace />} />
        <Route path="/forecast" element={<Navigate to="/analytics" replace />} />
        <Route
          path="/admin"
          element={
            <AdminOnly>
              <AdminConsole />
            </AdminOnly>
          }
        />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Route>
    </Routes>
  );
}
