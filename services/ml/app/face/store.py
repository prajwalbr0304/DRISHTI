"""Persistence for the face gallery, the ANN search, and the probe audit trail.

Three responsibilities, all parameterised SQL on an open connection so a write and
its audit row commit together (the house pattern from models.py / identity):

  * GALLERY   — ``PersonFaceEmbedding`` rows, one per enrolled face crop of a
                canonical person, scoped to a ``ModelVersion``.
  * SEARCH    — ``ORDER BY "Embedding" <=> :probe`` over the HNSW cosine index,
                mirroring cases/similar.py. Descriptors are ONLY ever compared
                inside one ModelVersionID: a cosine distance between two different
                encoders' output spaces is a meaningless number that would look
                like a confident answer.
  * AUDIT     — ``FaceSearchProbe`` + ``FaceProbeMatch``. A biometric search is a
                sensitive action, so the probe row is written in the SAME
                transaction as the search. If the audit cannot be written the
                search fails; an unlogged biometric query is not an outcome this
                module offers.

Nothing here merges or asserts an identity. ``confirm_probe`` records the
officer's decision and raises an ``EntityResolutionCandidate`` (Method='face')
for review, exactly like every other matching signal in this schema.
"""
from __future__ import annotations

import secrets
from typing import Any, Iterable, Optional

from psycopg2.extras import Json

from .. import models
from ..cases.embeddings import to_pgvector
from .encoders import FACE_EMBED_DIM, FaceEncoder

# ModelVersion.ModelType must be a model_type_enum member; a face descriptor is
# an embedding model.
_MODEL_TYPE = "embedding"

# Similarity bands shown to the reviewer. Deliberately verbal, not numeric-only:
# "0.41" means nothing to an officer, "possible — verify" does.
BAND_STRONG = "strong"
BAND_PROBABLE = "probable"
BAND_WEAK = "weak"


class FaceStoreError(RuntimeError):
    """A gallery/probe operation could not be completed."""


class GalleryEmpty(FaceStoreError):
    """No enrolled faces exist for the active model, so 1:N search is impossible."""


def new_probe_ref() -> str:
    """Opaque, unguessable handle for one probe (returned to the client)."""
    return "PROBE-" + secrets.token_urlsafe(16)


def band_for(similarity: float, encoder: FaceEncoder) -> str:
    if similarity >= encoder.strong_threshold:
        return BAND_STRONG
    if similarity >= encoder.recommended_threshold:
        return BAND_PROBABLE
    return BAND_WEAK


# ---------------------------------------------------------------------------
# Model version
# ---------------------------------------------------------------------------
def model_version_for(conn, encoder: FaceEncoder) -> int:
    """Register (idempotently) the encoder as a ModelVersion and return its id."""
    return models.get_or_create_model_version(
        conn,
        model_name=encoder.name,
        model_type=_MODEL_TYPE,
        version=encoder.version,
        framework=encoder.family,
        embedding_dim=encoder.dim,
        hyperparameters={
            "match_threshold": encoder.recommended_threshold,
            "strong_threshold": encoder.strong_threshold,
            "biometric": encoder.biometric,
        },
        metrics={},
    )


def gallery_model(conn) -> Optional[tuple[int, str, int, int]]:
    """The live gallery: (ModelVersionID, ModelName, face_count, person_count).

    Picks the model version that actually has enrolled, non-archived faces — the
    same "resolve the corpus first" move cases/similar.py makes, so a probe is
    never compared across encoder spaces.
    """
    with conn.cursor() as cur:
        cur.execute(
            'SELECT pfe."ModelVersionID", mv."ModelName", COUNT(*), '
            '       COUNT(DISTINCT pfe."CanonicalPersonID") '
            'FROM "PersonFaceEmbedding" pfe '
            'JOIN "ModelVersion" mv ON mv."ModelVersionID" = pfe."ModelVersionID" '
            'JOIN "CanonicalPerson" cp ON cp."CanonicalPersonID" = pfe."CanonicalPersonID" '
            'WHERE pfe."IsArchived" = FALSE '
            "  AND cp.\"ResolutionStatus\" <> 'merged' "
            'GROUP BY pfe."ModelVersionID", mv."ModelName" '
            'ORDER BY MAX(pfe."CreatedAt") DESC, pfe."ModelVersionID" DESC LIMIT 1')
        row = cur.fetchone()
    if not row:
        return None
    return int(row[0]), str(row[1]), int(row[2]), int(row[3])


