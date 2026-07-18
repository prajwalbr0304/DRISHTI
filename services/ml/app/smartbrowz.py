"""Catalyst SmartBrowz contract — PDF/image/screenshot output (Part B, row 16).

SmartBrowz (headless browser) renders authorized reports and board/disaster
exports to PDF or image (workflow §11). The pipeline is: immutable Data Store
source snapshot -> SmartBrowz render -> synthetic watermark + SHA-256 + version
-> private Stratus object -> audit -> `report.ready` Signal. This module is the
render boundary only; snapshotting, watermarking and Stratus storage are done by
the report job around it.

Narrow interface + in-memory fake (tests/local) + Catalyst-SDK impl (deployed).
No sensitive content is embedded beyond the authorized, watermarked snapshot.
"""
from __future__ import annotations

import hashlib
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class RenderResult:
    content_type: str          # application/pdf | image/png
    size: int
    sha256: str
    # Bytes are returned to the caller (report job) to store in Stratus; never
    # logged. In the fake, bytes are a deterministic placeholder.
    data: bytes = b""


class SmartBrowzClient(ABC):
    @abstractmethod
    def render_pdf(self, html: str, *, watermark: str = "Synthetic Hackathon Demo") -> RenderResult: ...

    @abstractmethod
    def screenshot(self, html_or_url: str, *, full_page: bool = True,
                   watermark: str = "Synthetic Hackathon Demo") -> RenderResult: ...


def _result(content_type: str, data: bytes) -> RenderResult:
    return RenderResult(content_type=content_type, size=len(data),
                        sha256=hashlib.sha256(data).hexdigest(), data=data)


class InMemorySmartBrowz(SmartBrowzClient):
    """Deterministic fake: returns a stub document carrying the watermark marker."""

    def render_pdf(self, html, *, watermark="Synthetic Hackathon Demo"):
        data = (f"%PDF-1.4 DRISHTI [{watermark}]\n" + html[:4096]).encode("utf-8")
        return _result("application/pdf", data)

    def screenshot(self, html_or_url, *, full_page=True, watermark="Synthetic Hackathon Demo"):
        data = (f"PNGSTUB DRISHTI [{watermark}] full_page={full_page} src={html_or_url[:256]}").encode("utf-8")
        return _result("image/png", data)


class CatalystSmartBrowz(SmartBrowzClient):
    """Deployed impl over the Catalyst SDK (SmartBrowz). SDK import deferred."""

    def __init__(self, app=None):
        import zcatalyst_sdk
        self._app = app or zcatalyst_sdk.initialize()
        self._sb = self._app.smart_browz()

    def render_pdf(self, html, *, watermark="Synthetic Hackathon Demo"):
        data = self._sb.convert_to_pdf(html=f"{html}\n<!-- {watermark} -->")
        return _result("application/pdf", data if isinstance(data, bytes) else bytes(data))

    def screenshot(self, html_or_url, *, full_page=True, watermark="Synthetic Hackathon Demo"):
        data = self._sb.get_screenshot(url=html_or_url, options={"fullPage": full_page})
        return _result("image/png", data if isinstance(data, bytes) else bytes(data))


def get_smartbrowz() -> SmartBrowzClient:
    if os.getenv("DRISHTI_USE_CATALYST_SMARTBROWZ", "").lower() == "true":
        return CatalystSmartBrowz()
    return InMemorySmartBrowz()
