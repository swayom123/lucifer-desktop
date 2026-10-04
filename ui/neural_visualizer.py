"""Procedural, state driven neural object drawn by Qt's native raster engine."""

import math
import random
import time
from typing import ClassVar

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget


class NeuralVisualizer(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.setMinimumSize(180, 180)
        self.setAccessibleName("Animated neural visualization")
        self.state = state
        self._target = "IDLE"
        self._blend = 0.0
        self._audio = 0.0
        self._audio_target = 0.0
        self._start = time.monotonic()
        self._last = self._start
        self._phase = 0.0
        self._rotation = 0.0
        self._color = [110.0, 185.0, 219.0]
        self._quality = "high"
        self._reduced_motion = False
        randomizer = random.Random(41)
        self._nodes = []
        for index in range(2300):
            y = 1 - 2 * (index + 0.5) / 2300
            angle = index * math.pi * (3 - math.sqrt(5))
            radius = math.sqrt(max(0, 1 - y * y))
            self._nodes.append(
                (radius * math.cos(angle), y, radius * math.sin(angle), randomizer.random())
            )
        self._stars = [
            (randomizer.random(), randomizer.random(), randomizer.random()) for _ in range(85)
        ]
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)
        state.changed.connect(self._set_state)
        state.level_changed.connect(self._set_audio)

    def set_quality(self, quality: str) -> None:
        self._quality = quality if quality in {"high", "reduced"} else "high"
        self._timer.setInterval(
            80 if self._reduced_motion else (33 if self._quality == "reduced" else 16)
        )
        self.update()

    def set_reduced_motion(self, enabled: bool) -> None:
        self._reduced_motion = enabled
        self._timer.setInterval(80 if enabled else (33 if self._quality == "reduced" else 16))

    def set_paused(self, paused: bool) -> None:
        if paused:
            self._timer.stop()
        elif self.isVisible():
            self._last = time.monotonic()
            self._timer.start()

    def _set_state(self, state: str) -> None:
        self._target = state
        self._blend = 0.0
        self.update()

    def _set_audio(self, level: float) -> None:
        self._audio_target = level

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._last = time.monotonic()
        self._timer.start()

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def _tick(self) -> None:
        now = time.monotonic()
        dt = min(0.1, now - self._last)
        self._last = now
        self._phase += dt * (0.2 if self._reduced_motion else 1)
        self._rotation += dt * (
            0.03 if self._reduced_motion else (0.10 if self._target == "IDLE" else 0.20)
        )
        for i, target in enumerate(self.COLORS[self._target]):
            self._color[i] += (target - self._color[i]) * min(1, dt * 5)
        self._audio += (self._audio_target - self._audio) * min(1, dt * 9)
        self._blend = min(1, self._blend + dt * 2.2)
        self.update()

    COLORS: ClassVar[dict[str, tuple[int, int, int]]] = {
        "IDLE": (110, 185, 219),
        "LISTENING": (96, 214, 204),
        "THINKING": (163, 149, 229),
        "SPEAKING": (148, 169, 232),
        "EXECUTING": (114, 180, 233),
        "SUCCESS": (114, 219, 184),
        "ERROR": (218, 128, 161),
    }

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = self.width(), self.height()
        center = QPointF(width / 2, height * 0.46)
        size = min(width * 0.35, height * 0.38, 230)
        if size <= 0:
            return
        t = self._phase
        state = self._target
        activity = self._blend
        red, green, blue = (round(channel) for channel in self._color)
        glow = QRadialGradient(center, size * 1.45)
        glow.setColorAt(0, QColor(red, green, blue, 35))
        glow.setColorAt(0.58, QColor(red, green, blue, 11))
        glow.setColorAt(1, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(center, size * 1.45, size * 1.45)
        base = QPointF(center.x(), center.y() + size * 0.95)
        painter.save()
        painter.translate(base)
        painter.scale(1, 0.12)
        base_glow = QRadialGradient(QPointF(0, 0), size * 1.15)
        base_glow.setColorAt(0, QColor(red, green, blue, 45))
        base_glow.setColorAt(0.4, QColor(red, green, blue, 20))
        base_glow.setColorAt(1, QColor(red, green, blue, 0))
        painter.setBrush(base_glow)
        painter.drawEllipse(QPointF(0, 0), size * 1.15, size * 1.15)
        painter.restore()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for ring, alpha in ((1.20, 26), (1.43, 12)):
            painter.setPen(QPen(QColor(red, green, blue, alpha), 1))
            painter.drawEllipse(center, size * ring, size * ring * 0.72)
        nodes = (
            self._nodes
            if self._quality == "high" and not self._reduced_motion
            else self._nodes[::3]
        )
        count = len(nodes)
        points = []
        rotation = self._rotation
        ca, sa = math.cos(rotation), math.sin(rotation)
        envelope = self._audio if state in {"LISTENING", "SPEAKING"} else 0.0
        for x, y, z, seed in nodes:
            # Coherent layered waves keep neighboring nodes moving together.
            wave = math.sin(4.2 * x + 3.1 * y + t * 0.75) * math.sin(
                3.5 * z - t * 0.52
            ) + 0.5 * math.sin(7 * y + 4 * z + t * 0.43)
            speech_strength = envelope * 0.17 + (0.035 if state == "SPEAKING" else 0)
            speech = math.sin(12 * y - t * 5.2 + 3 * x) * speech_strength
            execution = 0.16 * math.sin(t * 3 + y * 8) if state == "EXECUTING" else 0
            swell = 1 + 0.035 * math.sin(t * 1.3) + 0.095 * wave + speech + execution
            if state == "LISTENING":
                swell += 0.07 * activity
            if state in {"SUCCESS", "ERROR"}:
                swell += 0.10 * math.sin(min(1, activity) * math.pi)
            # Two unequal lobes and a shallow cleft give the field a neural silhouette.
            lobe_x = x * (1.04 + 0.08 * abs(y)) + (0.065 if x >= 0 else -0.045) * (1 - y * y)
            lobe_y = y - (0.12 * math.exp(-35 * x * x) * max(0, y - 0.25))
            px, pz = lobe_x * ca + z * sa, z * ca - lobe_x * sa
            perspective = 1 + pz * 0.13
            points.append(
                (
                    center.x() + px * size * swell * perspective,
                    center.y() + lobe_y * size * 0.86 * swell * perspective,
                    pz,
                    seed,
                )
            )
        # A sparse, moving web of edges supplies structure without filling the scene.
        step = 4 if count > 1000 else 3
        for i in range(0, count - 34, step):
            ax, ay, depth, seed = points[i]
            for offset in (13, 21):
                j = i + offset
                if j >= count:
                    continue
                bx, by, _, _ = points[j]
                if (ax - bx) ** 2 + (ay - by) ** 2 > (size * 0.29) ** 2:
                    continue
                pulse = 0.5 + 0.5 * math.sin(t * (3.8 if state == "THINKING" else 1.4) + i * 0.21)
                alpha = int(
                    (9 + 19 * pulse + 12 * activity * (state != "IDLE")) * (0.7 + 0.3 * depth)
                )
                painter.setPen(QPen(QColor(red, green, blue, alpha), 0.7))
                painter.drawLine(QPointF(ax, ay), QPointF(bx, by))
        # A few coherent surface paths read as neural energy passing through the field.
        for strand in range(11):
            path = QPainterPath()
            phase = strand * 0.58
            for segment in range(34):
                fy = -0.77 + segment * 0.046
                fx = 0.58 * math.sin(fy * 2.7 + phase) + 0.05 * math.sin(t * 1.5 + fy * 9 + phase)
                limit = math.sqrt(max(0.04, 1 - fy * fy))
                fx = max(-limit * 0.85, min(limit * 0.85, fx))
                fz = math.sqrt(max(0.02, 1 - fx * fx - fy * fy))
                rx = fx * ca + fz * sa
                rz = fz * ca - fx * sa
                pos = QPointF(
                    center.x() + rx * size * (1 + rz * 0.13),
                    center.y() + fy * size * 0.86 * (1 + rz * 0.13),
                )
                if segment == 0:
                    path.moveTo(pos)
                else:
                    path.lineTo(pos)
            pulse = 0.5 + 0.5 * math.sin(t * (3 if state == "THINKING" else 1.2) + phase * 3)
            alpha = int(12 + 30 * pulse + (22 if state == "THINKING" else 0))
            painter.setPen(QPen(QColor(red, green, blue, alpha), 1.15))
            painter.drawPath(path)
        painter.setPen(Qt.PenStyle.NoPen)
        for index, (px, py, depth, seed) in enumerate(points):
            shimmer = 0.5 + 0.5 * math.sin(t * 2.3 + index * 0.47)
            alpha = int(
                (54 + 108 * shimmer + (42 if state in {"THINKING", "SPEAKING"} else 0))
                * (0.62 + 0.38 * depth)
            )
            radius = (0.65 + 0.65 * seed + (0.4 if shimmer > 0.94 else 0)) * (0.85 + 0.2 * depth)
            painter.setBrush(QColor(red, green, blue, max(15, min(255, alpha))))
            painter.drawEllipse(QPointF(px, py), radius, radius)
        if self._quality == "high" and not self._reduced_motion:
            for x, y, seed in self._stars:
                drift = 0.012 * math.sin(t * 0.3 + seed * 8)
                painter.setBrush(QColor(95, 191, 248, int(18 + 38 * seed)))
                painter.drawEllipse(
                    QPointF((x + drift) * width, y * height), 0.8 + seed, 0.8 + seed
                )
        painter.end()
