import { useEffect } from "react";
import { FlaskConical, ShieldCheck, TriangleAlert } from "lucide-react";
import { runtime } from "@/config/runtime";
import { ROLE_LIST } from "@/config/roles";
import { useAuth } from "@/auth/AuthProvider";

/* ============================================================================
   Login gate. Shown by <RequireAuth> for any app route when there is no
   session.
     - catalyst mode : renders the embedded Catalyst Authentication iframe.
     - offline  mode : a synthetic demo-identity picker (local dev only).
   ========================================================================== */

const CATALYST_LOGIN_ELEMENT_ID = "drishti-catalyst-login";

function Brand() {
  return (
    <div className="flex items-center gap-3">
      <img src="/drishti.svg" alt="" className="size-9" aria-hidden="true" />
      <div className="leading-tight">
        <div className="text-16 font-semibold tracking-tight text-content">DRISHTI</div>
        <div className="text-12 text-content-dim">Decision intelligence for public safety</div>
      </div>
    </div>
  );
}

function DemoBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-severity-medium/40 bg-severity-medium/10 px-2 py-0.5 text-11 font-medium text-severity-medium">
      <FlaskConical className="size-3" />
      {runtime.demoBadge}
      <span className="text-content-dim">· Not for Operational Use</span>
    </span>
  );
}

function CatalystLogin() {
  const { renderSignIn, status, error } = useAuth();

  useEffect(() => {
    if (status === "unauthenticated") renderSignIn(CATALYST_LOGIN_ELEMENT_ID);
  }, [renderSignIn, status]);

  if (status === "error") {
    return (
      <div className="rounded-card border border-severity-critical/40 bg-severity-critical/10 p-4">
        <div className="flex items-center gap-2 text-13 font-medium text-severity-critical">
          <TriangleAlert className="size-4" /> Sign-in is unavailable
        </div>
        <p className="mt-2 text-12 text-content-dim">
          The Catalyst sign-in service could not load. This build must be opened on its
          deployed Catalyst domain, with Authentication set up in the Catalyst console.
        </p>
        {error && (
          <p className="mt-1 break-words font-mono text-[11px] text-content-dim">{error}</p>
        )}
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="mt-3 rounded-control border border-hairline bg-surface-2 px-3 py-1.5 text-12 text-content hover:border-primary/50"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div>
      <p className="mb-3 text-13 text-content-dim">Sign in with your Catalyst account to continue.</p>
      {/* The Catalyst Web SDK renders the branded login iframe into this element. */}
      <div id={CATALYST_LOGIN_ELEMENT_ID} className="min-h-[320px] w-full" />
    </div>
  );
}

function OfflineLogin() {
  const { signInOffline } = useAuth();
  return (
    <div>
      <p className="mb-1 text-13 text-content-dim">
        Continue with a synthetic demo identity (local development).
      </p>
      <p className="mb-3 text-11 text-content-dim">
        The server always re-derives the real role from the authenticated identity — this
        picker only chooses which demo view to open.
      </p>
      <div className="grid gap-2">
        {ROLE_LIST.map((r) => (
          <button
            key={r.id}
            type="button"
            onClick={() => signInOffline(r.id)}
            className="flex items-center justify-between rounded-control border border-hairline bg-surface-2 px-3 py-2 text-left transition-colors hover:border-primary/50"
          >
            <span className="flex flex-col">
              <span className="text-13 font-medium text-content">{r.label}</span>
              <span className="text-11 text-content-dim">{r.blurb}</span>
            </span>
            <span className="text-11 text-content-dim">{r.scope}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

export function LoginGate() {
  const { mode } = useAuth();
  return (
    <div className="flex min-h-screen w-full items-center justify-center bg-bg px-4 text-content">
      <div className="w-full max-w-md">
        <div className="mb-4 flex items-center justify-between">
          <Brand />
          <DemoBadge />
        </div>

        <div className="rounded-card border border-hairline bg-surface p-5 shadow-sm">
          {mode === "catalyst" ? <CatalystLogin /> : <OfflineLogin />}
        </div>

        <p className="mt-4 flex items-center gap-1.5 text-11 text-content-dim">
          <ShieldCheck className="size-3.5" />
          Evidence-backed. Human-controlled. Auditable. Synthetic data only.
        </p>
      </div>
    </div>
  );
}
