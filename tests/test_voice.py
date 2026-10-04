import threading
from types import SimpleNamespace

import numpy as np
from PySide6.QtCore import QByteArray
from PySide6.QtMultimedia import QAudioFormat

from core.models import Result
from voice.microphone import Microphone, sample_encoding, to_mono_pcm
from voice.speech_to_text import SpeechToText
from voice.wake_listener import WakeListener


def test_native_stereo_resampled_to_whisper():
    fmt = QAudioFormat()
    fmt.setSampleRate(48000)
    fmt.setChannelCount(2)
    fmt.setSampleFormat(QAudioFormat.SampleFormat.Int32)
    signal = np.sin(np.arange(48000) * 2 * np.pi * 400 / 48000) * 0.1
    raw = np.repeat((signal * 2147483648).astype("<i4"), 2).tobytes()
    pcm = to_mono_pcm(raw, fmt)
    assert len(pcm) == 16000 * 2
    samples = np.frombuffer(pcm, dtype="<i2")
    assert samples.max() > 1000
    assert samples.min() < -1000


def test_silence_never_loads_model(tmp_path, monkeypatch):
    import builtins

    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        assert not name.startswith("faster_whisper"), "Silence must not import the speech backend"
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    stt = SpeechToText(tmp_path)
    result = stt.transcribe(bytes(32000), threading.Event())
    assert result.code == "NO_SPEECH"
    assert stt.model is None


def test_cancel_before_recognition(tmp_path):
    cancelled = threading.Event()
    cancelled.set()
    assert SpeechToText(tmp_path).transcribe(bytes(32000), cancelled).code == "VOICE_CANCELLED"


def test_release_model_clears_cached_backend(tmp_path):
    stt = SpeechToText(tmp_path)
    stt.model = object()
    stt.release_model()
    assert stt.model is None


def test_low_confidence_and_cancel_after_recognition(tmp_path):
    stt = SpeechToText(tmp_path)
    pcm = (np.ones(16000) * 2000).astype("<i2").tobytes()

    class Model:
        def transcribe(self, audio, **kwargs):
            assert kwargs["vad_filter"]
            assert kwargs["condition_on_previous_text"] is False
            return [
                SimpleNamespace(text="unexpected command", no_speech_prob=0.9, avg_logprob=-2)
            ], None

    stt.model = Model()
    assert stt.transcribe(pcm, threading.Event()).code == "NO_SPEECH"
    cancelled = threading.Event()

    class CancellingModel:
        def transcribe(self, *args, **kwargs):
            cancelled.set()
            return [
                SimpleNamespace(text="Open VS Code", no_speech_prob=0.1, avg_logprob=-0.2)
            ], None

    stt.model = CancellingModel()
    assert stt.transcribe(pcm, cancelled).code == "VOICE_CANCELLED"


def test_microphone_cancel_discards_audio(qtbot):
    mic = Microphone()
    mic.recording = True
    mic.buffer = QByteArray(b"private audio")
    emitted = []
    mic.audio.connect(emitted.append)
    mic.cancel()
    assert not mic.recording
    assert mic.buffer.size() == 0
    assert emitted == []


def test_microphone_ends_capture_after_speech_pause(qtbot):
    mic = Microphone()
    fmt = QAudioFormat()
    fmt.setSampleRate(16000)
    fmt.setChannelCount(1)
    fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
    mic.audio_format = fmt
    mic.max_bytes = 16000 * 2 * 8
    mic.recording = True

    class Stream:
        chunk = b""

        def readAll(self):
            return QByteArray(self.chunk)

    stream = Stream()
    mic.stream = stream
    stream.chunk = (np.ones(1600) * 4000).astype("<i2").tobytes()
    mic._read()
    assert mic.speech_seen
    stream.chunk = bytes(3200)
    mic._read()
    assert mic.silence_timer.isActive()
    stream.chunk = (np.ones(1600) * 4000).astype("<i2").tobytes()
    mic._read()
    assert not mic.silence_timer.isActive()
    mic.cancel()


def test_wake_listener_only_forwards_wake_word(tmp_path, qtbot):
    listener = WakeListener(tmp_path, qtbot, wake_word="lucifer")
    commands = []
    wakes = []
    listener.command.connect(commands.append)
    listener.wake_detected.connect(lambda: wakes.append(True))
    listener.running = True
    listener._result(Result(True, "VOICE_TRANSCRIPT", "open VS Code"))
    assert commands == []
    listener.running = True
    listener._result(Result(True, "VOICE_TRANSCRIPT", "Lucifer open VS Code"))
    assert commands == ["open VS Code"]
    assert listener.paused
    listener.running = True
    listener.paused = False
    listener._result(Result(True, "VOICE_TRANSCRIPT", "Hey Lucifer"))
    assert wakes == [True]
    assert listener.awaiting_command


def test_wake_listener_rejects_wake_word_inside_another_word(tmp_path, qtbot):
    listener = WakeListener(tmp_path, qtbot, wake_word="lucifer")
    commands = []
    listener.command.connect(commands.append)
    listener.running = True

    listener._result(Result(True, "VOICE_TRANSCRIPT", "luciferous open VS Code"))

    assert commands == []
    assert not listener.paused


def test_unknown_microphone_sample_format_is_rejected():
    import pytest

    with pytest.raises(ValueError, match="Unsupported audio sample format"):
        sample_encoding(QAudioFormat.SampleFormat.Unknown)


def test_wake_listener_accepts_follow_up_without_repeated_wake_word(tmp_path, qtbot):
    listener = WakeListener(tmp_path, qtbot, wake_word="lucifer")
    commands = []
    listener.command.connect(commands.append)
    listener.running = True

    listener._result(Result(True, "VOICE_TRANSCRIPT", "Lucifer"))
    listener.paused = False
    listener._result(Result(True, "VOICE_TRANSCRIPT", "open VS Code"))

    assert commands == ["open VS Code"]
    assert listener.paused
    assert not listener.awaiting_command


def test_follow_up_mode_expires_when_no_command_is_recognized(tmp_path, qtbot):
    listener = WakeListener(tmp_path, qtbot, wake_word="lucifer")
    commands = []
    listener.command.connect(commands.append)
    listener.running = True
    listener.awaiting_command = True

    listener._result(Result(False, "NO_SPEECH", "No clear speech recognized."))

    assert commands == []
    assert not listener.awaiting_command
