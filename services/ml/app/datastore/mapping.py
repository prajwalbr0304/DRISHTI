"""Versioned AWS PostgreSQL -> Catalyst Data Store mapping (Prompt 14 E.1).

This module is the single source of truth for HOW the retained AWS RDS serving
schema projects into the deployed Catalyst Data Store operational layer. It is
data, not prose: the ds-import config generator, the serving-subset export
script and the mapping tests all consume it, so it cannot drift from a README.

Key rules encoded here (Prompt 14 §E, §24, phase-order rule):

  * Data Store is the deployed operational relational database. AWS RDS retains
    the COMPLETE historical/analytics corpus but is not the submitted app's
    operational store.
  * Every imported row carries a stable ``ExternalID`` (``<prefix>:<pk>``) so
    imports are idempotent (upsert by ExternalID) and referential links survive.
  * Not every table is imported. Each table has a ``Disposition``:
      - OPERATIONAL   -> curated rows imported to Data Store (the serving layer).
      - UI_PROJECTION -> a reviewed/curated projection is imported; the full
                         analytics artifact (graph, vectors, alerts) stays in AWS.
      - ANALYTICS_ONLY-> retained in AWS RDS only; never imported to Data Store.
      - RESERVED      -> namespace reserved for a later phase (Board/Disaster);
                         NOT created in Phase 14 (phase-order rule).
      - NOT_IMPORTED  -> handled elsewhere (auth handled by Catalyst; secrets/PII
                         never imported).
  * No credentials or real PII are ever imported. Synthetic-data labels,
    timestamps and lineage are preserved.

The mapping is versioned by ``MAPPING_VERSION``; the import job records it so a
serving-layer rebuild is reproducible.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

MAPPING_VERSION = "2026.07.18-1"

# Current Data Store development import ceiling (re-verify before a real import;
# current Catalyst docs cap development imports at 5,000 rows/table with no
# equivalent documented production ceiling). The curated subset is designed
# around this so no single table exceeds it in the development environment.
DEV_IMPORT_ROW_CAP = 5000


class Domain(str, Enum):
    GEOGRAPHY = "organisation_geography"
    CASE_LIFECYCLE = "case_lifecycle"
    CANONICAL_IDENTITY = "canonical_identity"
    EVIDENCE = "evidence"
    STRUCTURED = "structured_domains"
    GOVERNANCE = "governance"
    ANALYTICS = "analytics_contract"
    REFERENCE = "reference_lookups"
    EXTERNAL_CONTEXT = "external_context"
    ASSISTANT = "assistant_chat"
    INVESTIGATION_BOARD = "investigation_board"   # reserved (Prompt 16)
    DISASTER_RESPONSE = "disaster_response"       # reserved (Prompt 17)


class Disposition(str, Enum):
    OPERATIONAL = "operational"        # imported to Data Store (serving layer)
    UI_PROJECTION = "ui_projection"    # curated projection imported; full stays in AWS
    ANALYTICS_ONLY = "analytics_only"  # retained in AWS RDS only
    RESERVED = "reserved"              # later-phase namespace; not created now
    NOT_IMPORTED = "not_imported"      # auth/secret/PII handled outside import


@dataclass(frozen=True)
class TableMapping:
    """One AWS PostgreSQL table's projection into Catalyst Data Store."""
    source_table: str                       # exact quoted PG identifier (no quotes here)
    datastore_table: str                    # Data Store table/segment name
    domain: Domain
    disposition: Disposition
    pk_columns: tuple[str, ...]             # PG primary-key column(s) -> ExternalID
    external_id_prefix: str                 # ExternalID = "<prefix>:<pk...>"
    search_columns: tuple[str, ...] = ()    # Data Store full-text search columns
    excluded_columns: tuple[str, ...] = ()  # never projected (sensitive/secret/raw)
    note: str = ""

    def external_id(self, *pk_values: object) -> str:
        """Stable, idempotent ExternalID for a source row."""
        if len(pk_values) != len(self.pk_columns):
            raise ValueError(
                f"{self.source_table}: expected {len(self.pk_columns)} pk value(s), "
                f"got {len(pk_values)}")
        joined = "-".join(str(v) for v in pk_values)
        return f"{self.external_id_prefix}:{joined}"

    @property
    def imported(self) -> bool:
        return self.disposition in (Disposition.OPERATIONAL, Disposition.UI_PROJECTION)


