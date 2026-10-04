"""Bounded, explicit microphone capture using Qt's native audio device API."""

from PySide6.QtCore import QByteArray, QObject, QTimer, Signal
from PySide6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices


class Microphone(QObject):
    audio = Signal(bytes)
    level = Signal(int)
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.source = None
        self.stream = None
        self.buffer = QByteArray()
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.finish)
        self.monitor = QTimer(self)
        self.monitor.setInterval(100)
        self.monitor.timeout.connect(self._check_error)
        self.silence_timer = QTimer(self)
        self.silence_timer.setSingleShot(True)
        self.silence_timer.timeout.connect(self.finish)
        self.speech_seen = False
        self.recording = False

    @staticmethod
    def devices():
        return QMediaDevices.audioInputs()

    def start(self, device_id: bytes | None = None, duration_ms: int = 8000) -> None:
        if self.recording:
            return
        try:
            import av  # noqa: F401 — check optional voice dependencies before recording
            import numpy  # noqa: F401
        except ImportError:
            self.failed.emit("Install requirements-voice.txt to enable microphone commands.")
            return
        devices = self.devices()
        device = next(
            (item for item in devices if bytes(item.id()) == device_id),
            QMediaDevices.defaultAudioInput(),
        )
        if device.isNull():
            self.failed.emit("No microphone detected. Connect a microphone and try again.")
            return
        # Open in the device's native format: some PipeWire backends advertise 16 kHz
        # support but reject it on start. Resample to Whisper's 16 kHz after capture.
        self.audio_format = device.preferredFormat()
        if self.audio_format.channelCount() not in {1, 2}:
            self.failed.emit("Choose a mono or stereo microphone.")
            return
        try:
            sample_encoding(self.audio_format.sampleFormat())
        except ValueError:
            self.failed.emit("The selected microphone uses an unsupported audio format.")
            return
        duration_ms = max(1000, min(20000, duration_ms))
        self.max_bytes = self.audio_format.bytesForDuration(duration_ms * 1000)
        self.buffer.clear()
        self.speech_seen = False
        self.silence_timer.stop()
        self.source = QAudioSource(device, self.audio_format, self)
        self.recording = True
        self.stream = self.source.start()
        if not self.recording:
            return
        if self.stream is None or self.source.error().value != 0:
            self._fail()
            return
        self.stream.readyRead.connect(self._read)
        self.timer.start(duration_ms)
        self.monitor.start()

    def _read(self) -> None:
        if not self.recording or self.stream is None:
            return
        chunk = bytes(self.stream.readAll())
        self.buffer.append(chunk[: max(0, self.max_bytes - self.buffer.size())])
        import numpy as np

        dtype, scale, offset = sample_encoding(self.audio_format.sampleFormat())
        size = np.dtype(dtype).itemsize
        samples = np.frombuffer(chunk[: len(chunk) // size * size], dtype=dtype)
        # Meter from scalar extrema instead of allocating a normalized float copy
        # for every audio chunk.
        peak = (
            max(abs(float(samples.min()) - offset), abs(float(samples.max()) - offset)) / scale
            if samples.size
            else 0
        )
        self.level.emit(min(100, round(peak * 100)))
        # A fixed recording window delays every short command. Once speech has
        # started, finish after a natural pause; the duration timer remains a cap.
        if peak >= 0.025:
            self.speech_seen = True
            self.silence_timer.stop()
        elif self.speech_seen and not self.silence_timer.isActive():
            self.silence_timer.start(700)
        if self.buffer.size() >= self.max_bytes:
            self.finish()

    def _check_error(self) -> None:
        if self.recording and self.source and self.source.error().value != 0:
            self._fail()

    def _fail(self) -> None:
        self.cancel()
        self.failed.emit(
            "Microphone access failed. Check system audio permissions and the selected input."
        )

    def finish(self) -> None:
        if not self.recording:
            return
        self.recording = False
        self.timer.stop()
        self.silence_timer.stop()
        self.monitor.stop()
        if self.stream:
            self.buffer.append(
                bytes(self.stream.readAll())[: max(0, self.max_bytes - self.buffer.size())]
            )
        try:
            audio = to_mono_pcm(bytes(self.buffer), self.audio_format)
        except (ImportError, ValueError):
            self._release()
            self.failed.emit(
                "Audio conversion failed. Install requirements-voice.txt and try again."
            )
            return
        self._release()
        self.audio.emit(audio)

    def cancel(self) -> None:
        self.recording = False
        self.timer.stop()
        self.silence_timer.stop()
        self.monitor.stop()
        self._release()

    def _release(self) -> None:
        if self.source:
            self.source.stop()
            self.source.deleteLater()
        self.source = None
        self.stream = None
        self.buffer.clear()
        self.level.emit(0)


def sample_encoding(sample_format):
    """Native Qt formats mapped to NumPy dtype, full-scale value and offset."""
    encoding = {
        QAudioFormat.SampleFormat.Int16: ("<i2", 32768.0, 0),
        QAudioFormat.SampleFormat.Int32: ("<i4", 2147483648.0, 0),
        QAudioFormat.SampleFormat.Float: ("<f4", 1.0, 0),
        QAudioFormat.SampleFormat.UInt8: ("u1", 128.0, 128),
    }.get(sample_format)
    if encoding is None:
        raise ValueError("Unsupported audio sample format.")
    return encoding


def to_mono_pcm(raw: bytes, audio_format: QAudioFormat) -> bytes:
    """Convert native interleaved PCM to filtered 16 kHz mono using FFmpeg/PyAV."""
    import av
    import numpy as np

    dtype, scale, offset = sample_encoding(audio_format.sampleFormat())
    stride = np.dtype(dtype).itemsize * audio_format.channelCount()
    samples = np.frombuffer(raw[: len(raw) // stride * stride], dtype=dtype)
    if not samples.size:
        return b""
    floating = ((samples.astype(np.float32) - offset) / scale).reshape(1, -1)
    frame = av.AudioFrame.from_ndarray(
        floating, format="flt", layout="mono" if audio_format.channelCount() == 1 else "stereo"
    )
    frame.sample_rate = audio_format.sampleRate()
    resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
    frames = resampler.resample(frame) + resampler.resample(None)
    return b"".join(frame.to_ndarray().astype("<i2").tobytes() for frame in frames)
