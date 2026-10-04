"""Generate LiveKit Inference speech and stream it to the local audio server."""

from __future__ import annotations

import asyncio
import math
import os
import shutil
import sys

import aiohttp
from livekit.agents import inference

from config.settings import Settings


async def _speak(text: str) -> None:
    player = shutil.which("pw-play")
    if not player:
        raise RuntimeError("PipeWire audio playback is unavailable")

    process: asyncio.subprocess.Process | None = None
    audio_format: tuple[int, int] | None = None
    async with aiohttp.ClientSession() as http_session:
        tts = inference.TTS(
            model=os.getenv("LIVEKIT_TTS_MODEL", "cartesia/sonic-3"),
            voice=os.getenv("LIVEKIT_TTS_VOICE", "5cad89c9-d88a-4832-89fb-55f2f16d13d3"),
            language="en",
            http_session=http_session,
        )
        try:
            async with tts.synthesize(text) as stream:
                async for event in stream:
                    frame = event.frame
                    current_format = (frame.sample_rate, frame.num_channels)
                    if process is None:
                        audio_format = current_format
                        process = await asyncio.create_subprocess_exec(
                            player,
                            "--raw",
                            "--format=s16",
                            f"--rate={frame.sample_rate}",
                            f"--channels={frame.num_channels}",
                            "-",
                            stdin=asyncio.subprocess.PIPE,
                            stdout=asyncio.subprocess.DEVNULL,
                            stderr=asyncio.subprocess.DEVNULL,
                        )
                    elif current_format != audio_format:
                        raise RuntimeError("LiveKit changed audio format during playback")
                    assert process.stdin is not None
                    pcm = bytes(frame.data)
                    # Small level messages let the native visualizer follow actual TTS PCM.
                    samples = memoryview(pcm).cast("h")
                    rms = math.sqrt(sum(value * value for value in samples[::max(1, len(samples)//800)]) / max(1, len(samples[::max(1, len(samples)//800)])))
                    print(f"LEVEL:{min(100, round(rms / 327.68))}", flush=True)
                    process.stdin.write(pcm)
                    await process.stdin.drain()

            if process is None or process.stdin is None:
                raise RuntimeError("LiveKit returned no audio")
            process.stdin.close()
            await process.stdin.wait_closed()
            if await process.wait() != 0:
                raise RuntimeError("PipeWire could not play LiveKit audio")
        finally:
            await tts.aclose()
            if process is not None and process.returncode is None:
                process.terminate()
                await process.wait()


def main() -> int:
    Settings.load()
    text = sys.stdin.read().strip()
    if not text:
        return 0
    try:
        asyncio.run(_speak(text))
    except Exception:  # noqa: BLE001 - provider errors must become a clean worker failure.
        # Keep provider responses and credentials out of the parent process logs.
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
