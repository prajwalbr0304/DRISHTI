import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle, CalendarClock, CheckCircle2, ExternalLink, Fingerprint,
  MapPin, MinusCircle, ShieldQuestion, UserRound,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { FaceMatch } from "@/api/types";
import {
  approxAge, bandMeta, genderLabel, personName, similarityPct,
} from "./faceShared";

/** Similarity meter that animates from 0 to the score once on mount.
 *  Numeric value is always rendered as text, so the bar is redundant decoration. */
function SimilarityMeter({ value, threshold, bar, reducedMotion }: {
  value: number; threshold: number; bar: string; reducedMotion?: boolean;
}) {
  const [width, setWidth] = useState(reducedMotion ? value : 0);
  useEffect(() => {
    if (reducedMotion) {
      setWidth(value);
      return;
    }
    const id = requestAnimationFrame(() => setWidth(value));
    return () => cancelAnimationFrame(id);
  }, [value, reducedMotion]);

  return (
    <div className="space-y-1">
      <div
        className="relative h-1.5 w-full overflow-hidden rounded-full bg-surface-2"
        role="img"
        aria-label={`Similarity ${similarityPct(value)}, match threshold ${similarityPct(threshold)}`}
      >
        <div
          className={cn("h-full rounded-full transition-[width] duration-500 ease-out", bar)}
          style={{ width: `${Math.max(2, Math.min(100, width * 100))}%` }}
        />
        {/* threshold tick — makes "above/below the line" visible, not just stated */}
        <span
          aria-hidden
          className="absolute top-0 h-full w-px bg-content/50"
          style={{ left: `${Math.min(100, threshold * 100)}%` }}
        />
      </div>
      <div className="flex justify-between text-11 text-content-dim">
        <span className="tnum">{similarityPct(value)} similarity</span>
        <span className="tnum">threshold {similarityPct(threshold)}</span>
      </div>
    </div>
  );
}

interface Props {
  match: FaceMatch;
  threshold: number;
  /** Rank-based stagger for the reveal. */
  index?: number;
  reducedMotion?: boolean;
  /** Rendered larger, as the headline answer. */
  primary?: boolean;
  /** Omitted in read-only contexts (e.g. the standalone lookup). */
  onConfirm?: (match: FaceMatch) => void;
  confirmLabel?: string;
  confirming?: boolean;
  disabled?: boolean;
}

/** One matched person record: who they are, and what is already on file.
 *
 *  The card leads with the record, not the score. "84% similar" is not useful on
 *  its own — "this person has 3 cases as an accused in Bengaluru City" is the
 *  thing an officer acts on, and the score qualifies it. */
