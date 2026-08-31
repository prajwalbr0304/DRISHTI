"""Exercise the deployed authenticated gateway -> voice relay -> grounded Ask path.

Pass --audio a 16 kHz mono PCM WAV containing a non-sensitive test question.
This sends audio to AWS and saves the test conversation through the normal API.
"""
import argparse
import asyncio
import json
import wave

import httpx
import websockets


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", required=True)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--audio", required=True)
    parser.add_argument("--voice", default="kiara")
    parser.add_argument("--turns", type=int, choices=[1, 2], default=1)
    args = parser.parse_args()
    with wave.open(args.audio, "rb") as file:
        assert (file.getframerate(), file.getnchannels(), file.getsampwidth()) == (16000, 1, 2)
        pcm = file.readframes(file.getnframes())
    async with httpx.AsyncClient(timeout=40) as client:
        response = await client.post(args.api.rstrip("/") + "/chat/voice/session",
            headers={"Origin": args.origin}, json={"language": "en", "voice": args.voice, "audio_consent": True})
        print("Session endpoint:", response.status_code, flush=True)
        response.raise_for_status()
        session = response.json()
    async with websockets.connect(session["url"], origin=args.origin, open_timeout=60, max_size=2**20) as socket:
        await socket.send(json.dumps({"ticket": session["ticket"]}))
        complete = asyncio.Event()
        audio_bytes = 0
        answers = 0
        user_transcripts = 0
        sender = None
        fragments = ""
        pending_audio = pcm
        conversation_ids = set()

        async def send_audio():
            nonlocal pending_audio
            while not complete.is_set():
                frame = pending_audio[:1024] if pending_audio else bytes(1024)
                pending_audio = pending_audio[1024:]
                await socket.send(frame)
                await asyncio.sleep(0.032)

        try:
            async with asyncio.timeout(90 * args.turns):
                async for message in socket:
                    event = json.loads(message)
                    if event["type"] == "chunk":
                        fragments += event["data"]
                        assert len(fragments) <= 2000000
                        if not event["last"]:
                            continue
                        event = json.loads(fragments)
                        fragments = ""
                    kind = event["type"]
                    if kind == "ready":
                        print("Nova connected", flush=True)
                        sender = asyncio.create_task(send_audio())
                    elif kind == "audio":
                        audio_bytes += len(event["audio"]) * 3 // 4
                    elif kind == "answer":
                        answers += 1
                        result = event["answer"]
                        conversation_ids.add(result["session_id"])
                        print(json.dumps({"reply": result["reply"], "planner": result["planner_source"],
                                          "session_id": result["session_id"]}), flush=True)
                    elif kind == "transcript":
                        if event["role"] == "USER":
                            user_transcripts += 1
                        elif answers and audio_bytes:
                            if answers >= args.turns:
                                break
                            pending_audio = pcm
                    elif kind in {"error", "tool_error", "session_end"}:
                        raise RuntimeError(event.get("message", kind))
            assert answers >= args.turns and audio_bytes and user_transcripts >= args.turns, "Missing answer, audio or transcription"
            assert len(conversation_ids) == 1, "Voice turns did not retain the conversation"
            print({"answers": answers, "audio_bytes": audio_bytes, "user_transcripts": user_transcripts})
        finally:
            complete.set()
            if sender:
                sender.cancel()
                await asyncio.gather(sender, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
