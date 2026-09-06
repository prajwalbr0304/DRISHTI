import { useState } from "react";
import { Link } from "react-router-dom";
import {
  Database, History, Info, ScanFace, ShieldCheck, Users,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/common/PageHeader";
import { FaceScanner } from "@/components/face/FaceScanner";
import { similarityPct, useFaceStatus } from "@/components/face/faceShared";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api";
import { cn } from "@/lib/utils";

/** The biometric-search trail. This is deliberately on the same screen as the
 *  scanner, not buried in an admin page: face search is a sensitive capability
 *  and the people using it should see that every query is recorded. */
function ProbeTrail() {
  const q = useQuery({
    queryKey: ["face", "probes", 12],
    queryFn: ({ signal }) => api.face.probes({ limit: 12 }, signal),
    staleTime: 15_000,
  });

  if (q.isLoading) return <Skeleton className="h-32 w-full" />;
  const items = q.data?.items ?? [];

  return (
    <section className="rounded-card border border-hairline bg-surface p-4 shadow-card">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-heading-s font-bold text-content">
          <History className="size-4 text-content-dim" aria-hidden />
          Recent face searches
        </h2>
        {q.data?.total ? (
          <Badge variant="outline" className="tnum">{q.data.total} total</Badge>
        ) : null}
      </div>
      {items.length === 0 ? (
        <p className="text-12 text-content-dim">
          No face searches recorded yet. Every scan is logged here with who ran it
          and what was decided.
        </p>
      ) : (
        <ul className="divide-y divide-hairline">
          {items.map((p) => (
            <li
              key={p.probe_ref}
              className="flex flex-wrap items-center justify-between gap-2 py-2 text-12"
            >
              <span className="flex min-w-0 items-center gap-2">
                <Badge
                  variant={
                    p.decision === "confirmed" ? "low"
                      : p.decision === "rejected" ? "high"
                        : p.decision === "pending" ? "medium" : "neutral"
                  }
                  className="capitalize"
                >
                  {p.decision.replace(/_/g, " ")}
                </Badge>
                <span className="truncate text-content">
                  {p.top_canonical_person_id ? (
                    <Link
                      to={`/people/canonical/${p.top_canonical_person_id}`}
                      className="text-primary hover:underline"
                    >
                      {p.top_display_label ?? p.top_public_ref ?? `Person ${p.top_canonical_person_id}`}
                    </Link>
                  ) : (
                    <span className="text-content-dim">no candidate</span>
                  )}
                </span>
                {p.top_similarity != null && (
                  <span className="tnum text-content-dim">
                    {similarityPct(p.top_similarity)}
                  </span>
                )}
              </span>
              <span className="flex items-center gap-2 text-content-dim">
                <span className="truncate">{p.actor ?? "—"}</span>
                {p.origin && <span className="capitalize">· {p.origin.replace(/_/g, " ")}</span>}
                {p.latency_ms != null && <span className="tnum">· {p.latency_ms} ms</span>}
                <span className="tnum">{p.created_at?.slice(0, 16).replace("T", " ") ?? ""}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function StatChip({ icon, label, value, tone }: {
  icon: React.ReactNode; label: string; value: string;
  tone?: "default" | "warn";
}) {
  return (
    <div className="flex items-center gap-2 rounded-card border border-hairline bg-surface px-3 py-2">
      <span className={cn("[&_svg]:size-4",
        tone === "warn" ? "text-severity-medium" : "text-content-dim")}>{icon}</span>
      <div className="min-w-0">
        <div className="text-11 uppercase tracking-wide text-content-dim">{label}</div>
        <div className={cn("tnum truncate text-13 font-medium",
          tone === "warn" ? "text-severity-medium" : "text-content")}>{value}</div>
      </div>
    </div>
  );
}

/** Standalone face recognition: take a photo on the spot (or upload one) and see
 *  whether the person is already in the records.
 *
 *  This is the "walk-up" flow — a person in front of you, no case open yet. The
 *  same component is embedded in FIR intake, where a confirmed match links the
 *  new case to the existing identity instead of creating a duplicate. */
export function FaceSearchPage() {
  const statusQ = useFaceStatus();
  const s = statusQ.data;
  const [showTrail, setShowTrail] = useState(true);

  return (
    <div>
      <PageHeader
        title="Face Recognition"
        description="Check a face against enrolled person records. A match is an investigative lead for human confirmation, never an identification."
        info={
          <div className="space-y-2">
            <p>
              A photo is described as a 512-dimension ArcFace descriptor and compared
              against enrolled reference photos by cosine similarity, using an
              approximate-nearest-neighbour index so the search stays fast as records
              grow.
            </p>
            <p>
              Only reference photos that someone has explicitly enrolled are searched.
              The probe photo itself is never stored — the server keeps its hash, the
              face geometry and the descriptor for the audit trail.
            </p>
            <p>
              Confirming a match records a reviewable entity-resolution candidate. It
              never merges two identities automatically.
            </p>
          </div>
        }
        actions={
          <Button variant="outline" size="sm" onClick={() => setShowTrail((v) => !v)}>
            <History /> {showTrail ? "Hide" : "Show"} search log
          </Button>
        }
      />

      {statusQ.isLoading ? (
        <Skeleton className="mb-4 h-16 w-full" />
      ) : s ? (
        <div className="mb-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <StatChip
            icon={<ScanFace aria-hidden />}
            label="Engine"
            value={s.engine.biometric
              ? `ArcFace ${s.engine.pack ?? ""}`.trim()
              : "Degraded (photo match)"}
            tone={s.engine.biometric ? "default" : "warn"}
          />
          <StatChip
            icon={<Users aria-hidden />}
            label="People enrolled"
            value={s.gallery.person_count.toLocaleString()}
          />
          <StatChip
            icon={<Database aria-hidden />}
            label="Reference photos"
            value={s.gallery.face_count.toLocaleString()}
          />
          <StatChip
            icon={<ShieldCheck aria-hidden />}
            label="Match threshold"
            value={s.engine.recommended_threshold != null
              ? similarityPct(s.engine.recommended_threshold) : "—"}
          />
        </div>
      ) : null}

      <div className="space-y-4">
        <FaceScanner origin="standalone" />

        {s && s.gallery.face_count === 0 && (
          <div className="flex items-start gap-2 rounded-card border border-hairline bg-surface-2/40 p-3 text-12">
            <Info className="mt-0.5 size-4 shrink-0 text-content-dim" aria-hidden />
            <p className="text-content-dim">
              <span className="font-bold text-content">Build the gallery first.</span>{" "}
              Face search only finds people who have a reference photo on file. Open a
              person from{" "}
              <Link to="/people" className="text-primary hover:underline">
                People &amp; Entities
              </Link>{" "}
              and use <strong>Reference photos</strong> to add one. To seed many at
              once, run{" "}
              <code className="rounded-badge bg-surface-2 px-1 py-0.5 font-mono text-11">
                python -m app.batch face-enrol --dir ./photos
              </code>{" "}
              on the server, naming each file after the person&apos;s ID or public
              reference.
            </p>
          </div>
        )}

        {showTrail && <ProbeTrail />}
      </div>
    </div>
  );
}

export default FaceSearchPage;
