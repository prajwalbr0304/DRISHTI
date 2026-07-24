# Next DRISHTI session

- Phase: 25
- Status: blocked
- Updated: 2026-07-24T19:23:06+05:30
- Next action: Prompt 25 PENDING per rule J: strict acceptance (scripts/release_accept.py) returns non-zero. All local/security/AWS-model/load/recovery suites GREEN + local gate 16/16; the ONLY blocker is live-edge authorization. Remediate then re-run release_accept.py: RB-1 set DRISHTI_DEMO_AUTH=false on gateway_api + create 6 Catalyst users (drishti_role/district_id/unit_id) + re-run live six-role allow/deny (unauth /api/* must 401); RB-2 restore live NL /api/ask (QuickML or wired deterministic planner); RB-3 set DRISHTI_AWS_ADAPTER_URL/SECRET on deployed AppSail for the live Signal->adapter->TabFM chain; RB-4 automate IAM login for full browser E2E. See docs/phase-reports/PHASE_25_REPORT.md + POST_HACKATHON_BACKLOG.md. Do NOT start Prompt 26 until 25 is complete.

Read EXECUTION_STATE.json, FILE_MAP.json, DECISIONS.md, RELEASE_REQUIREMENTS.json, this file, the selected phase, and git status before acting.
