"""Default-browser navigation with constrained URLs and encoded queries."""

import webbrowser
from urllib.parse import urlencode, urlsplit

from core.models import Result


def validate_url(url: str) -> None:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        raise ValueError("Invalid web address.") from None
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or any(c.isspace() for c in url)
        or "\\" in url
        or port == 0
    ):
        raise ValueError("Use an http:// or https:// address without embedded credentials.")


def search_url(query: str, youtube: bool = False) -> str:
    base = "https://www.youtube.com/results?" if youtube else "https://www.google.com/search?"
    return base + urlencode({"search_query" if youtube else "q": query})


def open_url(url: str) -> Result:
    validate_url(url)
    if not webbrowser.open(url, new=2):
        return Result(False, "BROWSER_UNAVAILABLE", "The default browser could not be opened.")
    return Result(True, "BROWSER_REQUESTED", "Opened the address in your default browser.")


def web_search(query: str) -> Result:
    result = open_url(search_url(query))
    return Result(
        result.ok,
        result.code,
        "Google search opened in your default browser." if result.ok else result.message,
    )


def youtube_search(query: str) -> Result:
    result = open_url(search_url(query, youtube=True))
    return Result(
        result.ok,
        result.code,
        "YouTube search opened in your default browser." if result.ok else result.message,
    )
