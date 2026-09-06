import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  ArrowRight, Building2, Cpu, KeyRound, Landmark, Layers, LineChart, Loader2,
  LogIn, RotateCw, ScanEye, Search, ShieldAlert, ShieldCheck, TrafficCone,
  TriangleAlert, Users, UserCog,
  type LucideIcon,
} from "lucide-react";
import { ROLES, ROLE_LIST, type UserRole } from "@/config/roles";
import { useAuth } from "@/auth/AuthProvider";
import { SeatPicker } from "@/routes/login/SeatPicker";
import { useSeatStore, type SelectedSeat } from "@/stores/useSeatStore";
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

// Presentation-only: which role workspace opens after sign-in. The server ALWAYS
// re-derives + enforces the real role — this only picks the initial demo view.
// RoleProvider reads the same key ("drishti.role") and honors it for a
// full-access identity.
const WORKSPACE_KEY = "drishti.role";
function rememberWorkspace(role: UserRole) {
  try {
    localStorage.setItem(WORKSPACE_KEY, role);
  } catch {
    /* ignore storage availability */
  }
}

function loadRememberedWorkspace(): UserRole | null {
  try {
    const role = localStorage.getItem(WORKSPACE_KEY);
    return role && role in ROLES ? role as UserRole : null;
  } catch {
    return null;
  }
}

type Accent = "command" | "field" | "admin";

const ROLE_META: Record<UserRole, { icon: LucideIcon; accent: Accent }> = {
  dgp_state_command: { icon: Landmark, accent: "command" },
  senior_command: { icon: Layers, accent: "command" },
  district_command: { icon: Building2, accent: "command" },
  sho: { icon: ShieldCheck, accent: "field" },
  investigating_officer: { icon: Search, accent: "field" },
  system_admin: { icon: KeyRound, accent: "admin" },
};

function badgeClasses(accent: Accent): string {
  if (accent === "command") return "bg-severity-high/15 text-severity-high";
  if (accent === "admin") return "bg-accent/15 text-accent";
  return "bg-primary/15 text-primary";
}

function hoverBorder(accent: Accent): string {
  if (accent === "command") return "hover:border-severity-high/60";
  if (accent === "admin") return "hover:border-accent/60";
  return "hover:border-primary/60";
}

