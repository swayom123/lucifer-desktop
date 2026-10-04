"""Compose the real adapters; no simulated or disconnected tools are registered."""

from ai.llm import LLMClient
from ai.planner import Planner
from automation.application_registry import ApplicationRegistry
from config.settings import Settings
from core.assistant import Assistant
from core.models import Level
from core.tool_registry import Tool, ToolRegistry
from database.db import Database
from tools import browser, files, screenshots, system
from tools import media as media_module
from tools import notion as notion_module
from tools.answers import Answers
from tools.coding import CodingWorkflow
from tools.media import MediaPlayer
from tools.notion import NotionClient
from tools.react_app import ReactWorkflow


def build(settings: Settings) -> tuple[Assistant, ApplicationRegistry]:
    apps = ApplicationRegistry()
    client = LLMClient()
    coding = CodingWorkflow(apps, client)
    react = ReactWorkflow(client, coding)
    media = MediaPlayer(settings.data_dir)
    notion = NotionClient()
    answers = Answers(client)
    registry = ToolRegistry()
    definitions = [
        Tool(
            "answer_question",
            "Answer a factual question using live web search evidence",
            {"question": str},
            Level.SAFE,
            answers.answer_question,
        ),
        Tool(
            "create_react_app",
            "Create, build, repair and preview a React app in VS Code",
            {"request": str},
            Level.CONFIRM,
            react.create_react_app,
        ),
        Tool(
            "play_youtube",
            "Search YouTube and play music or video in Chrome, skip available ads",
            {"query": str},
            Level.SAFE,
            media.play_youtube,
        ),
        Tool(
            "stop_media",
            "Stop music/video and close Lucifer's playback browser",
            {},
            Level.SAFE,
            media.stop_media,
        ),
        Tool(
            "next_video",
            "Play the next video, episode or track in Lucifer's managed browser",
            {},
            Level.SAFE,
            media.next_video,
        ),
        Tool(
            "seek_video",
            "Skip forward or backward in the currently playing video",
            {"seconds": int},
            Level.SAFE,
            media.seek_video,
            media_module.validate_seek,
        ),
        Tool(
            "notion_schedule",
            "Schedule a meeting in the connected Notion calendar",
            {"title": str, "date": str},
            Level.CONFIRM,
            notion.schedule,
        ),
        Tool(
            "notion_today",
            "Read today's schedule from the connected Notion calendar",
            {},
            Level.SAFE,
            notion.today,
        ),
        Tool(
            "notion_upcoming",
            "Read upcoming schedule from the connected Notion calendar",
            {"days": int},
            Level.SAFE,
            notion.upcoming,
            notion_module.validate_days,
        ),
        Tool(
            "notion_note",
            "Save a note in the connected Notion notes page",
            {"content": str},
            Level.CONFIRM,
            notion.note,
        ),
        Tool(
            "open_application",
            "Launch the selected application",
            {"app_name": str},
            Level.SAFE,
            apps.launch,
            lambda a: apps.resolve(a["app_name"]),
            apps.level,
        ),
        Tool(
            "list_applications",
            "List installed applications",
            {},
            Level.SAFE,
            lambda: _list_applications(apps),
        ),
        Tool("web_search", "Open Google search", {"query": str}, Level.SAFE, browser.web_search),
        Tool(
            "youtube_search",
            "Open YouTube search",
            {"query": str},
            Level.SAFE,
            browser.youtube_search,
        ),
        Tool(
            "open_url",
            "Open a web address",
            {"url": str},
            Level.SAFE,
            browser.open_url,
            lambda a: browser.validate_url(a["url"]),
        ),
        Tool(
            "take_screenshot",
            "Capture your screen",
            {},
            Level.SAFE,
            lambda: screenshots.take_screenshot(settings.data_dir / "screenshots"),
        ),
        Tool("system_info", "Read system status", {}, Level.SAFE, system.system_info),
        Tool(
            "generate_program",
            "Generate, compile and run a program in the Lucifer workspace",
            {"request": str, "language": str},
            Level.CONFIRM,
            coding.generate_program,
        ),
        Tool(
            "open_folder",
            "Open a standard home folder",
            {"name": str},
            Level.SAFE,
            files.open_folder,
        ),
        Tool(
            "create_folder",
            "Create a folder in your home directory",
            {"name": str},
            Level.CONFIRM,
            files.create_folder,
            lambda a: files.validate_folder_name(a["name"]),
        ),
    ]
    for tool in definitions:
        registry.register(tool)
    assistant = Assistant(
        registry,
        Database(settings.data_dir / "lucifer.db"),
        Planner(client) if client.available else None,
    )
    assistant.cleanup = lambda: (react.close(), media.close())
    return assistant, apps


def _list_applications(apps: ApplicationRegistry):
    installed = [item["name"] for item in apps.discover() if item["installed"]]
    if not installed:
        from core.models import Result

        return Result(False, "NO_APPLICATIONS", "No launchable applications were found.")
    from core.models import Result

    return Result(
        True,
        "APPLICATIONS_LISTED",
        "Installed applications: " + ", ".join(installed),
        {"applications": installed},
    )
