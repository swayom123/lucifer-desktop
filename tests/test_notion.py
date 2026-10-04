from datetime import UTC, datetime

from tools.notion import NotionClient, validate_days


class FakeNotion(NotionClient):
    def __init__(self):
        super().__init__()
        self.token = "test-token"
        self.requests = []

    def _search(self, _query, _object_type):
        return []

    def _request(self, method, path, body=None):
        self.requests.append((method, path, body))
        if method == "GET":
            return {
                "properties": {
                    "Name": {"type": "title"},
                    "Date": {"type": "date"},
                }
            }
        if method == "POST" and path == "/pages":
            return {"url": "https://notion.so/example"}
        return {"results": []}


def test_schedule_builds_notion_calendar_page(monkeypatch):
    monkeypatch.setenv("NOTION_CALENDAR_DATA_SOURCE_ID", "calendar-id")
    client = FakeNotion()

    result = client.schedule("Presentation", "2026-09-23")

    assert result.ok
    method, path, body = client.requests[-1]
    assert method == "POST"
    assert path == "/pages"
    assert body["parent"] == {"data_source_id": "calendar-id"}
    assert body["properties"]["Date"]["date"]["start"] == "2026-09-23"


def test_today_queries_date_range(monkeypatch):
    monkeypatch.setenv("NOTION_CALENDAR_DATA_SOURCE_ID", "calendar-id")
    client = FakeNotion()
    result = client.today()

    assert result.ok
    assert client.requests[-1][1] == "/data_sources/calendar-id/query"
    filters = client.requests[-1][2]["filter"]["and"]
    assert filters[0]["date"]["on_or_after"] == datetime.now(UTC).date().isoformat()


def test_upcoming_days_validation():
    validate_days({"days": 7})


def test_schedule_requires_a_date_property(monkeypatch):
    monkeypatch.setenv("NOTION_CALENDAR_DATA_SOURCE_ID", "calendar-id")
    client = FakeNotion()
    client._properties = lambda _source: ("Name", None)

    result = client.schedule("Presentation", "2026-09-23")

    assert not result.ok
    assert result.code == "NOTION_UNAVAILABLE"
    assert "date property" in result.message
