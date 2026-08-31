import { useQuery } from "@tanstack/react-query";
import { LogOut } from "lucide-react";
import { api } from "@/api";
import { cn } from "@/lib/utils";
import { useAuth } from "@/auth";
import { useRole } from "@/providers/RoleProvider";
import { LANGUAGE_OPTIONS, useLanguage, type Language } from "@/providers/LanguageProvider";
import { useUIStore } from "@/stores/useUIStore";
import { useDistrictLabel } from "@/hooks/useDistricts";
import { PageHeader } from "@/components/common/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { RoleIcon } from "@/components/roles/RoleIcon";

/* ============================================================================
   Profile — the signed-in seat, its data scope, and the interface preferences
   that used to be buried in the account dropdown (density, language) plus live
   service health.

   The seat itself is deliberately NOT changeable here: an operational session
   has one identity from sign-in to sign-out. Choosing a different operational
   view means signing in again, so scope can never shift underneath work already
   in progress.
   ========================================================================== */

export function Profile() {
  const { role, def } = useRole();
  const { user, mode, signOut } = useAuth();
  const { language, setLanguage, t } = useLanguage();
  const density = useUIStore((s) => s.density);
  const setDensity = useUIStore((s) => s.setDensity);
  const districtLabel = useDistrictLabel();

  const health = useQuery({
    queryKey: ["health"],
    queryFn: ({ signal }) => api.health(signal),
    refetchInterval: 60_000,
    retry: false,
  });
  const status = health.isLoading
    ? "checking"
    : health.error
      ? "down"
      : health.data?.status ?? "down";

  return (
    <div>
      <PageHeader
        title="Profile"
        description="Your seat, the data scope it carries, and how this interface behaves."
        info={
          <p>
            The operational view is fixed for the session. To work as a different seat, log out and
            choose it again at sign-in — that way your scope cannot change part-way through a task.
          </p>
        }
        actions={
          <Button variant="outline" onClick={() => signOut()}>
            <LogOut /> {t("Log out")}
          </Button>
        }
      />

      <div className="grid gap-5 lg:grid-cols-2">
        {/* --- Seat ------------------------------------------------------- */}
        <Card title={t("Signed in as")}>
          <div className="flex items-start gap-3">
            <span className="grid size-11 shrink-0 place-items-center rounded-full bg-primary/15 text-primary">
              <RoleIcon role={role} className="size-5" />
            </span>
            <div className="min-w-0">
              <div className="truncate text-heading-s font-bold text-content">
                {user?.fullName ?? def.demoName}
              </div>
              {user?.email && (
                <div className="truncate text-body-m text-content-dim">{user.email}</div>
              )}
              <div className="mt-2 flex flex-wrap gap-1.5">
                <Badge variant="primary">{t(def.label)}</Badge>
                <Badge variant="neutral">{mode === "offline" ? t("Demo identity") : t("Catalyst session")}</Badge>
              </div>
            </div>
          </div>

          <dl className="mt-4 space-y-2 border-t border-hairline pt-4">
            <Row label={t("Responsibility")} value={t(def.blurb)} />
            <Row label={t("Data scope")} value={t(def.scope)} />
            <Row label={t("District filter")} value={t(districtLabel)} />
            <Row label={t("Username")} value={def.demoUsername} mono />
          </dl>

          <p className="mt-4 text-body-s text-content-dim">
            {t(
              "Scope is enforced by the services from your session, not by this screen. The district filter only narrows what you see.",
            )}
          </p>
        </Card>

        {/* --- Preferences ------------------------------------------------ */}
        <div className="space-y-5">
          <Card title={t("Interface")}>
            <div className="space-y-4">
              <Labelled label={t("Interface language")} hint={t("Kannada renders in its own script throughout.")}>
                <NativeSelect
                  aria-label={t("Interface language")}
                  value={language}
                  onChange={(v) => setLanguage(v as Language)}
                  options={LANGUAGE_OPTIONS.map((o) => ({ value: o.value, label: o.nativeLabel }))}
                  placeholder="English"
                  className="max-w-xs"
                />
              </Labelled>

              <Labelled
                label={t("Density")}
                hint={t("Compact reduces vertical spacing for data-heavy screens.")}
              >
                <div className="flex gap-1.5">
                  {(["comfortable", "compact"] as const).map((d) => (
                    <button
                      key={d}
                      type="button"
                      onClick={() => setDensity(d)}
                      aria-pressed={density === d}
                      className={cn(
                        "rounded-full border px-3 py-1 text-body-s font-bold transition-colors",
                        density === d
                          ? "border-primary bg-primary/12 text-primary"
                          : "border-hairline text-content-dim hover:bg-surface-2 hover:text-content",
                      )}
                    >
                      {d === "comfortable" ? t("Comfortable") : t("Compact")}
                    </button>
                  ))}
                </div>
              </Labelled>
            </div>
          </Card>

          <Card title={t("Service")}>
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  "size-2.5 shrink-0 rounded-full",
                  status === "ok" && "bg-severity-low",
                  status === "degraded" && "bg-severity-medium",
                  status === "checking" && "animate-pulse bg-content-dim",
                  status === "down" && "bg-severity-critical",
                )}
                aria-hidden
              />
              <span className="text-body-m text-content">
                {status === "checking" ? `${t("checking")}…` : t(status)}
              </span>
              {health.data?.version && (
                <span className="tnum text-body-s text-content-dim">v{health.data.version}</span>
              )}
              {health.data?.app && <Badge variant="neutral">{health.data.app}</Badge>}
            </div>
            <p className="mt-2 text-body-s text-content-dim">
              {t("Checked every 60 seconds against the analytics service.")}
            </p>
          </Card>
        </div>
      </div>
    </div>
  );
}

/* --------------------------------- bits ----------------------------------- */
function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-card border border-hairline bg-surface p-5 shadow-card">
      <h2 className="mb-4 text-heading-m font-bold text-content">{title}</h2>
      {children}
    </section>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-2">
      <dt className="text-body-s text-content-dim">{label}</dt>
      <dd className={cn("min-w-0 text-right text-body-m text-content", mono && "font-mono tnum")}>
        {value}
      </dd>
    </div>
  );
}

function Labelled({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <span className="block text-body-s font-bold text-content">{label}</span>
      {children}
      {hint && <span className="block text-body-s text-content-dim">{hint}</span>}
    </div>
  );
}