def gallery_size(conn, model_version_id: int) -> tuple[int, int]:
    """(face_count, person_count) enrolled under one model version."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT COUNT(*), COUNT(DISTINCT "CanonicalPersonID") '
            'FROM "PersonFaceEmbedding" '
            'WHERE "ModelVersionID"=%s AND "IsArchived"=FALSE', (model_version_id,))
        row = cur.fetchone()
    return (int(row[0]), int(row[1])) if row else (0, 0)


def probe_counts(conn) -> dict:
    """Probe-trail summary for the status endpoint."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT COUNT(*), '
            "       COUNT(*) FILTER (WHERE \"Decision\" = 'confirmed'), "
            "       COUNT(*) FILTER (WHERE \"Decision\" = 'pending'), "
            '       COUNT(*) FILTER (WHERE "CreatedAt" > now() - interval \'24 hours\') '
            'FROM "FaceSearchProbe"')
        row = cur.fetchone()
    return {
        "total": int(row[0] or 0),
        "confirmed": int(row[1] or 0),
        "pending": int(row[2] or 0),
        "last_24h": int(row[3] or 0),
    }


# ---------------------------------------------------------------------------
# Gallery writes
# ---------------------------------------------------------------------------
def person_exists(conn, cpid: int) -> Optional[tuple[str, Optional[str], str]]:
    """(PublicRef, DisplayLabel, ResolutionStatus) or None."""
    with conn.cursor() as cur:
        cur.execute('SELECT "PublicRef","DisplayLabel","ResolutionStatus" '
                    'FROM "CanonicalPerson" WHERE "CanonicalPersonID"=%s', (cpid,))
        row = cur.fetchone()
    return (row[0], row[1], row[2]) if row else None


def count_person_faces(conn, cpid: int, model_version_id: int) -> int:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT COUNT(*) FROM "PersonFaceEmbedding" '
            'WHERE "CanonicalPersonID"=%s AND "ModelVersionID"=%s AND "IsArchived"=FALSE',
            (cpid, model_version_id))
        return int(cur.fetchone()[0])


def enrol_face(conn, *, canonical_person_id: int, model_version_id: int,
               embedding, image_sha256: str, bounding_box: dict,
               detector_score: Optional[float], quality: Optional[float],
               face_count: int = 1, image_label: Optional[str] = None,
               evidence_item_id: Optional[int] = None,
               evidence_object_id: Optional[int] = None,
               enrolment_source: str = "manual_upload",
               actor: Optional[str] = None,
               make_primary: bool = False) -> tuple[int, bool]:
    """Insert one gallery descriptor. Returns (id, created).

    Re-enrolling the same photo for the same person under the same model is a
    no-op (the unique index on person+hash+model), which keeps repeated
    "confirm this match" clicks from skewing the gallery with duplicates.
    """
    vec = to_pgvector(embedding)
    with conn.cursor() as cur:
        if make_primary:
            # At most one reference photo per person (partial unique index).
            cur.execute('UPDATE "PersonFaceEmbedding" SET "IsPrimary"=FALSE '
                        'WHERE "CanonicalPersonID"=%s AND "IsPrimary"=TRUE',
                        (canonical_person_id,))
        cur.execute(
            'INSERT INTO "PersonFaceEmbedding" '
            '("CanonicalPersonID","ModelVersionID","Embedding","EvidenceItemID",'
            ' "EvidenceObjectID","ImageSha256","ImageLabel","BoundingBox",'
            ' "DetectorScore","QualityScore","FaceCount","IsPrimary",'
            ' "EnrolledByActor","EnrolmentSource") '
            'VALUES (%s,%s,%s::vector,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) '
            'ON CONFLICT ("CanonicalPersonID","ImageSha256","ModelVersionID") DO NOTHING '
            'RETURNING "PersonFaceEmbeddingID"',
            (canonical_person_id, model_version_id, vec, evidence_item_id,
             evidence_object_id, image_sha256, image_label, Json(bounding_box or {}),
             detector_score, quality, int(face_count), bool(make_primary),
             actor, enrolment_source))
        row = cur.fetchone()
        if row:
            return int(row[0]), True
        # Already enrolled — return the existing row so the caller stays idempotent.
        cur.execute(
            'SELECT "PersonFaceEmbeddingID" FROM "PersonFaceEmbedding" '
            'WHERE "CanonicalPersonID"=%s AND "ImageSha256"=%s AND "ModelVersionID"=%s',
            (canonical_person_id, image_sha256, model_version_id))
        existing = cur.fetchone()
    if not existing:  # pragma: no cover - ON CONFLICT fired but the row is gone
        raise FaceStoreError("The face could not be enrolled.")
    return int(existing[0]), False


