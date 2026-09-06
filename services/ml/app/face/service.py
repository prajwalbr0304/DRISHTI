"""Facial-recognition orchestration: probe -> descriptor -> ANN -> dossier.

The flow for "is this person already on record?":

  1. decode + size-check the probe image (attacker-reachable input);
  2. detect and describe the most prominent face (SCRFD + ArcFace);
  3. resolve WHICH gallery to search — the ModelVersion that actually holds
     enrolled faces — and refuse if the active encoder does not match it, because
     a cosine distance across two encoder spaces is a confident-looking lie;
  4. HNSW cosine ANN over ``PersonFaceEmbedding``, collapsed to the best face per
     person;
  5. hydrate each hit into a dossier (identity, aliases, the cases they are
     already attached to) — the actual answer the officer needs;
  6. write the probe + its shortlist to the audit trail IN THE SAME TRANSACTION,
     plus a ModelInference row like every other AI write in this service.

Governance, enforced here and not just documented:
  * a score is never an identification — ``matched`` only means "above threshold,
    worth a human look";
  * confirming a match records a decision and, when it collides with an identity
    already on the draft, raises an ``EntityResolutionCandidate`` (Method='face')
    for review. Nothing merges automatically;
  * probe bytes are never persisted. Only the SHA-256, geometry and descriptor.
"""
from __future__ import annotations

import hashlib
import time
from typing import Optional

from .. import audit, db
from .. import models as model_registry
from ..config import get_settings
from . import encoders as E
from . import modelfiles, schemas as S, store


class FaceServiceError(RuntimeError):
    """Base for typed failures the router maps to HTTP codes."""


class FaceDisabled(FaceServiceError):
    """The capability is switched off by configuration (503)."""


class FaceEngineUnavailable(FaceServiceError):
    """No usable encoder / model weights on this host (503)."""


class FaceGalleryUnavailable(FaceServiceError):
    """Nothing enrolled to search against, or a model-space mismatch (409)."""


class FaceInputError(FaceServiceError):
    """The submitted image was unusable (422)."""


class FaceNotFound(FaceServiceError):
    """A referenced person / probe / face row does not exist (404)."""


# Audit action names (extend the shared vocabulary in audit.Action).
ACTION_SEARCH = "face.search"
ACTION_ENROL = "face.enrol"
ACTION_DECIDE = "face.decision"
ACTION_ARCHIVE = "face.archive"


def _require_enabled() -> None:
    if not get_settings().face_search_enabled:
        raise FaceDisabled(
            "Facial recognition is disabled by server configuration "
            "(FACE_SEARCH_ENABLED=false).")


def _encoder() -> E.FaceEncoder:
    try:
        return E.get_encoder()
    except (E.FaceEncoderUnavailable, modelfiles.FaceModelsMissing) as exc:
        raise FaceEngineUnavailable(str(exc)) from exc


def _decode(image_bytes: bytes) -> E.DecodedImage:
    cap = get_settings().face_probe_max_bytes
    if len(image_bytes) > cap:
        raise FaceInputError(
            f"The image is {len(image_bytes) / 1e6:.1f} MB; the limit is "
            f"{cap / 1e6:.1f} MB. Capture or upload a smaller photo.")
    try:
        return E.decode_image(image_bytes)
    except E.FaceEncodeError as exc:
        raise FaceInputError(str(exc)) from exc


