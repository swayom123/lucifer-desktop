"""Browser worker. Click only public video controls, including available Skip Ad buttons."""

import json
import queue
import re
import signal
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlencode


def skip_ad(page):
    for selector in (".ytp-ad-skip-button", ".ytp-skip-ad-button", ".ytp-ad-skip-button-modern"):
        button = page.locator(selector).first
        if button.is_visible() and button.is_enabled():
            button.click(timeout=1000)
            return True
    return False


def control_media(page, action, seconds=0):
    """Control the active HTML5 video in the managed browser session."""
    from playwright.sync_api import Error

    if action == "seek":
        video = page.locator("video").first
        try:
            if not video.is_visible():
                return {"ok": False, "code": "NO_VIDEO", "message": "No active video was found."}
            current = video.evaluate(
                """(video, delta) => {
                    if (!Number.isFinite(video.duration)) return null;
                    video.currentTime = Math.max(0, Math.min(video.duration, video.currentTime + delta));
                    return video.currentTime;
                }""",
                seconds,
            )
            if current is None:
                return {
                    "ok": False,
                    "code": "NO_VIDEO",
                    "message": "The video position is unavailable.",
                }
            direction = "forward" if seconds > 0 else "back"
            return {
                "ok": True,
                "code": "VIDEO_SEEKED",
                "message": f"Skipped {abs(seconds)} seconds {direction}.",
            }
        except (Error, TypeError):
            return {"ok": False, "code": "NO_VIDEO", "message": "No active video was found."}

    selectors = (
        "button[aria-label*='next' i]",
        "button[title*='next' i]",
        "[data-testid*='next' i]",
        ".ytp-next-button",
        "[data-uia*='next' i]",
    )
    for selector in selectors:
        try:
            button = page.locator(selector).first
            if button.is_visible() and button.is_enabled():
                button.click(timeout=1500)
                return {"ok": True, "code": "NEXT_VIDEO", "message": "Playing the next video."}
        except (Error, TypeError):
            continue
    try:
        buttons = page.get_by_role(
            "button", name=re.compile(r"\bnext(?: video| episode| track)?\b", re.IGNORECASE)
        ).all()
        for button in buttons:
            if button.is_visible() and button.is_enabled():
                button.click(timeout=1500)
                return {"ok": True, "code": "NEXT_VIDEO", "message": "Playing the next video."}
    except (Error, TypeError):
        pass
    return {
        "ok": False,
        "code": "NEXT_UNAVAILABLE",
        "message": "The current site does not expose a next-video control.",
    }


def play(page, query):
    from playwright.sync_api import TimeoutError as BrowserTimeout

    page.goto(
        "https://www.youtube.com/results?" + urlencode({"search_query": query}),
        wait_until="domcontentloaded",
        timeout=30000,
    )
    # Consent/login/CAPTCHA decisions remain visible for the user; never bypass them.
    video = page.locator("ytd-video-renderer a#video-title").first
    try:
        video.wait_for(state="visible", timeout=15000)
    except BrowserTimeout:
        return {
            "ok": False,
            "code": "YOUTUBE_NEEDS_ATTENTION",
            "message": "YouTube is open in Chrome. Complete any consent or verification prompt, then ask again.",
        }
    title = video.get_attribute("title") or "the first video result"
    video.click(timeout=10000)
    page.locator("video").first.wait_for(state="attached", timeout=15000)
    play_button = page.locator(".ytp-play-button").first
    if (
        play_button.is_visible()
        and "play" in (play_button.get_attribute("aria-label") or "").lower()
    ):
        play_button.click()
    playing = False
    for _ in range(10):
        skip_ad(page)
        page.locator("video").first.evaluate("v => { if (v.paused) v.play().catch(() => {}); }")
        playing = page.locator("video").first.evaluate("v => !v.paused && v.currentTime > 0")
        if playing:
            break
        page.wait_for_timeout(500)
    return {
        "ok": bool(playing),
        "code": "YOUTUBE_PLAYING" if playing else "YOUTUBE_NEEDS_ATTENTION",
        "message": (
            f"Started YouTube playback for {title}. Available Skip Ad buttons will be clicked."
            if playing
            else "YouTube is open, but playback could not be verified. Check the player."
        ),
    }


def main():
    from playwright.sync_api import Error, sync_playwright

    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    profile = Path(sys.argv[1])
    profile.mkdir(parents=True, exist_ok=True, mode=0o700)
    reported = False
    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(profile),
                channel="chrome",
                headless=False,
                args=["--autoplay-policy=no-user-gesture-required"],
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                result = play(page, sys.argv[2])
                print(json.dumps(result), flush=True)
                reported = True
                commands = queue.Queue()

                def read_commands():
                    for line in sys.stdin:
                        commands.put(line)

                threading.Thread(target=read_commands, daemon=True).start()
                while not page.is_closed():
                    try:
                        skip_ad(page)
                        while True:
                            try:
                                command = json.loads(commands.get_nowait())
                                response = control_media(
                                    page, command.get("action", ""), int(command.get("seconds", 0))
                                )
                                print(json.dumps(response), flush=True)
                            except queue.Empty:
                                break
                            except (ValueError, TypeError):
                                response = {
                                    "ok": False,
                                    "code": "INVALID_MEDIA_COMMAND",
                                    "message": "Invalid media control.",
                                }
                                print(json.dumps(response), flush=True)
                        page.wait_for_timeout(1000)
                    except Error:
                        if page.is_closed():
                            break
                        time.sleep(1)
            finally:
                context.close()
    except (Error, OSError):
        if not reported:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "code": "PLAYBACK_FAILED",
                        "message": "YouTube playback failed. Check Chrome, network access and any page prompts.",
                    }
                ),
                flush=True,
            )


if __name__ == "__main__":
    main()
