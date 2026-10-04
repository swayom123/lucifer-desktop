"""Manage one on-demand Chrome playback worker, using a separate assistant profile."""

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

from core.models import Result


def validate_seek(arguments: dict) -> None:
    seconds = arguments["seconds"]
    if not -3600 <= seconds <= 3600 or seconds == 0:
        raise ValueError("Choose a skip between 1 second and 60 minutes.")


class MediaPlayer:
    def __init__(self, data_dir):
        self.profile = data_dir / "browser-profile"
        self.process = None

    def close(self):
        if self.process:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            if self.process.stdout:
                self.process.stdout.close()
            if self.process.stdin:
                self.process.stdin.close()
            self.process = None

    def play_youtube(self, query):
        self.close()
        environment = {
            key: value
            for key, value in os.environ.items()
            if not any(part in key.upper() for part in ("KEY", "TOKEN", "SECRET", "PASSWORD"))
        }
        self.process = subprocess.Popen(
            [sys.executable, "-m", "tools.media_worker", str(self.profile), query],
            cwd=Path(__file__).resolve().parents[1],
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        ready = threading.Event()
        output = []
        process = self.process

        def read_result():
            output.append(process.stdout.readline(16000))
            ready.set()

        threading.Thread(target=read_result, daemon=True).start()
        if not ready.wait(75):
            self.close()
            return Result(
                False, "PLAYBACK_TIMEOUT", "YouTube did not become ready in time. Try again."
            )
        try:
            result = json.loads(output[0])
            return Result(result["ok"], result["code"], result["message"])
        except (ValueError, KeyError, IndexError):
            self.close()
            return Result(
                False,
                "PLAYBACK_FAILED",
                "Chrome playback could not start. Check Chrome and Playwright.",
            )

    def _control(self, command: dict) -> Result:
        if not self.process or self.process.poll() is not None or not self.process.stdin:
            return Result(False, "NO_MEDIA", "There is no Lucifer video playing right now.")
        try:
            self.process.stdin.write(json.dumps(command) + "\n")
            self.process.stdin.flush()
            output = self.process.stdout.readline(16000)
            if not output:
                return Result(
                    False, "MEDIA_UNAVAILABLE", "The playback browser is no longer available."
                )
            result = json.loads(output)
            return Result(result["ok"], result["code"], result["message"])
        except (BrokenPipeError, OSError, ValueError, KeyError):
            return Result(
                False, "MEDIA_UNAVAILABLE", "The playback browser is no longer available."
            )

    def next_video(self) -> Result:
        return self._control({"action": "next"})

    def seek_video(self, seconds: int) -> Result:
        return self._control({"action": "seek", "seconds": seconds})

    def stop_media(self):
        self.close()
        return Result(True, "MEDIA_STOPPED", "Lucifer's music browser is closed.")