def _primary_face(encoder: E.FaceEncoder, image: E.DecodedImage,
                  *, max_faces: int = 5) -> tuple[list[E.DetectedFace], E.DetectedFace]:
    try:
        faces = encoder.detect_and_encode(image, max_faces=max_faces)
    except E.FaceEncodeError as exc:
        raise FaceInputError(str(exc)) from exc
    if not faces:
        raise FaceInputError(
            "No face was found in that image. Use a clear, front-facing photo "
            "where the face fills a good part of the frame.")
    return faces, faces[0]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _quality_warnings(face: E.DetectedFace, encoder: E.FaceEncoder,
                      faces: list[E.DetectedFace]) -> list[str]:
    out: list[str] = []
    if len(faces) > 1:
        out.append(f"{len(faces)} faces detected — the largest, most confident one "
                   "was used. Crop to a single face if that is not the subject.")
    q = face.quality
    if q is not None and q < 0.35:
        out.append(f"Low image quality ({q:.2f}). A blurred, dim or small face "
                   "weakens the match; re-capture if possible.")
    if not encoder.biometric:
        out.append("Degraded mode: this backend compares photographs, not faces. "
                   "It can only find the same photo already on record.")
    return out


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
def status() -> S.FaceStatusResponse:
    """Capability report. Never raises — the UI needs an honest answer even when
    the engine is missing."""
    settings = get_settings()
    snapshot = E.encoder_status()
    engine_raw = snapshot.get("encoder") or {}
    engine = S.FaceEngineInfo(
        name=engine_raw.get("name"), version=engine_raw.get("version"),
        family=engine_raw.get("family"), dim=engine_raw.get("dim"),
        biometric=bool(engine_raw.get("biometric")),
        recommended_threshold=engine_raw.get("recommended_threshold"),
        strong_threshold=engine_raw.get("strong_threshold"),
        note=engine_raw.get("note"), providers=engine_raw.get("providers") or [],
        pack=engine_raw.get("pack"))

    models_raw = snapshot.get("models") or {}
    models_info = S.FaceModelsInfo(
        pack=models_raw.get("pack", modelfiles.DEFAULT_PACK),
        present=bool(models_raw.get("present")),
        detector=models_raw.get("detector"), recogniser=models_raw.get("recogniser"),
        approx_download_mb=models_raw.get("approx_download_mb"),
        install_command=models_raw.get("install_command"),
        directory=models_raw.get("directory"))

    gallery = S.FaceGalleryInfo()
    probes: dict[str, int] = {}
    warnings: list[str] = []
    unavailable: Optional[str] = None

    enabled = bool(settings.face_search_enabled)
    available = bool(snapshot.get("available"))
    if not enabled:
        unavailable = ("Facial recognition is disabled by server configuration "
                       "(FACE_SEARCH_ENABLED=false).")
    elif not available:
        unavailable = str(snapshot.get("error") or "No face encoder is available.")

    if enabled and available:
        try:
            with db.ro_conn() as conn:
                live = store.gallery_model(conn)
                probes = store.probe_counts(conn)
        except Exception as exc:  # noqa: BLE001 — status must not fail on DB trouble
            warnings.append(f"Gallery state unavailable: {type(exc).__name__}.")
            live = None
        if live:
            mv_id, model_name, faces, persons = live
            mismatch = model_name != engine.name
            gallery = S.FaceGalleryInfo(
                model_version_id=mv_id, model_name=model_name,
                face_count=faces, person_count=persons, model_mismatch=mismatch)
            if mismatch:
                warnings.append(
                    f"The enrolled gallery was built with '{model_name}' but the "
                    f"active encoder is '{engine.name}'. Descriptors from different "
                    "models are not comparable — re-enrol the gallery, or set "
                    "DRISHTI_FACE_ENCODER back to the original model.")
        else:
            warnings.append(
                "No faces are enrolled yet, so there is nothing to match against. "
                "Add a reference photo from a person's record to build the gallery.")

    if models_info.install_command and not engine.biometric:
        warnings.append(
            f"Real face recognition is not installed. Run: {models_info.install_command}")

    search_ready = bool(enabled and available and gallery.face_count > 0
                        and not gallery.model_mismatch)
    return S.FaceStatusResponse(
        enabled=enabled, available=available, search_ready=search_ready,
        engine=engine, models=models_info, gallery=gallery, probes=probes,
        onnxruntime=snapshot.get("onnxruntime") or {},
        max_image_bytes=settings.face_probe_max_bytes,
        recommended_long_edge=settings.face_probe_long_edge,
        default_top_k=settings.face_top_k, max_top_k=settings.face_max_top_k,
        max_gallery_per_person=settings.face_max_gallery_per_person,
        unavailable_reason=unavailable, warnings=warnings)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
