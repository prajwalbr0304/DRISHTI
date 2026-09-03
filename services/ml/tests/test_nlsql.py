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
import pytest

from app.nlsql import briefing, engine, executor, glossary, guard, planner, scope
from app.nlsql.planner import FallbackPlanner, LLMPlanner, Plan, Turn
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
# INTERIM ("all roles have access to everything"): no command role is
# aggregate-only, so the aggregate/PII restriction is exercised through an
# injected aggregate-only role — the enforcement machinery stays covered.
AGG_ONLY = "dgp_state_command"


@pytest.fixture()
def aggregate_only_role(monkeypatch):
    from app.nlsql import schema as nl_schema
    monkeypatch.setattr(nl_schema, "AGGREGATE_ONLY_ROLES", frozenset({AGG_ONLY}))
    return AGG_ONLY


def test_no_command_role_is_aggregate_only():
    from app.nlsql import schema as nl_schema
    from app.roles import FUNCTIONAL_ROLES
    for role in FUNCTIONAL_ROLES:
        assert nl_schema.requires_aggregate(role) is False, role
        assert nl_schema.forbidden_tables(role) == nl_schema.GLOBAL_FORBIDDEN, role
    # Every command role may read individual PII through NL->SQL.
    assert scope.enforce_scope('SELECT "VictimName" FROM "Victim"', AGG_ONLY)
    assert scope.enforce_scope('SELECT "CrimeNo" FROM "CaseMaster"', AGG_ONLY)


def test_scope_aggregate_only_role_blocked_from_pii(aggregate_only_role):
    for sql in ['SELECT "VictimName" FROM "Victim"',
                'SELECT "AccusedName" FROM "Accused"',
                'SELECT * FROM "FinancialTransaction"']:
        with pytest.raises(scope.ScopeError):
            scope.enforce_scope(sql, aggregate_only_role)


def test_scope_aggregate_only_role_requires_aggregate(aggregate_only_role):
    with pytest.raises(scope.ScopeError):
        scope.enforce_scope('SELECT "CrimeNo" FROM "CaseMaster"', aggregate_only_role)


def test_scope_aggregate_only_role_allows_aggregate(aggregate_only_role):
    assert scope.enforce_scope('SELECT COUNT(*) FROM "CaseMaster"', aggregate_only_role)


def test_scope_blocks_governance_tables_for_all_roles():
    for role in ("investigating_officer", "crime_analyst", "sho", "dgp_state_command", "system_admin"):
        for sql in ('SELECT * FROM users', 'SELECT * FROM audit_logs',
                    'SELECT * FROM "ChatMessage"'):
            with pytest.raises(scope.ScopeError):
                scope.enforce_scope(sql, role)


def test_scope_investigator_may_read_pii():
    # non-aggregate PII read is allowed for an investigator (Phase-14 RLS adds
    # per-jurisdiction limits); the point is scoping is role-specific, not blanket.
    assert scope.enforce_scope('SELECT "VictimName" FROM "Victim"', "investigating_officer")


def test_is_aggregate_no_false_positive_on_column_name():
    # "AccusedMasterID" must not be read as the "Accused" table, and selecting a
    # column is not an aggregate.
    assert scope.is_aggregate('SELECT COUNT(*) FROM "CrimeRiskScore"') is True
    assert scope.is_aggregate('SELECT "AccusedMasterID" FROM "CrimeRiskScore"') is False
    assert scope.enforce_scope('SELECT COUNT(*) FROM "CrimeRiskScore" '
                               'WHERE "AccusedMasterID" IS NOT NULL', "dgp_state_command")


def test_referenced_tables():
    assert scope.referenced_tables(VALID) == {"CaseMaster", "Unit", "District"}


# ====================== executor guard ordering (no DB) ====================
# execute_select runs guard + scope BEFORE it ever connects, so these prove the
# blocks fire pre-database (defense-in-depth over the read-only role).
def test_executor_rejects_dml_before_db():
    with pytest.raises(guard.GuardError):
        executor.execute_select('DELETE FROM "State"', "crime_analyst")


def test_executor_rejects_injection_before_db():
    with pytest.raises(guard.GuardError):
        executor.execute_select('SELECT 1; DROP TABLE "State"', "crime_analyst")


