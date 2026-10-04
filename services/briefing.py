"""Local login briefing composed only from current measurements."""

from datetime import datetime

from core.models import Result
from tools.system import system_info


def build_briefing(now: datetime | None = None) -> Result:
    now = now or datetime.now().astimezone()
    greeting = (
        "Good morning" if now.hour < 12 else "Good afternoon" if now.hour < 18 else "Good evening"
    )
    introduction = (
        f"{greeting}. Lucifer is ready. Today is {now:%A, %B %d}. The time is {now:%I:%M %p}."
    )
    try:
        data = system_info().data
        battery = data["battery_percent"]
        parts = [introduction]
        if battery is not None:
            parts.append(f"Your battery is at {battery:.0f} percent.")
        parts.append(
            f"Memory usage is {data['ram_percent']:.0f} percent, "
            f"and disk usage is {data['disk_percent']:.0f} percent."
        )
        if not data["network_interface_up"]:
            parts.append("No active network interface was detected.")
        parts.append("What would you like to do?")
        return Result(True, "STARTUP_BRIEFING", " ".join(parts))
    except (OSError, RuntimeError, KeyError):
        return Result(True, "STARTUP_BRIEFING", introduction + " System readings are unavailable.")