def search(req: S.FaceSearchRequest, *, actor: Optional[str] = None,
           role: Optional[str] = None,
           request_id: Optional[str] = None) -> S.FaceSearchResponse:
    """1:N search of a probe photo against the enrolled gallery."""
    _require_enabled()
    settings = get_settings()
    encoder = _encoder()

    started = time.perf_counter()
    data = req.image_bytes()
    image = _decode(data)
    faces, face = _primary_face(encoder, image)
    sha = _sha256(data)
    encode_ms = int((time.perf_counter() - started) * 1000)

    top_k = int(req.top_k or settings.face_top_k)
    top_k = max(1, min(top_k, settings.face_max_top_k))
    threshold = (float(req.min_similarity) if req.min_similarity is not None
                 else float(encoder.recommended_threshold))
    warnings = _quality_warnings(face, encoder, faces)

    # The probe row is written in the SAME transaction as the search: a biometric
    # query without an audit record is not an outcome this service produces.
    with db.rw_conn() as conn:
        live = store.gallery_model(conn)
        if not live:
            raise FaceGalleryUnavailable(
                "No reference photos are enrolled yet, so there is nothing to "
                "match against. Add a photo to a person's record first.")
        mv_id, gallery_model_name, gallery_faces, gallery_persons = live
        if gallery_model_name != encoder.name:
            raise FaceGalleryUnavailable(
                f"The enrolled gallery was built with '{gallery_model_name}' but this "
                f"server is running '{encoder.name}'. Face descriptors from different "
                "models are not comparable, so the search was refused rather than "
                "returning meaningless scores.")

        # Return a shortlist even below the threshold (banded 'weak'), so an
        # officer can see "nothing close" instead of an unexplained empty result.
        raw_matches = store.search_gallery(
            conn, model_version_id=mv_id, embedding=face.embedding,
            top_k=top_k, min_similarity=0.0)
        for m in raw_matches:
            m["band"] = store.band_for(m["similarity"], encoder)
            m["above_threshold"] = m["similarity"] >= threshold

        dossiers = store.person_dossiers(
            conn, [m["canonical_person_id"] for m in raw_matches])

        matches: list[S.FaceMatch] = []
        for rank, m in enumerate(raw_matches, start=1):
            record = dossiers.get(m["canonical_person_id"])
            if record is None:
                # Fail closed: the ANN hit no longer resolves to a readable person.
                continue
            # Free-form person Attributes are restricted-sensitivity and are not
            # part of a match card: the officer needs identity + case history to
            # judge the hit, not the person's full attribute bag.
            person_payload = {k: v for k, v in record.items() if k != "attributes"}
            person_payload["recent_cases"] = [S.FaceRecentCase(**c)
                                              for c in record["recent_cases"]]
            matches.append(S.FaceMatch(
                rank=rank, canonical_person_id=m["canonical_person_id"],
                similarity=m["similarity"], distance=m["distance"],
                band=m["band"], above_threshold=m["above_threshold"],
                gallery_hits=m["gallery_hits"], gallery_quality=m["gallery_quality"],
                image_label=m["image_label"],
                person_face_embedding_id=m["person_face_embedding_id"],
                evidence_item_id=m["evidence_item_id"],
                person=S.FacePersonRecord(**person_payload)))

        latency_ms = int((time.perf_counter() - started) * 1000)
        above = [m for m in matches if m.above_threshold]
        best = above[0] if above else None
        probe_ref = store.new_probe_ref()
        decision = "pending" if above else "no_match"

        probe_id = store.record_probe(
            conn, probe_ref=probe_ref, model_version_id=mv_id, actor=actor,
            actor_role=role, request_id=request_id, origin=req.origin,
            intake_draft_key=req.intake_draft_key, case_master_id=req.case_id,
            image_sha256=sha, image_bytes=len(data), capture_mode=req.capture_mode,
            faces_detected=len(faces), bounding_box=(face.box.as_dict() if face.box else {}),
            detector_score=face.detector_score, quality=face.quality,
            embedding=face.embedding, gallery_size_=gallery_faces,
            threshold=threshold,
            matches=[{
                "canonical_person_id": m.canonical_person_id,
                "person_face_embedding_id": m.person_face_embedding_id,
                "similarity": m.similarity, "distance": m.distance, "band": m.band,
            } for m in matches],
            latency_ms=latency_ms, decision=decision)

        # Same audit contract as every other AI write in this service.
        model_registry.log_inference(
            conn, mv_id,
            inputs={"probe_ref": probe_ref, "capture_mode": req.capture_mode,
                    "origin": req.origin, "faces_detected": len(faces),
                    "gallery_faces": gallery_faces, "threshold": threshold,
                    "encode_ms": encode_ms},
            outputs={"match_count": len(matches),
                     "above_threshold": len(above),
                     "top_similarity": (best.similarity if best else None),
                     "top_canonical_person_id": (best.canonical_person_id
                                                 if best else None)},
            confidence=(best.similarity if best else None),
            case_master_id=req.case_id, ref_table="FaceSearchProbe",
            ref_id=str(probe_id), latency_ms=latency_ms)

        audit.record(ACTION_SEARCH, "FaceSearchProbe", probe_id, actor=actor,
                     detail={"probe_ref": probe_ref, "origin": req.origin,
                             "capture_mode": req.capture_mode,
                             "match_count": len(matches),
                             "above_threshold": len(above),
                             "top_similarity": (best.similarity if best else None),
                             "biometric": encoder.biometric},
                     conn=conn)

    if not matches:
        warnings.append(
            f"No similar face in the {gallery_persons} enrolled record(s). This "
            "person does not appear to be on file — proceed as a new identity.")
    elif not above:
        warnings.append(
            f"Nothing cleared the {threshold:.2f} match threshold. The closest "
            f"record scored {matches[0].similarity:.2f} and is shown as a weak lead "
            "only — treat it as unmatched unless a reviewer says otherwise.")

    return S.FaceSearchResponse(
        probe=S.FaceProbeInfo(
            probe_ref=probe_ref, faces_detected=len(faces),
            bounding_box=(face.box.as_dict() if face.box else {}),
            landmarks=face.landmarks, detector_score=face.detector_score,
            quality=face.quality, image_width=image.width, image_height=image.height,
            image_sha256=sha, capture_mode=req.capture_mode),
        matches=matches, best_match=best, matched=bool(best), threshold=threshold,
        model_name=encoder.name, model_version_id=mv_id,
        biometric=encoder.biometric, gallery_face_count=gallery_faces,
        gallery_person_count=gallery_persons, latency_ms=latency_ms,
        warnings=warnings)


