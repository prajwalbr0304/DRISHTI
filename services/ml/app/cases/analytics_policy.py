"""Versioned attestation for case-derived persisted analytics.

The database schema intentionally has no dedicated policy-generation column.  New
artifacts therefore carry this marker in an existing JSON metadata field.  A
missing marker is never inferred or backfilled: legacy artifacts remain
unverified until a producer replaces them under the current policy.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Optional

ATTESTATION_KEY = "analytics_policy_attestation"
POLICY_VERSION = "drishti.case-derived-analytics/v1"
_MODEL_VERSION_DIGEST_CHARS = 16


class DerivedArtifactUnavailable(RuntimeError):
    """An operational artifact cannot prove it was built under current policy."""


class PolicyStateUnavailable(DerivedArtifactUnavailable):
    """The current CaseVersion policy state is malformed and cannot be attested."""


class ArtifactPolicyMismatch(DerivedArtifactUnavailable):
    """A persisted artifact has no marker or has a marker for another policy."""


@dataclass(frozen=True)
class PolicyAttestation:
    version: str
    sha256: str
    relevant_case_versions: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "sha256": self.sha256,
            "relevant_case_versions": self.relevant_case_versions,
        }


def analytics_eligible_sql(alias: str = "cm") -> str:
    """Return the fail-closed SQL predicate for case-derived analytics.

    A case needs a current CaseVersion, and either policy signal independently
    excludes it.  The origin check is deliberate defense in depth for curated
    rows whose boolean exclusion flag is missing or malformed.
    """
    if not alias.replace("_", "").isalnum():
        raise ValueError("Unsafe SQL alias")
    current = (
        'cv_policy."CaseMasterID"='
        f'{alias}."CaseMasterID" AND cv_policy."IsCurrent"=TRUE'
    )
    return (
        'EXISTS (SELECT 1 FROM "CaseVersion" cv_policy '
        f'WHERE {current}) AND '
        'NOT EXISTS (SELECT 1 FROM "CaseVersion" cv_policy '
        f'WHERE {current} AND ('
        'cv_policy."SnapshotAttributes"->>\'record_origin\'=\'public_source_curated\' OR '
        'cv_policy."SnapshotAttributes" @> '
        '\'{"excluded_from_derived_analytics":true}\'::jsonb OR '
        '(cv_policy."SnapshotAttributes" ? \'record_origin\' AND '
        'jsonb_typeof(cv_policy."SnapshotAttributes"->\'record_origin\') <> \'string\') OR '
        '(cv_policy."SnapshotAttributes" ? \'excluded_from_derived_analytics\' AND '
        'jsonb_typeof(cv_policy."SnapshotAttributes"->\'excluded_from_derived_analytics\') '
        '<> \'boolean\')))'
    )


def _object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return {}


def current_attestation(conn) -> PolicyAttestation:
    """Hash the ordered current CaseVersions relevant to exclusion policy.

    Only current versions that are explicitly excluded or public-source curated
    enter the digest.  Malformed policy values fail closed instead of silently
    changing cohort membership.
    """
    with conn.cursor() as cur:
        cur.execute(
            'SELECT cv."CaseMasterID",cv."CaseVersionID",cv."VersionNo",'
            'cv."SnapshotAttributes" FROM "CaseVersion" cv '
            'WHERE cv."IsCurrent"=TRUE AND ('
            'cv."SnapshotAttributes"->>\'record_origin\'=\'public_source_curated\' OR '
            'cv."SnapshotAttributes" @> \'{"excluded_from_derived_analytics":true}\'::jsonb OR '
            '(cv."SnapshotAttributes" ? \'record_origin\' AND '
            'jsonb_typeof(cv."SnapshotAttributes"->\'record_origin\') <> \'string\') OR '
            '(cv."SnapshotAttributes" ? \'excluded_from_derived_analytics\' AND '
            'jsonb_typeof(cv."SnapshotAttributes"->\'excluded_from_derived_analytics\') '
            '<> \'boolean\')) '
            'ORDER BY cv."CaseMasterID",cv."CaseVersionID"'
        )
        rows = cur.fetchall()

    relevant: list[dict[str, Any]] = []
    for case_id, version_id, version_no, raw_attrs in rows:
        attrs = _object(raw_attrs)
        origin = attrs.get("record_origin")
        if origin is not None and not isinstance(origin, str):
            raise PolicyStateUnavailable(
                f"CaseVersion {version_id} has a non-string record_origin; "
                "case-derived analytics are unavailable until policy metadata is repaired."
            )
        has_exclusion = "excluded_from_derived_analytics" in attrs
        excluded = attrs.get("excluded_from_derived_analytics")
        if has_exclusion and not isinstance(excluded, bool):
            raise PolicyStateUnavailable(
                f"CaseVersion {version_id} has a non-boolean "
                "excluded_from_derived_analytics value; case-derived analytics are unavailable "
                "until policy metadata is repaired."
            )
        if origin != "public_source_curated" and excluded is not True:
            continue
        relevant.append({
            "case_master_id": int(case_id),
            "case_version_id": int(version_id),
            "version_no": int(version_no),
            "record_origin": origin,
            "excluded_from_derived_analytics": excluded if has_exclusion else None,
        })

    canonical = json.dumps(
        {"version": POLICY_VERSION, "current_case_versions": relevant},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return PolicyAttestation(
        version=POLICY_VERSION,
        sha256=hashlib.sha256(canonical).hexdigest(),
        relevant_case_versions=len(relevant),
    )


def coerce_attestation(value: Any) -> Optional[PolicyAttestation]:
    marker = _object(value)
    if ATTESTATION_KEY in marker:
        marker = _object(marker.get(ATTESTATION_KEY))
    version = marker.get("version")
    digest = marker.get("sha256")
    count = marker.get("relevant_case_versions")
    if not isinstance(version, str) or not isinstance(digest, str):
        return None
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest.lower()):
        return None
    try:
        n = int(count)
    except (TypeError, ValueError):
        return None
    if n < 0:
        return None
    return PolicyAttestation(version=version, sha256=digest.lower(), relevant_case_versions=n)


def same_attestation(left: PolicyAttestation, right: PolicyAttestation) -> bool:
    return (
        left.version == right.version
        and left.relevant_case_versions == right.relevant_case_versions
        and hmac.compare_digest(left.sha256, right.sha256)
    )


def stamp(metadata: Optional[Mapping[str, Any]], attestation: PolicyAttestation) -> dict[str, Any]:
    out = dict(metadata or {})
    out[ATTESTATION_KEY] = attestation.as_dict()
    return out


def require_current(
    conn,
    metadata: Any,
    artifact: str,
    *,
    current: Optional[PolicyAttestation] = None,
) -> PolicyAttestation:
    expected = current or current_attestation(conn)
    actual = coerce_attestation(metadata)
    if actual is None:
        raise ArtifactPolicyMismatch(
            f"{artifact} has no valid analytics-policy attestation; regenerate it under the "
            "current filtered case policy."
        )
    if not same_attestation(actual, expected):
        raise ArtifactPolicyMismatch(
            f"{artifact} was generated under analytics policy {actual.version}/"
            f"{actual.sha256[:12]}, not current policy {expected.version}/"
            f"{expected.sha256[:12]}; regenerate the artifact before serving it."
        )
    return expected


def require_supplied_current(
    conn,
    attestation: PolicyAttestation,
    artifact: str = "producer run",
) -> PolicyAttestation:
    current = current_attestation(conn)
    if not same_attestation(attestation, current):
        raise ArtifactPolicyMismatch(
            f"{artifact} crossed an analytics-policy change and cannot be persisted; rerun it "
            "against the current filtered case cohort."
        )
    return current


def policy_model_version(base_version: str, attestation: PolicyAttestation) -> str:
    """Return a deterministic version that can never resolve to a legacy model row."""
    return f"{base_version}+policy.{attestation.sha256[:_MODEL_VERSION_DIGEST_CHARS]}"


def require_model(
    conn,
    model_version_id: int,
    artifact: str,
    *,
    current: Optional[PolicyAttestation] = None,
) -> PolicyAttestation:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "Hyperparameters" FROM "ModelVersion" WHERE "ModelVersionID"=%s',
            (model_version_id,),
        )
        row = cur.fetchone()
    if not row:
        raise ArtifactPolicyMismatch(f"{artifact} references missing ModelVersion {model_version_id}.")
    return require_current(conn, row[0], f"{artifact} model", current=current)


def latest_complete_generation(
    conn,
    *,
    model_names: Iterable[str],
    ref_table: str,
    artifact: str,
    scope: Optional[Mapping[str, Any]] = None,
    current: Optional[PolicyAttestation] = None,
) -> dict[str, Any]:
    """Require an attested latest producer manifest, including valid zero runs."""
    names = [str(name) for name in model_names]
    if not names:
        raise ValueError("model_names must not be empty")
    with conn.cursor() as cur:
        cur.execute(
            'SELECT mi."Input",mi."Output",mv."Hyperparameters",mv."ModelName",'
            'mi."InferenceID",mv."ModelVersionID" FROM "ModelInference" mi '
            'JOIN "ModelVersion" mv ON mv."ModelVersionID"=mi."ModelVersionID" '
            'WHERE mi."RefTable"=%s AND mv."ModelName"=ANY(%s) '
            'ORDER BY mi."InferenceID" DESC LIMIT 500',
            (ref_table, names),
        )
        rows = cur.fetchall()
    wanted = dict(scope or {})
    selected = None
    for inputs, outputs, hyperparameters, model_name, inference_id, model_version_id in rows:
        inp = _object(inputs)
        if all(inp.get(key) == value for key, value in wanted.items()):
            selected = (inp, _object(outputs), hyperparameters, model_name,
                        inference_id, model_version_id)
            break
    if selected is None:
        raise DerivedArtifactUnavailable(
            f"{artifact} has no producer manifest for the requested scope; run the producer "
            "under the current analytics policy before serving this endpoint."
        )
    inp, out, hyperparameters, model_name, inference_id, model_version_id = selected
    expected = current or current_attestation(conn)
    require_current(conn, hyperparameters, f"{artifact} model {model_name}", current=expected)
    require_current(conn, inp, f"{artifact} generation {inference_id}", current=expected)
    if out.get("complete_generation") is not True:
        raise DerivedArtifactUnavailable(
            f"{artifact} latest producer manifest is not a complete generation for this scope."
        )
    return {
        "model_name": model_name,
        "model_version_id": int(model_version_id),
        "inference_id": int(inference_id),
        "inputs": inp,
        "outputs": out,
    }
