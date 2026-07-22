"""S3 gateway for the digital-evidence platform (Phase 5).

Wraps boto3 for the single PRIVATE evidence bucket and exposes only the narrow
operations the service needs:

  * ``presign_put``  — short-lived pre-signed URL for the browser to upload one
                       exact object (no AWS credentials ever reach the browser).
  * ``presign_get``  — short-lived pre-signed URL to download/preview one exact
                       object, forcing the correct content-type + filename.
  * ``head``         — object existence + size (upload completion check).
  * ``get_bytes``    — bounded read used only to re-compute SHA-256 for
                       server-side hash verification.
  * ``delete``       — remove one object (synthetic-demo reset only).

Every key is confined to ``<prefix>/`` inside the configured bucket. Credentials
come from the environment: a local SSO profile in dev, or the task role in a
deployment — never from code, the frontend, images, or committed files.

The gateway is a small Protocol so the service can be driven by an in-memory
fake in tests (no AWS calls, no network) while the real implementation uses
boto3 with SigV4 pre-signing (required in ap-south-1).
"""
from __future__ import annotations

import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional, Protocol

from ..config import get_settings


# ---------------------------------------------------------------------------
# Errors + value objects
# ---------------------------------------------------------------------------
class S3Error(Exception):
    """Any storage-layer failure (never carries credentials)."""


class ObjectNotFound(S3Error):
    """The requested object does not exist in the bucket."""


class S3NotConfigured(S3Error):
    """No evidence bucket is configured (metadata-only mode)."""


@dataclass(frozen=True)
class ObjectHead:
    exists: bool
    size: Optional[int] = None
    content_type: Optional[str] = None
    etag: Optional[str] = None


@dataclass(frozen=True)
class PresignedUpload:
    url: str
    method: str = "PUT"
    # Headers the browser MUST echo on the PUT (empty: we sign a bare put_object
    # so any content-type works, avoiding signature mismatches).
    headers: dict[str, str] = field(default_factory=dict)
    storage_key: str = ""
    expires_in: int = 900


# ---------------------------------------------------------------------------
# Key derivation (all keys confined to the configured prefix)
# ---------------------------------------------------------------------------
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_filename(name: Optional[str], fallback: str = "file") -> str:
    """A safe, bounded object-name component (never a path)."""
    base = (name or "").strip().replace("\\", "/").split("/")[-1]
    base = _SAFE.sub("_", base).strip("._") or fallback
    return base[:120]


def build_object_key(prefix: str, case_id: Optional[int], evidence_ref: str,
                     version_no: int, filename: str) -> str:
    """Deterministic, prefix-confined key:
    ``<prefix>/case-<id|unlinked>/<ref>/v<n>/<filename>``."""
    pfx = (prefix or "evidence").strip("/")
    case_part = f"case-{case_id}" if case_id else "unlinked"
    ref = _SAFE.sub("_", (evidence_ref or "item")).strip("._") or "item"
    return f"{pfx}/{case_part}/{ref}/v{int(version_no)}/{sanitize_filename(filename)}"


def key_in_prefix(key: str, prefix: str) -> bool:
    """Guard: a client-supplied storage key must stay inside the prefix (never
    let a completion call point at an arbitrary object)."""
    if not key or key.startswith("/") or ".." in key:
        return False
    return key.startswith((prefix or "evidence").strip("/") + "/")


# ---------------------------------------------------------------------------
# Gateway protocol + real boto3 implementation
# ---------------------------------------------------------------------------
class S3Gateway(Protocol):
    bucket: str

    def presign_put(self, key: str, expires_in: int) -> PresignedUpload: ...
    def presign_get(self, key: str, *, filename: Optional[str] = None,
                    content_type: Optional[str] = None,
                    expires_in: int = 900, disposition: str = "attachment") -> str: ...
    def head(self, key: str) -> ObjectHead: ...
    def get_bytes(self, key: str, max_bytes: int) -> bytes: ...
    def delete(self, key: str) -> None: ...


class Boto3S3Gateway:
    """Real S3 gateway. Lazily builds a SigV4 client from the configured region
    and (optional) SSO profile. Never logs credentials."""

    def __init__(self, bucket: str, *, region: str, profile: str = "",
                 endpoint_url: str = ""):
        self.bucket = bucket
        self._region = region
        self._profile = profile
        self._endpoint_url = endpoint_url or None
        self._client = None

    def _c(self):
        if self._client is None:
            import boto3
            from botocore.config import Config
            session = boto3.Session(
                profile_name=self._profile or None, region_name=self._region)
            self._client = session.client(
                "s3", endpoint_url=self._endpoint_url,
                config=Config(signature_version="s3v4",
                              s3={"addressing_style": "virtual"}))
        return self._client

    def presign_put(self, key: str, expires_in: int) -> PresignedUpload:
        try:
            url = self._c().generate_presigned_url(
                "put_object", Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=int(expires_in), HttpMethod="PUT")
        except Exception as exc:  # noqa: BLE001
            raise S3Error(f"could not presign upload: {type(exc).__name__}") from exc
        return PresignedUpload(url=url, method="PUT", headers={}, storage_key=key,
                               expires_in=int(expires_in))

    def presign_get(self, key: str, *, filename: Optional[str] = None,
                    content_type: Optional[str] = None, expires_in: int = 900,
                    disposition: str = "attachment") -> str:
        params = {"Bucket": self.bucket, "Key": key}
        if content_type:
            params["ResponseContentType"] = content_type
        disp = "inline" if disposition == "inline" else "attachment"
        if filename:
            params["ResponseContentDisposition"] = f'{disp}; filename="{sanitize_filename(filename)}"'
        else:
            params["ResponseContentDisposition"] = disp
        try:
            return self._c().generate_presigned_url(
                "get_object", Params=params, ExpiresIn=int(expires_in), HttpMethod="GET")
        except Exception as exc:  # noqa: BLE001
            raise S3Error(f"could not presign download: {type(exc).__name__}") from exc

    def head(self, key: str) -> ObjectHead:
        from botocore.exceptions import ClientError
        try:
            r = self._c().head_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchKey", "NotFound"):
                return ObjectHead(exists=False)
            raise S3Error(f"head failed: {code or type(exc).__name__}") from exc
        return ObjectHead(exists=True, size=int(r.get("ContentLength", 0)),
                          content_type=r.get("ContentType"),
                          etag=(r.get("ETag") or "").strip('"') or None)

    def get_bytes(self, key: str, max_bytes: int) -> bytes:
        from botocore.exceptions import ClientError
        try:
            r = self._c().get_object(Bucket=self.bucket, Key=key,
                                     Range=f"bytes=0-{int(max_bytes) - 1}")
            return r["Body"].read(int(max_bytes))
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchKey", "NotFound"):
                raise ObjectNotFound(key) from exc
            raise S3Error(f"get failed: {code or type(exc).__name__}") from exc

    def delete(self, key: str) -> None:
        try:
            self._c().delete_object(Bucket=self.bucket, Key=key)
        except Exception as exc:  # noqa: BLE001
            raise S3Error(f"delete failed: {type(exc).__name__}") from exc


