"""In-memory integrity gates for a built Datagen v2 Fixture.

Runs BEFORE any load. Every gate the roadmap (§27.8 / §31 / Prompt K) lists must
report ZERO failures. Returns a structured report and an overall ok flag.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Dict, List, Tuple

from . import boundaries as B
from . import scenario_registry as SR
from . import v2common as C


def _col(table: str, name: str) -> int:
    return C.TABLES[table].index(name)


def _pkset(world: C.World, table: str, pk: str) -> set:
    if table not in world.rows:
        return set()
    idx = _col(table, pk)
    return {r[idx] for r in world.rows[table]}


class Gate:
    def __init__(self, name: str):
        self.name = name
        self.failures = 0
        self.samples: List[str] = []

    def fail(self, detail: str):
        self.failures += 1
        if len(self.samples) < 60:
            self.samples.append(detail)

    def as_dict(self):
        return {"failures": self.failures, "samples": self.samples}


def validate(world: C.World, *, mode: str, check_spatial_all: bool = True) -> Tuple[bool, dict]:
    rows = world.rows
    gates: Dict[str, Gate] = {}

    def g(name) -> Gate:
        if name not in gates:
            gates[name] = Gate(name)
        return gates[name]

    person_ids = _pkset(world, "CanonicalPerson", "CanonicalPersonID")
    org_ids = _pkset(world, "CanonicalOrganisation", "CanonicalOrganisationID")
    entity_ids = _pkset(world, "CanonicalEntity", "CanonicalEntityID")
    case_ids = _pkset(world, "CaseMaster", "CaseMasterID")
    item_ids = _pkset(world, "EvidenceItem", "EvidenceItemID")
    egraph_ids = _pkset(world, "EntityGraph", "EntityID")

    # -- 1. duplicate CrimeNo / source key ----------------------------------
    gate = g("duplicate_crimeno")
    if "CaseMaster" in rows:
        ci = _col("CaseMaster", "CrimeNo")
        seen = set()
        for r in rows["CaseMaster"]:
            cn = r[ci]
            if cn in seen:
                gate.fail(f"dup CrimeNo {cn}")
            seen.add(cn)

    # -- 2. orphan foreign keys (canonical) ---------------------------------
    def check_fk(table, fkcol, target_set, allow_null=True, label=None):
        gate = g(f"orphan_fk_{label or table + '_' + fkcol}")
        if table not in rows:
            return
        idx = _col(table, fkcol)
        for r in rows[table]:
            v = r[idx]
            if v is None:
                if not allow_null:
                    gate.fail(f"{table}.{fkcol} null")
                continue
            if v not in target_set:
                gate.fail(f"{table}.{fkcol}={v} orphan")

    check_fk("CasePartyRole", "CaseMasterID", case_ids, allow_null=False)
    check_fk("Accused", "CaseMasterID", case_ids, allow_null=False)
    check_fk("Accused", "CanonicalPersonID", person_ids, allow_null=True)
    check_fk("Victim", "CaseMasterID", case_ids, allow_null=False)
    check_fk("Victim", "CanonicalPersonID", person_ids, allow_null=False, label="Victim_canon")
    check_fk("ComplainantDetails", "CanonicalPersonID", person_ids, allow_null=False, label="Compl_canon")
    check_fk("CaseVersion", "CaseMasterID", case_ids, allow_null=False)
    check_fk("CaseEvent", "CaseMasterID", case_ids, allow_null=False)
    check_fk("EvidenceObject", "EvidenceItemID", item_ids, allow_null=False)
    check_fk("EvidenceVersion", "EvidenceItemID", item_ids, allow_null=False)
    check_fk("EvidenceCaseLink", "CaseMasterID", case_ids, allow_null=False)
    check_fk("EvidenceEntityLink", "CanonicalEntityID", entity_ids, allow_null=False)
    check_fk("OutcomeObservation", "CaseMasterID", case_ids, allow_null=False)
    check_fk("Statement", "CaseMasterID", case_ids, allow_null=False)
    check_fk("NetworkEdge", "Source", egraph_ids, allow_null=False)
    check_fk("NetworkEdge", "Target", egraph_ids, allow_null=False)

    # -- 3. unstable canonical identity / name-based identity ---------------
    gate = g("unstable_canonical_identity")
    # each offender maps to exactly one canonical person
    if len(set(world.offender_person.values())) != len(world.offender_person):
        gate.fail("an offender maps to multiple canonical persons")
    # PublicRef uniqueness
    if "CanonicalPerson" in rows:
        pr = _col("CanonicalPerson", "PublicRef")
        refs = [r[pr] for r in rows["CanonicalPerson"]]
        if len(set(refs)) != len(refs):
            g("duplicate_canonical_ref").fail("duplicate CanonicalPerson PublicRef")

    gate = g("name_based_identity_link")
    # every non-unknown party role must carry a canonical person/org id
    if "CasePartyRole" in rows:
        ci_p = _col("CasePartyRole", "CanonicalPersonID")
        ci_o = _col("CasePartyRole", "CanonicalOrganisationID")
        ci_u = _col("CasePartyRole", "IsUnknownParty")
        for r in rows["CasePartyRole"]:
            if r[ci_p] is None and r[ci_o] is None and not r[ci_u]:
                gate.fail("CasePartyRole with no canonical id and not unknown")

    # -- 4. graph linkage + provenance --------------------------------------
    gate = g("unlinked_graph_person_node")
    gate_ce = g("graph_node_canonical_missing")
    if "EntityGraph" in rows:
        ci_ce = _col("EntityGraph", "CanonicalEntityID")
        ci_type = _col("EntityGraph", "EntityType")
        for r in rows["EntityGraph"]:
            ce = r[ci_ce]
            if ce is None:
                gate.fail(f"EntityGraph node {r[0]} has no CanonicalEntityID")
            elif ce not in entity_ids:
                gate_ce.fail(f"EntityGraph.CanonicalEntityID={ce} orphan")
    gate = g("unprovenanced_graph_edge")
    if "NetworkEdge" in rows:
        ci_prov = _col("NetworkEdge", "ProvenanceStatus")
        for r in rows["NetworkEdge"]:
            if r[ci_prov] not in ("verified", "synthetic_unverified"):
                gate.fail(f"NetworkEdge provenance={r[ci_prov]!r}")

    # -- 5. lifecycle: chargesheet prerequisite + category consistency ------
    events_by_case: Dict[int, set] = defaultdict(set)
    if "CaseEvent" in rows:
        ci_case = _col("CaseEvent", "CaseMasterID")
        ci_type = _col("CaseEvent", "EventType")
        for r in rows["CaseEvent"]:
            events_by_case[r[ci_case]].add(r[ci_type])
    cs_cases = _pkset(world, "ChargesheetDetails", "CaseMasterID")

    gate_cs = g("chargesheet_without_prerequisite")
    gate_life = g("invalid_missing_udr_lifecycle")
    gate_cat = g("invalid_category_transition")
    for case_id, meta in world.case_meta.items():
        kind = meta["kind"]
        status = meta["status"]
        converted = meta["converted"]
        ev = events_by_case.get(case_id, set())
        # Charge Sheeted must have chargesheet row + chargesheet_filed event + prior investigation/arrest
        if status == SR.S_CHARGESHEETED or status in (SR.S_PENDING_TRIAL, SR.S_CONVICTED, SR.S_ACQUITTED):
            if case_id not in cs_cases:
                gate_cs.fail(f"case {case_id} status={status} but no ChargesheetDetails")
            if SR.E_CHARGESHEET_FILED not in ev:
                gate_cs.fail(f"case {case_id} chargesheeted without chargesheet_filed event")
            if not (SR.E_INVESTIGATION in ev or SR.E_ARREST in ev):
                gate_cat.fail(f"case {case_id} chargesheet without investigation/arrest")
        # missing/udr/ncr/par must not have a chargesheet unless converted
        if kind in ("missing_person", "udr", "ncr", "par") and not converted:
            if case_id in cs_cases:
                gate_life.fail(f"{kind} case {case_id} has a chargesheet (illegal)")
        # missing person must have a missing_reported event
        if kind == "missing_person" and SR.E_MISSING_REPORTED not in ev:
            gate_life.fail(f"missing case {case_id} lacks missing_reported event")
        # udr must have inquest
        if kind == "udr" and SR.E_INQUEST not in ev:
            gate_life.fail(f"udr case {case_id} lacks inquest event")

    # -- 6. spatial containment (canonical CaseVersion coordinates) ---------
    gate = g("out_of_state_or_jurisdiction")
    if "CaseVersion" in rows:
        bnd = B.load_boundaries()
        id2name = {d["id"]: d["name"] for d in world.ctx.districts}
        ci_lat = _col("CaseVersion", "IncidentLatitude")
        ci_lon = _col("CaseVersion", "IncidentLongitude")
        ci_dist = _col("CaseVersion", "AssignedDistrictID")
        ci_cur = _col("CaseVersion", "IsCurrent")
        cv_rows = rows["CaseVersion"]
        step = 1 if (check_spatial_all or len(cv_rows) <= 6000) else max(1, len(cv_rows) // 6000)
        for r in cv_rows[::step]:
            if not r[ci_cur]:
                continue
            lat, lon, did = r[ci_lat], r[ci_lon], r[ci_dist]
            if lat is None or lon is None:
                continue
            if not bnd.in_state(float(lon), float(lat)):
                gate.fail(f"CaseVersion case coord out of state ({lon},{lat})")
                continue
            region = bnd.district(id2name.get(did, ""))
            if region is not None and not region.contains(float(lon), float(lat)):
                gate.fail(f"CaseVersion coord outside assigned district {did}")

    # -- 7. evidence object completeness ------------------------------------
    gate = g("evidence_object_missing_hash_or_provenance")
    if "EvidenceObject" in rows:
        ci_sha = _col("EvidenceObject", "Sha256")
        ci_prov = _col("EvidenceObject", "ManualProvenance")
        for r in rows["EvidenceObject"]:
            if not r[ci_sha]:
                gate.fail(f"EvidenceObject {r[0]} missing sha256")
            if r[ci_prov] is None:
                gate.fail(f"EvidenceObject {r[0]} missing manual provenance")
    # available file-backed items must have >=1 version
    gate_v = g("available_evidence_without_version")
    if "EvidenceItem" in rows and "EvidenceVersion" in rows:
        vi_item = _col("EvidenceVersion", "EvidenceItemID")
        versioned = {r[vi_item] for r in rows["EvidenceVersion"]}
        ci_id = _col("EvidenceItem", "EvidenceItemID")
        ci_state = _col("EvidenceItem", "State")
        ci_meta = _col("EvidenceItem", "ManualMetadata")
        for r in rows["EvidenceItem"]:
            if r[ci_state] == "available":
                meta = r[ci_meta]
                file_backed = getattr(meta, "s", "{}").find('"file_backed":true') >= 0 \
                    or getattr(meta, "s", "").find('"file_backed": true') >= 0
                if file_backed and r[ci_id] not in versioned:
                    gate_v.fail(f"available file-backed EvidenceItem {r[ci_id]} has no version")

    # -- 8. label leakage / outcome timing ----------------------------------
    gate = g("outcome_label_before_cutoff")
    if "OutcomeLabel" in rows:
        ci_cut = _col("OutcomeLabel", "ObservationCutoff")
        ci_ws = _col("OutcomeLabel", "LabelWindowStart")
        for r in rows["OutcomeLabel"]:
            if r[ci_ws] < r[ci_cut]:
                gate.fail("OutcomeLabel window starts before observation cutoff")
    gate = g("feature_snapshot_missing_cutoff_or_hash")
    if "FeatureSnapshot" in rows:
        ci_cut = _col("FeatureSnapshot", "ObservationCutoff")
        ci_hash = _col("FeatureSnapshot", "ContentHash")
        for r in rows["FeatureSnapshot"]:
            if not r[ci_cut] or not r[ci_hash]:
                gate.fail("FeatureSnapshot missing cutoff/hash")

    # -- 9. protected attributes excluded from feature schemas --------------
    gate = g("protected_feature_in_schema")
    if "FeatureDefinition" in rows:
        ci_name = _col("FeatureDefinition", "Name")
        ci_sens = _col("FeatureDefinition", "Sensitivity")
        banned = ("caste", "religion", "gender", "juvenile")
        for r in rows["FeatureDefinition"]:
            nm = (r[ci_name] or "").lower()
            if any(b in nm for b in banned) or r[ci_sens] == "protected":
                gate.fail(f"protected feature {r[ci_name]} present in schema")

    # -- 10. scenario minimum coverage (golden) -----------------------------
    gate = g("scenario_minimum_not_met")
    if mode == "golden":
        for name, minimum in SR.GOLDEN_SCENARIOS.items():
            got = world.coverage.get(name, 0)
            if got < minimum:
                gate.fail(f"{name}: {got}/{minimum}")

    total_failures = sum(gt.failures for gt in gates.values())
    report = {name: gt.as_dict() for name, gt in gates.items()}
    return total_failures == 0, {"ok": total_failures == 0,
                                 "total_failures": total_failures,
                                 "gates": report,
                                 "coverage": dict(world.coverage)}


def summarize(report: dict) -> str:
    lines = ["=" * 70, "DATAGEN v2 VALIDATION", "=" * 70,
             f"overall: {'PASS' if report['ok'] else 'FAIL'}  "
             f"(total failures={report['total_failures']})", "-" * 70]
    for name, gt in sorted(report["gates"].items()):
        flag = "ok" if gt["failures"] == 0 else f"FAIL x{gt['failures']}"
        lines.append(f"  {name:<45} {flag}")
        for s in gt["samples"]:
            lines.append(f"      - {s}")
    lines.append("=" * 70)
    return "\n".join(lines)