def list_person_faces(conn, cpid: int, *, include_archived: bool = False) -> list[dict]:
    """Enrolled descriptors for one person (metadata only — never the vector)."""
    sql = (
        'SELECT pfe."PersonFaceEmbeddingID", pfe."ModelVersionID", mv."ModelName", '
        '       pfe."ImageSha256", pfe."ImageLabel", pfe."BoundingBox", '
        '       pfe."DetectorScore"::float, pfe."QualityScore"::float, '
        '       pfe."IsPrimary", pfe."EnrolmentSource", pfe."EnrolledByActor", '
        '       pfe."EvidenceItemID", pfe."IsArchived", pfe."CreatedAt"::text, '
        '       pfe."Sensitivity" '
        'FROM "PersonFaceEmbedding" pfe '
        'JOIN "ModelVersion" mv ON mv."ModelVersionID" = pfe."ModelVersionID" '
        'WHERE pfe."CanonicalPersonID"=%s ')
    if not include_archived:
        sql += 'AND pfe."IsArchived"=FALSE '
    sql += 'ORDER BY pfe."IsPrimary" DESC, pfe."PersonFaceEmbeddingID" DESC LIMIT 50'
    with conn.cursor() as cur:
        cur.execute(sql, (cpid,))
        rows = cur.fetchall()
    return [{
        "person_face_embedding_id": int(r[0]),
        "model_version_id": int(r[1]),
        "model_name": r[2],
        "image_sha256": r[3],
        "image_label": r[4],
        "bounding_box": r[5] or {},
        "detector_score": r[6],
        "quality_score": r[7],
        "is_primary": bool(r[8]),
        "enrolment_source": r[9],
        "enrolled_by_actor": r[10],
        "evidence_item_id": r[11],
        "is_archived": bool(r[12]),
        "created_at": r[13],
        "sensitivity": r[14],
    } for r in rows]


def archive_face(conn, face_id: int, *, actor: Optional[str],
                 reason: Optional[str]) -> Optional[int]:
    """Retire a gallery descriptor. Archived, never deleted — a biometric record
    that was once searchable must stay reconstructible for audit."""
    with conn.cursor() as cur:
        cur.execute(
            'UPDATE "PersonFaceEmbedding" '
            'SET "IsArchived"=TRUE, "ArchivedAt"=now(), "ArchiveReason"=%s, '
            '    "IsPrimary"=FALSE '
            'WHERE "PersonFaceEmbeddingID"=%s AND "IsArchived"=FALSE '
            'RETURNING "CanonicalPersonID"',
            ((reason or f"retired by {actor or 'unknown actor'}")[:200], face_id))
        row = cur.fetchone()
    return int(row[0]) if row else None


