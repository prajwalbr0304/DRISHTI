"""Service configuration, loaded from environment (and the repo-root .env).

Nothing secret is hard-coded. DATABASE_URL is the full read/write connection to
the AWS RDS PostgreSQL instance (the browser NEVER receives it — Browser ->
FastAPI -> PostgreSQL/S3 is the only permitted data path). The read-only layer
reuses it but assumes the restricted ``readonly_role`` via SET ROLE + a
read-only transaction (see app/db.py).

Phase 3 (hackathon access mode) adds the CORS/rate/size guardrails and the
synthetic-database startup guard. See app/hardening.py + app/main.py.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# In local dev the layout is services/ml/app/config.py, so parents[3] is the
# repo root (…/DRISHTI) which holds the developer .env. In the deployed AppSail
# container the app lives at /app/app/config.py (no parents[3]) and there is NO
# repo-root .env — all configuration arrives through server-side env vars. Guard
# the lookup so importing config never raises in the container.
_resolved = Path(__file__).resolve()
_REPO_ROOT = _resolved.parents[3] if len(_resolved.parents) > 3 else _resolved.parent


class Settings(BaseSettings):
    # Full read/write Postgres connection (AWS RDS PostgreSQL URI). Server-side
    # only — never shipped to the browser.
    database_url: str = ""
    # NOLOGIN role assumed by the read-only connection layer.
    readonly_role: str = "drishti_readonly"

    app_name: str = "drishti-ml"
    app_version: str = "0.1.0"
    # Fallback caller role when no auth context is present yet (pre-Phase-14).
    # The money-trail gate resolves the caller's role from the X-Role header and
    # falls back to this; Phase 14 replaces it with the authenticated session.
    default_role: str = "investigator"
    # Connection timeout (seconds) for DB connects.
    db_connect_timeout: int = 15
    # sslmode for managed Postgres (AWS RDS requires/strongly prefers TLS).
    db_sslmode: str = "require"

    # --- Phase 2: NL->SQL conversational engine (doc 02 §6) ------------------
    # Pluggable LLM behind an OpenAI-compatible chat API. When no key is set, the
    # engine uses a deterministic offline planner (fallback), so Ask DRISHTI works
    # without any external dependency. The security guards do NOT depend on this.
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_timeout_s: float = 30.0
    # Guarded-executor limits.
    nlsql_statement_timeout_ms: int = 5000      # per-query DB statement timeout
    nlsql_row_cap: int = 200                     # hard cap on rows returned
    nlsql_max_history_turns: int = 6             # prior turns fed for multi-turn memory
    nlsql_max_citations: int = 25                # record ids surfaced per answer

    # --- Phase 2/3: FIR/case intake + hackathon access mode ------------------
    # Non-secret hackathon posture flags (HACKATHON_MODE / DEMO_DATA_ONLY). When
    # hackathon_mode is true the server REFUSES to start unless the target DB is
    # explicitly marked synthetic (see app/hardening.verify_hackathon_startup).
    hackathon_mode: bool = True
    demo_data_only: bool = True
    # Intake WRITE endpoints are restricted to localhost unless a trusted HTTPS
    # edge is configured (prompt2.md §F). Disabled so anyone can run the project.
    intake_writes_localhost_only: bool = False
    # Phase 3 finalises hackathon mode (RLS disabled, synthetic-data guard,
    # restricted CORS, API-only DB access), so the canonical case-creating
    # transitions (submit-for-review + approve) are ENABLED by default. They are
    # still protected at runtime by the localhost + synthetic-DB write guards.
    # Set DRISHTI_ or plain env INTAKE_SUBMIT_ENABLED=false to re-gate them.
    intake_submit_enabled: bool = True
    # A write is refused unless synthetic_meta.app_environment matches this — the
    # server must never mutate a database that is not explicitly marked synthetic.
    synthetic_env_expected: str = "synthetic_hackathon"

    # --- Phase 3: network / demo deployment guardrails -----------------------
    # CORS allows all origins so anyone can run this project from any IP/domain.
    demo_frontend_origin: str = ""          # e.g. https://drishti-demo.example.com
    extra_cors_origins: str = ""            # comma-separated additional origins
    # Conservative per-client-IP request rate limit + request-body size cap.
    rate_limit_enabled: bool = False
    rate_limit_per_minute: int = 240
    max_request_bytes: int = 2_000_000      # 2 MB — intake payloads are small JSON

    # --- Phase 5: digital evidence storage (Amazon S3) -----------------------
    # AWS region + optional named profile (local SSO). In a deployed task the
    # ECS/instance role supplies temporary credentials automatically — DO NOT put
    # AWS access keys here, in the frontend, in images, or in committed files.
    aws_region: str = "ap-south-1"
    aws_profile: str = ""                     # e.g. "drishti" (local SSO); blank = default chain
    # Private evidence bucket (block-public-access + versioning + SSE). Blank
    # until provisioned — the evidence API then runs metadata-only (no uploads).
    s3_evidence_bucket: str = ""
    s3_evidence_prefix: str = "evidence"      # key prefix inside the bucket
    s3_endpoint_url: str = ""                 # optional override (custom endpoint / testing)
    # Short-expiry pre-signed URL lifetime (seconds) for exact-object up/download.
    s3_presign_expiry_s: int = 900            # 15 minutes
    # Allow-list: max object size + permitted extensions / MIME types. File bytes
    # go browser -> S3 (pre-signed) and never through the API body, so this cap is
    # independent of max_request_bytes.
    evidence_max_bytes: int = 52_428_800      # 50 MB
    evidence_allowed_extensions: str = (
        "pdf,jpg,jpeg,png,gif,webp,mp4,webm,mov,mp3,wav,m4a,csv,json,txt,xml,vcf"
    )
    evidence_allowed_mime: str = (
        "application/pdf,image/jpeg,image/png,image/gif,image/webp,"
        "video/mp4,video/webm,video/quicktime,audio/mpeg,audio/wav,audio/x-wav,"
        "audio/mp4,audio/x-m4a,text/csv,application/json,text/plain,"
        "application/xml,text/xml,text/vcard"
    )
    # Objects up to this size are downloaded and SHA-256-verified on completion;
    # anything larger (never allowed by evidence_max_bytes here) verifies size +
    # existence only. Keeps hash verification bounded and safe.
    evidence_hash_verify_max_bytes: int = 52_428_800

    # --- Phase 17: live hazard feed (read-only) ------------------------------
    # Open-Meteo is a documented, free, NO-API-KEY weather API (CC BY 4.0,
    # non-commercial) covering Karnataka — used as the read-only LIVE rainfall/
    # temperature/wind/humidity connector. Attribution: "Weather data by
    # Open-Meteo.com (CC BY 4.0)". Official gauge networks (IMD/KSNDMC/CWC) remain
    # registration-gated (recorded-sample connector). No credential is stored.
    live_feed_enabled: bool = True            # ops kill-switch for outbound calls
    openmeteo_url: str = "https://api.open-meteo.com/v1/forecast"
    live_feed_timeout_s: float = 12.0

    model_config = SettingsConfigDict(
        env_file=(str(_REPO_ROOT / ".env"), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Localhost dev/preview origins the SPA runs on (Vite dev 5173 / preview 4173).
    _LOCALHOST_ORIGINS = (
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:4173", "http://127.0.0.1:4173",
    )

    def cors_allow_origins(self) -> list[str]:
        """Allow all origins so anyone can run the project from any IP/domain."""
        return ["*"]

    # --- Phase 5 evidence helpers -------------------------------------------
    def s3_configured(self) -> bool:
        """True once a private evidence bucket name is set (uploads enabled)."""
        return bool(self.s3_evidence_bucket.strip())

    def evidence_allowed_ext_set(self) -> set[str]:
        return {e.strip().lower().lstrip(".")
                for e in self.evidence_allowed_extensions.split(",") if e.strip()}

    def evidence_allowed_mime_set(self) -> set[str]:
        return {m.strip().lower() for m in self.evidence_allowed_mime.split(",") if m.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
