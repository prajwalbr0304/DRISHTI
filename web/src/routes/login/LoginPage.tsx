import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  ArrowRight, FlaskConical, KeyRound, Landmark, LineChart, Loader2, RotateCw,
  ScanEye, Search, ShieldAlert, ShieldCheck, Siren, TriangleAlert, Users,
  type LucideIcon,
} from "lucide-react";
import { runtime } from "@/config/runtime";
import { ROLES, ROLE_LIST, type UserRole } from "@/config/roles";
import { useAuth } from "@/auth/AuthProvider";
import { cn } from "@/lib/utils";
import "@/routes/login/login.css";

/* ============================================================================
   /login — the branded sign-in screen (Prompt 17 polish).

   RequireAuth redirects unauthenticated app routes here (preserving `from`).
     - offline mode  : a synthetic demo-identity picker (local dev).
     - catalyst mode : the embedded Catalyst Authentication iframe.
   On authentication we return the user to `from` (or their role's home). The
   server always re-derives the real role from the session — the picker only
   chooses which demo view to open.
   ========================================================================== */

const CATALYST_LOGIN_ELEMENT_ID = "drishti-catalyst-login";

// Presentation-only: which role workspace opens after the (super_admin) sign-in.
// The server ALWAYS re-derives + enforces the real role — this only picks the
// initial demo view. RoleProvider reads the same key ("drishti.role") and honors
// it for a super_admin identity.
const WORKSPACE_KEY = "drishti.role";
function rememberWorkspace(role: UserRole) {
  try {
    localStorage.setItem(WORKSPACE_KEY, role);
  } catch {
    /* ignore storage availability */
  }
}

type Accent = "crime" | "emergency" | "admin";

const ROLE_META: Record<UserRole, { icon: LucideIcon; accent: Accent }> = {
  investigator: { icon: Search, accent: "crime" },
  analyst: { icon: LineChart, accent: "crime" },
  supervisor: { icon: Users, accent: "crime" },
  policymaker: { icon: Landmark, accent: "crime" },
  disaster_coordinator: { icon: Siren, accent: "emergency" },
  super_admin: { icon: KeyRound, accent: "admin" },
};

function badgeClasses(accent: Accent): string {
  if (accent === "emergency") return "bg-severity-high/15 text-severity-high";
  if (accent === "admin") return "bg-accent/15 text-accent";
  return "bg-primary/15 text-primary";
}

function hoverBorder(accent: Accent): string {
  if (accent === "emergency") return "hover:border-severity-high/60";
  if (accent === "admin") return "hover:border-accent/60";
  return "hover:border-primary/60";
}

