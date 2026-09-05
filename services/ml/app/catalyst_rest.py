"""Direct Catalyst REST client (Admin scope) for the custom-container AppSail.

Why not the SDK: ``zcatalyst-sdk`` is built for the native Catalyst runtime. In a
custom OCI AppSail with a self-client refresh token it is unusable —

  * its base-URL constants default to internal ``*.localzoho.com`` domains that
    do not resolve in a custom container (only injected in native runtimes), and
  * ``RefreshTokenCredential.token()`` builds ``<accounts>//oauth/v2/token`` (a
    double slash) which 404s.

This client talks to the documented Catalyst REST API directly with the
self-client refresh token. Every request has a hard timeout (no hangs, unlike the
SDK on Windows) and refreshes/reties once on a 401. Proven against the IN DC
(token refresh + ZCQL both return 200). Region domains are env-overridable but
default to the India DC.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any, Optional

import requests

# (connect, read) seconds — bounded so a dependency stall never hangs a worker.
_TIMEOUT = (10, 30)
# Zia OCR reads a whole page-set (up to 20 MB) and is materially slower than a
# metadata call, so it gets its own longer read budget — still bounded.
_OCR_TIMEOUT = (10, 120)


def _accounts_url() -> str:
    return os.getenv("ZOHO_CATALYST_ACCOUNTS_URL", "https://accounts.zoho.in").rstrip("/")


def _api_domain() -> str:
    return os.getenv("ZOHO_CATALYST_API_DOMAIN", "https://api.catalyst.zoho.in").rstrip("/")


class CatalystRestError(RuntimeError):
    pass


class CatalystRestClient:
    """Thread-safe admin-scope REST client with cached access token."""

    def __init__(self) -> None:
        self._client_id = os.getenv("ZOHO_CATALYST_CLIENT_ID")
        self._client_secret = os.getenv("ZOHO_CATALYST_CLIENT_SECRET")
        self._refresh_token = os.getenv("ZOHO_CATALYST_REFRESH_TOKEN")
        self._project_id = (os.getenv("CATALYST_PROJECT_ID")
                            or os.getenv("ZOHO_CATALYST_PROJECT_ID"))
        self._zaid = os.getenv("ZOHO_CATALYST_ZAID") or os.getenv("CATALYST_PROJECT_KEY")
        self._env = os.getenv("ZOHO_CATALYST_ENVIRONMENT", "Development")
        self._token: Optional[str] = None
        self._exp = 0.0
        self._lock = threading.Lock()
        self._session = requests.Session()
        missing = [k for k, v in {
            "ZOHO_CATALYST_CLIENT_ID": self._client_id,
            "ZOHO_CATALYST_CLIENT_SECRET": self._client_secret,
            "ZOHO_CATALYST_REFRESH_TOKEN": self._refresh_token,
            "CATALYST_PROJECT_ID": self._project_id,
            "ZOHO_CATALYST_ZAID": self._zaid,
        }.items() if not v]
        if missing:
            raise CatalystRestError("missing Catalyst REST env: " + ", ".join(missing))

    # -- auth --------------------------------------------------------------
    def _access_token(self) -> str:
        with self._lock:
            if self._token and self._exp > time.time():
                return self._token
            r = self._session.post(_accounts_url() + "/oauth/v2/token", timeout=_TIMEOUT, data={
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            })
            r.raise_for_status()
            d = r.json()
            if not d.get("access_token"):
                raise CatalystRestError(f"token refresh failed: {d.get('error', d)}")
            self._token = d["access_token"]
            self._exp = time.time() + int(d.get("expires_in", 3600)) - 120
            return self._token

    def _headers(self) -> dict:
        return {
            "Authorization": "Zoho-oauthtoken " + self._access_token(),
            "Content-Type": "application/json",
            "Environment": self._env,
        }

    def _headers_multipart(self) -> dict:
        """Auth headers WITHOUT Content-Type.

        ``requests`` must set ``multipart/form-data`` itself so it can append the
        boundary; pre-setting Content-Type here produces a body the server cannot
        parse (a silent 400 that looks like a bad file).
        """
        return {
            "Authorization": "Zoho-oauthtoken " + self._access_token(),
            "Environment": self._env,
        }

    def _base(self) -> str:
        return f"{_api_domain()}/baas/v1/project/{self._project_id}"

    def _req(self, method: str, path: str, *, json=None, params=None,
             _retry: bool = True) -> requests.Response:
        r = self._session.request(method, self._base() + path, headers=self._headers(),
                                  json=json, params=params, timeout=_TIMEOUT)
        if r.status_code == 401 and _retry:
            with self._lock:
                self._token = None  # force refresh
            return self._req(method, path, json=json, params=params, _retry=False)
        return r

    def _req_multipart(self, path: str, *, files, data=None, timeout=None,
                       _retry: bool = True) -> requests.Response:
        """POST a multipart body (file upload). Same 401-refresh-once contract as
        ``_req``, but the file payload must be re-openable, so callers pass bytes
        (never a consumed stream)."""
        r = self._session.post(self._base() + path, headers=self._headers_multipart(),
                               files=files, data=data or {},
                               timeout=timeout or _OCR_TIMEOUT)
        if r.status_code == 401 and _retry:
            with self._lock:
                self._token = None  # force refresh
            return self._req_multipart(path, files=files, data=data,
                                       timeout=timeout, _retry=False)
        return r

    @staticmethod
    def _data(r: requests.Response):
        r.raise_for_status()
        body = r.json()
        if body.get("status") == "failure":
            raise CatalystRestError(str(body.get("data") or body))
        return body.get("data")

    # -- Data Store / ZCQL -------------------------------------------------
    def zcql(self, query: str) -> list[dict]:
        """Execute a ZCQL query; returns the raw row list ([{Table: {...}}])."""
        return self._data(self._req("POST", "/query", json={"query": query})) or []

    def insert_row(self, table: str, row: dict) -> dict:
        # Catalyst row API requires a JSON array of row objects.
        data = self._data(self._req("POST", f"/table/{table}/row", json=[row]))
        return data[0] if isinstance(data, list) and data else (data or row)

    def update_row(self, table: str, row: dict) -> dict:
        data = self._data(self._req("PUT", f"/table/{table}/row", json=[row]))
        return data[0] if isinstance(data, list) and data else (data or row)

    def delete_by_external_id(self, table: str, external_id: str) -> int:
        """Delete rows by ExternalID via ZCQL. Returns deleted count."""
        safe = str(external_id).replace("'", "''")
        rows = self.zcql(f"DELETE FROM {table} WHERE ExternalID = '{safe}'")
        try:
            return int(rows[0][table]["DELETED_ROWS_COUNT"])
        except Exception:  # noqa: BLE001
            return 0

    def search(self, text: str, table: str, columns: Optional[list[str]], max_results: int = 50) -> dict:
        body = {"search": text, "search_table_columns": {table: columns or []},
                "start": 0, "end": max_results}
        return self._data(self._req("POST", "/search", json=body)) or {}

    # -- Stratus -----------------------------------------------------------
    def stratus_presigned_url(self, bucket_name: str, object_key: str, *,
                              operation: str = "GET", expiry_in_seconds: int = 900) -> str:
        method = "PUT" if operation.upper() == "PUT" else "GET"
        data = self._data(self._req(method, "/bucket/object/signed-url",
                                    params={"bucket_name": bucket_name, "object_key": object_key,
                                            "expiry_in_seconds": expiry_in_seconds}))
        return (data or {}).get("signature")

    def stratus_get_object(self, bucket_name: str, object_key: str,
                           version_id: Optional[str] = None) -> Optional[dict]:
        params = {"bucket_name": bucket_name, "object_key": object_key}
        if version_id:
            params["version_id"] = version_id
        r = self._req("GET", "/bucket/object", params=params)
        if r.status_code == 404:
            return None
        return self._data(r)

    def stratus_list_versions(self, bucket_name: str, object_key: str) -> list[dict]:
        data = self._data(self._req("GET", "/bucket/objects/versions",
                                    params={"bucket_name": bucket_name, "object_key": object_key}))
        return (data or {}).get("version", []) if isinstance(data, dict) else []

    # -- Zia OCR -----------------------------------------------------------
    def zia_ocr(self, content: bytes, *, filename: str = "scan.jpg",
                content_type: str = "application/octet-stream",
                languages: Optional[list[str]] = None,
                model_type: str = "OCR") -> dict:
        """Recognise text in one image/PDF via Catalyst Zia OCR.

        ``POST /ml/ocr`` (multipart, scope ``ZohoCatalyst.mlkit.READ``). Returns
        the raw ``data`` object: ``{"confidence": <0-100>, "text": "..."}``.

        Zia gives ONE document-level confidence and plain text — no per-field
        values and no bounding boxes — so any field-level confidence has to be
        derived downstream by the parser, never claimed from this response.

        ``languages`` are Zia language codes (``eng``, ``kan``, ...). Passing them
        is optional and speeds up recognition; omitting them lets Zia auto-detect.
        """
        files = {"image": (filename, content, content_type or "application/octet-stream")}
        data: dict[str, Any] = {"model_type": model_type or "OCR"}
        if languages:
            # Zia accepts repeated language values for a multi-script page
            # (e.g. a Kannada FIR with English section numbers).
            data["language"] = [str(v) for v in languages if str(v).strip()]
        r = self._req_multipart("/ml/ocr", files=files, data=data)
        return self._data(r) or {}

    # -- Cache -------------------------------------------------------------
    def cache_put(self, segment_id: str, key: str, value: str, *, expiry_hours: int = 1) -> None:
        self._data(self._req("POST", f"/segment/{segment_id}/cache", json={
            "cache_name": key, "cache_value": value, "expiry_in_hours": int(expiry_hours)}))

    def cache_get(self, segment_id: str, key: str) -> Optional[str]:
        r = self._req("GET", f"/segment/{segment_id}/cache", params={"cacheKey": key})
        if r.status_code == 404:
            return None
        d = self._data(r) or {}
        v = d.get("cache_value")
        return None if v is None else str(v)


_CLIENT: Optional[CatalystRestClient] = None
_CLIENT_LOCK = threading.Lock()


def get_rest_client() -> CatalystRestClient:
    """Process-wide cached REST client (lazy)."""
    global _CLIENT
    if _CLIENT is None:
        with _CLIENT_LOCK:
            if _CLIENT is None:
                _CLIENT = CatalystRestClient()
    return _CLIENT
