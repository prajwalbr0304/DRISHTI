"""Nova 2 Sonic audio relay. AWS credentials and grounded tools stay server-side."""
from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from urllib.parse import quote, urlencode, urlparse

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from .chat import service
from .chat.identity import resolve_chat_caller
from .config import get_settings

router = APIRouter(tags=["voice"])
log = logging.getLogger(__name__)
MODEL = "amazon.nova-2-sonic-v1:0"
VOICES = {"kiara": "Kiara (India)", "arjun": "Arjun (India)",
          "tiffany": "Tiffany (US)", "matthew": "Matthew (US)",
          "amy": "Amy (UK)", "olivia": "Olivia (Australia)"}
MAX_SESSION_SECONDS = 450  # Renew before Bedrock's eight-minute connection limit.
_active: set[str] = set()
_used: dict[str, float] = {}


def enabled() -> bool:
    return (os.getenv("DRISHTI_SONIC_ENABLED", "").lower() == "true"
            and bool(get_settings().query_voice_enabled))


def origins() -> set[str]:
    return {s.strip() for s in os.getenv("DRISHTI_SONIC_ALLOWED_ORIGINS", "").split(",") if s.strip()}


def secret() -> bytes:
    key = os.getenv("ZOHO_APPSAIL_SIGNING_SECRET", "")
    if not key:
        raise ValueError("Voice session signing is not configured")
    return key.encode()


def configuration() -> dict:
    url = os.getenv("DRISHTI_SONIC_WS_URL", "")
    return {"sonic_available": enabled() and bool(url or os.getenv("DRISHTI_SONIC_RUNTIME_ARN")) and bool(origins()),
            "sonic_model": os.getenv("BEDROCK_SONIC_MODEL_ID", MODEL),
            "sonic_languages": ["en"], "sonic_voices": VOICES,
            "sonic_session_seconds": MAX_SESSION_SECONDS}


class SessionRequest(BaseModel):
    voice: str = "kiara"
    language: str = "en"
    session_id: int | None = Field(default=None, gt=0)
    audio_consent: bool = False


def mint_ticket(data: dict) -> str:
    payload = base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode()).decode().rstrip("=")
    return payload + "." + hmac.new(secret(), payload.encode(), hashlib.sha256).hexdigest()