export function LoginPage() {
  const { mode, status, user, error, signInOffline, renderSignIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from;
  const [workspace, setWorkspace] = useState<UserRole | null>(null);
  const setSeat = useSeatStore((s) => s.setSeat);
  const clearSeat = useSeatStore((s) => s.clearSeat);

  // Keep the public sign-in route as a single-screen experience, then restore
  // normal document scrolling as soon as the user leaves /login.
  useEffect(() => {
    document.documentElement.classList.add("login-scroll-lock");
    document.body.classList.add("login-scroll-lock");
    return () => {
      document.documentElement.classList.remove("login-scroll-lock");
      document.body.classList.remove("login-scroll-lock");
    };
  }, []);

  // Once authenticated (incl. an already-signed-in visit), leave /login.
  useEffect(() => {
    if (status !== "authenticated") return;
    const selectedRole = user?.demoRole ?? loadRememberedWorkspace();
    const home = selectedRole ? ROLES[selectedRole].home : "/command";
    // An explicit role choice owns the destination. This prevents the protected
    // route that originally sent the user to /login (often /command) from
    // overriding Cyber, Analyst, Traffic, SHO, or Investigator role homes.
    navigate(selectedRole ? home : from || home, { replace: true });
  }, [status, from, user, navigate]);

  const openOfflineWorkspace = (role: UserRole) => {
    // Keep RoleProvider and the offline identity in sync in the same click.
    // Without this, a previously explored demo role could override the newly
    // selected login card when the authenticated identity mounted.
    //
    // Clears any previously chosen seat: opening a GENERIC seat by role must not
    // silently keep sending the last specific seat's actor, or the board would
    // render for a jurisdiction the user thought they had left.
    clearSeat();
    rememberWorkspace(role);
    signInOffline(role);
  };

  const openSeat = (seat: SelectedSeat) => {
    // The seat carries both halves: its role picks the board, its posting picks
    // the jurisdiction. Store it before signing in so the first request already
    // sends the right actor.
    setSeat(seat);
    rememberWorkspace(seat.role);
    signInOffline(seat.role);
  };

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
    <div className="login-shell grid h-[100dvh] w-full overflow-hidden bg-bg text-content lg:grid-cols-[minmax(0,1.02fr)_minmax(560px,0.98fr)]">
      <HeroPanel />
      <main className="login-auth-panel relative flex min-h-0 items-center justify-center overflow-hidden px-5 py-5 sm:px-8 lg:px-10 lg:py-6 2xl:px-12">
        <div className="login-rise w-full max-w-[900px]">
          {/* header: mobile brand */}
          <div className="mb-4 flex items-center justify-between gap-3 lg:hidden">
            <Link to="/" className="flex items-center gap-2 lg:hidden" aria-label="DRISHTI home">
              <span className="grid size-9 place-items-center rounded-control bg-primary/15 text-primary">
                <ScanEye className="size-5" />
              </span>
              <span className="text-16 font-semibold tracking-tight text-content">DRISHTI</span>
            </Link>
          </div>

          <h1 className="text-28 font-semibold tracking-tight text-content xl:text-32">
            {mode === "offline" ? "Choose your operational view" : "Sign in to DRISHTI"}
          </h1>
          {mode !== "offline" && (
            <p className="mt-2 max-w-[72ch] text-13 leading-relaxed text-content-dim xl:text-14">
              Sign in with your Catalyst account to continue.
            </p>
          )}

          <div className="mt-5">
            {mode === "offline" ? (
              <>
                {/* Seat first. A role card can only open a generic seat, and with
                    ~11,825 provisioned seats the question is not "which role" but
                    "which posting" — an SP of Mysuru and an SP of Belagavi share a
                    role and command different districts. The role cards stay below
                    as a quick path when the specific posting does not matter. */}
                <SeatPicker onPick={openSeat} />
                <details className="mt-3">
                  <summary className="cursor-pointer text-12 text-content-dim transition-colors hover:text-content">
                    Or open a generic seat by role
                  </summary>
                  <div className="mt-2">
                    <RoleSelect onPick={openOfflineWorkspace} actionLabel="Open workspace" />
                  </div>
                </details>
              </>
            ) : (
              <div className="space-y-4">
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
                  <div className="mt-2">
                    <RoleSelect
                      onPick={(r) => {
                        rememberWorkspace(r);
                        setWorkspace(r);
                      }}
                      actionLabel="Set workspace"
                    />
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="login-panel-footer mt-5 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-t border-hairline pt-4">
          <p className="flex items-center gap-1.5 text-11 text-content-dim xl:text-12">
            <ShieldCheck className="size-4 shrink-0 text-accent" />
            Evidence-backed · Human-controlled · Auditable · Synthetic data only.
          </p>
          <Link to="/" className="inline-flex items-center gap-1 text-12 text-content-dim transition-colors hover:text-content">
            <ArrowRight className="size-4 rotate-180" /> Back to overview
          </Link>
          </div>
        </div>
      </main>
    </div>
  );
}

/* --------------------------------------------------------------------------- */
function HeroPanel() {
  return (
    <aside className="login-hero relative hidden min-h-0 flex-col justify-between overflow-hidden p-8 lg:flex xl:p-12 2xl:p-14">
      <div className="login-layer login-aurora" aria-hidden />
      <div className="login-layer login-grid" aria-hidden />
      <div className="login-rings" aria-hidden />
      <div className="login-radar" aria-hidden />
      <div className="login-layer login-noise" aria-hidden />

      {/* brand */}
      <div className="relative flex items-center gap-3">
        <span className="grid size-14 place-items-center rounded-card bg-white/10 text-white shadow-pop ring-1 ring-white/15 backdrop-blur">
          <ScanEye className="size-7" />
        </span>
        <div className="leading-tight">
          <div className="text-20 font-semibold tracking-tight text-white">DRISHTI</div>
          <div className="text-17 text-white/65">Decision intelligence for public safety</div>
        </div>
      </div>

      {/* headline + context cards */}
      <div className="relative max-w-[800px]">
        <h2 className="text-[66px] font-semibold leading-[1.03] tracking-tight text-white xl:text-[78px] 2xl:text-[86px]">
          One operational picture.<br />
          <span className="text-white/70">From first signal to reviewed action.</span>
        </h2>
        <p className="mt-6 max-w-[680px] text-17 leading-relaxed text-white/70 2xl:text-18">
          Two connected workspaces over one governed ontology — crime intelligence and
          emergency response — each keeping a human accountable for every decision.
        </p>

        <div className="mt-7 grid gap-4 sm:grid-cols-2 2xl:mt-8">
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
      <div className="relative flex flex-wrap items-center gap-x-8 gap-y-2.5 text-15 text-white/65 2xl:text-16">
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
    <div className="min-h-[180px] rounded-card border border-white/10 bg-white/[0.06] p-5 backdrop-blur-sm transition-colors hover:border-white/20 2xl:p-6">
      <Icon className={cn("size-6", tint)} />
      <div className="mt-3 text-18 font-semibold text-white">{title}</div>
      <div className="mt-1 text-14 leading-relaxed text-white/65 2xl:text-15">{copy}</div>
    </div>
  );
}

/* --------------------------------------------------------------------------- */
function RolePicker({ onPick }: { onPick: (r: UserRole) => void }) {
  return (
    <div className="login-role-grid grid grid-cols-2 gap-4">
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
              "login-rise login-role-card group relative flex min-w-0 rounded-card border border-hairline bg-surface p-5 text-left",
              "transition-all duration-150 hover:-translate-y-px hover:bg-surface-2/60 hover:shadow-pop",
              hoverBorder(meta.accent),
            )}
          >
            <div className="flex min-w-0 flex-1 items-center gap-4">
              <span className={cn("grid size-14 shrink-0 place-items-center rounded-control", badgeClasses(meta.accent))}>
                <Icon className="size-[30px]" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-17 font-bold leading-tight text-content xl:text-18">{r.label}</span>
                <span className="mt-2 grid grid-cols-[auto_minmax(0,1fr)] items-start gap-1.5 text-12 leading-relaxed text-content-dim xl:text-13">
                  <UserCog className="mt-0.5 size-3.5 shrink-0" />
                  <span className="break-words">{r.demoName} · {r.scope}</span>
                </span>
              </span>
              <ArrowRight className="size-4 shrink-0 text-content-dim opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100" />
            </div>
          </button>
        );
      })}
    </div>
  );
}

