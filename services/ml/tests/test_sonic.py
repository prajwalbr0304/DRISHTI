import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import sonic


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("DRISHTI_SONIC_ENABLED", "true")
    monkeypatch.setenv("ZOHO_APPSAIL_SIGNING_SECRET", "test-secret-not-for-deployment")
    monkeypatch.setenv("DRISHTI_SONIC_ALLOWED_ORIGINS", "https://drishti.example")
    monkeypatch.setenv("DRISHTI_SONIC_WS_URL", "wss://api.example/stream/voice")
    monkeypatch.setenv("DRISHTI_REQUIRE_GATEWAY_CONTEXT", "false")
    monkeypatch.setattr(sonic, "get_settings", lambda: SimpleNamespace(query_voice_enabled=True))
    app = FastAPI()
    app.include_router(sonic.router)
    return TestClient(app)


def ticket(**overrides):
    return sonic.mint_ticket({"aud": "drishti-sonic", "owner": "catalyst:123", "role": "system_admin",
        "voice": "kiara", "origin": "https://drishti.example", "exp": time.time() + 60,
        "nonce": "test-unique", **overrides})


def test_ticket_binding(configured):
    assert sonic.verify_ticket(ticket(), "https://drishti.example")["owner"] == "catalyst:123"
    for token, origin in [(ticket(), "https://evil.example"), (ticket(exp=0), "https://drishti.example"),
                           (ticket(aud="drishti-channel"), "https://drishti.example"),
                           (ticket() + "0", "https://drishti.example")]:
        with pytest.raises(ValueError):
            sonic.verify_ticket(token, origin)


def test_session_requires_consent_origin_language_and_owner(configured, monkeypatch):
    headers = {"origin": "https://drishti.example"}
    assert configured.post("/chat/voice/session", json={}, headers=headers).status_code == 400
    assert configured.post("/chat/voice/session", json={"audio_consent": True}).status_code == 403
    assert configured.post("/chat/voice/session", json={"audio_consent": True, "language": "kn"}, headers=headers).status_code == 400
    monkeypatch.setattr(sonic.service, "get_session", lambda *_: None)
    assert configured.post("/chat/voice/session", json={"audio_consent": True, "session_id": 123}, headers=headers).status_code == 404
    response = configured.post("/chat/voice/session", json={"audio_consent": True}, headers=headers)
    assert response.status_code == 200
    assert "ticket" in response.json()
    assert "AWS_ACCESS_KEY_ID" not in response.text


def test_disabled_and_unsigned_websocket(configured, monkeypatch):
    with configured.websocket_connect("/stream/voice", headers={"origin": "https://drishti.example"}) as ws:
        ws.send_json({"ticket": "invalid"})
        assert ws.receive_json()["type"] == "error"
    monkeypatch.setenv("DRISHTI_SONIC_ENABLED", "false")
    assert configured.post("/chat/voice/session", json={"audio_consent": True}).status_code == 503


def test_tool_validation_and_errors_always_return_result():
    async def run():
        emit = AsyncMock()
        ask = AsyncMock(return_value={"reply": "5 cases", "session_id": 1})
        stream = sonic.SonicStream(emit, ask)
        stream.event = AsyncMock()
        await stream.tool({"toolUseId": "a", "toolName": "ask_drishti", "content": '{"question":"case count"}'})
        ask.assert_awaited_once_with("case count")
        assert any(call.args[0] == "toolResult" for call in stream.event.await_args_list)
        ask.reset_mock()
        await stream.tool({"toolUseId": "b", "toolName": "delete_cases", "content": '{"question":"delete"}'})
        ask.assert_not_awaited()
        assert "error" in stream.event.await_args_list[-2].args[1]["content"]
        with pytest.raises(ValueError):
            await stream.audio_input(b"x")
        with pytest.raises(ValueError):
            await stream.audio_input(bytes(10000))
    asyncio.run(run())


def test_credential_provider_reuses_boto_chain(monkeypatch):
    import boto3
    calls = []
    credentials = SimpleNamespace(get_frozen_credentials=lambda: SimpleNamespace(access_key="id", secret_key="secret", token=None))
    def session():
        calls.append(True)
        return SimpleNamespace(get_credentials=lambda: credentials)
    monkeypatch.setattr(boto3, "Session", session)
    async def run():
        resolver = sonic.BotoCredentials()
        for _ in range(10):
            await resolver.get_identity(properties={})
    asyncio.run(run())
    assert len(calls) == 1


def test_relay_tickets_are_scoped_and_expire(configured, monkeypatch):
    monkeypatch.setenv("DRISHTI_SONIC_RUNTIME_ARN", "arn:aws:bedrock-agentcore:us-east-1:123:runtime/test")
    sid = "12345678-1234-1234-1234-123456789abc"
    body = {"ticket": ticket(nonce=sid), "runtime_session_id": sid}
    response = configured.post("/stream/voice/verify", json=body)
    assert response.status_code == 200
    tool = response.json()["ticket"]
    assert configured.post("/stream/voice/verify", json={**body, "ticket": tool}).status_code == 401
    assert configured.post("/stream/voice/verify", json={**body, "runtime_session_id": "x" * 36}).status_code == 401
    assert configured.post("/stream/voice/ask", json={**body, "question": "case count"}).status_code == 401
    claims = sonic.verify_ticket(tool, None, audience="drishti-sonic-tool", lifetime=451)
    seen = []
    def ask(role, question, **kwargs):
        seen.append((role, question, kwargs))
        return SimpleNamespace(session_id=88, model_dump=lambda **_: {"reply": "5 cases", "session_id": 88})
    monkeypatch.setattr(sonic.service, "ask", ask)
    result = configured.post("/stream/voice/ask", json={**body, "ticket": tool, "question": "case count"})
    assert result.status_code == 200
    assert seen[0][2]["owner_subject"] == "catalyst:123"
    next_claims = sonic.verify_ticket(result.json()["ticket"], None, audience="drishti-sonic-tool", lifetime=451)
    assert next_claims["exp"] == claims["exp"]
    assert next_claims["session_id"] == 88
    monkeypatch.setattr(sonic.service, "get_session", lambda *_: None)
    assert configured.post("/stream/voice/ask", json={**body, "ticket": result.json()["ticket"], "question": "more"}).status_code == 404
    assert configured.post("/stream/voice/ask", json={**body, "ticket": ticket(nonce=sid, aud="drishti-sonic-tool", exp=0), "question": "count"}).status_code == 401


def test_presign_binds_runtime_session(monkeypatch):
    import boto3
    from botocore.credentials import Credentials
    from urllib.parse import parse_qs, urlparse
    monkeypatch.setenv("DRISHTI_SONIC_RUNTIME_ARN", "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/test-abc")
    monkeypatch.setattr(boto3, "Session", lambda: SimpleNamespace(get_credentials=lambda: Credentials("fake-id", "fake-secret")))
    url = urlparse(sonic.runtime_url("unique-session"))
    query = parse_qs(url.query)
    assert url.scheme == "wss"
    assert query["X-Amzn-Bedrock-AgentCore-Runtime-Session-Id"] == ["unique-session"]
    assert query["X-Amz-Expires"] == ["60"]
    assert "X-Amz-Signature" in query
    assert "fake-secret" not in url.geturl()