export function FaceMatchCard({
  match, threshold, index = 0, reducedMotion, primary, onConfirm,
  confirmLabel = "This is the person", confirming, disabled,
}: Props) {
  const meta = bandMeta(match.band);
  const p = match.person;
  const age = approxAge(p.approx_birth_year);
  const gender = genderLabel(p.primary_gender_id);
  const BandIcon = match.band === "strong" ? CheckCircle2
    : match.band === "probable" ? ShieldQuestion : MinusCircle;

  return (
    <article
      className={cn(
        "rounded-card border bg-surface p-4",
        primary
          ? "border-primary/40 shadow-card"
          : "border-hairline",
        !reducedMotion && "animate-face-reveal",
      )}
      style={reducedMotion ? undefined : { animationDelay: `${index * 90}ms` }}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3
              className={cn(
                "truncate font-bold text-content",
                primary ? "text-heading-m" : "text-heading-s",
              )}
            >
              {personName(p)}
            </h3>
            <Badge variant={meta.badge} className="gap-1">
              <BandIcon className="size-3" aria-hidden />
              {meta.label}
            </Badge>
            {p.is_juvenile && (
              <Badge variant="high" className="gap-1">
                <AlertTriangle className="size-3" aria-hidden />
                Juvenile — protected
              </Badge>
            )}
            {p.resolution_status !== "canonical" && (
              <Badge variant="outline" className="capitalize">{p.resolution_status}</Badge>
            )}
          </div>
          <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-12 text-content-dim">
            <span className="tnum inline-flex items-center gap-1">
              <Fingerprint className="size-3" aria-hidden />
              {p.public_ref}
            </span>
            {gender && <span>· {gender}</span>}
            {age != null && <span>· approx. {age} yrs</span>}
            {p.aliases.length > 0 && (
              <span className="truncate">· also known as {p.aliases.slice(0, 3).join(", ")}</span>
            )}
          </p>
        </div>
        <div className={cn("w-full shrink-0", primary ? "sm:w-56" : "sm:w-44")}>
          <SimilarityMeter
            value={match.similarity}
            threshold={threshold}
            bar={meta.bar}
            reducedMotion={reducedMotion}
          />
        </div>
      </div>

      <p className={cn("mt-2 text-12", meta.text)}>{meta.guidance}</p>

      {/* --- what is already on file: the actual answer to "does this exist?" --- */}
      <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div>
          <dt className="text-11 uppercase tracking-wide text-content-dim">Cases</dt>
          <dd className="tnum text-13 font-medium text-content">{p.case_count}</dd>
        </div>
        <div>
          <dt className="text-11 uppercase tracking-wide text-content-dim">Roles</dt>
          <dd className="truncate text-13 text-content">
            {p.role_types.length
              ? p.role_types.map((r) => r.replace(/_/g, " ")).join(", ")
              : "—"}
          </dd>
        </div>
        <div>
          <dt className="text-11 uppercase tracking-wide text-content-dim">Districts</dt>
          <dd className="truncate text-13 text-content">
            {p.districts.length ? p.districts.join(", ") : "—"}
          </dd>
        </div>
        <div>
          <dt className="text-11 uppercase tracking-wide text-content-dim">Last seen</dt>
          <dd className="tnum text-13 text-content">{p.last_seen ?? "—"}</dd>
        </div>
      </dl>

      {p.recent_cases.length > 0 && (
        <ul className="mt-3 divide-y divide-hairline border-t border-hairline">
          {p.recent_cases.map((c, i) => (
            <li
              key={`${c.case_id}-${i}`}
              className="flex flex-wrap items-center justify-between gap-2 py-1.5 text-12"
            >
              <span className="flex min-w-0 items-center gap-2">
                <Badge variant="primary" className="capitalize">
                  {(c.role_type ?? "party").replace(/_/g, " ")}
                </Badge>
                <span className="tnum truncate font-medium text-content">
                  {c.crime_no ?? `Case ${c.case_id ?? "—"}`}
                </span>
                {c.crime_group && <span className="truncate text-content-dim">{c.crime_group}</span>}
              </span>
              <span className="flex items-center gap-2 text-content-dim">
                {c.district && (
                  <span className="inline-flex items-center gap-1">
                    <MapPin className="size-3" aria-hidden />
                    {c.district}
                  </span>
                )}
                {c.registered_date && (
                  <span className="tnum inline-flex items-center gap-1">
                    <CalendarClock className="size-3" aria-hidden />
                    {c.registered_date}
                  </span>
                )}
                {c.case_id != null && (
                  <Button variant="ghost" size="icon-sm" asChild>
                    <Link to={`/cases/${c.case_id}`} aria-label={`Open case ${c.crime_no ?? c.case_id}`}>
                      <ExternalLink />
                    </Link>
                  </Button>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" asChild>
          <Link to={`/people/canonical/${p.canonical_person_id}`}>
            <UserRound /> Open full record
          </Link>
        </Button>
        {onConfirm && (
          <Button
            size="sm"
            variant={match.above_threshold ? "primary" : "secondary"}
            onClick={() => onConfirm(match)}
            disabled={disabled || confirming}
          >
            <CheckCircle2 /> {confirmLabel}
          </Button>
        )}
        {match.gallery_hits > 1 && (
          <span className="text-11 text-content-dim">
            best of {match.gallery_hits} reference photos
          </span>
        )}
      </div>
    </article>
  );
}