function RoleSelect({ onPick, actionLabel }: {
  onPick: (r: UserRole) => void;
  actionLabel: string;
}) {
  const [selected, setSelected] = useState<UserRole>(ROLE_LIST[0].id);
  const role = ROLES[selected];
  const selectId = `role-select-${actionLabel.toLowerCase().replace(/\s+/g, "-")}`;

  return (
    <div className="rounded-card border border-hairline bg-surface p-3">
      <label htmlFor={selectId} className="text-11 font-semibold text-content">
        Operational workspace
      </label>
      <select
        id={selectId}
        value={selected}
        onChange={(event) => setSelected(event.target.value as UserRole)}
        className="mt-2 h-10 w-full rounded-control border border-hairline bg-surface-2 px-3 text-12 text-content outline-none transition-colors focus:border-primary"
      >
        {ROLE_LIST.map((entry) => (
          <option key={entry.id} value={entry.id}>
            {entry.label} — {entry.scope}
          </option>
        ))}
      </select>
      <div className="mt-2 flex items-center justify-between gap-3">
        <span className="min-w-0 truncate text-10 text-content-dim">{role.demoName}</span>
        <button
          type="button"
          onClick={() => onPick(selected)}
          className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-control bg-primary px-3 text-11 font-semibold text-primary-foreground transition-opacity hover:opacity-90"
        >
          {actionLabel} <ArrowRight className="size-3" />
        </button>
      </div>
    </div>
  );
}

