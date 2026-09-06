"""Typed request/response models for the facial-recognition API.

Probe images arrive as base64 in the JSON body: a probe is a transient query, not
evidence, so its bytes are never written to object storage or to Postgres — only
the SHA-256, the geometry and the descriptor are retained (see migration 025). A
photo that should become part of the record goes through the evidence pipeline and
is enrolled from there.
"""
from __future__ import annotations

import base64
import binascii
import re
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

CAPTURE_MODES = ("upload", "camera")
ORIGINS = ("intake_fir", "standalone", "case_file", "person_page", "enrolment")
DECISIONS = ("confirmed", "rejected", "no_match", "new_person")
BANDS = ("strong", "probable", "weak")

_DATA_URL = re.compile(r"^data:image/[a-zA-Z0-9.+-]+;base64,", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")
# A DoS backstop only, sized to sit just under the 2 MB request-body cap
# (BodySizeLimitMiddleware answers 413 above that). The MEANINGFUL limit is
# ``face_probe_max_bytes``, applied after decoding so the caller gets an error
# stating the actual size and the actual limit. Keeping this bound loose means
# that friendlier message is what a slightly-too-large photo normally hits.
MAX_BASE64_CHARS = 1_950_000


def decode_base64_image(raw: str) -> bytes:
    """Strict base64 (optionally data-URL prefixed) -> bytes."""
    if not raw:
        raise ValueError("No image was supplied.")
    if len(raw) > MAX_BASE64_CHARS:
        raise ValueError("The image is too large. Capture or upload a smaller photo.")
    body = _WHITESPACE.sub("", _DATA_URL.sub("", raw))
    # Tolerate URL-safe alphabet and missing padding from browser encoders.
    body = body.replace("-", "+").replace("_", "/")
    body += "=" * (-len(body) % 4)
    try:
        return base64.b64decode(body, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("The image could not be decoded (invalid base64).") from exc


class _ImageBody(BaseModel):
    image_base64: str = Field(..., min_length=32, max_length=MAX_BASE64_CHARS,
                              description="Raw or data-URL base64 image bytes.")

    @field_validator("image_base64")
    @classmethod
    def _check_decodable(cls, v: str) -> str:
        decode_base64_image(v)          # fail fast with a readable message
        return v

    def image_bytes(self) -> bytes:
        return decode_base64_image(self.image_base64)


# --- status -----------------------------------------------------------------
class FaceEngineInfo(BaseModel):
    name: Optional[str] = None
    version: Optional[str] = None
    family: Optional[str] = None
    dim: Optional[int] = None
    #: False means the backend compares IMAGES, not identities. The UI must say so.
    biometric: bool = False
    recommended_threshold: Optional[float] = None
    strong_threshold: Optional[float] = None
    note: Optional[str] = None
    providers: list[str] = Field(default_factory=list)
    pack: Optional[str] = None


class FaceModelsInfo(BaseModel):
    pack: str
    present: bool
    detector: Optional[str] = None
    recogniser: Optional[str] = None
    approx_download_mb: Optional[int] = None
    install_command: Optional[str] = None
    directory: Optional[str] = None


class FaceGalleryInfo(BaseModel):
    model_version_id: Optional[int] = None
    model_name: Optional[str] = None
    face_count: int = 0
    person_count: int = 0
    #: True when the ACTIVE encoder differs from the one that built the gallery —
    #: the two spaces are not comparable, so search must not silently proceed.
    model_mismatch: bool = False


class FaceStatusResponse(BaseModel):
    enabled: bool
    available: bool
    search_ready: bool
    engine: FaceEngineInfo
    models: Optional[FaceModelsInfo] = None
    gallery: FaceGalleryInfo
    probes: dict[str, int] = Field(default_factory=dict)
    onnxruntime: dict[str, Any] = Field(default_factory=dict)
    max_image_bytes: int
    recommended_long_edge: int
    default_top_k: int
    max_top_k: int
    max_gallery_per_person: int
    unavailable_reason: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)


# --- search -----------------------------------------------------------------
class FaceSearchRequest(_ImageBody):
    top_k: Optional[int] = Field(None, ge=1, le=25)
    #: Override the encoder's default cut-off. Lower surfaces weaker leads —
    #: allowed, but they come back banded 'weak' and labelled as such.
    min_similarity: Optional[float] = Field(None, ge=0.0, le=1.0)
    capture_mode: str = Field("upload", pattern="^(upload|camera)$")
    origin: str = Field("standalone")
    intake_draft_key: Optional[str] = Field(None, max_length=120)
    case_id: Optional[int] = None
    actor: Optional[str] = Field(None, max_length=120)

    @field_validator("origin")
    @classmethod
    def _known_origin(cls, v: str) -> str:
        if v not in ORIGINS:
            raise ValueError(f"origin must be one of {', '.join(ORIGINS)}")
        return v


class FaceRecentCase(BaseModel):
    case_id: Optional[int] = None
    crime_no: Optional[str] = None
    registered_date: Optional[str] = None
    role_type: Optional[str] = None
    crime_group: Optional[str] = None
    district: Optional[str] = None
    status: Optional[str] = None


class FacePersonRecord(BaseModel):
    """The dossier shown for a matched person."""
    canonical_person_id: int
    public_ref: str
    display_label: Optional[str] = None
    is_unknown: bool = False
    primary_gender_id: Optional[int] = None
    approx_birth_year: Optional[int] = None
    is_juvenile: bool = False
    resolution_status: str = "canonical"
    canonical_entity_id: Optional[int] = None
    aliases: list[str] = Field(default_factory=list)
    case_count: int = 0
    role_types: list[str] = Field(default_factory=list)
    districts: list[str] = Field(default_factory=list)
    recent_cases: list[FaceRecentCase] = Field(default_factory=list)
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None


class FaceMatch(BaseModel):
    rank: int
    canonical_person_id: int
    similarity: float
    distance: Optional[float] = None
    #: strong | probable | weak — verbal because a bare cosine means nothing to
    #: the officer reading it.
    band: str = "weak"
    #: True only when the score clears the encoder's match threshold.
    above_threshold: bool = False
    gallery_hits: int = 1
    gallery_quality: Optional[float] = None
    image_label: Optional[str] = None
    person_face_embedding_id: Optional[int] = None
    evidence_item_id: Optional[int] = None
    person: FacePersonRecord


class FaceProbeInfo(BaseModel):
    probe_ref: str
    faces_detected: int = 0
    bounding_box: dict[str, Any] = Field(default_factory=dict)
    landmarks: list[list[float]] = Field(default_factory=list)
    detector_score: Optional[float] = None
    quality: Optional[float] = None
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    image_sha256: Optional[str] = None
    capture_mode: str = "upload"


class FaceSearchResponse(BaseModel):
    probe: FaceProbeInfo
    matches: list[FaceMatch] = Field(default_factory=list)
    #: The highest-confidence hit that cleared the threshold, if any. This is the
    #: "already on record" answer; everything else is a shortlist.
    best_match: Optional[FaceMatch] = None
    matched: bool = False
    threshold: float
    model_name: str
    model_version_id: int
    biometric: bool
    gallery_face_count: int = 0
    gallery_person_count: int = 0
    latency_ms: int = 0
    #: Never omitted: a score is a lead, not an identification.
    disclaimer: str = (
        "A face score is an investigative lead requiring human confirmation, not "
        "an identification. Confirming a match records a reviewable entity-"
        "resolution candidate; it never merges identities automatically.")
    warnings: list[str] = Field(default_factory=list)


# --- enrolment --------------------------------------------------------------
class FaceEnrolRequest(_ImageBody):
    canonical_person_id: int = Field(..., ge=1)
    image_label: Optional[str] = Field(None, max_length=160)
    evidence_item_id: Optional[int] = None
    make_primary: bool = False
    capture_mode: str = Field("upload", pattern="^(upload|camera)$")
    actor: Optional[str] = Field(None, max_length=120)


class FaceRecord(BaseModel):
    person_face_embedding_id: int
    model_version_id: int
    model_name: Optional[str] = None
    image_sha256: str
    image_label: Optional[str] = None
    bounding_box: dict[str, Any] = Field(default_factory=dict)
    detector_score: Optional[float] = None
    quality_score: Optional[float] = None
    is_primary: bool = False
    enrolment_source: str = "manual_upload"
    enrolled_by_actor: Optional[str] = None
    evidence_item_id: Optional[int] = None
    is_archived: bool = False
    created_at: Optional[str] = None
    sensitivity: str = "restricted"


class FaceEnrolResponse(BaseModel):
    created: bool
    face: FaceRecord
    canonical_person_id: int
    gallery_face_count: int
    detector_score: Optional[float] = None
    quality: Optional[float] = None
    warnings: list[str] = Field(default_factory=list)


class FaceListResponse(BaseModel):
    canonical_person_id: int
    faces: list[FaceRecord] = Field(default_factory=list)
    model_name: Optional[str] = None
    biometric: bool = False


class FaceDeleteResponse(BaseModel):
    archived: bool
    person_face_embedding_id: int
    canonical_person_id: Optional[int] = None
    gallery_face_count: int = 0


# --- probe decision ---------------------------------------------------------
class FaceDecisionRequest(BaseModel):
    decision: str = Field(..., pattern="^(confirmed|rejected|no_match|new_person)$")
    #: Required for 'confirmed': which shortlisted person the officer accepted.
    canonical_person_id: Optional[int] = Field(None, ge=1)
    #: When confirming, add the probe descriptor to that person's gallery so the
    #: next search recognises this pose too. Off by default — enrolling a probe is
    #: a deliberate act, not a side effect of clicking through a shortlist.
    enrol_probe: bool = False
    #: An identity already attached to the draft/case. If it differs from the
    #: confirmed person, a face-method EntityResolutionCandidate is raised for
    #: review instead of quietly overwriting either record.
    existing_canonical_person_id: Optional[int] = Field(None, ge=1)
    note: Optional[str] = Field(None, max_length=500)
    actor: Optional[str] = Field(None, max_length=120)


class FaceDecisionResponse(BaseModel):
    probe_ref: str
    decision: str
    canonical_person_id: Optional[int] = None
    enrolled_face_id: Optional[int] = None
    entity_resolution_candidate_id: Optional[int] = None
    message: str
    warnings: list[str] = Field(default_factory=list)


# --- probe trail ------------------------------------------------------------
class FaceProbeTrailItem(BaseModel):
    probe_ref: str
    actor: Optional[str] = None
    actor_role: Optional[str] = None
    origin: Optional[str] = None
    capture_mode: Optional[str] = None
    faces_detected: int = 0
    match_count: int = 0
    top_similarity: Optional[float] = None
    top_canonical_person_id: Optional[int] = None
    top_display_label: Optional[str] = None
    top_public_ref: Optional[str] = None
    decision: str = "pending"
    created_at: Optional[str] = None
    latency_ms: Optional[int] = None
    model_name: Optional[str] = None


class FaceProbeTrailResponse(BaseModel):
    items: list[FaceProbeTrailItem] = Field(default_factory=list)
    total: int = 0
