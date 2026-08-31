from unittest.mock import patch
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.chat.router import ask
from app.chat.schemas import AskRequest, VoiceIn


@pytest.mark.parametrize("confidence,auto_send,confirmed,allowed", [
    (None, False, False, False),
    (None, True, False, True),
    (0.2, True, False, False),
    (0.2, False, True, True),
    (0.9, False, False, True),
])
def test_voice_consent_boundary(confidence, auto_send, confirmed, allowed):
    req = AskRequest(question="case count", voice=VoiceIn(
        confidence=confidence, auto_send=auto_send, confirmed=confirmed))
    request = Request({"type": "http", "headers": []})
    caller = SimpleNamespace(role="system_admin", owner_subject="voice-test")
    with patch("app.chat.router.get_settings", return_value=SimpleNamespace(
        voice_low_confidence_threshold=0.6)), patch("app.chat.router._caller", return_value=caller), \
            patch("app.chat.router.service.ask", return_value={"ok": True}) as service:
        if allowed:
            assert ask(req, request, None, None) == {"ok": True}
            assert service.call_args.kwargs["voice"]["confidence"] == confidence
            assert service.call_args.kwargs["voice"]["confirmed"] == confirmed
        else:
            with pytest.raises(HTTPException) as exc:
                ask(req, request, None, None)
            assert exc.value.status_code == 409
            service.assert_not_called()
