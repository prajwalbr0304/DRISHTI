"""Service configuration, loaded from environment (and the repo-root .env).

Nothing secret is hard-coded. DATABASE_URL is the full read/write connection;
the read-only layer reuses it but assumes the restricted ``readonly_role`` via
SET ROLE + a read-only transaction (see app/db.py).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# services/ml/app/config.py -> parents[3] == repo root (…/DRISHTI)
_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    # Full read/write Postgres connection (Supabase URI).
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
    # sslmode for managed Postgres (Supabase requires TLS).
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

    model_config = SettingsConfigDict(
        env_file=(str(_REPO_ROOT / ".env"), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