# ---------------------------------------------------------------------------
# ANN search
# ---------------------------------------------------------------------------
def search_gallery(conn, *, model_version_id: int, embedding,
                   top_k: int = 5, min_similarity: float = 0.0,
                   exclude_person_ids: Iterable[int] = ()) -> list[dict]:
    """Top-k nearest PERSONS for a probe descriptor.

    A person may have several enrolled photos, so the ANN is over-fetched and then
    collapsed to each person's best-scoring face. Merged-away identities are
    excluded: surfacing one would point an officer at a record that has been
    superseded.
    """
    if int(top_k) <= 0:
        return []
    vec = to_pgvector(embedding)
    # Over-fetch so grouping by person still fills the shortlist when one person
    # holds several gallery photos.
    fetch = min(400, max(int(top_k) * 8, 40))

    params: list[Any] = [vec, model_version_id]
    where_extra = ""
    excluded = sorted({int(p) for p in exclude_person_ids})
    if excluded:
        where_extra = 'AND pfe."CanonicalPersonID" <> ALL(%s) '
        params.append(excluded)
    params += [vec, fetch]

    with conn.cursor() as cur:
        cur.execute(
            'SELECT pfe."PersonFaceEmbeddingID", pfe."CanonicalPersonID", '
            '       (pfe."Embedding" <=> %s::vector) AS dist, '
            '       pfe."QualityScore"::float, pfe."ImageLabel", pfe."BoundingBox", '
            '       pfe."EvidenceItemID", pfe."IsPrimary" '
            'FROM "PersonFaceEmbedding" pfe '
            'JOIN "CanonicalPerson" cp ON cp."CanonicalPersonID" = pfe."CanonicalPersonID" '
            'WHERE pfe."ModelVersionID"=%s '
            '  AND pfe."IsArchived"=FALSE '
            "  AND cp.\"ResolutionStatus\" <> 'merged' " + where_extra +
            'ORDER BY pfe."Embedding" <=> %s::vector LIMIT %s', params)
        rows = cur.fetchall()

    best: dict[int, dict] = {}
    for r in rows:
        # Cosine distance in [0,2] -> similarity in [-1,1]; clamp for display.
        dist = float(r[2])
        similarity = round(max(0.0, min(1.0, 1.0 - dist)), 5)
        cpid = int(r[1])
        prev = best.get(cpid)
        if prev is not None and prev["similarity"] >= similarity:
            prev["gallery_hits"] += 1
            continue
        hits = (prev["gallery_hits"] + 1) if prev else 1
        best[cpid] = {
            "canonical_person_id": cpid,
            "person_face_embedding_id": int(r[0]),
            "similarity": similarity,
            "distance": round(dist, 6),
            "gallery_quality": r[3],
            "image_label": r[4],
            "bounding_box": r[5] or {},
            "evidence_item_id": r[6],
            "is_primary_photo": bool(r[7]),
            "gallery_hits": hits,
        }

    ranked = sorted(best.values(), key=lambda m: m["similarity"], reverse=True)
    kept = [m for m in ranked if m["similarity"] >= float(min_similarity)]
    return kept[:int(top_k)]