export function LoginPage() {
  const { mode, status, user, error, signInOffline, renderSignIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from;
  const [workspace, setWorkspace] = useState<UserRole | null>(null);

  // Once authenticated (incl. an already-signed-in visit), leave /login.
  useEffect(() => {
    if (status !== "authenticated") return;
    const home = user?.demoRole ? ROLES[user.demoRole].home : "/command";
    navigate(from || home, { replace: true });
  }, [status, from, user, navigate]);

  if (status === "initializing") {
    return (
      <div className="grid min-h-screen w-full place-items-center bg-bg text-content-dim">
        <span className="inline-flex items-center gap-2 text-13">
          <Loader2 className="size-4 animate-spin text-primary" /> Checking your session…
        </span>
      </div>
    );
  }

  return (
    <div className="grid min-h-screen w-full bg-bg text-content lg:grid-cols-[1.05fr_minmax(440px,0.95fr)]">
      <HeroPanel />
      <main className="relative flex items-center justify-center px-5 py-10 sm:px-8">
        <div className="login-rise w-full max-w-md">
          {/* header: mobile brand + demo badge */}
          <div className="mb-6 flex items-center justify-between gap-3">
            <Link to="/" className="flex items-center gap-2 lg:hidden" aria-label="DRISHTI home">
              <span className="grid size-9 place-items-center rounded-control bg-primary/15 text-primary">
                <ScanEye className="size-5" />
              </span>
              <span className="text-16 font-semibold tracking-tight text-content">DRISHTI</span>
            </Link>
            <span className="ml-auto inline-flex items-center gap-1 rounded-full border border-severity-medium/40 bg-severity-medium/10 px-2.5 py-1 text-11 font-medium text-severity-medium">
              <FlaskConical className="size-3" /> {runtime.demoBadge}
            </span>
          </div>

          <h1 className="text-28 font-semibold tracking-tight text-content">
            {mode === "offline" ? "Choose your operational view" : "Sign in to DRISHTI"}
          </h1>
          <p className="mt-1.5 text-13 text-content-dim">
            {mode === "offline"
              ? "Continue with a synthetic demo identity. The server re-derives the real role from the authenticated session — this only chooses which view opens."
              : "Sign in with your Catalyst account to continue."}
          </p>

          <div className="mt-6">
            {mode === "offline" ? (
              <RolePicker onPick={signInOffline} />
            ) : (
              <div className="space-y-6">
                <CatalystEmbed status={status} error={error} renderSignIn={renderSignIn} />
                <div>
                  <div className="flex items-center gap-1.5 text-13 font-semibold text-content">
                    <Users className="size-3.5 text-primary" /> Explore a role workspace
                  </div>
                  <p className="mt-1 text-12 text-content-dim">
                    Optional — pick the workspace that opens after you sign in. This selects the
                    role-specific view only; the server re-derives and enforces the real role on
                    every request.
                  </p>
                  {workspace && (
                    <p className="mt-2 rounded-control border border-primary/30 bg-primary/10 px-2.5 py-1.5 text-12 text-content">
                      <span className="font-medium">{ROLES[workspace].label}</span> workspace will
                      open after sign-in.
                    </p>
                  )}
                  <div className="mt-3">
                    <RolePicker
                      onPick={(r) => {
                        rememberWorkspace(r);
                        setWorkspace(r);
                      }}
                    />
                  </div>
                </div>
              </div>
            )}
          </div>

          <p className="mt-6 flex items-center gap-1.5 text-11 text-content-dim">
            <ShieldCheck className="size-3.5 shrink-0 text-accent" />
            Evidence-backed · Human-controlled · Auditable · Synthetic data only.
          </p>
          <Link to="/" className="mt-2 inline-flex items-center gap-1 text-12 text-content-dim transition-colors hover:text-content">
            <ArrowRight className="size-3.5 rotate-180" /> Back to overview
          </Link>
        </div>
      </main>
    </div>
  );
}

/* --------------------------------------------------------------------------- */
function HeroPanel() {
  return (
    <aside className="login-hero relative hidden flex-col justify-between overflow-hidden p-10 lg:flex xl:p-14">
      <div className="login-layer login-aurora" aria-hidden />
      <div className="login-layer login-grid" aria-hidden />
      <div className="login-rings" aria-hidden />
      <div className="login-radar" aria-hidden />
      <div className="login-layer login-noise" aria-hidden />

      {/* brand */}
      <div className="relative flex items-center gap-3">
        <span className="grid size-11 place-items-center rounded-card bg-white/10 text-white shadow-pop ring-1 ring-white/15 backdrop-blur">
          <ScanEye className="size-6" />
        </span>
        <div className="leading-tight">
          <div className="text-20 font-semibold tracking-tight text-white">DRISHTI</div>
          <div className="text-12 text-white/60">Decision intelligence for public safety</div>
        </div>
      </div>

      {/* headline + context cards */}
      <div className="relative max-w-lg">
        <h2 className="text-36 font-semibold leading-[1.1] tracking-tight text-white">
          One operational picture.<br />
          <span className="text-white/70">From first signal to reviewed action.</span>
        </h2>
        <p className="mt-4 max-w-md text-14 text-white/60">
          Two connected workspaces over one governed ontology — crime intelligence and
          emergency response — each keeping a human accountable for every decision.
        </p>

        <div className="mt-8 grid gap-3 sm:grid-cols-2">
          <ContextCard
            icon={ScanEye}
            title="Crime Intelligence"
            copy="FIRs, people, networks, hotspots and forecasting."
            tint="text-sky-300"
          />
          <ContextCard
            icon={ShieldAlert}
            title="Emergency Response"
            copy="Multi-hazard forecasting, readiness and evacuation."
            tint="text-amber-300"
          />
        </div>
      </div>

      {/* trust footer */}
      <div className="relative flex flex-wrap items-center gap-x-5 gap-y-2 text-11 text-white/55">
        {["Reproducible forecasts", "Human-in-the-loop", "Append-only audit", "Synthetic data"].map((t) => (
          <span key={t} className="inline-flex items-center gap-1.5">
            <span className="size-1.5 rounded-full bg-accent/80" /> {t}
          </span>
        ))}
      </div>
    </aside>
  );
}

function ContextCard({ icon: Icon, title, copy, tint }: {
  icon: LucideIcon; title: string; copy: string; tint: string;
}) {
  return (
    <div className="rounded-card border border-white/10 bg-white/[0.06] p-4 backdrop-blur-sm transition-colors hover:border-white/20">
      <Icon className={cn("size-5", tint)} />
      <div className="mt-2.5 text-14 font-semibold text-white">{title}</div>
      <div className="mt-0.5 text-12 leading-snug text-white/55">{copy}</div>
    </div>
  );
}

/* --------------------------------------------------------------------------- */
function RolePicker({ onPick }: { onPick: (r: UserRole) => void }) {
  return (
    <div className="grid gap-2.5 sm:grid-cols-2">
      {ROLE_LIST.map((r, i) => {
        const meta = ROLE_META[r.id];
        const Icon = meta.icon;
        return (
          <button
            key={r.id}
            type="button"
            onClick={() => onPick(r.id)}
            style={{ animationDelay: `${80 + i * 45}ms` }}
            className={cn(
              "login-rise group relative flex flex-col rounded-card border border-hairline bg-surface p-3.5 text-left",
              "transition-all duration-150 hover:-translate-y-0.5 hover:bg-surface-2/60 hover:shadow-pop",
              hoverBorder(meta.accent),
            )}
          >
            <div className="flex items-center gap-2.5">
              <span className={cn("grid size-9 shrink-0 place-items-center rounded-control", badgeClasses(meta.accent))}>
                <Icon className="size-[18px]" />
              </span>
              <span className="min-w-0 flex-1 text-14 font-semibold text-content">{r.label}</span>
              <ArrowRight className="size-4 shrink-0 text-content-dim opacity-0 transition-opacity group-hover:opacity-100" />
            </div>
            <p className="mt-2 text-12 leading-snug text-content-dim">{r.blurb}</p>
            <div className="mt-2 flex items-center gap-2">
              <span className="truncate rounded-full border border-hairline bg-surface-2 px-2 py-0.5 text-[11px] text-content-dim">
                {r.scope}
              </span>
              {r.id === "disaster_coordinator" && (
                <span className="rounded-full bg-severity-high/15 px-2 py-0.5 text-[11px] font-medium text-severity-high">
                  Emergency
                </span>
              )}
            </div>
          </button>
        );
      })}
    </div>
  );
}

/* --------------------------------------------------------------------------- */
function CatalystEmbed({ status, error, renderSignIn }: {
  status: string; error?: string; renderSignIn: (id: string) => void;
}) {
  useEffect(() => {
    if (status === "unauthenticated") renderSignIn(CATALYST_LOGIN_ELEMENT_ID);
  }, [status, renderSignIn]);

  if (status === "error") {
    return (
      <div className="rounded-card border border-severity-critical/40 bg-severity-critical/10 p-4">
        <div className="flex items-center gap-2 text-13 font-medium text-severity-critical">
          <TriangleAlert className="size-4" /> Sign-in is unavailable
        </div>
        <p className="mt-2 text-12 text-content-dim">
          The Catalyst sign-in service could not load. This build must be opened on its
          deployed Catalyst domain, with Authentication set up in the console.
        </p>
        {error && <p className="mt-1 break-words font-mono text-[11px] text-content-dim">{error}</p>}
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="mt-3 inline-flex items-center gap-1.5 rounded-control border border-hairline bg-surface-2 px-3 py-1.5 text-12 text-content transition-colors hover:border-primary/50"
        >
          <RotateCw className="size-3.5" /> Retry
        </button>
      </div>
    );
  }

  return (
    <div className="rounded-card border border-hairline bg-surface p-4">
      <div id={CATALYST_LOGIN_ELEMENT_ID} className="min-h-[320px] w-full" />
    </div>
  );
}
