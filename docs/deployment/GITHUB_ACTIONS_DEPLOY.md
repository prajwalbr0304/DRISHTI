# Frontend CI + deploy to Zoho Catalyst

`.github/workflows/deploy-catalyst.yml` runs on every push to `main` that touches `web/`.

## What it always does (no setup needed)

Builds + validates the web client: `tsc --noEmit` → `vite build` → `check-bundle-secrets`
(which fails the build if a secret / DB URL / AWS URL leaks into the bundle). This is a
fast gate that catches a broken build **before** it reaches Catalyst.

## Deploying to the live app — recommended path (Slate Git integration)

The live demo (`drishti-uryfmaue.onslate.in`) is a **Git-integrated Slate app**. The
native "push → auto-deploy" for it is the **Slate Git integration's Auto-Deploy**, not
GitHub Actions:

1. Console → **Slate → `drishti` app → App Settings** (Git integration).
2. Ensure **Auto-Deploy** is **ON** for branch `main`. Re-authorize the GitHub connection
   if deployments stopped tracking new commits.
3. To deploy immediately, click **Create Deployment** (builds the latest `main`).

This is the reliable route because the CLI **cannot** target a Git-managed Slate app
(`catalyst deploy slate drishti` → "not found in config", and `catalyst pull`/create are
interactive), and the classic Web Client Hosting deploy (`catalyst deploy --only client`)
fails for this app with `ZIPSANITIZER_FILES_COUNT_EXCEEDED` — the landing animation ships
hundreds of frame images, which exceed the classic client's file cap (Slate handles it).

## Optional: let GitHub Actions deploy to a CLI-managed Slate app

If you prefer Actions to do the deploy (to a **separate**, CLI-managed Slate app with its
own URL), set both of these, then push:

1. Generate a CLI token locally (you are already logged in — no device verification):
   ```
   catalyst token:generate --current
   ```
2. GitHub repo → **Settings → Secrets and variables → Actions**:
   - **Secret** `CATALYST_TOKEN` = the token from step 1
   - **Variable** `SLATE_APP_NAME` = the CLI-registered Slate app name to deploy to

The deploy step is skipped unless `SLATE_APP_NAME` is set, so the build gate works with no
configuration.

## Scope + safety

- **Frontend only.** Functions/AppSail are **not** deployed here: `catalyst deploy --only
  functions` resets each function's Console env (the signed-context secret the live Signal
  + cron depend on). Deploy those manually and re-apply the secret — see
  `docs/phase-reports/PHASE_23_REPORT.md` §7.
- Treat `CATALYST_TOKEN` like a credential; rotate it after the hackathon.
