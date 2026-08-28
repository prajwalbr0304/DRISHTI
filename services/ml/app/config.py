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

# Bedrock is fail-closed to an exact reviewed Chinese-origin identity, so an
# environment change cannot silently switch DRISHTI to Claude, GPT/OpenAI, or
# another unapproved provider. Arbitrary endpoint providers are disabled below.
APPROVED_CHINESE_BEDROCK_MODELS = frozenset({"zai.glm-4.7-flash"})


def is_approved_chinese_bedrock_model(model_id: str) -> bool:
    """Bedrock is restricted to exact reviewed model IDs (fail closed)."""
    return (model_id or "").strip().lower() in APPROVED_CHINESE_BEDROCK_MODELS

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
    default_role: str = "investigating_officer"
    # Connection timeout (seconds) for DB connects.
    db_connect_timeout: int = 15
    # sslmode for managed Postgres (AWS RDS requires/strongly prefers TLS).
    db_sslmode: str = "require"

    # --- Prompt 19 §A: query-voice vs evidence-extraction scope --------------
    # Voice DICTATION of a question and spoken read-back of the answer are IN
    # hackathon scope. This is deliberately kept SEPARATE from evidence
    # extraction: OCR, uploaded-document parsing, automatic FIR field extraction,
    # evidence-media transcription and face/object recognition remain OUT of
    # scope. The two are named as INDEPENDENT flags so enabling voice query can
    # never silently turn on evidence extraction. query_voice may be true;
    # evidence_extraction MUST stay false for this submission.
    query_voice_enabled: bool = True
    evidence_extraction_enabled: bool = False

    # --- Prompt 19 §B: semantic planner (Chinese-model-only, fail-closed) ----
    # Semantic planning is restricted to reviewed Chinese-origin model families.
    # There is no Claude, GPT/OpenAI, or other commercial-model fallback. The
    # engine FAILS CLOSED to the labelled deterministic planner when a provider,
    # model identity, or network path is unavailable; SQL safety never depends on
    # model cooperation.
    #   "" (unset)    -> deterministic offline planner is the primary
    #   "aws_bedrock" -> reviewed Chinese model through Bedrock Converse
    # Legacy QuickML/OpenAI-compatible selectors are intentionally disabled
    # because an arbitrary endpoint cannot prove which model it actually serves.
    semantic_planner_provider: str = ""
    # Legacy QuickML serving settings are retained so old environments parse;
    # the arbitrary endpoint selector is disabled by quickml_llm_configured().
    quickml_llm_endpoint: str = ""
    quickml_llm_model: str = ""
    quickml_llm_api_key: str = ""
    quickml_llm_timeout_s: float = 30.0
    # Legacy arbitrary OpenAI-compatible transport settings are retained only so
    # old environments still parse; selection is disabled by
    # openai_compatible_configured() and these values are never invoked.
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""
    llm_timeout_s: float = 30.0
    # Amazon Bedrock Runtime. Local development may use an AWS SSO profile.
    # Catalyst AppSail has no AWS credentials; when its signed AWS adapter is
    # configured, BedrockPlanner routes Converse through that Lambda execution
    # role instead. GLM 4.7 Flash is available in the adapter's Mumbai region.
    bedrock_region: str = "ap-south-1"
    bedrock_model_id: str = ""
    bedrock_aws_profile: str = ""
    # Explicit local-development escape hatch. It stays false in AppSail, where
    # the signed adapter is mandatory and no AWS credential may be installed.
    bedrock_direct_sdk_enabled: bool = False
    bedrock_timeout_s: float = 30.0
    # Guarded-executor limits.
    nlsql_statement_timeout_ms: int = 5000      # per-query DB statement timeout
    nlsql_row_cap: int = 200                     # hard cap on rows returned
    nlsql_max_history_turns: int = 6             # prior turns fed for multi-turn memory
    nlsql_max_citations: int = 25                # record ids surfaced per answer
    # Voice transcript below this recogniser confidence is flagged low-confidence
    # and must be confirmed/edited before it can execute (Prompt 19 §E.3).
    voice_low_confidence_threshold: float = 0.6

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
    # CORS is an EXACT allow-list (localhost dev/preview + the configured demo
    # origin(s)). No wildcard by default: the deployed browser only talks to a
    # known origin, and the release gate (Prompts 22/25) fails on wildcard
    # production CORS. A purely-local throwaway demo that must accept any origin
    # can opt in with DRISHTI_CORS_ALLOW_ALL=true; the deployed AppSail never sets it.
    demo_frontend_origin: str = ""          # e.g. https://drishti-demo.example.com
    extra_cors_origins: str = ""            # comma-separated additional origins
    cors_allow_all: bool = False            # opt-in wildcard for a local-only demo
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
        """Exact allow-list of CORS origins (localhost + configured demo origin).
        No wildcard in hackathon/deployed mode: the browser only talks to a known
        origin. ``DRISHTI_CORS_ALLOW_ALL=true`` opts a local-only demo into ``*``.
        """
        if self.cors_allow_all:
            return ["*"]
        origins = list(self._LOCALHOST_ORIGINS)
        if self.demo_frontend_origin.strip():
            origins.append(self.demo_frontend_origin.strip())
        for extra in self.extra_cors_origins.split(","):
            e = extra.strip()
            if e and e not in origins:
                origins.append(e)
        return origins

    # --- Phase 5 evidence helpers -------------------------------------------
    def s3_configured(self) -> bool:
        """True once a private evidence bucket name is set (uploads enabled)."""
        return bool(self.s3_evidence_bucket.strip())

    def stratus_evidence_configured(self) -> bool:
        """True when Catalyst Stratus is the evidence object store (the deployed
        AppSail has no AWS creds, so evidence files live in Stratus, not S3)."""
        import os
        return (os.getenv("DRISHTI_USE_CATALYST_STRATUS", "").strip().lower() == "true"
                and bool(os.getenv("DRISHTI_STRATUS_EVIDENCE_BUCKET", "").strip()))

    def storage_configured(self) -> bool:
        """True when evidence FILES can be stored — either a private S3 bucket
        (local/AWS) or the Catalyst Stratus evidence bucket (deployed AppSail)."""
        return self.s3_configured() or self.stratus_evidence_configured()

    def evidence_allowed_ext_set(self) -> set[str]:
        return {e.strip().lower().lstrip(".")
                for e in self.evidence_allowed_extensions.split(",") if e.strip()}

    def evidence_allowed_mime_set(self) -> set[str]:
        return {m.strip().lower() for m in self.evidence_allowed_mime.split(",") if m.strip()}

    # --- Prompt 19 semantic-planner helpers ---------------------------------
    def semantic_provider(self) -> str:
        """Normalised semantic-planner provider id ("" when none configured)."""
        return (self.semantic_planner_provider or "").strip().lower()

    def quickml_llm_configured(self) -> bool:
        """Legacy arbitrary QuickML serving endpoints are disabled.

        The deployed semantic path is exact-model Bedrock; a configurable chat
        completions URL cannot prove the identity of the model behind it.
        """
        return False

    def openai_compatible_configured(self) -> bool:
        """The legacy arbitrary OpenAI-compatible transport is disabled.

        Chinese models must use the governed Catalyst QuickML endpoint or the
        exact-model Bedrock adapter; an arbitrary URL cannot prove model identity.
        """
        return False

    def bedrock_model_allowed(self) -> bool:
        """True only for an exact, reviewed Chinese-origin Bedrock model ID."""
        return is_approved_chinese_bedrock_model(self.bedrock_model_id)

    def bedrock_configured(self) -> bool:
        """True only once an approved Chinese Bedrock model is selected."""
        return self.bedrock_model_allowed()

    def primary_planner_name(self) -> str:
        """The planner that SHOULD serve in the live-ready contract, given config.
        The deterministic offline planner is the honest primary when nothing is
        configured (local/offline demo)."""
        provider = self.semantic_provider()
        # Preserve the configured intent even when the model is absent/rejected;
        # the engine then reports a degraded aws-bedrock -> deterministic fallback
        # instead of disguising a policy/configuration failure as normal offline mode.
        if provider == "aws_bedrock":
            return "aws-bedrock"
        return "deterministic-fallback"


@lru_cache
def get_settings() -> Settings:
    return Settings()