# ---------------------------------------------------------------------------
# Enrolment
# ---------------------------------------------------------------------------
def enrol(req: S.FaceEnrolRequest, *, actor: Optional[str] = None,
          role: Optional[str] = None) -> S.FaceEnrolResponse:
    """Add a reference photo to a canonical person's gallery."""
    _require_enabled()
    settings = get_settings()
    encoder = _encoder()

    data = req.image_bytes()
    image = _decode(data)
    faces, face = _primary_face(encoder, image)
    sha = _sha256(data)
    warnings = _quality_warnings(face, encoder, faces)

    if (settings.face_require_detection_for_enrol and encoder.biometric
            and face.detector_score is None):
        raise FaceInputError(
            "No face was detected in that photo, so it cannot be used as a "
            "reference image.")
    if (face.quality is not None and encoder.biometric
            and face.quality < encoder.min_enrol_quality):
        raise FaceInputError(
            f"That photo is too poor to enrol (quality {face.quality:.2f}, minimum "
            f"{encoder.min_enrol_quality:.2f}). A weak reference photo produces "
            "false matches for everyone. Use a sharper, better-lit, front-facing image.")

    with db.rw_conn() as conn:
        person = store.person_exists(conn, req.canonical_person_id)
        if person is None:
            raise FaceNotFound(
                f"CanonicalPerson {req.canonical_person_id} not found.")
        if person[2] == "merged":
            raise FaceInputError(
                f"{person[0]} has been merged into another identity; enrol the "
                "photo against the surviving record instead.")

        mv_id = store.model_version_for(conn, encoder)
        existing = store.count_person_faces(conn, req.canonical_person_id, mv_id)
        if existing >= settings.face_max_gallery_per_person:
            raise FaceInputError(
                f"{person[0]} already has {existing} reference photos (the limit is "
                f"{settings.face_max_gallery_per_person}). Retire one before adding "
                "another — an over-represented person crowds out other matches.")

        face_id, created = store.enrol_face(
            conn, canonical_person_id=req.canonical_person_id,
            model_version_id=mv_id, embedding=face.embedding, image_sha256=sha,
            bounding_box=(face.box.as_dict() if face.box else {}),
            detector_score=face.detector_score, quality=face.quality,
            face_count=len(faces), image_label=req.image_label,
            evidence_item_id=req.evidence_item_id,
            enrolment_source=("camera_capture" if req.capture_mode == "camera"
                              else "manual_upload"),
            actor=actor, make_primary=req.make_primary)

        rows = store.list_person_faces(conn, req.canonical_person_id)
        total = store.count_person_faces(conn, req.canonical_person_id, mv_id)
        audit.record(ACTION_ENROL, "PersonFaceEmbedding", face_id, actor=actor,
                     detail={"canonical_person_id": req.canonical_person_id,
                             "public_ref": person[0], "created": created,
                             "model_name": encoder.name,
                             "quality": face.quality,
                             "gallery_size": total},
                     conn=conn)

    record = next((r for r in rows if r["person_face_embedding_id"] == face_id), None)
    if record is None:  # pragma: no cover - just-inserted row must be listed
        raise FaceServiceError("The enrolled face could not be read back.")
    if not created:
        warnings.append("That exact photo was already enrolled for this person; "
                        "the existing record was reused.")
    return S.FaceEnrolResponse(
        created=created, face=S.FaceRecord(**record),
        canonical_person_id=req.canonical_person_id, gallery_face_count=total,
        detector_score=face.detector_score, quality=face.quality,
        warnings=warnings)


