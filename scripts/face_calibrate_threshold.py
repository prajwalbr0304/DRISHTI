"""Calibrate the face match threshold against the ACTUAL enrolled gallery.

Why this is needed: the shipped default (0.36) is the widely used ArcFace
shortlist operating point for real photographs. This gallery is synthetic
portraits from a single generator, so different people are systematically more
alike than real people are, and impostor pairs score far above 0.36 — which
would put confident-looking wrong dossiers in front of a reviewer.

Method (no image encoding needed, and no assumption about probe quality):
  * IMPOSTOR distribution — for a random sample of enrolled faces, find each
    one's nearest neighbour BELONGING TO A DIFFERENT PERSON via the pgvector
    HNSW index. That is exactly the score a probe of a stranger would have to
    beat, and taking the max per probe is the honest worst case.
  * GENUINE side — every person has one enrolled portrait and the demo probe is
    that same portrait, so the genuine score is ~0.999 (measured end to end).
    The separation question is therefore "how high do impostors reach".

Feed the result to DRISHTI_FACE_MATCH_THRESHOLD / DRISHTI_FACE_STRONG_THRESHOLD.
Re-run whenever the gallery or the model pack changes.

Read-only. Prints no credentials.

  python scripts/face_calibrate_threshold.py [model_name_substring] [sample_size]
"""
from __future__ import annotations

import os
import statistics
import sys

import psycopg2
from dotenv import load_dotenv

load_dotenv()

WANT = sys.argv[1] if len(sys.argv) > 1 else "buffalo_s"
SAMPLE = int(sys.argv[2]) if len(sys.argv) > 2 else 500

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

cur.execute(
    'SELECT pfe."ModelVersionID", mv."ModelName", COUNT(*) '
    'FROM "PersonFaceEmbedding" pfe '
    'JOIN "ModelVersion" mv ON mv."ModelVersionID" = pfe."ModelVersionID" '
    'WHERE pfe."IsArchived" = FALSE AND mv."ModelName" LIKE %s '
    'GROUP BY pfe."ModelVersionID", mv."ModelName" '
    'ORDER BY COUNT(*) DESC LIMIT 1', (f"%{WANT}%",))
row = cur.fetchone()
if not row:
    print(f"no enrolled gallery matching '{WANT}'")
    raise SystemExit(1)
mv_id, model_name, total = row
print(f"gallery : {model_name} (ModelVersionID {mv_id}) — {total:,} faces")
print(f"sample  : {SAMPLE:,} probes, each compared against the whole gallery\n")

cur.execute(
    'SELECT 1.0 - (a."Embedding" <=> b."Embedding") AS sim, '
    '       a."CanonicalPersonID", b."CanonicalPersonID" '
    'FROM ( '
    '    SELECT "CanonicalPersonID", "Embedding" FROM "PersonFaceEmbedding" '
    '    WHERE "ModelVersionID" = %s AND "IsArchived" = FALSE '
    '    ORDER BY random() LIMIT %s '
    ') a '
    'CROSS JOIN LATERAL ( '
    '    SELECT p."CanonicalPersonID", p."Embedding" '
    '    FROM "PersonFaceEmbedding" p '
    '    WHERE p."ModelVersionID" = %s AND p."IsArchived" = FALSE '
    '      AND p."CanonicalPersonID" <> a."CanonicalPersonID" '
    '    ORDER BY p."Embedding" <=> a."Embedding" LIMIT 1 '
    ') b',
    (mv_id, SAMPLE, mv_id))
rows = cur.fetchall()
sims = sorted(float(r[0]) for r in rows)
if not sims:
    print("no comparisons returned")
    raise SystemExit(1)


def pct(p: float) -> float:
    idx = min(len(sims) - 1, max(0, int(round(p / 100.0 * (len(sims) - 1)))))
    return sims[idx]


print("IMPOSTOR (nearest different person) similarity")
print(f"  n        : {len(sims):,}")
print(f"  min      : {sims[0]:.4f}")
print(f"  median   : {statistics.median(sims):.4f}")
print(f"  p95      : {pct(95):.4f}")
print(f"  p99      : {pct(99):.4f}")
print(f"  max      : {sims[-1]:.4f}")

for t in (0.36, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70):
    over = sum(1 for s in sims if s >= t)
    print(f"  impostors >= {t:.2f} : {over:6,} / {len(sims):,} "
          f"({over / len(sims) * 100:6.2f}%)")

worst = sims[-1]
print(f"\nworst impostor pair: {worst:.4f} "
      f"({rows[[float(r[0]) for r in rows].index(worst)][1]} vs "
      f"{rows[[float(r[0]) for r in rows].index(worst)][2]})")

# Genuine probes of the same portrait land ~0.999, so anything comfortably above
# the impostor ceiling and below ~0.95 keeps every true hit while dropping the
# false ones. Round up to a value an operator can read.
rec = min(0.90, max(0.45, round(worst + 0.05, 2)))
print(f"\nRECOMMENDED DRISHTI_FACE_MATCH_THRESHOLD  = {rec:.2f}")
print(f"RECOMMENDED DRISHTI_FACE_STRONG_THRESHOLD = {max(rec + 0.15, 0.75):.2f}")

cur.close()
conn.close()
