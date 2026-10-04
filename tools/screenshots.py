"""Actual screen capture. Wayland uses the user's desktop consent portal."""

import asyncio
import os
import shutil
import uuid
from contextlib import suppress
from pathlib import Path
from urllib.parse import unquote, urlsplit

from core.models import Result


async def portal_screenshot() -> Path:
    from dbus_next import Message, MessageType, Variant
    from dbus_next.aio import MessageBus

    bus = await MessageBus().connect()
    response = asyncio.get_running_loop().create_future()
    token = "lucifer_" + uuid.uuid4().hex
    sender = bus.unique_name.lstrip(":").replace(".", "_")
    request_path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"

    def receive(message):
        if (
            message.message_type == MessageType.SIGNAL
            and message.path == request_path
            and message.interface == "org.freedesktop.portal.Request"
            and message.member == "Response"
            and not response.done()
        ):
            response.set_result(message.body)

    bus.add_message_handler(receive)
    try:
        rule = (
            "type='signal',sender='org.freedesktop.portal.Desktop',"
            f"interface='org.freedesktop.portal.Request',path='{request_path}'"
        )
        reply = await bus.call(
            Message(
                destination="org.freedesktop.DBus",
                path="/org/freedesktop/DBus",
                interface="org.freedesktop.DBus",
                member="AddMatch",
                signature="s",
                body=[rule],
            )
        )
        if reply.message_type == MessageType.ERROR:
            raise RuntimeError("Portal subscription failed")
        reply = await bus.call(
            Message(
                destination="org.freedesktop.portal.Desktop",
                path="/org/freedesktop/portal/desktop",
                interface="org.freedesktop.portal.Screenshot",
                member="Screenshot",
                signature="sa{sv}",
                body=["", {"handle_token": Variant("s", token), "interactive": Variant("b", True)}],
            )
        )
        if reply.message_type == MessageType.ERROR:
            raise RuntimeError("Screenshot portal unavailable")
        status, values = await asyncio.wait_for(response, timeout=90)
        if status != 0:
            raise PermissionError("Screen capture was cancelled or denied.")
        uri = urlsplit(values["uri"].value)
        if uri.scheme != "file" or uri.netloc not in {"", "localhost"}:
            raise RuntimeError("Invalid screenshot response")
        return Path(unquote(uri.path))
    finally:
        # Close any surviving interactive request on timeout/cancellation.
        try:
            with suppress(TimeoutError):
                await asyncio.wait_for(
                    bus.call(
                        Message(
                            destination="org.freedesktop.portal.Desktop",
                            path=request_path,
                            interface="org.freedesktop.portal.Request",
                            member="Close",
                        )
                    ),
                    timeout=2,
                )
        finally:
            bus.disconnect()


def take_screenshot(directory: Path) -> Result:
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination = directory / f"lucifer-{uuid.uuid4().hex}.png"
    try:
        descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        if os.environ.get("WAYLAND_DISPLAY"):
            source = asyncio.run(asyncio.wait_for(portal_screenshot(), timeout=100))
            shutil.copyfile(source, destination)
        else:
            import mss

            with mss.mss() as capture:
                capture.shot(mon=0, output=str(destination))
        if not destination.is_file() or destination.stat().st_size == 0:
            raise RuntimeError("No screenshot received")
        if os.name == "posix":
            destination.chmod(0o600)
        return Result(
            True,
            "SCREENSHOT_SAVED",
            f"Screenshot saved to {destination}.",
            {"path": str(destination)},
        )
    except (TimeoutError, PermissionError):
        destination.unlink(missing_ok=True)
        return Result(
            False,
            "SCREENSHOT_DENIED",
            "Screenshot cancelled or consent timed out. Allow capture in the desktop dialog.",
        )
    except Exception:  # noqa: BLE001 — isolate adapter failures without leaking secrets
        destination.unlink(missing_ok=True)
        return Result(
            False,
            "SCREENSHOT_UNAVAILABLE",
            "Screen capture is unavailable. Check desktop screen-recording permissions "
            "and the Screenshot portal on Wayland.",
        )
