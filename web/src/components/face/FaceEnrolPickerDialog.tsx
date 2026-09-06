import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, Loader2, ScanFace, Search, ShieldAlert, UserPlus, Users2,
} from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import { useRole } from "@/providers/RoleProvider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { useFaceStatus } from "./faceShared";

export interface FaceEnrolTarget {
  canonicalPersonId: number;
  label: string;
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called with the chosen person. The caller then opens FaceEnrolDialog. */
  onPick: (target: FaceEnrolTarget) => void;
}

/** Choose WHICH person a reference photo belongs to, before adding it.
 *
 *  A face gallery is addressed by CanonicalPersonID, so a photo cannot be
 *  uploaded on its own — it is always an attribute of a named identity. The
 *  graph explorer lists graph nodes, and not every person who exists has one
 *  (anyone registered through intake has a canonical record but no graph node
 *  until the enrichment job runs). So this searches the canonical identity
 *  layer directly, which is the complete set, and can mint a new record when
 *  the subject genuinely is not on file yet. */
export function FaceEnrolPickerDialog({ open, onOpenChange, onPick }: Props) {
  const { role } = useRole();
  const qc = useQueryClient();
  const actor = `demo.${role}`;
  const statusQ = useFaceStatus(open);

  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [creating, setCreating] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const status = statusQ.data;
  // Enrolment needs an engine, but NOT `search_ready`: search_ready also demands
  // a non-empty gallery, and enrolling is precisely how an empty one is filled.
  const engineReady = !!status?.enabled && !!status?.available;
  const degraded = !!status?.engine && !status.engine.biometric;

  const searchQ = useQuery({
    queryKey: ["identity", "persons", "search", term],
    queryFn: ({ signal }) => api.identity.searchPersons({ q: term, page_size: 10 }, signal),
    enabled: open && term.length >= 2,
  });

  const reset = () => {
    setQ("");
    setTerm("");
    setNewLabel("");
    setErr(null);
  };

  const createAndPick = async () => {
    const label = newLabel.trim();
    if (!label) return;
    setCreating(true);
    setErr(null);
    try {
      const p = await api.identity.createPerson({ display_label: label, actor });
      qc.invalidateQueries({ queryKey: ["identity"] });
      onPick({ canonicalPersonId: p.canonical_person_id, label: p.display_label ?? p.public_ref });
      reset();
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setCreating(false);
    }
  };

  const items = searchQ.data?.items ?? [];

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) reset();
        onOpenChange(v);
      }}
    >
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Add a reference photo</DialogTitle>
          <DialogDescription>
            Pick the person the photo belongs to. Reference photos are what every
            face scan is matched against.
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-[70vh] space-y-3 overflow-y-auto pr-1">
          {!engineReady && (
            <div className="flex items-start gap-2 rounded-card border border-severity-high/40 bg-severity-high/5 p-3 text-12">
              <ShieldAlert className="mt-0.5 size-4 shrink-0 text-severity-high" aria-hidden />
              <div>
                <p className="font-bold text-severity-high">Face engine unavailable</p>
                <p className="mt-0.5 text-content-dim">
                  {status?.unavailable_reason ?? "No face engine is configured."}
                  {status?.models?.install_command && (
                    <>
                      {" "}Run{" "}
                      <code className="rounded-badge bg-surface-2 px-1 py-0.5 font-mono text-11">
                        {status.models.install_command}
                      </code>{" "}on the server.
                    </>
                  )}
                </p>
              </div>
            </div>
          )}
          {engineReady && degraded && (
            <div className="flex items-start gap-2 rounded-card border border-severity-medium/40 bg-severity-medium/5 p-3 text-12">
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-severity-medium" aria-hidden />
              <p className="text-content-dim">
                <span className="font-bold text-severity-medium">Degraded mode.</span>{" "}
                The fallback backend stores an image fingerprint rather than a face
                descriptor, so photos added now will only ever match the identical file.
              </p>
            </div>
          )}

          <section>
            <form
              className="flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                setTerm(q.trim());
              }}
            >
              <label className="relative min-w-0 flex-1">
                <span className="sr-only">Search person records by name or reference</span>
                <Search
                  className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-content-dim"
                  aria-hidden
                />
                <Input
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="Search name or reference…"
                  className="h-8 pl-8"
                />
              </label>
              <Button size="sm" type="submit" variant="secondary" disabled={q.trim().length < 2}>
                Search
              </Button>
            </form>

            {term.length >= 2 && (
              <ul className="mt-2 divide-y divide-hairline rounded-control border border-hairline">
                {searchQ.isLoading ? (
                  <li className="px-2.5 py-2 text-12 text-content-dim">Searching…</li>
                ) : searchQ.error ? (
                  <li className="flex items-center gap-1.5 px-2.5 py-2 text-12 text-severity-high">
                    <AlertTriangle className="size-3.5 shrink-0" aria-hidden />
                    {errorMessage(searchQ.error)}
                  </li>
                ) : items.length === 0 ? (
                  <li className="px-2.5 py-2 text-12 text-content-dim">
                    No person matches “{term}”. Create a new record below if this
                    person is not on file.
                  </li>
                ) : (
                  items.map((p) => {
                    const label = p.display_label?.trim() || p.public_ref;
                    const merged = p.resolution_status === "merged";
                    return (
                      <li key={p.canonical_person_id} className="flex items-center justify-between gap-2 px-2.5 py-2">
                        <div className="min-w-0">
                          <p className="truncate text-13 font-medium text-content">
                            {p.is_unknown ? "Unknown / unidentified" : label}
                          </p>
                          <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-12 text-content-dim">
                            <Badge variant="neutral" className="tnum">{p.public_ref}</Badge>
                            {merged && <Badge variant="medium">merged</Badge>}
                            {typeof p.case_count === "number" && (
                              <span className="tnum">
                                {p.case_count} case{p.case_count === 1 ? "" : "s"}
                              </span>
                            )}
                          </div>
                        </div>
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={!engineReady || merged}
                          title={merged
                            ? "This record was merged into another identity — enrol against the surviving record."
                            : undefined}
                          onClick={() => onPick({ canonicalPersonId: p.canonical_person_id, label })}
                        >
                          <ScanFace /> Photos
                        </Button>
                      </li>
                    );
                  })
                )}
              </ul>
            )}
            {term.length < 2 && (
              <p className="mt-2 flex items-start gap-1.5 text-12 text-content-dim">
                <Users2 className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                Search the canonical identity layer — it includes people registered
                through intake who do not have a graph node yet.
              </p>
            )}
          </section>

          <section className="rounded-card border border-hairline bg-surface-2 p-3">
            <p className="text-12 font-medium text-content">Not on file yet?</p>
            <p className="mt-0.5 text-12 text-content-dim">
              Create the person record first — a photo is always attached to a named
              identity so the match it later produces is attributable.
            </p>
            <form
              className="mt-2 flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                void createAndPick();
              }}
            >
              <label className="min-w-0 flex-1">
                <span className="sr-only">New person label</span>
                <Input
                  value={newLabel}
                  onChange={(e) => setNewLabel(e.target.value)}
                  placeholder="New person label…"
                  className="h-8"
                  maxLength={160}
                />
              </label>
              <Button
                size="sm"
                type="submit"
                variant="secondary"
                disabled={!newLabel.trim() || creating || !engineReady}
              >
                {creating ? <Loader2 className="animate-spin" /> : <UserPlus />}
                Create and add photo
              </Button>
            </form>
          </section>

          {err && (
            <p className="flex items-start gap-1.5 text-12 text-severity-high" role="alert">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
              {err}
            </p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