# ---------------------------------------------------------------------------
# Person dossier hydration (what the officer actually reads)
# ---------------------------------------------------------------------------
def person_dossiers(conn, cpids: list[int]) -> dict[int, dict]:
    """Compact record summaries for matched persons: identity, aliases, and the
    cases they are already attached to. This is the payload that answers "does
    this person already exist in our records, and what do we know?"."""
    if not cpids:
        return {}
    out: dict[int, dict] = {}
    with conn.cursor() as cur:
        cur.execute(
            'SELECT cp."CanonicalPersonID", cp."PublicRef", cp."DisplayLabel", '
            '       cp."IsUnknown", cp."PrimaryGenderID", cp."ApproxBirthYear", '
            '       cp."IsJuvenile", cp."ResolutionStatus", cp."Attributes", '
            '       ce."CanonicalEntityID" '
            'FROM "CanonicalPerson" cp '
            'LEFT JOIN LATERAL (SELECT c."CanonicalEntityID" FROM "CanonicalEntity" c '
            '                   WHERE c."CanonicalPersonID"=cp."CanonicalPersonID" '
            '                   ORDER BY c."CanonicalEntityID" LIMIT 1) ce ON TRUE '
            'WHERE cp."CanonicalPersonID" = ANY(%s)', (cpids,))
        for r in cur.fetchall():
            out[int(r[0])] = {
                "canonical_person_id": int(r[0]),
                "public_ref": r[1],
                "display_label": r[2],
                "is_unknown": bool(r[3]),
                "primary_gender_id": r[4],
                "approx_birth_year": r[5],
                "is_juvenile": bool(r[6]),
                "resolution_status": r[7],
                "attributes": r[8] or {},
                "canonical_entity_id": int(r[9]) if r[9] is not None else None,
                "aliases": [],
                "case_count": 0,
                "role_types": [],
                "districts": [],
                "recent_cases": [],
                "first_seen": None,
                "last_seen": None,
            }
        if not out:
            return {}
        ids = list(out)

        cur.execute(
            'SELECT "CanonicalPersonID","AliasName" FROM "PersonAlias" '
            'WHERE "CanonicalPersonID" = ANY(%s) ORDER BY "PersonAliasID" LIMIT 200',
            (ids,))
        for cpid, alias in cur.fetchall():
            bucket = out[int(cpid)]["aliases"]
            if alias and alias not in bucket and len(bucket) < 6:
                bucket.append(alias)

        # Case involvement: the "already on record" evidence.
        cur.execute(
            'SELECT r."CanonicalPersonID", r."CaseMasterID", '
            '       COALESCE(NULLIF(cv."SnapshotAttributes" #>> '
            '           \'{official_references,police_crime_no}\', \'\'), cm."CrimeNo"), '
            '       cm."CrimeRegisteredDate"::text, r."RoleType", '
            '       ch."CrimeGroupName", d."DistrictName", st."CaseStatusName" '
            'FROM "CasePartyRole" r '
            'LEFT JOIN "CaseMaster" cm ON cm."CaseMasterID" = r."CaseMasterID" '
            'LEFT JOIN "Unit" u ON u."UnitID" = cm."PoliceStationID" '
            'LEFT JOIN "District" d ON d."DistrictID" = u."DistrictID" '
            'LEFT JOIN "CrimeHead" ch ON ch."CrimeHeadID" = cm."CrimeMajorHeadID" '
            'LEFT JOIN "CaseStatusMaster" st ON st."CaseStatusID" = cm."CaseStatusID" '
            'LEFT JOIN LATERAL (SELECT cv0."SnapshotAttributes" FROM "CaseVersion" cv0 '
            '                   WHERE cv0."CaseMasterID"=r."CaseMasterID" '
            '                     AND cv0."IsCurrent"=TRUE '
            '                   ORDER BY cv0."VersionNo" DESC LIMIT 1) cv ON TRUE '
            'WHERE r."CanonicalPersonID" = ANY(%s) '
            'ORDER BY r."CanonicalPersonID", cm."CrimeRegisteredDate" DESC NULLS LAST, '
            '         r."CasePartyRoleID" DESC LIMIT 600', (ids,))
        for row in cur.fetchall():
            entry = out.get(int(row[0]))
            if entry is None:
                continue
            entry["case_count"] += 1
            role, district, date = row[4], row[6], row[3]
            if role and role not in entry["role_types"]:
                entry["role_types"].append(role)
            if district and district not in entry["districts"]:
                entry["districts"].append(district)
            if date:
                if entry["last_seen"] is None or date > entry["last_seen"]:
                    entry["last_seen"] = date
                if entry["first_seen"] is None or date < entry["first_seen"]:
                    entry["first_seen"] = date
            if len(entry["recent_cases"]) < 5:
                entry["recent_cases"].append({
                    "case_id": int(row[1]) if row[1] is not None else None,
                    "crime_no": row[2],
                    "registered_date": date,
                    "role_type": role,
                    "crime_group": row[5],
                    "district": district,
                    "status": row[7],
                })
    return out


# ---------------------------------------------------------------------------
# Probe audit
# ---------------------------------------------------------------------------
def record_probe(conn, *, probe_ref: str, model_version_id: int,
                 actor: Optional[str], actor_role: Optional[str],
                 request_id: Optional[str], origin: str,
                 intake_draft_key: Optional[str], case_master_id: Optional[int],
                 image_sha256: str, image_bytes: int, capture_mode: str,
                 faces_detected: int, bounding_box: dict,
                 detector_score: Optional[float], quality: Optional[float],
                 embedding, gallery_size_: int, threshold: float,
                 matches: list[dict], latency_ms: Optional[int],
                 decision: str = "pending") -> int:
    """Write the probe row + its shortlist. Same transaction as the search."""
    top = matches[0] if matches else None
    vec = to_pgvector(embedding) if embedding is not None else None
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "FaceSearchProbe" '
            '("ProbeRef","ModelVersionID","Actor","ActorRole","RequestID","Origin",'
            ' "IntakeDraftKey","CaseMasterID","ImageSha256","ImageBytes","CaptureMode",'
            ' "FacesDetected","BoundingBox","DetectorScore","QualityScore","Embedding",'
            ' "GallerySize","MatchCount","TopSimilarity","TopCanonicalPersonID",'
            ' "Threshold","Decision","LatencyMs") '
            'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector,'
            '        %s,%s,%s,%s,%s,%s,%s) '
            'RETURNING "FaceSearchProbeID"',
            (probe_ref, model_version_id, actor, actor_role, request_id, origin,
             intake_draft_key, case_master_id, image_sha256, int(image_bytes),
             capture_mode, int(faces_detected), Json(bounding_box or {}),
             detector_score, quality, vec, int(gallery_size_), len(matches),
             (top["similarity"] if top else None),
             (top["canonical_person_id"] if top else None),
             round(float(threshold), 5), decision, latency_ms))
        probe_id = int(cur.fetchone()[0])

        for rank, m in enumerate(matches, start=1):
            cur.execute(
                'INSERT INTO "FaceProbeMatch" '
                '("FaceSearchProbeID","CanonicalPersonID","PersonFaceEmbeddingID",'
                ' "RankOrder","Similarity","Distance","Band") '
                'VALUES (%s,%s,%s,%s,%s,%s,%s)',
                (probe_id, m["canonical_person_id"], m.get("person_face_embedding_id"),
                 rank, m["similarity"], m.get("distance"), m.get("band", BAND_WEAK)))
    return probe_id