def test_executor_escalation_aggregate_only_pii_fails(aggregate_only_role):
    # THE escalation guarantee: an aggregate-only role cannot read individual
    # PII, even with hand-crafted SQL — enforced in the executor, not the prompt.
    with pytest.raises(scope.ScopeError):
        executor.execute_select('SELECT "VictimName" FROM "Victim" v '
                                'JOIN "CaseMaster" cm ON cm."CaseMasterID"=v."CaseMasterID"',
                                aggregate_only_role)


def test_executor_escalation_credentials_fails_any_role():
    with pytest.raises(scope.ScopeError):
        executor.execute_select("SELECT * FROM users", "system_admin")


# ============ model-authored CaseMaster aggregates (no DB) =================
# The seal keeps an unfiltered case aggregate out of the database. It must NOT
# also throw the semantic planner's analysis away: the server composes its
# analytics-eligibility policy around the model's SQL and seals THAT.
_MODEL_AGG = (
    'SELECT "District"."DistrictName", COUNT(*) AS case_count FROM "CaseMaster" '
    'JOIN "Unit" ON "Unit"."UnitID" = "CaseMaster"."PoliceStationID" '
    'JOIN "District" ON "District"."DistrictID" = "Unit"."DistrictID" '
    'WHERE "CaseMaster"."CrimeRegisteredDate" >= \'2024-01-01\' '
    'GROUP BY "District"."DistrictName" ORDER BY case_count DESC LIMIT 3'
)


def test_raw_model_case_aggregate_still_fails_closed():
    # unchanged guarantee: the model's own string cannot cross the boundary
    assert executor.needs_case_aggregate_seal(_MODEL_AGG) is True
    with pytest.raises(scope.ScopeError):
        executor.execute_select(_MODEL_AGG, "crime_analyst")


def test_model_case_aggregate_is_authorized_by_composing_policy():
    sealed = executor.authorize_model_case_aggregate(_MODEL_AGG)
    assert sealed is not None
    text = str(sealed)
    # the model's analysis survives verbatim (date filter + LIMIT 3 intact) …
    assert "'2024-01-01'" in text and "LIMIT 3" in text
    # … but every relation reference now goes through the server's policy CTE
    assert "drishti_case_master_policy" in text
    assert '"CaseMaster"' not in text.split(") SELECT", 1)[1]
    assert 'FROM "CaseMaster" cm_policy_src' in text
    assert '"CaseVersion"' in text          # analytics-eligibility predicate
    assert scope.is_aggregate(text)
    # the composed string satisfies the executor's exact-object seal
    assert executor.needs_case_aggregate_seal(sealed) is False
    scope.enforce_scope(guard.validate_select(sealed), "crime_analyst")


def test_composed_model_aggregate_passes_aggregate_only_scope(aggregate_only_role):
    # the policy CTE it adds ("CaseVersion") must not trip an aggregate-only seat
    sealed = executor.authorize_model_case_aggregate(_MODEL_AGG)
    scope.enforce_scope(guard.validate_select(sealed), aggregate_only_role)


def test_deterministic_plan_is_not_rewrapped():
    plan = FallbackPlanner().plan("top 5 districts by theft", "crime_analyst", "en", [])
    assert executor.needs_case_aggregate_seal(plan.sql) is False


def test_model_case_aggregate_preserves_string_literals():
    sealed = executor.authorize_model_case_aggregate(
        'SELECT COUNT(*) AS n, \'"CaseMaster"\' AS label FROM "CaseMaster" cm')
    assert sealed is not None
    assert '\'"CaseMaster"\'' in str(sealed)     # literal untouched


@pytest.mark.parametrize("sql", [
    'SELECT COUNT(*) FROM "public"."CaseMaster"',            # schema-qualified
    "SELECT COUNT(*) FROM CaseMaster",                        # unquoted
    'WITH x AS (SELECT * FROM "CaseMaster") SELECT COUNT(*) FROM x',  # own CTE
    'SELECT COUNT(*) FROM "CaseMaster" drishti_case_master_policy',   # name clash
    'DELETE FROM "CaseMaster"',                               # not a SELECT
])
def test_model_case_aggregate_fails_closed_when_not_exactly_composable(sql):
    assert executor.authorize_model_case_aggregate(sql) is None


def test_non_case_aggregate_needs_no_seal():
    assert executor.needs_case_aggregate_seal(
        'SELECT COUNT(*) AS n FROM "Unit"') is False
    assert executor.authorize_model_case_aggregate(
        'SELECT COUNT(*) AS n FROM "Unit"') is None


