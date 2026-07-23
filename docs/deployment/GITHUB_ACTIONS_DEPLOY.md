# GitHub Actions → Zoho Catalyst auto-deploy (frontend)

`.github/workflows/deploy-catalyst.yml` builds the DRISHTI web client and deploys it to
the existing Catalyst project **DHRISTI** (`48361000000030003`, India DC) on every push to
`main` that touches `web/**`. This is the reliable auto-deploy path (the Slate Git
auto-deploy was not firing).

## One-time setup (owner)

1. **Generate a Catalyst CLI token** (you are already logged in on your machine):
   ```
   catalyst token:generate --current
   ```
   Copy the printed token. (`--current` returns the token for your active CLI session —
   no device-verification step. Without `--current`, `catalyst token:generate` starts a
   device-verification flow instead.)

2. **Add it as a GitHub Actions secret:**
   GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `CATALYST_TOKEN`
   - Value: the token from step 1

That's the only secret needed. `VITE_API_BASE_URL` (the live API Gateway origin) is already
committed in `web/.env.production`, and the project/DC binding comes from
`infra/catalyst/.catalystrc`.

## What runs on push to `main`

1. `npm ci` + `npm run build` in `web/` (production build; `check-bundle-secrets` fails the
   build if a secret/DB/AWS URL leaks into the bundle).
2. Stage `web/dist` into `infra/catalyst/client/` (keeps the committed
   `client-package.json`).
3. `catalyst deploy client --token $CATALYST_TOKEN` from `infra/catalyst/`.

Trigger manually anytime via the **Actions** tab → *Deploy frontend to Zoho Catalyst* →
**Run workflow**.

## Scope + safety notes

- **Frontend only.** Functions and AppSail are intentionally **not** deployed here:
  `catalyst deploy --only functions` resets each function's Console environment, which
  would break the live `prediction-requested` Signal and the `drishti_forecast` cron
  (they depend on `ZOHO_APPSAIL_SIGNING_SECRET` set in the Console). Deploy those manually
  and re-apply the secret, per `docs/phase-reports/PHASE_23_REPORT.md` §7.
- The token authorizes CLI actions as its owner — treat it like a credential. Rotate it
  after the hackathon (`catalyst token:generate` a new one; the old one can be revoked
  from the Catalyst Console).
- If your live frontend is a **named Slate app** rather than the project client, change the
  final step to `catalyst deploy slate <app-name> --token "$CATALYST_TOKEN"` (run from
  `web/dist`) to target that app.
