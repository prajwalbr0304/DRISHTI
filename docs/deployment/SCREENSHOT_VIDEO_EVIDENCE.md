# DRISHTI — Screenshot / Video Evidence Manifest (Prompt 25 Part H)

> Capture instructions + integrity hashes for demo screenshots/videos. All captures must be
> **synthetic, redacted** (no tokens, cookies, private URLs, account IDs, emails, or real PII)
> and correspond to the **live Catalyst URL**. Hashes of currently-captured media are in
> `artifacts/phase-25/evidence-media-hashes.json` (56 files indexed, SHA-256).

## Integrity index

- Machine-readable hashes: **`artifacts/phase-25/evidence-media-hashes.json`** (regenerate any time with the command below).
- Existing captures: 56 PNGs under `artifacts/phase-23/` (live login + landing + navigation + role-picker + IAM sign-in trigger).

```text
python -c "import hashlib,glob,json,os; files=[]; [files.extend(glob.glob(f'artifacts/{d}/**/*.{e}',recursive=True)) for d in ['phase-23','phase-24','phase-25'] for e in ['png','jpg','jpeg','gif','webm','mp4']]; idx=[{'path':f.replace(os.sep,'/'),'bytes':os.path.getsize(f),'sha256':hashlib.sha256(open(f,'rb').read()).hexdigest()} for f in sorted(set(files))]; json.dump({'count':len(idx),'media':idx},open('artifacts/phase-25/evidence-media-hashes.json','w'),indent=2); print(len(idx))"
```

## Redaction rules (apply before adding any capture)

- Blur/crop any Zoho IAM email, OTP/device code, session cookie, bearer token, AWS account id, or private endpoint.
- Show only synthetic data (the app carries a synthetic-demo badge — keep it visible).
- Never capture the AppSail/RDS/adapter secrets or the Console configuration screens with values.

## Required capture set (one still per mandatory journey + one end-to-end video)

| ID | Capture | Source URL | Status |
|---|---|---|---|
| S1 | Role-card landing (synthetic badge visible) | `drishti-frvfpunc.onslate.in/` (canonical) | Captured (`artifacts/phase-23/_e2e_1_landing.png`); re-capture against canonical URL at demo time |
| S2 | Live Catalyst IAM sign-in trigger | Slate → login | Captured (`artifacts/phase-23/_c2_1_login1.png`) |
| S3 | Ask DRISHTI bilingual answer + typed visual | app → Ask | **Re-capture live (RB-2) or use deterministic local** |
| S4 | Map hotspots/heatmap | app → Map | To capture |
| S5 | Case detail → similar → network | app → Cases | To capture |
| S6 | FIR draft→validate→submit→approve (no pre-approval prediction) | app → Intake | To capture (deterministic local ok) |
| S7 | Evidence upload → Stratus (hash, no OCR) | app → Evidence | To capture |
| S8 | Investigation Board (share/lock/branch/export) | app → Board | To capture |
| S9 | Forecast fan chart (real TimesFM T4 result) | app → Forecast | To capture |
| S10 | Command Center (stats/alerts/workload) | app → Command Center | To capture |
| S11 | Disaster overview → allocation → route/no-route → Board pin | app → Disaster | To capture |
| V1 | End-to-end demo video (≤ 6 min, redacted) | full flow | To capture for submission |

## Capture procedure

1. Open the live Slate URL in a clean browser profile; confirm the synthetic badge.
2. For each journey in `HACKATHON_DEMO_CHECKLIST.md`, capture one still at the grounded-answer/result state.
3. For any live gap (RB-1/RB-2/RB-3), capture the **deterministic local** equivalent and label it "local deterministic demo".
4. Record the end-to-end video following `HACKATHON_DEMO_RUNBOOK.md` §2.
5. Redact per the rules above, place under `artifacts/phase-25/media/`, then regenerate the hash index.

> **Honesty note:** fresh submission captures should be re-taken at demo time against the live URL.
> Prompt 26 independently verifies that screenshots are recent, synthetic, redacted and match the
> deployed Catalyst URL.