# ============================ planner (no DB) ==============================
@pytest.mark.parametrize("question,intent", [
    ("top 5 districts by theft", "top_districts"),
    ("how many cyber crime FIRs in Bengaluru City", "count"),
    ("monthly trend of robbery", "trend"),
    ("show recent murder cases in Mysuru", "list_cases"),
])
def test_fallback_planner_intents(question, intent):
    plan = FallbackPlanner().plan(question, "crime_analyst", "en", [])
    assert plan.intent == intent
    assert plan.sql and guard.validate_select(plan.sql)   # every emitted SQL is guard-valid


def test_fallback_planner_clarifies_unmatched():
    plan = FallbackPlanner().plan("hello there friend", "crime_analyst", "en", [])
    assert plan.needs_clarification and not plan.sql


@pytest.mark.parametrize("question,intent", [
    # reference-entity counts: no case/FIR word -> count the reference table
    ("how many police stations are there in Mysuru", "count_stations"),
    ("how many districts are there", "count_districts"),
    # naming cases/FIRs makes it a CASE count even when a district/station is
    # also named — otherwise the district-count SQL answers the wrong question
    # and overrides a correct semantic plan.
    ("how many FIRs in Mysuru district", "count"),
    ("how many theft cases were registered at each police station", "count"),
])
def test_fallback_reference_entity_counts_do_not_capture_case_counts(question, intent):
    plan = FallbackPlanner().plan(question, "crime_analyst", "en", [])
    assert plan.intent == intent
    assert plan.sql and guard.validate_select(plan.sql)


def test_fallback_aggregate_only_list_becomes_aggregate(aggregate_only_role):
    plan = FallbackPlanner().plan("list recent theft cases in Mysuru",
                                  aggregate_only_role, "en", [])
    assert plan.sql and scope.is_aggregate(plan.sql)   # no case list for that role
    scope.enforce_scope(plan.sql, aggregate_only_role)  # and it passes scope


def test_fallback_command_role_gets_the_case_list():
    # INTERIM: a command seat asking for a list gets the list, not an aggregate.
    plan = FallbackPlanner().plan("list recent theft cases in Mysuru",
                                  "dgp_state_command", "en", [])
    assert plan.sql and not scope.is_aggregate(plan.sql)
    scope.enforce_scope(plan.sql, "dgp_state_command")


def test_fallback_case_details_by_crime_number():
    plan = FallbackPlanner().plan(
        "give me the case details of 100010033202600001",
        "system_admin",
        "en",
        [],
    )
    assert plan.intent == "case_details"
    assert plan.sql and "100010033202600001" in plan.sql
    assert 'cm."CrimeNo"' in plan.sql and 'cm."BriefFacts"' in plan.sql
    assert guard.validate_select(plan.sql)
    scope.enforce_scope(plan.sql, "system_admin")


def test_fallback_aggregate_only_case_details_clarifies(aggregate_only_role):
    plan = FallbackPlanner().plan(
        "give me the case details of 100010033202600001",
        aggregate_only_role,
        "en",
        [],
    )
    assert plan.needs_clarification
    assert not plan.sql


def test_briefing_detects_admin_dashboard_without_case_brief_collision():
    assert briefing.is_briefing_request("give me the dashboard brief of admin dashboard")
    assert briefing.is_briefing_request("can you tell me about the dashboard you are currently in")
    assert briefing.is_briefing_request("describe the current dashboard")
    assert not briefing.is_briefing_request("brief facts of case 100010033202600001")


@pytest.mark.parametrize("question,canonical", [
    ("how many cases are there in Mysore", "Mysuru"),
    ("how many cases are there in Belgaum", "Belagavi"),
    ("how many cases are there in Bellary", "Ballari"),
    ("how many cases are there in Gulbarga", "Kalaburagi"),
    ("how many cases are there in Bangalore", "Bengaluru City"),
    ("Mangaluru alli eshtu cases", "Dakshina Kannada"),
])
def test_fallback_normalizes_common_district_aliases(question, canonical):
    plan = FallbackPlanner().plan(question, "system_admin", "en", [])
    assert plan.intent == "count"
    assert plan.filters["places"] == [canonical]
    assert canonical in str(plan.sql)


def test_fallback_counts_multiple_named_districts_separately():
    plan = FallbackPlanner().plan(
        "how many cases are there in Mysore and Belgaum", "system_admin", "en", [])
    assert plan.intent == "count_by_district"
    assert plan.filters["places"] == ["Mysuru", "Belagavi"]
    assert "Mysuru" in str(plan.sql) and "Belagavi" in str(plan.sql)
    assert "GROUP BY" in str(plan.sql)