def person_faces(cpid: int) -> S.FaceListResponse:
    """Enrolled reference photos for one person (metadata only)."""
    _require_enabled()
    with db.ro_conn() as conn:
        if store.person_exists(conn, cpid) is None:
            raise FaceNotFound(f"CanonicalPerson {cpid} not found.")
        rows = store.list_person_faces(conn, cpid)
    try:
        encoder = _encoder()
        model_name, biometric = encoder.name, encoder.biometric
    except FaceEngineUnavailable:
        model_name, biometric = None, False
    return S.FaceListResponse(
        canonical_person_id=cpid, faces=[S.FaceRecord(**r) for r in rows],
        model_name=model_name, biometric=biometric)


def remove_face(face_id: int, *, actor: Optional[str] = None,
                reason: Optional[str] = None) -> S.FaceDeleteResponse:
    """Retire a reference photo (archived for audit, never hard-deleted)."""
    _require_enabled()
    with db.rw_conn() as conn:
        cpid = store.archive_face(conn, face_id, actor=actor, reason=reason)
        if cpid is None:
            raise FaceNotFound(
                f"Reference photo {face_id} not found, or already retired.")
        live = store.gallery_model(conn)
        remaining = (store.count_person_faces(conn, cpid, live[0]) if live else 0)
        audit.record(ACTION_ARCHIVE, "PersonFaceEmbedding", face_id, actor=actor,
                     detail={"canonical_person_id": cpid, "remaining": remaining},
                     conn=conn)
    return S.FaceDeleteResponse(archived=True, person_face_embedding_id=face_id,
                                canonical_person_id=cpid,
                                gallery_face_count=remaining)


