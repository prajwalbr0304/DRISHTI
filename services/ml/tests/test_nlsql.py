"""Phase-2 NL->SQL engine tests.

Security is the point, so most guards are unit-tested WITHOUT a DB (the guard +
scope layers are pure and fire before any connection):
  * injection (stacked statements, comment/dollar-quote smuggling) is rejected,
  * DDL/DML is rejected,
  * a permission-escalation attempt (policymaker reading PII / non-aggregate,
    or anyone touching credential/governance tables) MUST fail,
  * the deterministic planner maps common intents, clarifies otherwise, resolves
    multi-turn pronouns, and never emits an unescaped literal.
Integration (@requires_db) proves valid queries run read-only, the row cap
holds, answers are grounded + cited + persisted, and multi-turn memory works.
"""
import json

import pytest

from app.nlsql import engine, executor, glossary, guard, planner, scope
from app.nlsql.planner import FallbackPlanner, LLMPlanner, Turn
from conftest import requires_db


def _has_kannada(text: str) -> bool:
    return any("\u0c80" <= c <= "\u0cff" for c in text or "")

VALID = (
    'SELECT d."DistrictName", COUNT(*) AS case_count FROM "CaseMaster" cm '
    'JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
    'JOIN "District" d ON d."DistrictID"=u."DistrictID" GROUP BY d."DistrictName"'
)


# ============================ guard (no DB) ================================
def test_guard_allows_plain_select():
    assert guard.validate_select(VALID).lower().startswith("select")


def test_guard_allows_cte():
    cte = ('WITH t AS (SELECT "DistrictID" FROM "District") '
           'SELECT COUNT(*) FROM "CaseMaster"')
    assert guard.validate_select(cte)


def test_guard_preserves_literal_semicolon():
    # a ';' inside a string literal is data, not a statement separator
    out = guard.validate_select("SELECT 'a;b' AS x")
    assert "a;b" in out


@pytest.mark.parametrize("sql", [
    'SELECT 1; DROP TABLE "State"',
    "SELECT 1; SELECT 2",
    'SELECT * FROM "CaseMaster"; DELETE FROM "State"',
])
def test_guard_blocks_stacked_statements(sql):
    with pytest.raises(guard.GuardError):
        guard.validate_select(sql)


@pytest.mark.parametrize("sql", [
    'INSERT INTO "State" ("StateName") VALUES (\'x\')',
    'UPDATE "State" SET "StateName"=\'x\'',
    'DELETE FROM "State"',
    'DROP TABLE "State"',
    'ALTER TABLE "State" ADD COLUMN c int',
    'TRUNCATE "State"',
    'CREATE TABLE evil (id int)',
    'GRANT SELECT ON "State" TO drishti_readonly',
    'SELECT * INTO evil FROM "CaseMaster"',
    'WITH t AS (INSERT INTO "State" VALUES (1) RETURNING 1) SELECT * FROM t',
])
def test_guard_blocks_ddl_dml(sql):
    with pytest.raises(guard.GuardError):
        guard.validate_select(sql)


def test_guard_blocks_comment_smuggling():
    with pytest.raises(guard.GuardError):
        guard.validate_select("SELECT 1 --\nDROP TABLE x")
    with pytest.raises(guard.GuardError):
        guard.validate_select("SELECT 1 /* ; */ ; DROP TABLE x")


def test_guard_blocks_dollar_quote():
    with pytest.raises(guard.GuardError):
        guard.validate_select("SELECT $$ ; drop table x $$")


@pytest.mark.parametrize("sql", [
    "SELECT pg_sleep(10)",
    "SELECT pg_read_file('/etc/passwd')",
    "SELECT * FROM dblink('x','y')",
])
def test_guard_blocks_dangerous_functions(sql):
    with pytest.raises(guard.GuardError):
        guard.validate_select(sql)


def test_guard_rejects_non_select():
    with pytest.raises(guard.GuardError):
        guard.validate_select("VACUUM")


def test_enforce_limits_wraps_with_cap():
    wrapped = guard.enforce_limits(VALID, 200)
    assert wrapped.strip().lower().startswith("select * from")
    assert wrapped.rstrip().lower().endswith("limit 200")


# ============================ scope (no DB) ================================
def test_scope_policymaker_blocked_from_pii():
    for sql in ['SELECT "VictimName" FROM "Victim"',
                'SELECT "AccusedName" FROM "Accused"',
                'SELECT * FROM "FinancialTransaction"']:
        with pytest.raises(scope.ScopeError):
            scope.enforce_scope(sql, "policymaker")


