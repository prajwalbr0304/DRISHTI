"""AgentCore audio transport; all identity and grounded answers remain in Zoho."""
import asyncio
import contextlib
import json
import logging
import os
import time
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from sonic_stream import SonicStream

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
log = logging.getLogger(__name__)
used_sessions: set[str] = set()


@app.get("/ping")
async def ping():
    return {"status": "Healthy"}


@app.post("/invocations")
async def invocations():
    raise HTTPException(400, "Connect through the authenticated WebSocket voice session")


@app.websocket("/ws")
async def voice(ws: WebSocket):
    await ws.accept()
    sonic = None
    tasks = []
    try:
        sid = ws.headers.get("x-amzn-bedrock-agentcore-runtime-session-id", "")
        if len(sid) < 33 or sid in used_sessions:
            raise ValueError("Missing or reused runtime session")
        # The presigned URL binds this ID to an isolated AgentCore session.
        # Never accept a second socket for that session, including after closure.
        used_sessions.add(sid)
        api = os.environ["DRISHTI_VOICE_BACKEND_URL"].rstrip("/")
        if urlparse(api).scheme != "https":
            raise ValueError("HTTPS backend required")
        async with httpx.AsyncClient(timeout=65, follow_redirects=False) as client:
            async with asyncio.timeout(15):
                first = await ws.receive_json()
                response = await client.post(api + "/stream/voice/verify", json={
                    "ticket": first.get("ticket", ""), "runtime_session_id": sid})
                response.raise_for_status()
            authorization = response.json()

            async def ask(question):
                response = await client.post(api + "/stream/voice/ask", json={
                    "ticket": authorization["ticket"], "runtime_session_id": sid, "question": question})
                response.raise_for_status()
                result = response.json()
                authorization["ticket"] = result["ticket"]
                return result["answer"]

            output_lock = asyncio.Lock()

            async def emit(event):
                # AgentCore caps each frame at 32 KB; preserve large answer cards
                # with application-level chunks rather than truncating results.
                payload = json.dumps(event, ensure_ascii=True)
                async with output_lock:
                    if len(payload) <= 28000:
                        await ws.send_text(payload)
                    else:
                        for offset in range(0, len(payload), 12000):
                            await ws.send_json({"type": "chunk", "data": payload[offset:offset + 12000],
                                                "last": offset + 12000 >= len(payload)})

            sonic = SonicStream(emit, ask, authorization["voice"])
            async with asyncio.timeout(440):
                await sonic.start(authorization["history"])

                async def incoming():
                    started, size = time.monotonic(), 0
                    while True:
                        message = await ws.receive()
                        if message["type"] == "websocket.disconnect":
                            return
                        pcm = message.get("bytes")
                        if pcm is None:
                            raise ValueError("Only PCM audio accepted")
                        size += len(pcm)
                        if size > (time.monotonic() - started + 2) * 32000:
                            raise ValueError("Audio rate exceeded")
                        await sonic.audio_input(pcm)

                tasks = [asyncio.create_task(incoming()), asyncio.create_task(sonic.receive())]
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
    except TimeoutError:
        with contextlib.suppress(Exception):
            await ws.send_json({"type": "session_end"})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.warning("Voice relay failed (%s)", type(exc).__name__)
        with contextlib.suppress(Exception):
            await ws.send_json({"type": "error", "message": "Nova voice is unavailable. Reconnect or use browser voice."})
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if sonic:
            await sonic.close()
        with contextlib.suppress(Exception):
            await ws.close()