def _m(*args, **kwargs) -> TableMapping:
    return TableMapping(*args, **kwargs)


# ---------------------------------------------------------------------------
# The registry. Keyed by source table name (exact PG identifier).
# ---------------------------------------------------------------------------
_MAPPINGS: list[TableMapping] = [
    # --- organisation / geography -----------------------------------------
    _m("State", "State", Domain.GEOGRAPHY, Disposition.OPERATIONAL,
       ("StateID",), "state", search_columns=("StateName",)),
    _m("District", "District", Domain.GEOGRAPHY, Disposition.OPERATIONAL,
       ("DistrictID",), "district", search_columns=("DistrictName",)),
    _m("UnitType", "UnitType", Domain.GEOGRAPHY, Disposition.OPERATIONAL,
       ("UnitTypeID",), "unittype"),
    _m("Unit", "Unit", Domain.GEOGRAPHY, Disposition.OPERATIONAL,
       ("UnitID",), "unit", search_columns=("UnitName",)),
    _m("UnitLocation", "UnitLocation", Domain.GEOGRAPHY, Disposition.OPERATIONAL,
       ("UnitLocationID",), "unitloc",
       note="GeoJSON + canonical CRS/source/version; GiST only on the AWS mirror."),
    _m("JurisdictionBoundary", "JurisdictionBoundary", Domain.GEOGRAPHY,
       Disposition.OPERATIONAL, ("JurisdictionBoundaryID",), "jbound",
       note="Validated GeoJSON stored in Data Store; PostGIS geometry stays in AWS."),
    _m("JurisdictionReassignment", "JurisdictionReassignment", Domain.GEOGRAPHY,
       Disposition.OPERATIONAL, ("JurisdictionReassignmentID",), "jreassign"),
    _m("SpatialRepairRun", "SpatialRepairRun", Domain.GEOGRAPHY,
       Disposition.OPERATIONAL, ("SpatialRepairRunID",), "spatialrepair"),
    _m("Rank", "Rank", Domain.GEOGRAPHY, Disposition.OPERATIONAL, ("RankID",), "rank"),
    _m("Designation", "Designation", Domain.GEOGRAPHY, Disposition.OPERATIONAL,
       ("DesignationID",), "designation"),
    _m("Employee", "Employee", Domain.GEOGRAPHY, Disposition.OPERATIONAL,
       ("EmployeeID",), "employee", search_columns=("EmployeeName",),
       note="Synthetic officer records; links deployable personnel to Unit."),

    # --- case lifecycle ----------------------------------------------------
    _m("CaseMaster", "Case", Domain.CASE_LIFECYCLE, Disposition.OPERATIONAL,
       ("CaseMasterID",), "case", search_columns=("CrimeNo", "Brief", "FIRNo"),
       note="Primary case/FIR record; full-text search target."),
    _m("CaseVersion", "CaseVersion", Domain.CASE_LIFECYCLE, Disposition.OPERATIONAL,
       ("CaseVersionID",), "casever"),
    _m("CaseEvent", "CaseEvent", Domain.CASE_LIFECYCLE, Disposition.OPERATIONAL,
       ("CaseEventID",), "caseevt"),
    _m("CaseSource", "CaseSource", Domain.CASE_LIFECYCLE, Disposition.OPERATIONAL,
       ("CaseSourceID",), "casesrc"),
    _m("CaseCategory", "CaseCategory", Domain.CASE_LIFECYCLE, Disposition.OPERATIONAL,
       ("CaseCategoryID",), "casecat", search_columns=("CategoryName",)),
    _m("CaseCategoryWorkflow", "CaseCategoryWorkflow", Domain.CASE_LIFECYCLE,
       Disposition.OPERATIONAL, ("CaseCategoryWorkflowID",), "casewf"),
    _m("CaseStatusMaster", "CaseStatusMaster", Domain.CASE_LIFECYCLE,
       Disposition.OPERATIONAL, ("CaseStatusID",), "casestatus"),
    _m("CaseDisposition", "CaseDisposition", Domain.CASE_LIFECYCLE,
       Disposition.OPERATIONAL, ("CaseDispositionID",), "casedisp"),
    _m("ChargesheetDetails", "ChargesheetDetails", Domain.CASE_LIFECYCLE,
       Disposition.OPERATIONAL, ("ChargesheetID",), "chargesheet"),
    _m("ArrestSurrender", "ArrestSurrender", Domain.CASE_LIFECYCLE,
       Disposition.OPERATIONAL, ("ArrestSurrenderID",), "arrest"),
    _m("AlertHistory", "AlertHistory", Domain.CASE_LIFECYCLE, Disposition.OPERATIONAL,
       ("AlertID",), "alert",
       note="Reused by Prompt 17 hazard alerts via an additive nullable HazardEventID."),

    # --- canonical identity ------------------------------------------------
    _m("CanonicalPerson", "CanonicalPerson", Domain.CANONICAL_IDENTITY,
       Disposition.OPERATIONAL, ("CanonicalPersonID",), "person",
       search_columns=("DisplayName", "PrimaryName"),
       note="Stable identity; replaces A1/A2/name matching."),
    _m("CanonicalOrganisation", "CanonicalOrganisation", Domain.CANONICAL_IDENTITY,
       Disposition.OPERATIONAL, ("CanonicalOrganisationID",), "org",
       search_columns=("OrganisationName",)),
    _m("CanonicalEntity", "CanonicalEntity", Domain.CANONICAL_IDENTITY,
       Disposition.OPERATIONAL, ("CanonicalEntityID",), "entity"),
    _m("CasePartyRole", "CasePartyRole", Domain.CANONICAL_IDENTITY,
       Disposition.OPERATIONAL, ("CasePartyRoleID",), "party"),
    _m("PersonAlias", "PersonAlias", Domain.CANONICAL_IDENTITY, Disposition.OPERATIONAL,
       ("PersonAliasID",), "alias", search_columns=("AliasName",)),
    _m("PersonIdentifier", "PersonIdentifier", Domain.CANONICAL_IDENTITY,
       Disposition.OPERATIONAL, ("PersonIdentifierID",), "personid",
       excluded_columns=("RawIdentifierValue",),
       note="Sensitivity-classified; raw identifier values are not projected."),
    _m("PersonContact", "PersonContact", Domain.CANONICAL_IDENTITY,
       Disposition.OPERATIONAL, ("PersonContactID",), "contact"),
    _m("PersonAddress", "PersonAddress", Domain.CANONICAL_IDENTITY,
       Disposition.OPERATIONAL, ("PersonAddressID",), "address"),
    _m("EntityResolutionCandidate", "EntityResolutionCandidate",
       Domain.CANONICAL_IDENTITY, Disposition.OPERATIONAL,
       ("EntityResolutionCandidateID",), "erc"),
    _m("EntityMergeHistory", "EntityMergeHistory", Domain.CANONICAL_IDENTITY,
       Disposition.OPERATIONAL, ("EntityMergeHistoryID",), "merge"),
    _m("GangMembership", "GangMembership", Domain.CANONICAL_IDENTITY,
       Disposition.UI_PROJECTION, ("GangMembershipID",), "gang",
       note="Reviewed affiliations projected for UI; full graph analytics in AWS."),

    # --- evidence ----------------------------------------------------------
    _m("EvidenceItem", "EvidenceItem", Domain.EVIDENCE, Disposition.OPERATIONAL,
       ("EvidenceItemID",), "evid", search_columns=("Title", "Description", "Tags"),
       note="Manual metadata only; no OCR/extraction. File bytes live in Stratus."),
    _m("EvidenceObject", "EvidenceObject", Domain.EVIDENCE, Disposition.OPERATIONAL,
       ("EvidenceObjectID",), "evobj",
       note="SHA-256/size/MIME/object-key/version + Stratus lineage; no bytes here."),
    _m("EvidenceVersion", "EvidenceVersion", Domain.EVIDENCE, Disposition.OPERATIONAL,
       ("EvidenceVersionID",), "evver"),
    _m("EvidenceCaseLink", "EvidenceCaseLink", Domain.EVIDENCE, Disposition.OPERATIONAL,
       ("EvidenceCaseLinkID",), "evcase"),
    _m("EvidenceEntityLink", "EvidenceEntityLink", Domain.EVIDENCE,
       Disposition.OPERATIONAL, ("EvidenceEntityLinkID",), "eventity"),
    _m("EvidenceActivityEvent", "EvidenceActivityEvent", Domain.EVIDENCE,
       Disposition.OPERATIONAL, ("EvidenceActivityEventID",), "evact",
       note="Append-only activity/custody trail."),

    # --- structured investigative / court domains --------------------------
    _m("Statement", "Statement", Domain.STRUCTURED, Disposition.OPERATIONAL,
       ("StatementID",), "stmt", search_columns=("StatementText",),
       excluded_columns=("RestrictedText",)),
    _m("StatementVersion", "StatementVersion", Domain.STRUCTURED,
       Disposition.OPERATIONAL, ("StatementVersionID",), "stmtver"),
    _m("Seizure", "Seizure", Domain.STRUCTURED, Disposition.OPERATIONAL,
       ("SeizureID",), "seizure"),
    _m("PropertyItem", "PropertyItem", Domain.STRUCTURED, Disposition.OPERATIONAL,
       ("PropertyItemID",), "property", search_columns=("Description",)),
    _m("LabResult", "LabResult", Domain.STRUCTURED, Disposition.OPERATIONAL,
       ("LabResultID",), "lab"),
    _m("Device", "Device", Domain.STRUCTURED, Disposition.OPERATIONAL,
       ("DeviceID",), "device"),
    _m("DeviceArtifact", "DeviceArtifact", Domain.STRUCTURED, Disposition.OPERATIONAL,
       ("DeviceArtifactID",), "devart"),
    _m("CommunicationEvent", "CommunicationEvent", Domain.STRUCTURED,
       Disposition.OPERATIONAL, ("CommunicationEventID",), "commevt",
       note="CDR/chat/IP events; large volumes stay bounded in the curated subset."),
    _m("LocationObservation", "LocationObservation", Domain.STRUCTURED,
       Disposition.OPERATIONAL, ("LocationObservationID",), "locobs"),
    _m("DigitalImportBatch", "DigitalImportBatch", Domain.STRUCTURED,
       Disposition.OPERATIONAL, ("DigitalImportBatchID",), "digbatch"),
    _m("FinancialAccount", "FinancialAccount", Domain.STRUCTURED,
       Disposition.OPERATIONAL, ("AccountID",), "acct",
       excluded_columns=("RawAccountNo",)),
    _m("FinancialTransaction", "FinancialTransaction", Domain.STRUCTURED,
       Disposition.OPERATIONAL, ("TransactionID",), "txn"),
    _m("TransactionLink", "TransactionLink", Domain.STRUCTURED,
       Disposition.OPERATIONAL, ("TransactionLinkID",), "txnlink"),
    _m("CourtEvent", "CourtEvent", Domain.STRUCTURED, Disposition.OPERATIONAL,
       ("CourtEventID",), "court"),
    _m("BailEvent", "BailEvent", Domain.STRUCTURED, Disposition.OPERATIONAL,
       ("BailEventID",), "bail"),
    _m("OutcomeObservation", "OutcomeObservation", Domain.STRUCTURED,
       Disposition.OPERATIONAL, ("OutcomeObservationID",), "outcome",
       note="Verified final events only; the basis for leakage-safe labels."),

    # --- governance / ingestion / audit ------------------------------------
    _m("SourceSystem", "SourceSystem", Domain.GOVERNANCE, Disposition.OPERATIONAL,
       ("SourceSystemID",), "srcsys"),
    _m("SourceRecord", "SourceRecord", Domain.GOVERNANCE, Disposition.OPERATIONAL,
       ("SourceRecordID",), "srcrec",
       note="Provenance for every canonical row; supersession/retraction."),
    _m("IngestionJob", "IngestionJob", Domain.GOVERNANCE, Disposition.OPERATIONAL,
       ("IngestionJobID",), "ingjob"),
    _m("IngestionRecord", "IngestionRecord", Domain.GOVERNANCE, Disposition.OPERATIONAL,
       ("IngestionRecordID",), "ingrec"),
    _m("ImportBatch", "ImportBatch", Domain.GOVERNANCE, Disposition.OPERATIONAL,
       ("ImportBatchID",), "impbatch"),
    _m("ImportStagingRow", "ImportStagingRow", Domain.GOVERNANCE,
       Disposition.OPERATIONAL, ("ImportStagingRowID",), "impstage",
       note="Rejected/invalid rows stay staged; never canonical."),
    _m("ImportTemplate", "ImportTemplate", Domain.GOVERNANCE, Disposition.OPERATIONAL,
       ("ImportTemplateID",), "imptpl"),
    _m("ImportTemplateVersion", "ImportTemplateVersion", Domain.GOVERNANCE,
       Disposition.OPERATIONAL, ("ImportTemplateVersionID",), "imptplver"),
    _m("DataQualityIssue", "DataQualityIssue", Domain.GOVERNANCE,
       Disposition.OPERATIONAL, ("DataQualityIssueID",), "dqi"),
    _m("audit_logs", "AuditEvent", Domain.GOVERNANCE, Disposition.OPERATIONAL,
       ("log_id",), "audit",
       excluded_columns=("raw_payload",),
       note="Append-only; request id/actor/action/resource only. No secrets/narratives."),
    _m("DemoActor", "DemoActor", Domain.GOVERNANCE, Disposition.OPERATIONAL,
       ("DemoActorID",), "actor",
       note="Synthetic presentation profiles. Real identity is Catalyst Auth."),
    _m("SavedQuery", "SavedQuery", Domain.GOVERNANCE, Disposition.OPERATIONAL,
       ("SavedQueryID",), "savedq"),
    _m("SyntheticDataRun", "SyntheticDataRun", Domain.GOVERNANCE,
       Disposition.OPERATIONAL, ("SyntheticDataRunID",), "synrun"),

    # --- analytics contract (governance metadata the UI needs) -------------
    _m("FeatureDefinition", "FeatureDefinition", Domain.ANALYTICS,
       Disposition.OPERATIONAL, ("FeatureDefinitionID",), "featdef"),
    _m("FeatureSchemaVersion", "FeatureSchemaVersion", Domain.ANALYTICS,
       Disposition.OPERATIONAL, ("FeatureSchemaVersionID",), "featschema"),
    _m("FeatureSnapshot", "FeatureSnapshot", Domain.ANALYTICS,
       Disposition.OPERATIONAL, ("FeatureSnapshotID",), "featsnap",
       note="Immutable; the reproducible basis of every prediction."),
    _m("TrainingDatasetSnapshot", "TrainingDatasetSnapshot", Domain.ANALYTICS,
       Disposition.OPERATIONAL, ("TrainingDatasetSnapshotID",), "trainsnap"),
    _m("OutcomeLabel", "OutcomeLabel", Domain.ANALYTICS, Disposition.OPERATIONAL,
       ("OutcomeLabelID",), "label"),
    _m("PredictionRequest", "PredictionRequest", Domain.ANALYTICS,
       Disposition.OPERATIONAL, ("PredictionRequestID",), "predreq"),
    _m("PredictionResult", "PredictionResult", Domain.ANALYTICS,
       Disposition.OPERATIONAL, ("PredictionResultID",), "predres"),
    _m("PredictionReview", "PredictionReview", Domain.ANALYTICS,
       Disposition.OPERATIONAL, ("PredictionReviewID",), "predrev"),
    _m("ModelVersion", "ModelVersion", Domain.ANALYTICS, Disposition.OPERATIONAL,
       ("ModelVersionID",), "model", search_columns=("ModelName",)),
    _m("ModelInference", "ModelInference", Domain.ANALYTICS, Disposition.OPERATIONAL,
       ("InferenceID",), "inference"),
    _m("ModelBenchmark", "ModelBenchmark", Domain.ANALYTICS, Disposition.OPERATIONAL,
       ("ModelBenchmarkID",), "benchmark"),
    # UI projections of heavier analytics; the full artifact stays in AWS.
    _m("EntityGraph", "GraphEntity", Domain.ANALYTICS, Disposition.UI_PROJECTION,
       ("EntityID",), "gnode",
       note="Curated reviewed-node projection; full graph/PostGIS in AWS."),
    _m("NetworkEdge", "GraphEdge", Domain.ANALYTICS, Disposition.UI_PROJECTION,
       ("EdgeID",), "gedge",
       note="Reviewed/provenanced edges only; candidate edges stay in AWS."),
    _m("drishti_hidden_associations", "HiddenAssociation", Domain.ANALYTICS,
       Disposition.UI_PROJECTION, ("association_id",), "hidden",
       note="Reviewer-confirmed associations only."),
    _m("CrimePattern", "CrimePattern", Domain.ANALYTICS, Disposition.UI_PROJECTION,
       ("PatternID",), "pattern"),
    _m("CrimePatternCase", "CrimePatternCase", Domain.ANALYTICS,
       Disposition.UI_PROJECTION, ("PatternCaseID",), "patterncase"),
    _m("CrimeHotspot", "CrimeHotspot", Domain.ANALYTICS, Disposition.UI_PROJECTION,
       ("HotspotID",), "hotspot"),
    _m("CrimePrediction", "CrimePrediction", Domain.ANALYTICS,
       Disposition.UI_PROJECTION, ("PredictionID",), "areapred"),
    _m("ForecastBacktest", "ForecastBacktest", Domain.ANALYTICS,
       Disposition.UI_PROJECTION, ("BacktestID",), "backtest"),
    _m("MoneyAlert", "MoneyAlert", Domain.ANALYTICS, Disposition.UI_PROJECTION,
       ("MoneyAlertID",), "moneyalert"),
    _m("MoneyAlertReview", "MoneyAlertReview", Domain.ANALYTICS,
       Disposition.UI_PROJECTION, ("MoneyAlertReviewID",), "moneyrev"),
    _m("OfficerRecommendation", "OfficerRecommendation", Domain.ANALYTICS,
       Disposition.UI_PROJECTION, ("RecommendationID",), "officerrec"),
    _m("AISummary", "AISummary", Domain.ANALYTICS, Disposition.UI_PROJECTION,
       ("SummaryID",), "aisummary"),
    # Analytics-only: retained in AWS RDS, never imported to Data Store.
    _m("CrimeEmbedding", "CrimeEmbedding", Domain.ANALYTICS, Disposition.ANALYTICS_ONLY,
       ("EmbeddingID",), "embedding",
       note="pgvector embeddings stay in AWS; only version metadata is referenced."),
    _m("CrimeRiskScore", "CrimeRiskScore", Domain.ANALYTICS, Disposition.ANALYTICS_ONLY,
       ("RiskScoreID",), "riskscore",
       note="Synthetic individual risk is NOT operationalised (Prompt 13). AWS only."),

    # --- reference / lookups ----------------------------------------------
    _m("Act", "Act", Domain.REFERENCE, Disposition.OPERATIONAL, ("ActID",), "act",
       search_columns=("ActName",)),
    _m("Section", "Section", Domain.REFERENCE, Disposition.OPERATIONAL,
       ("SectionID",), "section", search_columns=("SectionNo", "Description")),
    _m("ActSectionAssociation", "ActSectionAssociation", Domain.REFERENCE,
       Disposition.OPERATIONAL, ("AssociationID",), "actsection"),
    _m("CrimeHead", "CrimeHead", Domain.REFERENCE, Disposition.OPERATIONAL,
       ("CrimeHeadID",), "crimehead", search_columns=("HeadName",)),
    _m("CrimeSubHead", "CrimeSubHead", Domain.REFERENCE, Disposition.OPERATIONAL,
       ("CrimeSubHeadID",), "crimesubhead"),
    _m("CrimeHeadActSection", "CrimeHeadActSection", Domain.REFERENCE,
       Disposition.OPERATIONAL, ("CrimeHeadActSectionID",), "chas"),
    _m("GravityOffence", "GravityOffence", Domain.REFERENCE, Disposition.OPERATIONAL,
       ("GravityOffenceID",), "gravity"),
    _m("CasteMaster", "CasteMaster", Domain.REFERENCE, Disposition.NOT_IMPORTED,
       ("CasteID",), "caste",
       note="Protected attribute — excluded from the operational serving layer and "
            "from all model feature schemas."),
    _m("ReligionMaster", "ReligionMaster", Domain.REFERENCE, Disposition.NOT_IMPORTED,
       ("ReligionID",), "religion",
       note="Protected attribute — excluded from serving layer and feature schemas."),
    _m("OccupationMaster", "OccupationMaster", Domain.REFERENCE,
       Disposition.OPERATIONAL, ("OccupationID",), "occupation"),

    # --- external context --------------------------------------------------
    _m("WeatherIndicator", "WeatherIndicator", Domain.EXTERNAL_CONTEXT,
       Disposition.OPERATIONAL, ("WeatherIndicatorID",), "weather"),
    _m("HolidayCalendar", "HolidayCalendar", Domain.EXTERNAL_CONTEXT,
       Disposition.OPERATIONAL, ("HolidayID",), "holiday"),
    _m("PublicEvent", "PublicEvent", Domain.EXTERNAL_CONTEXT, Disposition.OPERATIONAL,
       ("PublicEventID",), "pubevent"),
    _m("AreaContextObservation", "AreaContextObservation", Domain.EXTERNAL_CONTEXT,
       Disposition.OPERATIONAL, ("AreaContextObservationID",), "areactx"),
    _m("ExternalSourceVersion", "ExternalSourceVersion", Domain.EXTERNAL_CONTEXT,
       Disposition.OPERATIONAL, ("ExternalSourceVersionID",), "extsrcver"),
    _m("EconomicIndicator", "EconomicIndicator", Domain.EXTERNAL_CONTEXT,
       Disposition.ANALYTICS_ONLY, ("EconomicIndicatorID",), "econ",
       note="Analytics context; retained in AWS, not part of the serving layer."),
    _m("SocialIndicator", "SocialIndicator", Domain.EXTERNAL_CONTEXT,
       Disposition.ANALYTICS_ONLY, ("SocialIndicatorID",), "social",
       note="Analytics context; retained in AWS, not part of the serving layer."),

    # --- assistant / chat --------------------------------------------------
    _m("ChatSession", "ChatSession", Domain.ASSISTANT, Disposition.OPERATIONAL,
       ("ChatSessionID",), "chatsess"),
    _m("ChatMessage", "ChatMessage", Domain.ASSISTANT, Disposition.OPERATIONAL,
       ("ChatMessageID",), "chatmsg",
       excluded_columns=("RawPrompt",),
       note="Data-minimised prompt/response/citation metadata only."),

    # --- legacy tables retained in AWS only (canonical identity supersedes) -
    _m("Accused", "Accused", Domain.CANONICAL_IDENTITY, Disposition.ANALYTICS_ONLY,
       ("AccusedID",), "legacy_accused",
       note="Legacy; superseded by CanonicalPerson/CasePartyRole. AWS history only."),
    _m("Victim", "Victim", Domain.CANONICAL_IDENTITY, Disposition.ANALYTICS_ONLY,
       ("VictimID",), "legacy_victim", note="Legacy; superseded by canonical identity."),
    _m("ComplainantDetails", "ComplainantDetails", Domain.CANONICAL_IDENTITY,
       Disposition.ANALYTICS_ONLY, ("ComplainantID",), "legacy_complainant",
       note="Legacy; superseded by canonical identity."),

    # --- auth / secrets: never imported (Catalyst Authentication owns identity) -
    _m("users", "AuthUser", Domain.GOVERNANCE, Disposition.NOT_IMPORTED,
       ("user_id",), "authuser",
       note="Deployed identity is Catalyst Authentication mapped to demo roles."),
    _m("roles", "Role", Domain.GOVERNANCE, Disposition.NOT_IMPORTED,
       ("role_id",), "role", note="Demo roles are server-side config, not imported data."),
    _m("role_permissions", "RolePermission", Domain.GOVERNANCE,
       Disposition.NOT_IMPORTED, ("id",), "roleperm",
       note="Authorization matrix enforced in code, not imported."),
    _m("synthetic_meta", "SyntheticMeta", Domain.GOVERNANCE, Disposition.NOT_IMPORTED,
       ("Key",), "meta",
       note="The synthetic marker is set as Data Store deploy config, not imported."),

    # --- voice / OCR deferred (out of hackathon scope) ---------------------
    _m("VoiceTranscript", "VoiceTranscript", Domain.STRUCTURED, Disposition.NOT_IMPORTED,
       ("VoiceTranscriptID",), "voice",
       note="Voice/transcription deferred (Prompt 6). Not part of hackathon serving layer."),
    _m("Inv_OccuranceTime", "Inv_OccuranceTime", Domain.CASE_LIFECYCLE,
       Disposition.ANALYTICS_ONLY, ("CaseMasterID",), "occtime",
       note="Legacy occurrence-time aux table; folded into CaseMaster on the serving layer."),
    _m("inv_arrestsurrenderaccused", "InvArrestAccused", Domain.CASE_LIFECYCLE,
       Disposition.ANALYTICS_ONLY, ("id",), "invarrest",
       note="Legacy arrest-accused join; superseded by canonical CasePartyRole."),
]