def test_scope_policymaker_requires_aggregate():
    with pytest.raises(scope.ScopeError):
        scope.enforce_scope('SELECT "CrimeNo" FROM "CaseMaster"', "policymaker")


def test_scope_policymaker_allows_aggregate():
    assert scope.enforce_scope('SELECT COUNT(*) FROM "CaseMaster"', "policymaker")


def test_scope_blocks_governance_tables_for_all_roles():
    for role in ("investigator", "analyst", "supervisor", "policymaker", "super_admin"):
        for sql in ('SELECT * FROM users', 'SELECT * FROM audit_logs',
                    'SELECT * FROM "ChatMessage"'):
            with pytest.raises(scope.ScopeError):
                scope.enforce_scope(sql, role)


def test_scope_investigator_may_read_pii():
    # non-aggregate PII read is allowed for an investigator (Phase-14 RLS adds
    # per-jurisdiction limits); the point is scoping is role-specific, not blanket.
    assert scope.enforce_scope('SELECT "VictimName" FROM "Victim"', "investigator")


def test_is_aggregate_no_false_positive_on_column_name():
    # "AccusedMasterID" must not be read as the "Accused" table, and selecting a
    # column is not an aggregate.
    assert scope.is_aggregate('SELECT COUNT(*) FROM "CrimeRiskScore"') is True
    assert scope.is_aggregate('SELECT "AccusedMasterID" FROM "CrimeRiskScore"') is False
    assert scope.enforce_scope('SELECT COUNT(*) FROM "CrimeRiskScore" '
                               'WHERE "AccusedMasterID" IS NOT NULL', "policymaker")


def test_referenced_tables():
    assert scope.referenced_tables(VALID) == {"CaseMaster", "Unit", "District"}


# ====================== executor guard ordering (no DB) ====================
# execute_select runs guard + scope BEFORE it ever connects, so these prove the
# blocks fire pre-database (defense-in-depth over the read-only role).
def test_executor_rejects_dml_before_db():
    with pytest.raises(guard.GuardError):
        executor.execute_select('DELETE FROM "State"', "analyst")


def test_executor_rejects_injection_before_db():
    with pytest.raises(guard.GuardError):
        executor.execute_select('SELECT 1; DROP TABLE "State"', "analyst")


def test_executor_escalation_policymaker_pii_fails():
    # THE escalation guarantee: a policymaker cannot read individual PII, even
    # with hand-crafted SQL — enforced in the executor, not the prompt.
    with pytest.raises(scope.ScopeError):
        executor.execute_select('SELECT "VictimName" FROM "Victim" v '
                                'JOIN "CaseMaster" cm ON cm."CaseMasterID"=v."CaseMasterID"',
                                "policymaker")


def test_executor_escalation_credentials_fails_any_role():
    with pytest.raises(scope.ScopeError):
        executor.execute_select("SELECT * FROM users", "super_admin")


# ============================ planner (no DB) ==============================
@pytest.mark.parametrize("question,intent", [
    ("top 5 districts by theft", "top_districts"),
    ("how many cyber crime FIRs in Bengaluru City", "count"),
    ("monthly trend of robbery", "trend"),
    ("show recent murder cases in Mysuru", "list_cases"),
])
def test_fallback_planner_intents(question, intent):
    plan = FallbackPlanner().plan(question, "analyst", "en", [])
    assert plan.intent == intent
    assert plan.sql and guard.validate_select(plan.sql)   # every emitted SQL is guard-valid


def test_fallback_planner_clarifies_unmatched():
    plan = FallbackPlanner().plan("hello there friend", "analyst", "en", [])
    assert plan.needs_clarification and not plan.sql


def test_fallback_policymaker_list_becomes_aggregate():
    plan = FallbackPlanner().plan("list recent theft cases in Mysuru", "policymaker", "en", [])
    assert plan.sql and scope.is_aggregate(plan.sql)      # no case list for policymaker
    scope.enforce_scope(plan.sql, "policymaker")           # and it passes scope


def test_fallback_multiturn_pronoun_resolution():
    history = [Turn("user", "cyber crime in Bengaluru City"),
               Turn("assistant", "…")]
    plan = FallbackPlanner().plan("how many there?", "analyst", "en", history)
    assert plan.sql and "Bengaluru" in plan.sql and "cyber" in plan.sql.lower()


