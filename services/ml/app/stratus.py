"""Catalyst Stratus object-store contract (Prompt 14 Part B, matrix row 8).

Stratus is the deployed system of record for application OBJECTS: digital
evidence, import staging files and generated reports. This module is the narrow,
testable boundary — an in-memory fake for local/CI and a Catalyst-SDK-backed
implementation for deployment. Bucket layout + lifecycle live in
`infra/catalyst/stratus/buckets.json`.

Security posture (report §7.4):
  * private buckets/prefixes; short-expiry EXACT-object presigned up/download;
  * object versioning; SHA-256 + size + MIME + object-key + version recorded in
    Data Store (via EvidenceObject / ImportBatch / Report rows), never the bytes;
  * new evidence is quarantined until size/type/hash + an isolated malware scan
    pass — this module carries the metadata contract only and performs **no OCR,
    transcription, semantic media analysis or canonical-field extraction**.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

# Logical buckets (resolved to real Stratus bucket names via env / buckets.json).
BUCKET_EVIDENCE = "evidence"
BUCKET_IMPORT = "import"
BUCKET_REPORT = "report"
_VALID_BUCKETS = (BUCKET_EVIDENCE, BUCKET_IMPORT, BUCKET_REPORT)

# Presigned-URL lifetime (seconds) — short by default for exact-object transfer.
DEFAULT_PRESIGN_TTL_S = 900


@dataclass(frozen=True)
class ObjectRef:
    """Immutable pointer to a stored object (recorded in Data Store, not bytes)."""
    bucket: str
    key: str
    version_id: str
    size: Optional[int] = None
    content_type: Optional[str] = None
    sha256: Optional[str] = None

    def as_record(self) -> dict:
        return {"bucket": self.bucket, "object_key": self.key, "version_id": self.version_id,
                "size": self.size, "content_type": self.content_type, "sha256": self.sha256}


class StratusClient(ABC):
    """Presigned transfer + versioned object metadata. No byte streaming through the API."""

    @abstractmethod
    def presign_put(self, bucket: str, key: str, *, content_type: str,
                    ttl_s: int = DEFAULT_PRESIGN_TTL_S) -> str: ...

    @abstractmethod
    def presign_get(self, bucket: str, key: str, *, version_id: Optional[str] = None,
                    ttl_s: int = DEFAULT_PRESIGN_TTL_S) -> str: ...

    @abstractmethod
    def head(self, bucket: str, key: str, *, version_id: Optional[str] = None) -> Optional[ObjectRef]: ...

    @abstractmethod
    def list_versions(self, bucket: str, key: str) -> list[ObjectRef]: ...


def _check_bucket(bucket: str) -> None:
    if bucket not in _VALID_BUCKETS:
        raise ValueError(f"unknown logical bucket {bucket!r}; expected one of {_VALID_BUCKETS}")


class InMemoryStratus(StratusClient):
    """Deterministic fake for tests/local runs. Presigned URLs are opaque stubs."""

    def __init__(self) -> None:
        self._objs: dict[tuple[str, str], list[ObjectRef]] = {}

    def put_object(self, ref: ObjectRef) -> ObjectRef:
        _check_bucket(ref.bucket)
        self._objs.setdefault((ref.bucket, ref.key), []).append(ref)
        return ref

    def presign_put(self, bucket, key, *, content_type, ttl_s=DEFAULT_PRESIGN_TTL_S):
        _check_bucket(bucket)
        return f"memory://{bucket}/{key}?op=put&ct={content_type}&ttl={ttl_s}"

    def presign_get(self, bucket, key, *, version_id=None, ttl_s=DEFAULT_PRESIGN_TTL_S):
        _check_bucket(bucket)
        return f"memory://{bucket}/{key}?op=get&v={version_id or 'latest'}&ttl={ttl_s}"

    def head(self, bucket, key, *, version_id=None):
        versions = self._objs.get((bucket, key), [])
        if not versions:
            return None
        if version_id:
            return next((o for o in versions if o.version_id == version_id), None)
        return versions[-1]

    def list_versions(self, bucket, key):
        return list(self._objs.get((bucket, key), []))


class CatalystStratus(StratusClient):
    """Deployed implementation over the Catalyst SDK (Stratus). SDK import deferred."""

    def __init__(self, app=None):
        import zcatalyst_sdk  # only present in the AppSail image
        self._app = app or zcatalyst_sdk.initialize()
        self._stratus = self._app.stratus()

    def _bucket(self, bucket: str):
        _check_bucket(bucket)
        name = os.getenv(f"DRISHTI_STRATUS_{bucket.upper()}_BUCKET", "")
        if not name:
            raise RuntimeError(f"DRISHTI_STRATUS_{bucket.upper()}_BUCKET not configured")
        return self._stratus.bucket(name)

    def presign_put(self, bucket, key, *, content_type, ttl_s=DEFAULT_PRESIGN_TTL_S):
        return self._bucket(bucket).generate_presigned_url(
            key, operation="PUT", expiry_in_seconds=ttl_s, content_type=content_type)

    def presign_get(self, bucket, key, *, version_id=None, ttl_s=DEFAULT_PRESIGN_TTL_S):
        return self._bucket(bucket).generate_presigned_url(
            key, operation="GET", expiry_in_seconds=ttl_s, version_id=version_id)

    def head(self, bucket, key, *, version_id=None):
        obj = self._bucket(bucket).head_object(key, version_id=version_id)
        if not obj:
            return None
        return ObjectRef(bucket=bucket, key=key, version_id=obj.get("version_id", "1"),
                         size=obj.get("size"), content_type=obj.get("content_type"),
                         sha256=obj.get("sha256"))

    def list_versions(self, bucket, key):
        rows = self._bucket(bucket).list_object_versions(key) or []
        return [ObjectRef(bucket=bucket, key=key, version_id=r.get("version_id", "1"),
                          size=r.get("size"), content_type=r.get("content_type")) for r in rows]


def get_stratus() -> StratusClient:
    """Factory: Catalyst Stratus when running in AppSail, else the in-memory fake."""
    if os.getenv("DRISHTI_USE_CATALYST_STRATUS", "").lower() == "true":
        return CatalystStratus()
    return InMemoryStratus()
