---
name: catalyst-deployment
description: Safely inventory, plan, validate, deploy, live-verify, roll back, and document DRISHTI Zoho Catalyst resources in the existing India-DC project. Use for Prompts 21, 23, 25, and 26 Catalyst data-boundary or cloud evidence work.
---

# DRISHTI Catalyst Deployment

Only the `catalyst-operator` may mutate Catalyst resources.

## Preflight

1. Verify the existing DHRISTI project `48361000000030003`, organization `60075362708`, and India DC.
2. Run `scripts/catalyst_preflight.py --repo <root> --dc in --phase <N>`.
3. Inventory actual Authentication, API Gateway, AppSail, Slate/Web Client, Data Store, Stratus, Functions, Signals, schedules, QuickML, Zia, SmartBrowz, Mail, and Push state.
4. Record existing component IDs before creating anything.
5. Resolve placeholders and configuration errors before deployment.

Follow `references/deployment-order.md`.

## Mutation

- Write a redacted change plan and cost/rollback notes first.
- Reuse intended compatible components; never create a duplicate project/application.
- Deploy in dependency order and stop on the first failed mandatory stage.
- Keep operational data in Data Store/Stratus and public access through Gateway/AppSail.
- Use unavailable/not-used statuses honestly; never substitute configuration or a mock for live proof.

## Verification

Capture authenticated live invocation results, component IDs/URLs without secrets, timestamps, exit codes, and artifact hashes. Verify one real Signal and scheduled job when required, then exercise rollback. The primary orchestrator runs the strict phase gate.