def verify_ticket(ticket: str, origin: str | None, *, audience="drishti-sonic", lifetime=61) -> dict:
    if len(ticket) > 8192:
        raise ValueError("Invalid ticket")
    payload, signature = ticket.split(".", 1)
    expected = hmac.new(secret(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise ValueError("Invalid ticket")
    data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    if origin is None:
        origin = data.get("origin")
    now = time.time()
    if (data.get("aud") != audience or origin not in origins()
            or data.get("origin") != origin or not data.get("owner")
            or not isinstance(data.get("exp"), (int, float))
            or not now < data["exp"] <= now + lifetime
            or data.get("voice") not in VOICES or not data.get("nonce")):
        raise ValueError("Invalid ticket")
    return data


def runtime_url(nonce: str) -> str:
    """Use the same SigV4 query signing as the AgentCore SDK, without its web stack."""
    import boto3
    from botocore.auth import SigV4QueryAuth
    from botocore.awsrequest import AWSRequest
    arn = os.environ["DRISHTI_SONIC_RUNTIME_ARN"]
    parts = arn.split(":")
    if len(parts) != 6 or parts[2] != "bedrock-agentcore" or not parts[5].startswith("runtime/"):
        raise ValueError("Invalid voice runtime ARN")
    region = parts[3]
    host = f"bedrock-agentcore.{region}.amazonaws.com"
    query = urlencode({"X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": nonce, "qualifier": "DEFAULT"})
    request = AWSRequest(method="GET", url=f"https://{host}/runtimes/{quote(arn, safe='')}/ws?{query}",
                         headers={"host": host})
    credentials = boto3.Session().get_credentials()
    if credentials is None:
        raise ValueError("Voice signing credentials unavailable")
    SigV4QueryAuth(credentials.get_frozen_credentials(), "bedrock-agentcore", region, expires=60).add_auth(request)
    return request.url.replace("https://", "wss://", 1)


@router.post("/chat/voice/session")
async def voice_session(body: SessionRequest, request: Request):
    if not configuration()["sonic_available"]:
        raise HTTPException(503, "Nova voice is not configured")
    if not body.audio_consent:
        raise HTTPException(400, "Audio streaming consent is required")
    if body.language != "en" or body.voice not in VOICES:
        raise HTTPException(400, "Unsupported Nova voice or language; use browser voice for Kannada")
    origin = request.headers.get("origin", "")
    if origin not in origins():
        raise HTTPException(403, "Voice origin is not allowed")
    caller = resolve_chat_caller(request, x_role=request.headers.get("x-role"),
                                 x_demo_actor=request.headers.get("x-demo-actor"))
    if body.session_id is not None:
        detail = await asyncio.to_thread(service.get_session, body.session_id, caller.owner_subject)
        if detail is None or detail.role != service._resolve_role(caller.role):
            raise HTTPException(404, "Conversation not found")
    nonce = str(uuid.uuid4())
    url = (await asyncio.to_thread(runtime_url, nonce) if os.getenv("DRISHTI_SONIC_RUNTIME_ARN")
           else os.environ["DRISHTI_SONIC_WS_URL"])
    parsed = urlparse(url)
    if parsed.scheme != "wss" and not (parsed.scheme == "ws" and parsed.hostname in {"localhost", "127.0.0.1"}):
        raise HTTPException(503, "Secure voice transport is not configured")
    data = {"aud": "drishti-sonic", "owner": caller.owner_subject, "role": caller.role,
            "origin": origin, "voice": body.voice, "session_id": body.session_id,
            "exp": time.time() + 60, "nonce": nonce}
    return {"url": url, "ticket": mint_ticket(data), "expires_in": 60,
            "session_seconds": MAX_SESSION_SECONDS, "model": MODEL}


class RelayTicket(BaseModel):
    ticket: str = Field(min_length=1, max_length=8192)
    runtime_session_id: str = Field(min_length=33, max_length=256)


class RelayQuestion(RelayTicket):
    question: str = Field(min_length=1, max_length=2000)


def relay_claims(body: RelayTicket, *, tool=False) -> dict:
    if not enabled() or not os.getenv("DRISHTI_SONIC_RUNTIME_ARN"):
        raise HTTPException(503, "Voice relay is disabled")
    try:
        data = verify_ticket(body.ticket, None, audience="drishti-sonic-tool" if tool else "drishti-sonic",
                             lifetime=MAX_SESSION_SECONDS + 1 if tool else 61)
        if data["nonce"] != body.runtime_session_id:
            raise ValueError("Invalid runtime session")
        return data
    except (ValueError, KeyError, TypeError):
        raise HTTPException(401, "Invalid or expired voice authorization") from None


async def conversation_history(data: dict) -> list:
    if not data.get("session_id"):
        return []
    detail = await asyncio.to_thread(service.get_session, data["session_id"], data["owner"])
    if detail is None or detail.role != service._resolve_role(data["role"]):
        raise HTTPException(404, "Conversation not found")
    return [(m.sender.upper(), (m.content or "")[:4000]) for m in detail.messages[-12:]
            if m.sender in {"user", "assistant"} and m.content]


# These paths bypass gateway context only because the scoped HMAC ticket is
# independently verified here. Neither the browser nor the model supplies identity.
@router.post("/stream/voice/verify")
async def relay_verify(body: RelayTicket):
    data = relay_claims(body)
    history = await conversation_history(data)
    data.update(aud="drishti-sonic-tool", exp=time.time() + MAX_SESSION_SECONDS)
    return {"ticket": mint_ticket(data), "voice": data["voice"], "history": history}


@router.post("/stream/voice/ask")
async def relay_ask(body: RelayQuestion):
    data = relay_claims(body, tool=True)
    await conversation_history(data)
    result = await asyncio.to_thread(service.ask, data["role"], body.question,
        owner_subject=data["owner"], language="en", session_id=data.get("session_id"),
        voice={"transcript": body.question, "language": "en", "confidence": None,
               "auto_send": True, "provider": "amazon-nova-2-sonic"})
    data["session_id"] = result.session_id
    # Retain the original expiry: tool calls must not extend authorization.
    return {"answer": result.model_dump(mode="json"), "ticket": mint_ticket(data)}


from .sonic_stream import BotoCredentials, SonicStream  # Re-export for existing probes.


@router.websocket("/stream/voice")
async def voice_stream(ws: WebSocket):
    origin = ws.headers.get("origin", "")
    if not enabled() or origin not in origins():
        await ws.close(code=1008)
        return
    await ws.accept()
    sonic = None
    tasks = []
    owner = None
    try:
        async with asyncio.timeout(10):
            first = await ws.receive_json()
            ticket = verify_ticket(first.get("ticket", ""), origin)
        now = time.time()
        for nonce, exp in list(_used.items()):
            if exp < now:
                del _used[nonce]
        if ticket["nonce"] in _used or ticket["owner"] in _active or len(_active) >= 8:
            raise ValueError("Voice session already active or capacity reached")
        _used[ticket["nonce"]] = ticket["exp"]
        owner = ticket["owner"]
        _active.add(owner)
        session_id = ticket.get("session_id")
        history = []
        if session_id:
            detail = await asyncio.to_thread(service.get_session, session_id, owner)
            if detail is None or detail.role != service._resolve_role(ticket["role"]):
                raise ValueError("Invalid conversation")
            history = [(m.sender.upper(), (m.content or "")[:4000]) for m in detail.messages[-12:]
                       if m.sender in {"user", "assistant"} and m.content]

        async def ask(question):
            nonlocal session_id
            result = await asyncio.to_thread(service.ask, ticket["role"], question,
                owner_subject=owner, language="en", session_id=session_id,
                voice={"transcript": question, "language": "en", "confidence": None,
                       "auto_send": True, "provider": "amazon-nova-2-sonic"})
            session_id = result.session_id
            return result.model_dump(mode="json")

        sonic = SonicStream(ws.send_json, ask, ticket["voice"])
        async with asyncio.timeout(MAX_SESSION_SECONDS):
            await sonic.start(history)
            async def incoming():
                while True:
                    message = await ws.receive()
                    if message["type"] == "websocket.disconnect":
                        return
                    if message.get("bytes") is not None:
                        await sonic.audio_input(message["bytes"])
                    else:
                        raise ValueError("Only PCM audio is accepted after authentication")
            tasks = [asyncio.create_task(incoming()), asyncio.create_task(sonic.receive())]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
    except TimeoutError:
        with contextlib.suppress(Exception):
            await ws.send_json({"type": "session_end", "message": "Voice session ended. Reconnect to continue the same conversation."})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.warning("Nova voice connection failed (%s)", type(exc).__name__)
        with contextlib.suppress(Exception):
            await ws.send_json({"type": "error", "message": "Nova voice is unavailable. Reconnect or use browser voice. Your conversation is retained."})
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if sonic:
            await sonic.close()
        if owner:
            _active.discard(owner)
        with contextlib.suppress(Exception):
            await ws.close()
