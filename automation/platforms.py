"""Explicit supported-platform detection."""

import platform


def detect_os() -> str:
    name = platform.system()
    if name not in {"Linux", "Windows", "Darwin"}:
        raise RuntimeError("This operating system is not supported.")
    return name
