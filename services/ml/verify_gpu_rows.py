"""Independently verify that GPU-backed forecast rows really landed in the DB.

Reads "CrimePrediction" directly and reports the provenance fields the GPU path is
supposed to stamp into Features: actual_device, gpu_name, model_artifact_digest,
served_via. Fails loudly if any timesfm row is not marked cuda.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import db  # noqa: E402

Q_SUMMARY = """
SELECT p."Features"->>'layer'          AS layer,
       p."Features"->>'actual_device'  AS device,
       p."Features"->>'gpu_name'       AS gpu,
       p."Features"->>'served_via'     AS served_via,
       count(*)                        AS rows,
       min(p."PredictionStart")        AS start,
       max(p."PredictionEnd")          AS finish
FROM "CrimePrediction" p
GROUP BY 1,2,3,4
ORDER BY 5 DESC
"""

Q_SAMPLE = """
SELECT p."DistrictID",
       p."PredictedCount",
       p."Confidence",
       p."Features"->>'district'                AS district,
       p."Features"->>'gpu_name'                AS gpu,
       p."Features"->>'actual_device'           AS device,
       jsonb_array_length((p."Features"->'trajectory')::jsonb) AS traj_steps,
       (p."Features"->'trajectory'->0->>'median') AS next_median,
       (p."Features"->'trajectory'->0->>'p10')    AS next_p10,
       (p."Features"->'trajectory'->0->>'p90')    AS next_p90
FROM "CrimePrediction" p
WHERE p."Features"->>'layer' = 'timesfm'
ORDER BY p."PredictedCount" DESC
LIMIT 8
"""

Q_MV = """
SELECT m."ModelVersionID", m."ModelName", m."Version", m."Framework", m."ModelType"
FROM "ModelVersion" m
WHERE m."ModelName" = 'drishti-timesfm-2.5-200m'
ORDER BY m."ModelVersionID" DESC LIMIT 3
"""


def main() -> int:
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            print("=== CrimePrediction rows by layer / device ===")
            cur.execute(Q_SUMMARY)
            bad = 0
            for layer, device, gpu, served, rows, start, finish in cur.fetchall():
                print(f"  layer={layer!s:<12} device={device!s:<6} gpu={gpu!s:<10} "
                      f"served_via={served!s:<20} rows={rows:<5} {start} -> {finish}")
                if layer == "timesfm" and device != "cuda":
                    bad += rows

            print("\n=== top timesfm districts (GPU-backed) ===")
            cur.execute(Q_SAMPLE)
            for r in cur.fetchall():
                (did, cnt, conf, dname, gpu, dev, steps, med, p10, p90) = r
                print(f"  district {did:<4} {str(dname)[:22]:<22} predicted={float(cnt):>8.2f} "
                      f"conf={float(conf):.4f} steps={steps} "
                      f"next[p10/med/p90]={p10}/{med}/{p90} {dev}/{gpu}")

            print("\n=== ModelVersion registrations ===")
            cur.execute(Q_MV)
            for mv in cur.fetchall():
                print(f"  id={mv[0]} name={mv[1]} version={mv[2]} "
                      f"framework={mv[3]} type={mv[4]}")

    if bad:
        print(f"\n[FAIL] {bad} timesfm row(s) not marked device=cuda")
        return 1
    print("\n[OK] every timesfm row is stamped device=cuda")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
