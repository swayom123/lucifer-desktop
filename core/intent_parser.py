"""Conservative offline grammar. Unknown commands never become shell commands."""

import re

from core.models import Action


def parse(command: str) -> Action:
    if not isinstance(command, str) or not command.strip() or len(command) > 2000:
        raise ValueError("Enter a command of 1–2000 characters.")
    text = re.sub(r"^(?:hey\s+)?lucifer[,! .]*", "", command.strip(), flags=re.IGNORECASE).strip()
    text = text.rstrip(".!?").strip()
    lowered = text.casefold()
    if re.fullmatch(r"(?:play|go to|skip to) (?:the )?next (?:video|song|track|episode)", lowered):
        return Action.create("next_video")
    match = re.fullmatch(
        r"(?:skip|forward|jump) (?:forward )?(\d+)\s*(seconds?|secs?|minutes?|mins?)|"
        r"(?:go )?back(?:ward)? (\d+)\s*(seconds?|secs?|minutes?|mins?)",
        lowered,
    )
    if match:
        amount = int(match[1] or match[3])
        unit = match[2] or match[4]
        seconds = amount * (60 if unit.startswith("min") else 1)
        if match[3]:
            seconds = -seconds
        return Action.create("seek_video", seconds=seconds)
    if lowered in {"take a screenshot", "screenshot", "take screenshot"}:
        return Action.create("take_screenshot")
    if lowered in {
        "system status",
        "system information",
        "what's my battery percentage",
        "battery",
        "cpu usage",
        "ram usage",
        "how much ram am i using",
    }:
        return Action.create("system_info")
    if lowered in {
        "list apps",
        "list applications",
        "list installed applications",
        "show apps",
        "show applications",
        "what apps are installed",
    }:
        return Action.create("list_applications")
    match = re.fullmatch(
        r"(?:write|create|make|build) (?:a |an )?(?:program|project|file) (?:for |that )?(.+?)\s+in\s+(c\+\+|c|python|javascript|js)",
        text,
        re.IGNORECASE,
    )
    if match:
        language = match[2].casefold()
        return Action.create(
            "generate_program",
            request=match[1].strip(),
            language="javascript" if language == "js" else language,
        )
    match = re.fullmatch(r"search (google|youtube|the web|web) for (.+)", text, re.IGNORECASE)
    if match:
        return Action.create(
            "youtube_search" if match[1].lower() == "youtube" else "web_search",
            query=match[2].strip(),
        )
    match = re.fullmatch(r"create (?:a )?folder (?:called |named )?(.+)", text, re.IGNORECASE)
    if match:
        return Action.create("create_folder", name=match[1].strip())
    match = re.fullmatch(
        r"open (?:my )?(downloads|documents|desktop|home)(?: folder)?", text, re.IGNORECASE
    )
    if match:
        return Action.create("open_folder", name=match[1].lower())
    match = re.fullmatch(r"open (.+)", text, re.IGNORECASE)
    if match:
        target = match[1].strip()
        if target.lower() == "github":
            return Action.create("open_url", url="https://github.com")
        if re.match(r"https?://", target, re.IGNORECASE):
            return Action.create("open_url", url=target)
        return Action.create("open_application", app_name=target)
    raise ValueError(
        "Command not supported yet. Try “Open VS Code”, “Search Google for Python "
        "decorators”, “Take a screenshot”, or “System status”."
    )
