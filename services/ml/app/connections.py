"""Catalyst Connections contract — OAuth token lifecycle (Prompt 14 Part B, row 19).

Connections manages OAuth/OIDC credentials for a compatible third-party/AWS
integration so tokens are refreshed centrally rather than embedded. DRISHTI uses
it for the protected external integration WHEN that integration exposes
OAuth/OIDC. The protected AWS model adapter (app/predict/adapter.py) currently
authenticates with a signed service request (HMAC), not OAuth — so this module
records that **signed-service-auth gap** honestly and returns `None` unless a
Connection is actually configured.

Narrow interface + in-memory fake (tests/local) + Catalyst-SDK impl (deployed).
Connection descriptors live in `infra/catalyst/connections/connections.json`.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TokenResult:
    access_token: Optional[str]
    connection: str
    auth_mode: str  # "oauth" | "signed-service-auth" | "unconfigured"

    @property
    def available(self) -> bool:
        return self.access_token is not None


class ConnectionsClient(ABC):
    @abstractmethod
    def access_token(self, connection: str) -> TokenResult: ...


class NullConnections(ConnectionsClient):
    """Default when no OAuth Connection is configured. Honestly reports the
    signed-service-auth gap instead of pretending an OAuth token exists."""

    def access_token(self, connection: str) -> TokenResult:
        return TokenResult(access_token=None, connection=connection,
                           auth_mode="signed-service-auth")


class CatalystConnections(ConnectionsClient):
    """Deployed impl over the Catalyst SDK (Connections). SDK import deferred."""

    def __init__(self, app=None):
        import zcatalyst_sdk
        self._app = app or zcatalyst_sdk.initialize()
        self._conn = self._app.connection() if hasattr(self._app, "connection") else None

    def access_token(self, connection: str) -> TokenResult:
        if self._conn is None:
            return TokenResult(None, connection, "unconfigured")
        token = self._conn.get_access_token(connection)
        return TokenResult(access_token=token, connection=connection, auth_mode="oauth")


def get_connections() -> ConnectionsClient:
    """Factory: Catalyst Connections only when a connection id is configured and
    the integration is OAuth/OIDC-compatible; otherwise the null client records
    the documented signed-service-auth gap."""
    if os.getenv("DRISHTI_AWS_CONNECTION_ID") and \
            os.getenv("DRISHTI_USE_CATALYST_CONNECTIONS", "").lower() == "true":
        return CatalystConnections()
    return NullConnections()
