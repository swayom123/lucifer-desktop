"""Small Notion API adapter for calendar planning and assistant notes."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.models import Result

API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2026-03-11"
MAX_RESPONSE_BYTES = 2_000_000


class NotionError(RuntimeError):
    """A user-safe Notion connection failure."""


class NotionClient:
    def __init__(self) -> None:
        self.token = os.getenv("NOTION_API_KEY", "").strip()
        self.connection_name = os.getenv("NOTION_CONNECTION_NAME", "Lucifer").strip() or "Lucifer"
        self.calendar_id = os.getenv("NOTION_CALENDAR_DATA_SOURCE_ID", "").strip()
        self.notes_page_id = os.getenv("NOTION_NOTES_PAGE_ID", "").strip()

    @property
    def available(self) -> bool:
        return bool(self.token)

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        if not self.available:
            raise NotionError("Notion is not configured. Add NOTION_API_KEY to .env.")
        payload = json.dumps(body).encode() if body is not None else None
        request = Request(
            API_URL + path,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Notion-Version": NOTION_VERSION,
                "User-Agent": "Lucifer-Desktop/1.0",
            },
            method=method,
        )
        try:
            with urlopen(request, timeout=30) as response:
                content = response.read(MAX_RESPONSE_BYTES + 1)
            if len(content) > MAX_RESPONSE_BYTES:
                raise NotionError("Notion returned more data than Lucifer can safely process.")
            value = json.loads(content)
            if not isinstance(value, dict):
                raise NotionError("Notion returned an invalid response.")
            return value
        except HTTPError as error:
            if error.code in {401, 403}:
                raise NotionError(
                    "Notion denied access. Share the calendar or notes page with the Lucifer integration."
                ) from error
            if error.code == 404:
                raise NotionError(
                    "The configured Notion calendar or notes target was not found."
                ) from error
            if error.code == 429:
                raise NotionError("Notion is rate limiting requests. Try again shortly.") from error
            raise NotionError("Notion could not complete that request.") from error
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            raise NotionError(
                "Notion could not be reached. Check the network connection."
            ) from error

    def _search(self, query: str, object_type: str) -> list[dict]:
        body = {"page_size": 20, "filter": {"property": "object", "value": object_type}}
        if query:
            body["query"] = query
        return self._request("POST", "/search", body).get("results", [])

    def _calendar_source(self) -> tuple[str, dict]:
        if self.calendar_id:
            return self.calendar_id, self._request("GET", f"/data_sources/{self.calendar_id}")
        for query in ("Calendar", "Schedule", "Meetings"):
            matches = self._search(query, "data_source")
            if matches:
                source_id = matches[0]["id"]
                return source_id, self._request("GET", f"/data_sources/{source_id}")
        raise NotionError(
            "No shared Notion calendar was found. Share your calendar database with the Lucifer integration."
        )

    @staticmethod
    def _properties(source: dict) -> tuple[str, str | None]:
        properties = source.get("properties", {})
        title_name = next(
            (name for name, value in properties.items() if value.get("type") == "title"), None
        )
        date_name = next(
            (name for name, value in properties.items() if value.get("type") == "date"), None
        )
        if not title_name:
            raise NotionError("The Notion calendar needs a title property.")
        return title_name, date_name

    @staticmethod
    def _title(properties: dict) -> str:
        for value in properties.values():
            if value.get("type") == "title":
                return (
                    "".join(item.get("plain_text", "") for item in value.get("title", []))
                    or "Untitled"
                )
        return "Untitled"

    @staticmethod
    def _date(properties: dict) -> str:
        for value in properties.values():
            if value.get("type") == "date" and value.get("date"):
                return value["date"].get("start", "")
        return ""

    def schedule(self, title: str, date_text: str) -> Result:
        try:
            source_id, source = self._calendar_source()
            title_name, date_name = self._properties(source)
            if not date_name:
                raise NotionError("The Notion calendar needs a date property to schedule events.")
            start = _parse_date(date_text)
            properties = {title_name: {"title": [{"text": {"content": title.strip()}}]}}
            properties[date_name] = {"date": {"start": start}}
            body = {
                "parent": {"data_source_id": source_id},
                "properties": properties,
                "children": _paragraphs(f"Scheduled for {start} by Lucifer."),
            }
            page = self._request("POST", "/pages", body)
            return Result(
                True,
                "NOTION_MEETING_CREATED",
                f"Scheduled “{title}” in Notion for {start}.",
                {"url": page.get("url", "")},
            )
        except NotionError as error:
            return Result(False, "NOTION_UNAVAILABLE", str(error))

    def _plan(self, start: date, end: date, label: str) -> Result:
        try:
            source_id, source = self._calendar_source()
            _title_name, date_name = self._properties(source)
            if not date_name:
                raise NotionError("The Notion calendar needs a date property to read plans.")
            response = self._request(
                "POST",
                f"/data_sources/{source_id}/query",
                {
                    "page_size": 100,
                    "filter": {
                        "and": [
                            {"property": date_name, "date": {"on_or_after": start.isoformat()}},
                            {"property": date_name, "date": {"on_or_before": end.isoformat()}},
                        ]
                    },
                    "sorts": [{"property": date_name, "direction": "ascending"}],
                },
            )
            rows = response.get("results", [])
            if not rows:
                return Result(True, "NOTION_PLAN_EMPTY", f"You have no Notion events {label}.")
            lines = [f"Your Notion plan {label}:"]
            for item in rows[:20]:
                when = self._date(item.get("properties", {}))
                lines.append(f"• {when}: {self._title(item.get('properties', {}))}")
            return Result(True, "NOTION_PLAN", "\n".join(lines))
        except NotionError as error:
            return Result(False, "NOTION_UNAVAILABLE", str(error))

    def today(self) -> Result:
        current = datetime.now().astimezone().date()
        return self._plan(current, current, "for today")

    def upcoming(self, days: int) -> Result:
        current = datetime.now().astimezone().date()
        return self._plan(current, current + timedelta(days=days), f"for the next {days} days")

    def note(self, content: str) -> Result:
        try:
            parent_id = self.notes_page_id
            if not parent_id:
                for query in ("Notes", "Journal", "Work"):
                    matches = self._search(query, "page")
                    if matches:
                        parent_id = matches[0]["id"]
                        break
            if not parent_id:
                raise NotionError(
                    "No shared Notion notes page was found. Share a Notes page with the Lucifer integration."
                )
            today = datetime.now().astimezone().date().isoformat()
            page = self._request(
                "POST",
                "/pages",
                {
                    "parent": {"page_id": parent_id},
                    "properties": {
                        "title": {"title": [{"text": {"content": f"Lucifer note · {today}"}}]}
                    },
                    "children": _paragraphs(content.strip()),
                },
            )
            return Result(
                True,
                "NOTION_NOTE_CREATED",
                "Saved your note in Notion.",
                {"url": page.get("url", "")},
            )
        except NotionError as error:
            return Result(False, "NOTION_UNAVAILABLE", str(error))


def validate_days(arguments: dict) -> None:
    if not 1 <= arguments["days"] <= 30:
        raise ValueError("Choose between 1 and 30 upcoming days.")


def _parse_date(value: str) -> str:
    normalized = value.strip().casefold()
    current = datetime.now().astimezone().date()
    if normalized in {"today", "todays", "today's"}:
        return current.isoformat()
    if normalized == "tomorrow":
        return (current + timedelta(days=1)).isoformat()
    try:
        return date.fromisoformat(value.strip()).isoformat()
    except ValueError as error:
        raise NotionError("Use a date such as today, tomorrow, or YYYY-MM-DD.") from error


def _paragraphs(text: str) -> list[dict]:
    return [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": text[:2000]}}]},
        }
    ]
