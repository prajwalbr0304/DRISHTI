"""Shared infrastructure for the DRISHTI Datagen v2 scenario-driven generator.

This module holds the small, dependency-free building blocks every v2 domain
module uses so there are no circular imports:

  * ``Seq``      — a monotonic id allocator (canonical ids are minted here,
                    never derived from names / A1-A2 sequences / array indexes).
  * ``TABLES``   — the central registry mapping every target table to its exact,
                    ordered, quoted column list (single source of truth for the
                    COPY loader).
  * ``World``    — the mutable accumulator the domain builders append rows to,
                    plus stable identity maps and scenario-coverage counters.
  * ``Fixture``  — the ordered, load-ready result (a list of ``LoadOp``) plus the
                    scenario coverage / run metadata the loader persists.

Nothing here touches the database.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

# --- unmistakably-synthetic public-ref helpers ------------------------------
# Every externally visible identifier is prefixed so it can NEVER be mistaken
# for a copied real-world identifier (roadmap §27.4).
SYN_PREFIX = "SYN"


def person_ref(n: int) -> str:
    return f"{SYN_PREFIX}-PERSON-{n:07d}"


def org_ref(n: int) -> str:
    return f"{SYN_PREFIX}-ORG-{n:06d}"


def entity_ref(n: int) -> str:
    return f"{SYN_PREFIX}-ENT-{n:07d}"


def synth_token(kind: str, n: int) -> str:
    return f"{SYN_PREFIX}-{kind.upper()}-{n:08d}"


class Seq:
    """A simple monotonic counter starting at ``start`` (default 1)."""

    __slots__ = ("_n",)

    def __init__(self, start: int = 1):
        self._n = start - 1

    def next(self) -> int:
        self._n += 1
        return self._n

    @property
    def current(self) -> int:
        return self._n


# ---------------------------------------------------------------------------
# Central column registry. The ORDER here is the exact COPY column order.
# ---------------------------------------------------------------------------
TABLES: Dict[str, List[str]] = {}


def register(table: str, columns: Sequence[str]) -> None:
    TABLES[table] = list(columns)


@dataclass
class LoadOp:
    """One COPY operation: rows -> table(columns), in dependency order."""

    table: str
    columns: List[str]
    rows: List[tuple]

    def __len__(self) -> int:
        return len(self.rows)


@dataclass
class Fixture:
    mode: str
    run_key: str
    seed: int
    target_firs: int
    ops: List[LoadOp] = field(default_factory=list)
    scenario_coverage: Dict[str, int] = field(default_factory=dict)
    totals: Dict[str, int] = field(default_factory=dict)
    generator_version: str = "2.0.0"

    def op_map(self) -> Dict[str, LoadOp]:
        return {op.table: op for op in self.ops}


class World:
    """Mutable accumulator shared by all v2 domain builders.

    Domain modules call ``world.add(table, tuple(...))`` to append a row, and
    ``world.cover("scenario_name")`` to record scenario coverage. Stable identity
    maps (offender -> canonical person, gang -> canonical org, person -> entity)
    live here so a repeat person keeps ONE CanonicalPersonID across all cases.
    """

    def __init__(self, cfg, ctx, rng):
        self.cfg = cfg
        self.ctx = ctx
        self.rng = rng

        # row buffers keyed by table name
        self.rows: Dict[str, List[tuple]] = defaultdict(list)

        # id allocators (canonical ids minted here — never names/indexes)
        self.seq: Dict[str, Seq] = defaultdict(Seq)

        # stable identity maps
        self.offender_person: Dict[int, int] = {}   # offender_idx -> CanonicalPersonID
        self.gang_org: Dict[int, int] = {}          # gang_idx     -> CanonicalOrganisationID
        self.person_entity: Dict[int, int] = {}     # CanonicalPersonID -> CanonicalEntityID
        self.org_entity: Dict[int, int] = {}        # CanonicalOrganisationID -> CanonicalEntityID
        self.person_gender: Dict[int, int] = {}     # CanonicalPersonID -> genderid (for reuse)
        self.person_birthyear: Dict[int, int] = {}  # CanonicalPersonID -> approx birth year
        self.person_label: Dict[int, str] = {}      # CanonicalPersonID -> display label
        self.person_case_count: Dict[int, int] = {} # CanonicalPersonID -> #cases (repeat detection)

        # scenario coverage counter (named-scenario -> count)
        self.coverage: Counter = Counter()

        # per-case lifecycle metadata for validation (kind/category/status/flags)
        self.case_meta: Dict[int, dict] = {}
        # per-area aggregate stats for leakage-safe labels (set by build)
        self.area_stats: Dict[int, dict] = {}
        self.feature_schema_version_id = None

        # convenience: primary synthetic source system id (set by build)
        self.source_system: Dict[str, int] = {}

        # observation cutoff / label window (set by build; used by labels + gates)
        self.observation_cutoff = None
        self.label_window_start = None
        self.label_window_end = None

    # -- row + coverage helpers ---------------------------------------------
    def add(self, table: str, row: tuple) -> None:
        if table not in TABLES:
            raise KeyError(f"unregistered table {table!r} — register() its columns")
        self.rows[table].append(row)

    def next_id(self, table: str) -> int:
        return self.seq[table].next()

    def cover(self, scenario: str, n: int = 1) -> None:
        self.coverage[scenario] += n

    # -- assembly -----------------------------------------------------------
    def to_ops(self, order: Sequence[str]) -> List[LoadOp]:
        """Emit LoadOps in the given dependency order (skips empty tables)."""
        ops: List[LoadOp] = []
        for table in order:
            rows = self.rows.get(table)
            if rows:
                ops.append(LoadOp(table, TABLES[table], rows))
        return ops


# ---------------------------------------------------------------------------
# Canonical load order (parents before children). The loader also uses the
# REVERSE of this list when truncating a prior synthetic fixture.
# ---------------------------------------------------------------------------
V2_LOAD_ORDER: List[str] = [
    # security / run metadata
    "SyntheticDataRun",
    # source + ingestion staging
    "SourceSystem", "SourceRecord", "IngestionJob", "IngestionRecord",
    # canonical identity
    "CanonicalPerson", "CanonicalOrganisation", "CanonicalEntity",
    "PersonAlias", "PersonIdentifier", "PersonContact", "PersonAddress",
    "EntityResolutionCandidate", "EntityMergeHistory",
    # operational core (regenerated cleanly). CasePartyRole precedes the legacy
    # person tables because Accused.CasePartyRoleID is a hard FK to it.
    "CaseMaster", "CasePartyRole",
    "ComplainantDetails", "Victim", "Accused",
    "ActSectionAssociation", "ArrestSurrender", "inv_arrestsurrenderaccused",
    "ChargesheetDetails", "Inv_OccuranceTime",
    # case workflow
    "CaseSource", "CaseVersion", "CaseCategoryWorkflow", "CaseEvent",
    # evidence
    "EvidenceItem", "EvidenceObject", "EvidenceVersion", "EvidenceCaseLink",
    "EvidenceActivityEvent", "EvidenceEntityLink",
    # statements
    "Statement", "StatementVersion",
    # property / seizure
    "Seizure", "PropertyItem",
    # digital
    "Device", "DeviceArtifact", "CommunicationEvent", "LocationObservation",
    "DigitalImportBatch",
    # financial (canonical, provenance-backed)
    "FinancialAccount", "FinancialTransaction", "TransactionLink",
    # court / outcomes
    "CourtEvent", "BailEvent", "CaseDisposition", "OutcomeObservation",
    # jurisdiction + external context
    "JurisdictionBoundary", "UnitLocation", "ExternalSourceVersion",
    "HolidayCalendar", "PublicEvent", "AreaContextObservation",
    # feature / prediction governance + labels
    "FeatureDefinition", "FeatureSchemaVersion", "TrainingDatasetSnapshot",
    "FeatureSnapshot", "OutcomeLabel",
    "PredictionRequest", "PredictionResult", "PredictionReview",
    # graph (provenanced)
    "EntityGraph", "NetworkEdge", "GangMembership",
    # data quality (staging problems — deliberately NOT canonical)
    "DataQualityIssue",
    # audit fixtures
    "audit_logs",
]

# Tables the v2 loader is allowed to TRUNCATE on a --confirm-synthetic-dev-target
# reload. Reference/org tables are reloaded fresh too. Governance/RBAC seed
# tables (roles/users/role_permissions) and boundary caches are preserved.
REFERENCE_LOAD_ORDER: List[str] = [
    "State", "District", "UnitType", "Unit", "Rank", "Designation", "Employee",
    "Court", "CaseCategory", "GravityOffence", "CrimeHead", "CrimeSubHead",
    "CaseStatusMaster", "CasteMaster", "ReligionMaster", "OccupationMaster",
    "Act", "Section", "CrimeHeadActSection",
]