def probe_by_ref(conn, probe_ref: str) -> Optional[dict]:
    """Load a probe by its opaque handle, including its retained descriptor."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT p."FaceSearchProbeID", p."ProbeRef", p."ModelVersionID", '
            '       mv."ModelName", p."Actor", p."ActorRole", p."Origin", '
            '       p."IntakeDraftKey", p."CaseMasterID", p."ImageSha256", '
            '       p."FacesDetected", p."BoundingBox", p."DetectorScore"::float, '
            '       p."QualityScore"::float, p."TopSimilarity"::float, '
            '       p."TopCanonicalPersonID", p."Threshold"::float, p."Decision", '
            '       p."DecidedCanonicalPersonID", p."CreatedAt"::text, '
            '       p."Embedding"::text, p."MatchCount", p."GallerySize" '
            'FROM "FaceSearchProbe" p '
            'JOIN "ModelVersion" mv ON mv."ModelVersionID" = p."ModelVersionID" '
            'WHERE p."ProbeRef"=%s', (probe_ref,))
        r = cur.fetchone()
    if not r:
        return None
    return {
        "face_search_probe_id": int(r[0]), "probe_ref": r[1],
        "model_version_id": int(r[2]), "model_name": r[3],
        "actor": r[4], "actor_role": r[5], "origin": r[6],
        "intake_draft_key": r[7], "case_master_id": r[8],
        "image_sha256": r[9], "faces_detected": int(r[10] or 0),
        "bounding_box": r[11] or {}, "detector_score": r[12], "quality_score": r[13],
        "top_similarity": r[14], "top_canonical_person_id": r[15],
        "threshold": r[16], "decision": r[17],
        "decided_canonical_person_id": r[18], "created_at": r[19],
        "embedding_literal": r[20], "match_count": int(r[21] or 0),
        "gallery_size": int(r[22] or 0),
    }


def probe_matches(conn, probe_id: int) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "CanonicalPersonID","PersonFaceEmbeddingID","RankOrder",'
            '       "Similarity"::float,"Distance"::float,"Band" '
            'FROM "FaceProbeMatch" WHERE "FaceSearchProbeID"=%s ORDER BY "RankOrder"',
            (probe_id,))
        rows = cur.fetchall()
    return [{"canonical_person_id": int(r[0]), "person_face_embedding_id": r[1],
             "rank": int(r[2]), "similarity": r[3], "distance": r[4], "band": r[5]}
            for r in rows]


def set_probe_decision(conn, probe_id: int, *, decision: str,
                       canonical_person_id: Optional[int],
                       actor: Optional[str]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            'UPDATE "FaceSearchProbe" '
            'SET "Decision"=%s, "DecidedCanonicalPersonID"=%s, "DecidedByActor"=%s, '
            '    "DecidedAt"=now() '
            'WHERE "FaceSearchProbeID"=%s',
            (decision, canonical_person_id, actor, probe_id))


def recent_probes(conn, *, limit: int = 25,
                  intake_draft_key: Optional[str] = None) -> list[dict]:
    """The probe trail, newest first — the review surface for biometric searches."""
    clauses, params = [], []
    if intake_draft_key:
        clauses.append('p."IntakeDraftKey"=%s')
        params.append(intake_draft_key)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(max(1, min(int(limit), 200)))
    with conn.cursor() as cur:
        cur.execute(
            'SELECT p."ProbeRef", p."Actor", p."ActorRole", p."Origin", '
            '       p."CaptureMode", p."FacesDetected", p."MatchCount", '
            '       p."TopSimilarity"::float, p."TopCanonicalPersonID", '
            '       cp."DisplayLabel", cp."PublicRef", p."Decision", '
            '       p."CreatedAt"::text, p."LatencyMs", mv."ModelName" '
            'FROM "FaceSearchProbe" p '
            'LEFT JOIN "CanonicalPerson" cp '
            '       ON cp."CanonicalPersonID" = p."TopCanonicalPersonID" '
            'JOIN "ModelVersion" mv ON mv."ModelVersionID" = p."ModelVersionID" '
            f'{where} ORDER BY p."FaceSearchProbeID" DESC LIMIT %s', params)
        rows = cur.fetchall()
    return [{
        "probe_ref": r[0], "actor": r[1], "actor_role": r[2], "origin": r[3],
        "capture_mode": r[4], "faces_detected": int(r[5] or 0),
        "match_count": int(r[6] or 0), "top_similarity": r[7],
        "top_canonical_person_id": r[8], "top_display_label": r[9],
        "top_public_ref": r[10], "decision": r[11], "created_at": r[12],
        "latency_ms": r[13], "model_name": r[14],
    } for r in rows]


# ---------------------------------------------------------------------------
# Confirmation -> review candidate (NEVER an automatic merge)
# ---------------------------------------------------------------------------
def raise_face_candidate(conn, *, person_a: int, person_b: int, similarity: float,
                         probe_ref: str, actor: Optional[str],
                         features: Optional[dict] = None) -> Optional[int]:
    """Record a face-proposed person match for human review.

    Used when a probe is confirmed against an EXISTING identity while the draft
    already carries a different one — i.e. the only case where two canonical
    people are being suggested as the same person. Pairs are stored in a stable
    order and never merged automatically.
    """
    lo, hi = sorted((int(person_a), int(person_b)))
    if lo == hi:
        return None
    payload = {"source": "face_search", "probe_ref": probe_ref,
               "cosine_similarity": round(float(similarity), 5),
               **(features or {})}
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "EntityResolutionCandidateID" FROM "EntityResolutionCandidate" '
            'WHERE "CanonicalPersonA"=%s AND "CanonicalPersonB"=%s '
            "  AND \"Method\"='face' AND \"Status\"='pending'", (lo, hi))
        existing = cur.fetchone()
        if existing:
            return int(existing[0])
        cur.execute(
            'INSERT INTO "EntityResolutionCandidate" '
            '("CanonicalPersonA","CanonicalPersonB","Method","Score","MatchFeatures",'
            ' "Status","ReviewedByActor") '
            "VALUES (%s,%s,'face',%s,%s,'pending',NULL) "
            'RETURNING "EntityResolutionCandidateID"',
            (lo, hi, round(min(1.0, max(0.0, float(similarity))), 5), Json(payload)))
        return int(cur.fetchone()[0])


def link_evidence_to_person(conn, *, evidence_item_id: int, canonical_entity_id: int,
                            confidence: float, probe_ref: str) -> Optional[int]:
    """Record 'this photo depicts this entity' as a CANDIDATE link.

    Uses the existing EvidenceEntityLink review workflow, so a face-derived
    depiction claim carries the same candidate/reviewed state as any other.
    """
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "EvidenceEntityLink" '
            '("EvidenceItemID","CanonicalEntityID","LinkType","Confidence",'
            ' "ReviewStatus") '
            "VALUES (%s,%s,'depicts',%s,'candidate') "
            'ON CONFLICT ("EvidenceItemID","CanonicalEntityID","LinkType") DO NOTHING '
            'RETURNING "EvidenceEntityLinkID"',
            (evidence_item_id, canonical_entity_id,
             round(min(1.0, max(0.0, float(confidence))), 5)))
        row = cur.fetchone()
    return int(row[0]) if row else None


def parse_vector_literal(literal: Optional[str]) -> Optional[list[float]]:
    """Parse pgvector's '[a,b,c]' text form back into floats."""
    if not literal:
        return None
    body = literal.strip()
    if body.startswith("[") and body.endswith("]"):
        body = body[1:-1]
    if not body:
        return None
    try:
        vals = [float(x) for x in body.split(",")]
    except ValueError:
        return None
    return vals if len(vals) == FACE_EMBED_DIM else None