# Fast lookup by source table.
MAPPINGS: dict[str, TableMapping] = {m.source_table: m for m in _MAPPINGS}


# ---------------------------------------------------------------------------
# Reserved namespaces for later phases (created in Prompt 16/17, NOT here).
# The phase-order rule allows Phase 14 to reserve ExternalID/namespace/adapter
# contracts only. These are intentionally not backed by a source PG table yet.
# ---------------------------------------------------------------------------
RESERVED_NAMESPACES: dict[Domain, tuple[str, ...]] = {
    Domain.INVESTIGATION_BOARD: (
        "InvestigationBoard", "BoardNode", "BoardEdge", "BoardAnnotation",
        "BoardCollaborator", "BoardActivity"),
    Domain.DISASTER_RESPONSE: (
        "HazardType", "HazardEvent", "HazardPrediction", "HazardRiskZone",
        "HydroMetReading", "Resource", "ReliefShelter", "ResourceAllocation",
        "EvacuationRoute", "ResponsePlan", "ResponseTask"),
}

RESERVED_EXTERNAL_ID_PREFIXES: dict[str, str] = {
    # Prompt 16
    "InvestigationBoard": "board", "BoardNode": "bnode", "BoardEdge": "bedge",
    "BoardAnnotation": "bann", "BoardCollaborator": "bcollab", "BoardActivity": "bact",
    # Prompt 17
    "HazardType": "haztype", "HazardEvent": "hazevt", "HazardPrediction": "hazpred",
    "HazardRiskZone": "riskzone", "HydroMetReading": "hydromet", "Resource": "resource",
    "ReliefShelter": "shelter", "ResourceAllocation": "alloc",
    "EvacuationRoute": "evacroute", "ResponsePlan": "resplan", "ResponseTask": "restask",
}