def test_fallback_resolves_north_karnataka_to_explicit_districts():
    plan = FallbackPlanner().plan(
        "how many cases are there in North Karnataka", "system_admin", "en", [])
    assert plan.intent == "count"
    assert plan.filters["region"] == "North Karnataka"
    assert len(plan.filters["region_districts"]) == 14
    assert all(name in str(plan.sql) for name in ("Belagavi", "Kalaburagi", "Vijayapura"))


def test_semantic_sql_must_cover_every_resolved_district():
    filters = planner._extract("cases in Mysore and Belgaum")
    assert planner.sql_covers_resolved_jurisdictions(
        'SELECT COUNT(*) FROM "District" WHERE "DistrictName" IN (\'Mysuru\', \'Belagavi\')',
        filters,
    )
    assert not planner.sql_covers_resolved_jurisdictions(
        'SELECT COUNT(*) FROM "District" WHERE "DistrictName" = \'Mysore\'',
        filters,
    )


def test_engine_preserves_multi_district_breakdown():
    semantic = Plan(
        sql=(
            'SELECT COUNT(*) FROM "CaseMaster" cm '
            'JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
            'JOIN "District" d ON d."DistrictID"=u."DistrictID" '
            'WHERE d."DistrictName" IN (\'Mysuru\', \'Belagavi\')'
        ),
        intent="count",
        confidence=0.95,
        language="en",
    )
    fallback = FallbackPlanner().plan(
        "how many cases are there in Mysore and Belgaum", "system_admin", "en", [])

    assert engine._must_use_grounded_jurisdiction_plan(semantic, fallback)


def test_fallback_multiturn_pronoun_resolution():
    history = [Turn("user", "cyber crime in Bengaluru City"),
               Turn("assistant", "…")]
    plan = FallbackPlanner().plan("how many there?", "crime_analyst", "en", history)
    assert plan.sql and "Bengaluru" in plan.sql and "cyber" in plan.sql.lower()


def test_fallback_escapes_literals():
    assert planner._lit("O'Brien") == "'O''Brien'"


def test_schema_validator_rejects_column_from_wrong_table():
    from app.nlsql.schema import SchemaReferenceError, validate_qualified_columns
    bad = ('SELECT cm."DistrictID" FROM "CaseMaster" cm '
           'JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID"')
    with pytest.raises(SchemaReferenceError, match="not a column"):
        validate_qualified_columns(bad)
    validate_qualified_columns(
        'SELECT d."DistrictID" FROM "CaseMaster" cm '
        'JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
        'JOIN "District" d ON d."DistrictID"=u."DistrictID"')
    validate_qualified_columns(
        'SELECT cm."CaseMasterID" FROM "CaseMaster" cm '
        'WHERE cm."BriefFacts" ILIKE \'%cm."DistrictID"%\'')


def test_socioeconomic_and_project_context_routes_are_detected():
    from app.nlsql import project_context
    assert engine._is_socioeconomic_request("Explain the socio-economic correlations with crime, with caveats")
    assert engine._is_socioeconomic_request("Does rainfall have a relationship with crime?")
    assert engine._requested_socioeconomic_indicator(
        "Explain the relationship between literacy and crime") == "literacy_rate"
    assert engine._requested_socioeconomic_indicator(
        "Does rainfall have a relationship with crime?") == "rainfall_mm"
    assert project_context.is_project_context_request("What architecture does DRISHTI use?")
    assert project_context.is_project_context_request("Is this real-time data or synthetic data?")
    assert project_context.is_project_context_request("Is the crime data real-time or synthetic data?")
    assert not project_context.is_project_context_request("How many cases are in Mysuru?")
    assert not project_context.is_project_context_request("How many cases does DRISHTI have?")
    combined = project_context.answer("What architecture and data sources does DRISHTI use?")
    assert "React/Vite" in combined and "synthetic demonstration data" in combined


def test_arbitrary_openai_compatible_planner_fails_closed():
    class _S:
        llm_model = "qwen2.5-14b-instruct"
        llm_base_url = "https://api.openai.com/v1"
        llm_api_key = "not-used"
        llm_timeout_s = 5.0
        nlsql_max_history_turns = 6

    with pytest.raises(RuntimeError, match="disabled"):
        LLMPlanner(_S()).plan("count cases", "crime_analyst", "en", [])


