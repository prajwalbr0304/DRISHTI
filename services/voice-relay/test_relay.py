import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ml" / "app"))
spec = importlib.util.spec_from_file_location("voice_relay", Path(__file__).with_name("relay.py"))
relay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relay)


@pytest.fixture
def client(monkeypatch):
    relay.used_sessions.clear()
    monkeypatch.setenv("DRISHTI_VOICE_BACKEND_URL", "https://backend.example")
    return TestClient(relay.app)


def test_missing_session_and_replay_never_invoke_nova(client, monkeypatch):
    calls = []
    monkeypatch.setattr(relay, "SonicStream", lambda *args: calls.append(args))
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "error"
    sid = "12345678-1234-1234-1234-123456789abc"
    relay.used_sessions.add(sid)
    with client.websocket_connect("/ws", headers={"x-amzn-bedrock-agentcore-runtime-session-id": sid}) as ws:
        assert ws.receive_json()["type"] == "error"
    assert not calls


def test_backend_auth_failure_never_invokes_nova(client, monkeypatch):
    calls = []
    class Http:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, json):
            calls.append(url)
            def denied(): raise ValueError("unauthorized")
            return SimpleNamespace(raise_for_status=denied)
    monkeypatch.setattr(relay.httpx, "AsyncClient", lambda **_: Http())
    def never(*args): raise AssertionError("Nova must not start")
    monkeypatch.setattr(relay, "SonicStream", never)
    with client.websocket_connect("/ws", headers={"x-amzn-bedrock-agentcore-runtime-session-id": "x" * 36}) as ws:
        ws.send_json({"ticket": "invalid"})
        assert ws.receive_json()["type"] == "error"
    assert calls == ["https://backend.example/stream/voice/verify"]
    assert client.get("/ping").json() == {"status": "Healthy"}
    assert client.post("/invocations").status_code == 400