# ---------------------------------------------------------------------------
# Helpers (consumed by ds-import config generation, the export script + tests).
# ---------------------------------------------------------------------------
def all_mappings() -> list[TableMapping]:
    return list(_MAPPINGS)


def by_disposition(disposition: Disposition) -> list[TableMapping]:
    return [m for m in _MAPPINGS if m.disposition == disposition]


def imported_tables() -> list[TableMapping]:
    """Tables whose rows are imported to Data Store (OPERATIONAL + UI_PROJECTION)."""
    return [m for m in _MAPPINGS if m.imported]


def datastore_tables() -> list[str]:
    """Distinct Data Store table names that receive imported rows."""
    seen: list[str] = []
    for m in imported_tables():
        if m.datastore_table not in seen:
            seen.append(m.datastore_table)
    return seen


def search_enabled_tables() -> list[TableMapping]:
    """Tables that declare Data Store full-text search columns (requirement #10)."""
    return [m for m in imported_tables() if m.search_columns]


def external_id(source_table: str, *pk_values: object) -> str:
    """Compute the stable ExternalID for a row of ``source_table``."""
    m = MAPPINGS.get(source_table)
    if m is None:
        raise KeyError(f"no mapping for source table {source_table!r}")
    return m.external_id(*pk_values)


def reserved_namespaces() -> dict[Domain, tuple[str, ...]]:
    return dict(RESERVED_NAMESPACES)


