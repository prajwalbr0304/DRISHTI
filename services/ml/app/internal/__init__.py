"""Internal (service-to-service) endpoints for the signed-context trust boundary.

These endpoints are reachable only with a valid HMAC-signed context minted by the
Catalyst gateway / event / cron functions (see ``app/gateway_context.py`` and
``infra/catalyst/functions/``). They are never called by the browser directly.

Phase 14 Part B ships the trust boundary itself plus a guarded ``/internal/ping``
proof endpoint. The business internal endpoints referenced by the event
functions (``/internal/evidence/validate``, ``/internal/features/snapshot``,
``/internal/predictions/dispatch``, ``/internal/notify``, ``/internal/ops/*``)
are implemented/enabled by their owning phases; they all use
``require_service_context`` when added.
"""