def test_fallback_escapes_literals():
    assert planner._lit("O'Brien") == "'O''Brien'"


def test_llm_planner_parses_json(monkeypatch):
    import httpx

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            payload = {"sql": 'SELECT COUNT(*) FROM "CaseMaster"',
                       "needs_clarification": False, "confidence": 0.9, "language": "en"}
            return {"choices": [{"message": {"content": json.dumps(payload)}}]}

    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Resp())

    class _S:
        llm_model = "m"
        llm_base_url = "http://x/v1"
        llm_api_key = "k"
        llm_timeout_s = 5.0
        nlsql_max_history_turns = 6

    plan = LLMPlanner(_S()).plan("count cases", "analyst", "en", [])
    assert plan.source == "openai-compatible"     # provider-neutral label (Prompt 19 §B)
    assert plan.sql and guard.validate_select(plan.sql)
    assert not plan.needs_clarification


# ============================ integration (DB) =============================
@requires_db
def test_executor_runs_valid_select_read_only():
    sql, columns, rows = executor.execute_select(VALID, "analyst")
    assert "DistrictName" in columns and "case_count" in columns
    assert isinstance(rows, list)


@requires_db
def test_executor_enforces_row_cap():
    from app.config import get_settings
    cap = get_settings().nlsql_row_cap
    _, _, rows = executor.execute_select('SELECT cm."CaseMasterID" FROM "CaseMaster" cm', "analyst")
    assert len(rows) <= cap


@requires_db
def test_engine_answer_is_grounded_cited_and_persisted():
    from app import db
    o = engine.ask("analyst", "top 5 districts by theft")
    assert not o.blocked and not o.needs_clarification
    assert o.sql and "select" in o.sql.lower()
    assert 0.0 <= o.confidence <= 1.0
    assert o.model_version and "@" in o.model_version
    assert o.session_id
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "GeneratedSQL","Confidence","Sender"::text FROM "ChatMessage" '
                'WHERE "SessionID"=%s AND "Sender"=\'assistant\' ORDER BY "MessageID" DESC LIMIT 1',
                (o.session_id,))
            row = cur.fetchone()
    assert row and row[0] and row[1] is not None      # SQL + confidence persisted


@requires_db
def test_engine_policymaker_answer_is_aggregate_not_blocked():
    o = engine.ask("policymaker", "show recent theft cases in Mysuru")
    assert not o.blocked
    assert o.sql and ("count(" in o.sql.lower() or "group by" in o.sql.lower())


@requires_db
def test_engine_multiturn_memory_resolves_reference():
    t1 = engine.ask("analyst", "cyber crime in Bengaluru City")
    t2 = engine.ask("analyst", "how many there?", session_id=t1.session_id)
    assert t1.session_id == t2.session_id
    assert "Bengaluru" in (t2.sql or "") and "cyber" in (t2.sql or "").lower()


@requires_db
def test_engine_clarifies_ambiguous_without_sql():
    o = engine.ask("analyst", "hello")
    assert o.needs_clarification and not o.sql


# ======================= Kannada / multilingual (Phase 3) ==================
def test_detect_language_en_kn():
    assert engine.detect_language("how many thefts in Mysuru") == "en"
    assert engine.detect_language("ಬೆಂಗಳೂರಿನಲ್ಲಿ ಎಷ್ಟು ಕಳ್ಳತನ") == "kn"
    assert engine.detect_language("") == "en"


def test_glossary_has_core_police_terms():
    gt = glossary.glossary_text()
    # the doc's examples must be present, correctly mapped
    assert "ಎಫ್‌ಐಆರ್" in gt          # FIR
    assert "ಆರೋಪಿ" in gt             # accused
    assert "ಕಳ್ಳತನ" in gt            # theft
    assert gt.count("->") >= 20      # a real curated glossary, not a stub


@pytest.mark.parametrize("question,intent", [
    ("ಬೆಂಗಳೂರಿನಲ್ಲಿ ಎಷ್ಟು ಕಳ್ಳತನ ಪ್ರಕರಣಗಳು", "count"),      # how many thefts in Bengaluru
    ("ಕಳ್ಳತನದಲ್ಲಿ ಟಾಪ್ 5 ಜಿಲ್ಲೆಗಳು", "top_districts"),        # top 5 districts by theft
    ("ದರೋಡೆ ಪ್ರವೃತ್ತಿ", "trend"),                              # robbery trend
    ("ಮೈಸೂರಿನಲ್ಲಿ ಸೈಬರ್ ಪ್ರಕರಣಗಳನ್ನು ತೋರಿಸಿ", "list_cases"),  # show cyber cases in Mysuru
])
def test_fallback_kannada_intents(question, intent):
    plan = FallbackPlanner().plan(question, "analyst", "kn", [])
    assert plan.intent == intent
    assert plan.sql and guard.validate_select(plan.sql)   # KN questions still yield guard-valid SQL
    assert plan.language == "kn"


