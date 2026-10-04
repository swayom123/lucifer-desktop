"""Download the speech model once; runtime recognition is local-only."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import Settings
from voice.speech_to_text import SpeechToText


def main() -> None:
    from faster_whisper import WhisperModel

    settings = Settings.load()
    stt = SpeechToText(settings.data_dir / "models")
    if stt.model_name not in {"tiny.en", "base.en", "small.en", "small", "base", "tiny"}:
        raise SystemExit("Choose tiny, base or small (optionally .en) for STT_MODEL.")
    print(f"Downloading/loading {stt.model_name}; microphone remains off.", flush=True)
    WhisperModel(
        stt.model_name,
        device="cpu",
        compute_type="int8",
        download_root=str(stt.cache),
        cpu_threads=4,
    )
    print("Local speech model is ready.", flush=True)


if __name__ == "__main__":
    main()
