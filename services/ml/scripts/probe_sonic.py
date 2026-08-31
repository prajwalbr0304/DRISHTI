"""Paid, small real-model probe: AWS_PROFILE=prajwal-sso python scripts/probe_sonic.py."""
import asyncio
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.sonic import SonicStream


async def main():
    counts = {"audio_bytes": 0, "transcripts": 0, "user_transcripts": 0, "tools": 0}
    ready = asyncio.Event()
    finished = asyncio.Event()

    async def emit(event):
        kind = event["type"]
        if kind == "ready":
            print("Bedrock stream connected", flush=True)
            ready.set()
        if kind == "audio":
            counts["audio_bytes"] += len(event["audio"]) * 3 // 4
        if kind == "transcript":
            counts["transcripts"] += 1
            if event.get("role") == "USER":
                counts["user_transcripts"] += 1
            elif counts["tools"] and counts["audio_bytes"]:
                finished.set()

    async def ask(question):
        print("Grounded tool invoked", flush=True)
        counts["tools"] += 1
        return {"reply": "The connection test succeeded. This is test data, not a police statistic.", "cited_record_ids": []}

    stream = SonicStream(emit, ask)
    receiver = None
    sender = None
    try:
        async with asyncio.timeout(70):
            await stream.start()
            receiver = asyncio.create_task(stream.receive())
            pcm = b""
            if len(sys.argv) > 1:
                with wave.open(sys.argv[1], "rb") as recording:
                    assert (recording.getframerate(), recording.getnchannels(), recording.getsampwidth()) == (16000, 1, 2)
                    pcm = recording.readframes(recording.getnframes())
            async def silence():
                for offset in range(0, len(pcm), 1024):
                    await stream.audio_input(pcm[offset:offset + 1024])
                    await asyncio.sleep(0.032)
                while not finished.is_set():
                    await stream.audio_input(bytes(1024))
                    await asyncio.sleep(0.032)
            sender = asyncio.create_task(silence())
            ready_wait = asyncio.create_task(ready.wait())
            done, _ = await asyncio.wait([ready_wait, receiver], return_when=asyncio.FIRST_COMPLETED)
            if receiver in done:
                receiver.result()
            if not pcm:
                await stream.text("Please run the DRISHTI connection test.")
                print("Text input sent", flush=True)
            try:
                finish_wait = asyncio.create_task(finished.wait())
                done, _ = await asyncio.wait([finish_wait, receiver], return_when=asyncio.FIRST_COMPLETED)
                if receiver in done:
                    receiver.result()
            finally:
                sender.cancel()
                await asyncio.gather(sender, return_exceptions=True)
            print(counts)
            assert counts["tools"] and counts["audio_bytes"], "No grounded tool/audio response"
            if pcm:
                assert counts["user_transcripts"], "No speech transcription returned"
    finally:
        if sender:
            sender.cancel()
            await asyncio.gather(sender, return_exceptions=True)
        await stream.close()
        if receiver:
            receiver.cancel()
            await asyncio.gather(receiver, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
