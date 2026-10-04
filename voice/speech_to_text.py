"""Offline, cached faster-whisper transcription. No audio leaves this process."""

import gc
import math
import os
import threading
from pathlib import Path

from core.models import Result


def pcm_rms(pcm: bytes) -> float:
    """Return normalized 16-bit PCM RMS without allocating a float sample array."""
    if not pcm or len(pcm) % 2:
        return 0.0
    samples = memoryview(pcm).cast("h")
    mean_square = sum(sample * sample for sample in samples) / len(samples)
    return math.sqrt(mean_square) / 32768.0


class SpeechToText:
    def __init__(self, cache: Path):
        self.cache = cache
        self.model_name = os.getenv("STT_MODEL", "base.en")
        try:
            self.cpu_threads = max(1, min(4, int(os.getenv("STT_CPU_THREADS", "2"))))
        except ValueError:
            self.cpu_threads = 2
        self.model = None

    def transcribe(self, pcm: bytes, cancelled: threading.Event) -> Result:
        if cancelled.is_set():
            return Result(False, "VOICE_CANCELLED", "Voice command cancelled.")
        if len(pcm) < 8000 or len(pcm) % 2:
            return Result(
                False,
                "NO_SPEECH",
                "No clear speech captured. Try again and speak after clicking Listen.",
            )
        # Most hands-free windows are quiet. Reject them before importing NumPy or
        # allocating the float32 buffer required by Whisper.
        if pcm_rms(pcm) < 0.002:
            return Result(
                False,
                "NO_SPEECH",
                "The microphone was quiet. Check the input device and try again.",
            )
        try:
            import numpy as np
        except ImportError:
            return Result(
                False,
                "VOICE_SETUP_REQUIRED",
                "Install requirements-voice.txt to enable local speech recognition.",
            )
        audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
        audio /= 32768.0
        try:
            if self.model is None:
                from faster_whisper import WhisperModel

                self.model = WhisperModel(
                    self.model_name,
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=self.cpu_threads,
                    num_workers=1,
                    download_root=str(self.cache),
                    local_files_only=True,
                )
            if cancelled.is_set():
                return Result(False, "VOICE_CANCELLED", "Voice command cancelled.")
            try:
                segments, _ = self.model.transcribe(
                    audio,
                    language="en",
                    beam_size=5,
                    hotwords=(
                        "Lucifer, VS Code, Visual Studio Code, Google, YouTube, system status, "
                        "Hindi music, Hindi songs, Bollywood music, latest music"
                    ),
                    vad_filter=True,
                    condition_on_previous_text=False,
                    vad_parameters={"min_silence_duration_ms": 400},
                )
                text = " ".join(
                    segment.text.strip()
                    for segment in segments
                    if segment.no_speech_prob < 0.6 and segment.avg_logprob > -1.0
                ).strip()
            finally:
                # The model owns the persistent memory; release each request's float copy.
                del audio
            if cancelled.is_set():
                return Result(False, "VOICE_CANCELLED", "Voice command cancelled.")
            if not text:
                return Result(False, "NO_SPEECH", "No clear speech recognized. Please try again.")
            return Result(True, "VOICE_TRANSCRIPT", text)
        except ImportError:
            return Result(
                False,
                "VOICE_SETUP_REQUIRED",
                "Install requirements-voice.txt to enable local speech recognition.",
            )
        except Exception:  # noqa: BLE001 — optional model/backend failures must not crash desktop
            return Result(
                False,
                "VOICE_MODEL_UNAVAILABLE",
                "Speech model unavailable. Run .venv/bin/python scripts/setup_voice.py, then retry.",
            )

    def release_model(self) -> None:
        """Release native Whisper allocations when the assistant is shutting down."""
        model, self.model = self.model, None
        del model
        gc.collect()
