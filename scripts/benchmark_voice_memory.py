"""Compare cached STT models using synthetic speech; no microphone or desktop actions.

Run once per model in a fresh process:
  .venv/bin/python scripts/benchmark_voice_memory.py base.en
"""

import ctypes
import ctypes.util
import json
import os
import resource
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import Settings
from voice.speech_to_text import SpeechToText


def synthesize(phrase):
    import av
    import numpy as np

    library = ctypes.util.find_library("espeak-ng") or ctypes.util.find_library("espeak")
    if not library:
        raise SystemExit("The benchmark needs the local espeak speech library.")
    engine = ctypes.CDLL(library)
    rate = engine.espeak_Initialize(2, 0, None, 0)  # synchronous PCM retrieval
    chunks = []
    callback_type = ctypes.CFUNCTYPE(
        ctypes.c_int, ctypes.POINTER(ctypes.c_short), ctypes.c_int, ctypes.c_void_p
    )

    @callback_type
    def collect(samples, count, events):
        if samples and count:
            chunks.append(ctypes.string_at(samples, count * 2))
        return 0

    engine.espeak_SetSynthCallback(collect)
    engine.espeak_SetVoiceByName(b"en")
    text = phrase.encode() + b"\0"
    engine.espeak_Synth(text, len(text), 0, 0, 0, 1, None, None)
    engine.espeak_Synchronize()
    engine.espeak_Terminate()
    samples = np.frombuffer(b"".join(chunks), dtype="<i2").reshape(1, -1)
    frame = av.AudioFrame.from_ndarray(samples, format="s16", layout="mono")
    frame.sample_rate = rate
    resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
    frames = resampler.resample(frame) + resampler.resample(None)
    return b"".join(frame.to_ndarray().tobytes() for frame in frames)


def main():
    settings = Settings.load()
    os.environ["STT_MODEL"] = sys.argv[1]
    stt = SpeechToText(settings.data_dir / "models")
    results = []
    for phrase in ("Lucifer", "Open Visual Studio Code", "Search Google for Python tutorials"):
        pcm = synthesize(phrase)
        started = time.monotonic()
        result = stt.transcribe(pcm, threading.Event())
        results.append(
            {
                "input": phrase,
                "text": result.message,
                "ok": result.ok,
                "seconds": round(time.monotonic() - started, 2),
            }
        )
    print(
        json.dumps(
            {
                "model": stt.model_name,
                "peak_rss_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
                "results": results,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
