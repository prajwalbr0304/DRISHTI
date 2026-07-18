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

import re
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


@lru_cache(maxsize=1)
def get_gateway() -> S3Gateway:
    """Cached real gateway. Raises S3NotConfigured when no bucket is set — the
    guard layer returns 503 before the service reaches this."""
    s = get_settings()
    if not s.s3_configured():
        raise S3NotConfigured("No S3_EVIDENCE_BUCKET configured.")
    return Boto3S3Gateway(
        s.s3_evidence_bucket.strip(), region=s.aws_region,
        profile=s.aws_profile, endpoint_url=s.s3_endpoint_url)