class StratusEvidenceGateway:
    """S3Gateway backed by Catalyst Stratus (deployed AppSail path).

    The AppSail has no AWS credentials, so evidence objects live in the private
    Stratus evidence bucket rather than S3. Presigned PUT/GET + head come from
    the Stratus client; byte read (for server-side SHA-256 verification) is done
    by fetching a short-lived presigned GET (Stratus streams no bytes through its
    API). ``delete`` is a no-op (the synthetic-demo reset relies on versioning /
    expiry, never a hard delete — matches the chain-of-custody posture)."""

    def __init__(self, client=None):
        from ..stratus import BUCKET_EVIDENCE, get_stratus
        self._s = client or get_stratus()
        self._logical = BUCKET_EVIDENCE
        self.bucket = os.getenv("DRISHTI_STRATUS_EVIDENCE_BUCKET", "evidence").strip() or "evidence"

    def presign_put(self, key: str, expires_in: int) -> PresignedUpload:
        # Stratus presigned PUT is not content-type-bound, so any upload type
        # works; sign a bare octet-stream put like the S3 gateway does.
        try:
            url = self._s.presign_put(self._logical, key,
                                      content_type="application/octet-stream", ttl_s=int(expires_in))
        except Exception as exc:  # noqa: BLE001
            raise S3Error(f"could not presign upload: {type(exc).__name__}") from exc
        return PresignedUpload(url=url, method="PUT", headers={}, storage_key=key,
                               expires_in=int(expires_in))

    def presign_get(self, key: str, *, filename: Optional[str] = None,
                    content_type: Optional[str] = None, expires_in: int = 900,
                    disposition: str = "attachment") -> str:
        try:
            return self._s.presign_get(self._logical, key, ttl_s=int(expires_in))
        except Exception as exc:  # noqa: BLE001
            raise S3Error(f"could not presign download: {type(exc).__name__}") from exc

    def head(self, key: str) -> ObjectHead:
        try:
            ref = self._s.head(self._logical, key)
        except Exception as exc:  # noqa: BLE001
            raise S3Error(f"head failed: {type(exc).__name__}") from exc
        if not ref:
            return ObjectHead(exists=False)
        # Stratus object-metadata 'size' is unreliable (observed 83 for a verified
        # 71-byte object — the downloaded bytes are correct). Report size=None so
        # the service skips the byte-count equality check and relies on the
        # authoritative SHA-256 verification (computed from the actual bytes).
        return ObjectHead(exists=True, size=None, content_type=ref.content_type,
                          etag=ref.version_id)

    def get_bytes(self, key: str, max_bytes: int) -> bytes:
        # Stratus streams no bytes via its API; read the object through a
        # short-lived presigned GET (the URL is self-generated + trusted).
        try:
            url = self._s.presign_get(self._logical, key, ttl_s=120)
        except Exception as exc:  # noqa: BLE001
            raise S3Error(f"could not presign read: {type(exc).__name__}") from exc
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 (trusted signed URL)
                return resp.read(int(max_bytes))
        except urllib.error.HTTPError as exc:  # type: ignore[attr-defined]
            if getattr(exc, "code", None) in (403, 404):
                raise ObjectNotFound(key) from exc
            raise S3Error(f"get failed: {exc.code}") from exc
        except Exception as exc:  # noqa: BLE001
            raise S3Error(f"get failed: {type(exc).__name__}") from exc

    def delete(self, key: str) -> None:  # noqa: D401 - see class docstring
        return None


@lru_cache(maxsize=1)
def get_gateway() -> S3Gateway:
    """Cached gateway. Prefers Catalyst Stratus when configured (deployed
    AppSail), else a private S3 bucket. Raises S3NotConfigured when neither is
    set — the guard layer returns 503 before the service reaches this."""
    s = get_settings()
    if s.stratus_evidence_configured():
        return StratusEvidenceGateway()
    if not s.s3_configured():
        raise S3NotConfigured("No evidence object store configured (S3 or Stratus).")
    return Boto3S3Gateway(
        s.s3_evidence_bucket.strip(), region=s.aws_region,
        profile=s.aws_profile, endpoint_url=s.s3_endpoint_url)