def test_fallback_kannada_resolves_district_and_crime():
    plan = FallbackPlanner().plan("ಬೆಂಗಳೂರಿನಲ್ಲಿ ಎಷ್ಟು ಸೈಬರ್ ಅಪರಾಧ", "analyst", "kn", [])
    assert "Bengaluru" in plan.sql and "cyber" in plan.sql.lower()


def test_fallback_kannada_multiturn_pronoun():
    history = [Turn("user", "ಬೆಂಗಳೂರಿನಲ್ಲಿ ಸೈಬರ್ ಅಪರಾಧ"), Turn("assistant", "…")]
    plan = FallbackPlanner().plan("ಅಲ್ಲಿ ಎಷ್ಟು?", "analyst", "kn", history)   # "how many there?"
    assert plan.sql and "Bengaluru" in plan.sql and "cyber" in plan.sql.lower()


def test_kannada_scope_still_enforced_for_policymaker():
    # a KN 'show cases' request from a policymaker must still be aggregated (no list)
    plan = FallbackPlanner().plan("ಪ್ರಕರಣಗಳನ್ನು ತೋರಿಸಿ", "policymaker", "kn", [])
    assert plan.sql and scope.is_aggregate(plan.sql)
    scope.enforce_scope(plan.sql, "policymaker")


@requires_db
def test_engine_answers_in_kannada():
    o = engine.ask("analyst", "ಕಳ್ಳತನದಲ್ಲಿ ಟಾಪ್ 5 ಜಿಲ್ಲೆಗಳು")
    assert o.language == "kn"
    assert not o.blocked
    assert _has_kannada(o.reply)      # the reply is in the asked language


# ======================= Voice + translate (Phase 4/5) =====================
def test_translate_graceful_without_llm(monkeypatch):
    from app.config import get_settings
    from app.chat import service as chat_service
    # force "no model configured" regardless of the dev environment
    monkeypatch.setattr(get_settings(), "llm_api_key", "", raising=False)
    r = chat_service.translate("ಬೆಂಗಳೂರಿನಲ್ಲಿ ಎಷ್ಟು ಕಳ್ಳತನ", "en")
    assert r.target == "en"
    assert r.available is False and r.translated is None   # never fabricates


@requires_db
def test_engine_persists_low_confidence_voice_transcript():
    from app import db
    o = engine.ask("analyst", "top 5 districts by theft",
                   voice={"confidence": 0.4, "language": "en"})
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT vt."Confidence"::float, vt."IsLowConfidence", vt."TranscriptText" '
                'FROM "VoiceTranscript" vt JOIN "ChatMessage" m ON m."MessageID"=vt."MessageID" '
                'WHERE m."SessionID"=%s', (o.session_id,))
            row = cur.fetchone()
    assert row is not None
    assert abs(row[0] - 0.4) < 1e-6
    assert row[1] is True                         # flagged low-confidence (<0.6)
    assert row[2] == "top 5 districts by theft"


@requires_db
def test_engine_high_confidence_voice_not_flagged():
    from app import db
    o = engine.ask("analyst", "how many cyber cases in Mysuru",
                   voice={"confidence": 0.95, "language": "en"})
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT vt."IsLowConfidence" FROM "VoiceTranscript" vt '
                'JOIN "ChatMessage" m ON m."MessageID"=vt."MessageID" WHERE m."SessionID"=%s',
                (o.session_id,))
            row = cur.fetchone()
    assert row is not None and row[0] is False


@requires_db
def test_engine_no_voice_no_transcript():
    from app import db
    o = engine.ask("analyst", "top 3 districts by robbery")   # typed, not spoken
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT COUNT(*) FROM "VoiceTranscript" vt '
                'JOIN "ChatMessage" m ON m."MessageID"=vt."MessageID" WHERE m."SessionID"=%s',
                (o.session_id,))
            n = cur.fetchone()[0]
    assert n == 0