/* --------------------------------------------------------------------------- */
function CatalystEmbed({ status, error, renderSignIn }: {
  status: string; error?: string; renderSignIn: (id: string) => void;
}) {
  const [widgetReady, setWidgetReady] = useState(false);
  const [widgetTimedOut, setWidgetTimedOut] = useState(false);

  useEffect(() => {
    if (status !== "unauthenticated") return;
    setWidgetReady(false);
    setWidgetTimedOut(false);
    renderSignIn(CATALYST_LOGIN_ELEMENT_ID);
    const host = document.getElementById(CATALYST_LOGIN_ELEMENT_ID);
    if (!host) return;
    // Zoho's embedded login body is taller than the form and shows its own
    // scrollbar. The card is sized (below) to fit the full email/password step,
    // so disable the iframe's scrollbar for a clean card with no dead space.
    const tidy = () => {
      const iframe = host.querySelector("iframe");
      if (iframe) {
        iframe.setAttribute("scrolling", "no");
        iframe.style.overflow = "hidden";
      }
      if (host.childElementCount > 0) setWidgetReady(true);
    };
    tidy();
    // If the SDK never injects the sign-in iframe (it can stall after a
    // sign-out / SSO hand-off), surface a Reload instead of an endless spinner.
    const guard = window.setTimeout(() => {
      if (host.childElementCount === 0) setWidgetTimedOut(true);
    }, 8000);
    const obs = new MutationObserver(tidy);
    obs.observe(host, { childList: true, subtree: true });
    return () => { obs.disconnect(); window.clearTimeout(guard); };
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
    <div className="overflow-hidden rounded-card border border-hairline bg-surface shadow-pop">
      <div className="flex items-center gap-2 border-b border-hairline bg-surface-2/40 px-4 py-2.5">
        <span className="grid size-6 place-items-center rounded-control bg-primary/15 text-primary">
          <LogIn className="size-3.5" />
        </span>
        <span className="text-13 font-semibold text-content">Catalyst sign-in</span>
        <span className="ml-auto inline-flex items-center gap-1 text-11 font-medium text-content-dim">
          <ShieldCheck className="size-3 text-accent" /> Secured by Zoho Catalyst
        </span>
      </div>
      <div className="relative px-4 py-3">
        {/* The Catalyst SDK injects an iframe sized to 100% of this host. 360px
            fits the full Zoho step (heading + field + NEXT + Forgot Password,
            and the password/OTP steps) without the internal scrollbar (disabled
            in the effect); the loader overlays it until the iframe mounts. */}
        <div
          id={CATALYST_LOGIN_ELEMENT_ID}
          className="login-catalyst-host relative mx-auto h-[360px] w-full max-w-[400px]"
        />
        {!widgetReady && (
          <div className="absolute inset-0 grid place-items-center">
            {widgetTimedOut ? (
              <div className="flex flex-col items-center gap-2 text-center">
                <span className="text-12 text-content-dim">Sign-in is taking longer than expected.</span>
                <button
                  type="button"
                  onClick={() => window.location.reload()}
                  className="inline-flex items-center gap-1.5 rounded-control border border-hairline bg-surface-2 px-3 py-1.5 text-12 text-content transition-colors hover:border-primary/50"
                >
                  <RotateCw className="size-3.5" /> Reload
                </button>
              </div>
            ) : (
              <span className="pointer-events-none inline-flex items-center gap-2 text-12 text-content-dim">
                <Loader2 className="size-4 animate-spin text-primary" /> Loading secure sign-in…
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
