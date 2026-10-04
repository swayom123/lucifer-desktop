"""Read-only real system telemetry."""

from pathlib import Path

import psutil

from core.models import Result


def system_info() -> Result:
    cpu = psutil.cpu_percent(interval=0.2)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage(str(Path.home()))
    battery = psutil.sensors_battery()
    network = any(
        item.isup and name not in {"lo", "lo0"} for name, item in psutil.net_if_stats().items()
    )
    data = {
        "cpu_percent": cpu,
        "ram_percent": memory.percent,
        "disk_percent": disk.percent,
        "battery_percent": battery.percent if battery else None,
        "network_interface_up": network,
    }
    charge = f"{battery.percent:.0f}%" if battery else "unavailable"
    return Result(
        True,
        "SYSTEM_INFO",
        f"CPU {cpu:.0f}% · RAM {memory.percent:.0f}% · Disk {disk.percent:.0f}%\n"
        f"Battery {charge} · Network interface {'up' if network else 'down'}",
        data,
    )