# ---------------------------------------------------------------------------
# Probe decision
# ---------------------------------------------------------------------------
def decide(probe_ref: str, req: S.FaceDecisionRequest, *,
           actor: Optional[str] = None) -> S.FaceDecisionResponse:
    """Record the officer's disposition of a shortlist.

    'confirmed' is a REVIEWABLE assertion, not a merge: if the draft already
    carries a different identity, this raises an EntityResolutionCandidate
    (Method='face') and leaves both records intact.
    """
    _require_enabled()
    warnings: list[str] = []
    if req.decision == "confirmed" and req.canonical_person_id is None:
        raise FaceInputError(
            "Confirming a match needs the canonical_person_id that was accepted.")

    with db.rw_conn() as conn:
        probe = store.probe_by_ref(conn, probe_ref)
        if probe is None:
            raise FaceNotFound(f"Face probe {probe_ref} not found.")
        if probe["decision"] not in ("pending", "no_match"):
            raise FaceInputError(
                f"That probe was already resolved as '{probe['decision']}'. "
                "Run a fresh scan to record a different outcome.")

        cpid = req.canonical_person_id
        enrolled_id: Optional[int] = None
        candidate_id: Optional[int] = None

        if req.decision == "confirmed":
            if store.person_exists(conn, cpid) is None:
                raise FaceNotFound(f"CanonicalPerson {cpid} not found.")
            shortlist = {m["canonical_person_id"] for m in
                         store.probe_matches(conn, probe["face_search_probe_id"])}
            if cpid not in shortlist:
                raise FaceInputError(
                    "That person was not in this probe's shortlist. Only a candidate "
                    "the search actually returned can be confirmed against it.")

            if req.enrol_probe:
                vec = store.parse_vector_literal(probe["embedding_literal"])
                if vec is None:
                    warnings.append("The probe descriptor is no longer available, so "
                                    "the photo was not added to the gallery.")
                else:
                    settings = get_settings()
                    held = store.count_person_faces(conn, cpid, probe["model_version_id"])
                    if held >= settings.face_max_gallery_per_person:
                        warnings.append(
                            f"Gallery limit reached ({held}/"
                            f"{settings.face_max_gallery_per_person}); the probe photo "
                            "was not added.")
                    else:
                        enrolled_id, created = store.enrol_face(
                            conn, canonical_person_id=cpid,
                            model_version_id=probe["model_version_id"],
                            embedding=vec, image_sha256=probe["image_sha256"],
                            bounding_box=probe["bounding_box"],
                            detector_score=probe["detector_score"],
                            quality=probe["quality_score"],
                            image_label=f"probe {probe_ref}",
                            enrolment_source="probe_confirmation", actor=actor)
                        if not created:
                            warnings.append("That probe photo was already enrolled "
                                            "for this person.")

            other = req.existing_canonical_person_id
            if other is not None and int(other) != int(cpid):
                candidate_id = store.raise_face_candidate(
                    conn, person_a=int(other), person_b=int(cpid),
                    similarity=float(probe["top_similarity"] or 0.0),
                    probe_ref=probe_ref, actor=actor,
                    features={"draft_person": int(other), "matched_person": int(cpid),
                              "origin": probe["origin"]})
                warnings.append(
                    "This record already had a different identity attached. Both were "
                    "kept and a face-method match candidate was raised for review — "
                    "identities are never merged on a face score.")

        store.set_probe_decision(conn, probe["face_search_probe_id"],
                                 decision=req.decision,
                                 canonical_person_id=cpid, actor=actor)
        audit.record(ACTION_DECIDE, "FaceSearchProbe",
                     probe["face_search_probe_id"], actor=actor,
                     detail={"probe_ref": probe_ref, "decision": req.decision,
                             "canonical_person_id": cpid,
                             "enrolled_face_id": enrolled_id,
                             "entity_resolution_candidate_id": candidate_id},
                     conn=conn)

    messages = {
        "confirmed": "Match confirmed and recorded for review.",
        "rejected": "Shortlist rejected. No identity was linked.",
        "no_match": "Recorded as no match. Treat this as a new identity.",
        "new_person": "Recorded as a new person; no existing record was linked.",
    }
    return S.FaceDecisionResponse(
        probe_ref=probe_ref, decision=req.decision, canonical_person_id=cpid,
        enrolled_face_id=enrolled_id, entity_resolution_candidate_id=candidate_id,
        message=messages[req.decision], warnings=warnings)


def probe_trail(*, limit: int = 25,
                intake_draft_key: Optional[str] = None) -> S.FaceProbeTrailResponse:
    """The biometric-search audit trail (who searched for whom, and the outcome)."""
    _require_enabled()
    with db.ro_conn() as conn:
        items = store.recent_probes(conn, limit=limit,
                                    intake_draft_key=intake_draft_key)
        counts = store.probe_counts(conn)
    return S.FaceProbeTrailResponse(
        items=[S.FaceProbeTrailItem(**i) for i in items],
        total=counts.get("total", len(items)))