def is_reserved(datastore_table: str) -> bool:
    for tables in RESERVED_NAMESPACES.values():
        if datastore_table in tables:
            return True
    return False


def validate_mapping() -> list[str]:
    """Return a list of consistency problems (empty == valid). Used by tests.

    Guards against silent drift: duplicate ExternalID prefixes, empty pk columns,
    a reserved namespace colliding with an operational table, or a protected
    attribute accidentally marked importable.
    """
    problems: list[str] = []
    prefixes: dict[str, str] = {}
    ds_names = {m.datastore_table for m in _MAPPINGS}

    for m in _MAPPINGS:
        if not m.pk_columns:
            problems.append(f"{m.source_table}: no pk_columns")
        if not m.external_id_prefix:
            problems.append(f"{m.source_table}: empty external_id_prefix")
        if m.external_id_prefix in prefixes and prefixes[m.external_id_prefix] != m.source_table:
            problems.append(
                f"duplicate ExternalID prefix {m.external_id_prefix!r} on "
                f"{m.source_table} and {prefixes[m.external_id_prefix]}")
        prefixes[m.external_id_prefix] = m.source_table

    # Reserved namespaces must not collide with any current Data Store table.
    for tables in RESERVED_NAMESPACES.values():
        for t in tables:
            if t in ds_names:
                problems.append(f"reserved namespace {t!r} collides with a mapped table")

    # Protected attributes must never be importable.
    for name in ("CasteMaster", "ReligionMaster"):
        if MAPPINGS[name].imported:
            problems.append(f"protected attribute {name} must not be imported")

    return problems