# ============================ integration (DB) =============================
@requires_db
def test_executor_runs_valid_select_read_only():
    sealed = executor.authorize_model_case_aggregate(VALID)
    assert sealed is not None
    sql, columns, rows = executor.execute_select(sealed, "crime_analyst")
    assert "drishti_case_master_policy" in sql
    assert "DistrictName" in columns and "case_count" in columns
    assert isinstance(rows, list)


@requires_db
def test_executor_enforces_row_cap():
    from app.config import get_settings
    cap = get_settings().nlsql_row_cap
    _, _, rows = executor.execute_select('SELECT cm."CaseMasterID" FROM "CaseMaster" cm', "crime_analyst")
    assert len(rows) <= cap


@requires_db
def test_engine_answer_is_grounded_cited_and_persisted():
    from app import db
    o = engine.ask("crime_analyst", "top 5 districts by theft")
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
def test_engine_aggregate_only_answer_is_aggregate_not_blocked(aggregate_only_role):
    o = engine.ask(aggregate_only_role, "show recent theft cases in Mysuru")
    assert not o.blocked
    assert o.sql and ("count(" in o.sql.lower() or "group by" in o.sql.lower())


@requires_db
def test_engine_command_role_answer_is_not_forced_to_aggregate():
    # INTERIM: a command seat is not aggregate-only, so the answer may list rows.
    o = engine.ask("dgp_state_command", "show recent theft cases in Mysuru")
    assert not o.blocked and o.sql


@requires_db
def test_engine_multiturn_memory_resolves_reference():
    t1 = engine.ask("crime_analyst", "cyber crime in Bengaluru City")
    t2 = engine.ask("crime_analyst", "how many there?", session_id=t1.session_id)
    assert t1.session_id == t2.session_id
    assert "Bengaluru" in (t2.sql or "") and "cyber" in (t2.sql or "").lower()


@requires_db
def test_engine_clarifies_ambiguous_without_sql():
    o = engine.ask("crime_analyst", "hello")
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
    plan = FallbackPlanner().plan(question, "crime_analyst", "kn", [])
    assert plan.intent == intent
    assert plan.sql and guard.validate_select(plan.sql)   # KN questions still yield guard-valid SQL
    assert plan.language == "kn"


def test_fallback_kannada_resolves_district_and_crime():
    plan = FallbackPlanner().plan("ಬೆಂಗಳೂರಿನಲ್ಲಿ ಎಷ್ಟು ಸೈಬರ್ ಅಪರಾಧ", "crime_analyst", "kn", [])
    assert "Bengaluru" in plan.sql and "cyber" in plan.sql.lower()


def test_fallback_kannada_multiturn_pronoun():
    history = [Turn("user", "ಬೆಂಗಳೂರಿನಲ್ಲಿ ಸೈಬರ್ ಅಪರಾಧ"), Turn("assistant", "…")]
    plan = FallbackPlanner().plan("ಅಲ್ಲಿ ಎಷ್ಟು?", "crime_analyst", "kn", history)   # "how many there?"
    assert plan.sql and "Bengaluru" in plan.sql and "cyber" in plan.sql.lower()


def test_kannada_scope_still_enforced_for_an_aggregate_only_role(aggregate_only_role):
    # a KN 'show cases' request from an aggregate-only seat must still be
    # aggregated (no case list), in Kannada as in English.
    plan = FallbackPlanner().plan("ಪ್ರಕರಣಗಳನ್ನು ತೋರಿಸಿ", aggregate_only_role, "kn", [])
    assert plan.sql and scope.is_aggregate(plan.sql)
    scope.enforce_scope(plan.sql, aggregate_only_role)


@requires_db
def test_engine_answers_in_kannada():
    o = engine.ask("crime_analyst", "ಕಳ್ಳತನದಲ್ಲಿ ಟಾಪ್ 5 ಜಿಲ್ಲೆಗಳು")
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
    o = engine.ask("crime_analyst", "top 5 districts by theft",
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
    o = engine.ask("crime_analyst", "how many cyber cases in Mysuru",
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
    o = engine.ask("crime_analyst", "top 3 districts by robbery")   # typed, not spoken
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT COUNT(*) FROM "VoiceTranscript" vt '
                'JOIN "ChatMessage" m ON m."MessageID"=vt."MessageID" WHERE m."SessionID"=%s',
                (o.session_id,))
            n = cur.fetchone()[0]
    assert n == 0
