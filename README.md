# Lucifer

## New modular foundation (Phases 1–2)

The `lucifer/` package adds a separate, production-oriented foundation for the future
multi-agent operating layer. The existing desktop assistant described below is preserved.
The API and CLI accept and persist typed tasks. A separate Phase 2 engine can validate
plans, route registered agents, run dependent tasks with bounded retries, and verify
their results. No provider or agent is registered by default, and tools cannot execute.

Install the foundation and development tools in a Python 3.12+ environment:

```bash
python -m pip install -e '.[foundation,dev]'
```

Run the local API, bound to loopback:

```bash
python -m uvicorn lucifer.apps.api.app:app --host 127.0.0.1 --port 8000
```

Submit and inspect tasks through `POST /tasks` and `GET /tasks/{id}`. `GET /health`
reports API availability. The CLI uses the same SQLite database:

```bash
lucifer-core health
lucifer-core create "Inspect this repository"
lucifer-core show TASK_UUID
```

Set `LUCIFER_DATA_DIR` or `LUCIFER_FOUNDATION_DB` to choose the data location.
`LUCIFER_LOG_LEVEL` controls JSON log verbosity. No API keys are needed for Phase 1.
The API is local development only and has no authentication; keep it on loopback.

Run Phase 1 checks:

```bash
ruff check lucifer tests/test_foundation.py tests/test_phase2.py
mypy lucifer
pytest -q tests/test_foundation.py tests/test_phase2.py
```

See [architecture](docs/architecture.md) for boundaries and the next milestone.
See [task lifecycle](docs/task-lifecycle.md) for Phase 2 transitions and limits.

## Existing desktop assistant

A native Python/PySide6 desktop assistant with real, permission-aware desktop actions.
This release implements AI-routed typed and voice commands, hands-free local recognition,
LiveKit speech output and a spoken login briefing. It never invents system data.

## Implemented

- Native dark dashboard and floating status overlay, responsive during desktop operations.
- Typed offline command parsing and a validated extensible tool registry.
- Discover and launch known installed applications: VS Code, Chrome/Chromium, Firefox,
  Terminal, File Manager, Spotify, Calculator and Settings (availability depends on OS).
- Google/YouTube search and HTTP(S) URLs in the default browser.
- Actual PNG screenshots: desktop consent portal on Wayland; mss on X11/Windows/macOS.
- Home/Downloads/Documents/Desktop folder opening; confirmed creation of home folders.
- Real CPU, RAM, disk, battery and network-interface status.
- Private SQLite history, structured rotating logs, explicit confirmation dialogs.
- Policy, application registry, history, system status and truthful integration/settings pages.
- Single-instance main launcher and bounded history retention.
- Hands-free local wake listener and guarded coding workflow using Groq with Gemini fallback.

Close/focus apps, general file search, volume control, shutdown/restart, Gmail and calendar
remain future work. Hands-free wake listening and guarded code generation are enabled locally
on Linux after login.

## Coding workflow

Say **“Lucifer, write a program of merge sort in C”** or type the same request. Lucifer asks the
configured coding model for a JSON source plan, validates it, creates a private project under
`~/LuciferProjects`, writes a relevant source filename, compiles it with an allowlisted compiler,
runs it with a short timeout, retries once with compiler diagnostics if needed, and opens the
project in VS Code. C, C++, Python and JavaScript are supported when their local toolchain is installed.

Generated code is untrusted. Lucifer rejects common process, shell, file and network operations
and requires a confirmation dialog before the workflow writes, compiles or runs it. It never
executes model-supplied shell commands. This is a guarded local workflow, not a full OS sandbox;
review generated code before confirming. Provider requests contain the coding request and model
context; API keys are loaded from `.env`, never logged.

## Quick start on this computer

```bash
cd /home/swayom/lucifer
.venv/bin/python main.py
```

A Python 3.12 virtual environment and all development dependencies are already installed here.

To add Lucifer to the Linux applications menu, run:

```bash
.venv/bin/python scripts/install_desktop.py
```

Search for **Lucifer** in the applications menu and click its icon. Clicking it again brings
the running window forward, including when Lucifer was started in the tray at login. The
launcher uses this project's virtual environment and reads `.env` from the project directory.
If you move the project, rerun the installer to update its paths. The menu entry is separate
from the optional login autostart entry.

## Install on another computer

Python 3.12+ is required; Python 3.12 is recommended for future speech dependencies.
Use a local graphical session, not a headless server.

Linux/macOS:

```bash
cd lucifer
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

Windows PowerShell:

```powershell
cd lucifer
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
```

Or use `uv venv --python 3.12` and `uv pip install -r requirements.txt`.
`requirements.lock.txt` records the exact versions tested on Linux/Python 3.12; use
`requirements.txt` for cross-platform resolution.
Linux may require Qt's system libraries (on Debian/Ubuntu: `libxcb-cursor0`, `libxkbcommon-x11-0`,
`libegl1`, and `libgl1`). Wayland capture requires a working `xdg-desktop-portal` and your
compositor's portal backend, such as `xdg-desktop-portal-gnome`.

## Configuration and API keys

Copy `.env.example` to `.env` and add the provider credentials you want to use. The application
loads `.env` from the project root. Groq/Gemini keys enable AI planning, answers and code
generation. `LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET` enable LiveKit Inference speech through
Cartesia Sonic 3; `LIVEKIT_TTS_VOICE` selects the Cartesia voice UUID and defaults to Brandon.
Never commit `.env`.
SQLite is stored inside the data directory rather than accepting arbitrary database URLs.

Default data directories:

- Linux: `$XDG_DATA_HOME/lucifer` or `~/.local/share/lucifer`
- Windows: `%LOCALAPPDATA%\lucifer`
- macOS: `~/Library/Application Support/lucifer`

## Voice commands

Voice is hands-free on this computer. Say **“Lucifer”**, wait for “Yes, how can I help?”, then
say “Open Visual Studio Code”, “System status”, or “Search Google for Python decorators” without
repeating the wake word. You can also say “Lucifer open Visual Studio Code” in one breath. The
local listener pauses while Lucifer speaks so it cannot trigger on its own response.

The listener uses short local Whisper windows. Audio stays in memory and is discarded after
recognition; it accepts either a wake-word command or the single follow-up phrase immediately
after acknowledging the wake word. Click **Listen** or press **Ctrl+Space** for manual fallback.
Choose the microphone in the Home voice controls. The neural visualization follows microphone
level during manual capture and LiveKit speech output when that provider is active. Settings
offers Reduced visual quality and Reduce motion options; the animation pauses when the window
is hidden or minimized.

Lucifer transcribes locally, displays the recognized command, routes it through the existing
parser and permissions, and reads the result using LiveKit Inference with Cartesia's Brandon
voice. Speech streams directly to PipeWire and is discarded during playback. If LiveKit is
unavailable, Lucifer automatically uses local Speech Dispatcher. Confirmations
still require an explicit dialog click. Recognition can mishear names or search terms; use
typed input when exact wording matters. Microphone audio stays local and is never saved; response
text is sent to LiveKit/Cartesia for synthesis. Your Gemini key is not used for recognition.

For a new installation:

```bash
uv pip install --python .venv/bin/python -r requirements-voice.txt
.venv/bin/python scripts/setup_voice.py
```

The setup script downloads a model once from Hugging Face. Runtime transcription uses only
the local cache at `<data directory>/models`. `STT_MODEL` selects the model; the installed
configuration uses `base.en` for lower memory use. Set `STT_MODEL=small.en` for better accuracy
at a higher memory cost, then rerun setup. Manual and hands-free input share one model,
and silent input does not load the recognition backend. First recognition
loads the model into RAM and can take longer. No microphone is opened during model setup.
Native device audio is converted to 16 kHz mono using PyAV. This installation's Qt/PipeWire
backend is tested; other platform audio and permission flows still need verification.

The listener is active while Lucifer is running in the desktop session, even when its window is
not focused. “Hey Lucifer” and “Lucifer” are accepted. It is not active before login or after
Lucifer is closed.

## Try it

With the configured Groq/Gemini keys, requests are interpreted by AI rather than requiring
an exact command phrase. Examples:

- “Who is the richest person in the world?” — retrieves public web search evidence, refines
  the lookup when needed, and answers with source links. Unverified facts are identified.
- “Make a student form in React” — after confirmation, creates a new project in
  `~/LuciferProjects`, installs a fixed React/Vite dependency set, builds it, repairs errors
  up to twice, checks startup in headless Chrome, opens VS Code and a local preview.
- “Play latest English music” — searches YouTube in a dedicated Chrome profile and starts
  the first video result. Visible Skip Ad buttons are clicked when available; unskippable ads,
  consent, login and verification prompts still require normal site interaction.
- “Launch my code editor and search Google for React forms” — executes an ordered plan,
  validating all steps first and stopping on failure. Each gated step needs its own approval.

AI planning supports up to five registered actions per request. Unsupported tasks produce
an explanation or clarification; this does not grant unrestricted control of the computer.
Standard mode keeps up to eight recent conversation turns in memory for five minutes, allowing
short clarification replies such as “Hindi songs” to complete an earlier “Play songs” request.
Conversation mode can be started with “Lucifer, start conversation mode” or from the Home screen.
It keeps up to forty recent turns in memory for up to two hours while active, listens for the
next turn after Lucifer replies, and ends from the on-screen control or “end conversation”.
Conversation context is included in the configured AI provider request, is cleared on exit, and
is never stored in history or logs.
Without keys, the original offline commands below remain available. With keys, provider
errors or quota limits are reported without executing an unverified plan.

Install `requirements.txt` for Playwright and DDGS; browser workflows use installed Google
Chrome. React projects need Node.js 22.12+ and npm. Packages are installed with lifecycle
scripts disabled. Preview servers bind only to localhost and remain active while Lucifer
runs; a new React preview replaces the previous preview. Projects remain on disk. Run
`npm run dev` in a saved project to reopen its preview later. Browser checks catch startup
errors; they do not prove every generated feature is correct.

The existing AI keys are reused; Lucifer does not purchase credits or provision paid
services. Provider billing/quota depends on the accounts behind those keys. Requests, search
evidence and repair diagnostics are sent to the configured provider; microphone audio is not.

```text
Open VS Code
Search Google for Python decorators
Search YouTube for Python tutorials
Open GitHub
Open https://example.com
Take a screenshot
Open my Downloads folder
Create a folder called AI Projects
Open terminal
System status
```

The UI displays success or failure. On Wayland, finish the desktop capture/share dialog;
requests time out after approximately 100 seconds. Screenshots go to `screenshots/` in the
data directory. A launch/search result means the OS accepted a launch request; it does
not prove a window gained focus or a remote web page loaded.

The offline grammar supports one action per command. Unknown requests fail safely.
Application names are resolved against built-in aliases plus visible Linux `.desktop` application names, never treated as executable commands.
To add a known app, extend `automation/application_registry.py` with OS-specific candidates.
Linux application-menu entries are enumerated automatically; custom aliases and full Windows/macOS menu discovery remain future work.
Standard folders currently use their English home-directory names; localized/custom XDG
folder locations are not yet resolved.

## Architecture

```text
PySide6 UI → worker thread → Assistant
                             ├─ deterministic parser → immutable Action
                             ├─ validated ToolRegistry
                             ├─ Permissions → single-use confirmation
                             ├─ desktop adapters → structured Result
                             └─ SQLite history + JSON action log
```

- `main.py`: desktop launcher, theme and instance lock.
- `config/`: environment configuration and policy documentation.
- `core/`: action/result types, parsing, state updates, registry, permissions, orchestration.
- `automation/`: OS detection, application aliases/discovery and shell-free launching.
- `tools/`: browser, screenshot, folder and read-only system actions.
- `database/`: parameterized SQLite storage; connections close after each operation.
- `services/`: private rotating JSON logs.
- `ui/`: dashboard/navigation, confirmation dialog, worker and floating overlay.
- `tests/`: core, security and Qt interaction tests.
- `voice/`, `ai/`, `assets/`, `database/migrations/`, `ui/components/`: reserved extension locations.

No generic terminal tool is registered. AI plans produce registered structured actions
and pass through the same validation and confirmation boundary. Multi-step plans execute
sequentially, prompt per gated action, and stop on failure.

## Security and privacy

Level 1 executes automatically. Level 2 (folder creation and terminal launch) requires a
button confirmation. Level 3 always requires confirmation; destructive/sensitive tools
are not registered in this release. Policy cannot be weakened by modifying
`config/permissions.json`, which documents the code-enforced policy.
Confirmations are random, bound to immutable actions, expire after 120 seconds and are
consumed once. Closing/cancelling a confirmation does not execute the action.
Screenshot capture may require an additional OS-level permission.

No raw shell strings, `shell=True`, sudo, arbitrary LLM code, account passwords or API keys
are accepted as tool execution. Paths are resolved and constrained to the home directory;
hidden and credential folders are blocked. Folder creation only accepts a simple name.
Python extensions themselves are trusted code; this is not a sandbox for malicious plugins.

History stores canonical action names, timestamps, result codes and durations, **not the raw
command or argument values**. Live text is session-only. This deliberately favors privacy
over replaying exact search queries. History is bounded to 1,000 entries. Logs rotate at
1 MB with three backups. Screenshots may contain sensitive content and are never uploaded
or automatically deleted. POSIX data directories/files use private modes; Windows relies
on the user profile's ACLs. The desktop portal can retain its own original capture file.

## Tests and development

```bash
python -m pip install -r requirements-dev.txt -r requirements-voice.txt
QT_QPA_PLATFORM=offscreen python -m pytest -q  # Linux/macOS
python -m ruff check .
```

Windows: set `$env:QT_QPA_PLATFORM = "offscreen"` before running pytest.
Core tests use deterministic adapters and never require an LLM, open browsers, or kill processes.
Qt tests type commands, inject voice results, check feedback/history, cancel confirmations and verify that cancelled speech never executes a tool. Install requirements-voice.txt as well to run audio tests.

**Opt-in real desktop test** (opens VS Code/browser and requests OS screenshot consent):

```bash
python scripts/desktop_smoke.py
# Only test screen capture through the actual UI:
python scripts/desktop_smoke.py --screenshot-only
```

The test writes `desktop-smoke.json` and an image of Lucifer's own window to the data directory.
See `TESTING.md` for the observed validation results and platform limits.

## Startup setup

**Enabled on this computer:** `~/.config/autostart/lucifer.desktop` launches Lucifer after
Ubuntu desktop login with `--startup --background`. Lucifer stays in the tray instead of
opening a window; eight seconds after launch, it reads a local briefing using LiveKit's
Brandon voice, with Speech Dispatcher as fallback. The briefing includes the current date/time,
battery when available, RAM/disk
usage and a warning if no network interface is up. No weather, news or calendar data is
invented. LiveKit speech sends response text to the configured cloud service; the local
Speech Dispatcher fallback remains on-device. Hands-free microphone listening starts after
the configured startup delay and recognition remains local.

This runs after signing in, not at the lock screen before login. Duplicate startup
invocations exit silently while an instance already holds the app lock. Normal manual
launches do not automatically speak. If both speech providers are unavailable, text remains visible.
To preview the briefing, close any existing Lucifer instance and run:

```bash
.venv/bin/python main.py --startup
```

To disable login startup, remove `~/.config/autostart/lucifer.desktop` (the application
remains installed). The eight-second startup delay allows desktop/audio initialization.
Saying “Lucifer” shows the window and overlay automatically before processing the next phrase.
The tray menu has Open Lucifer and Quit Lucifer. Closing the window hides it and leaves the
listener running. The startup mechanism follows the [Freedesktop autostart specification](https://specifications.freedesktop.org/autostart/0.5/).

On other computers, startup remains opt-in. These entries launch the visible UI, not a wake
listener. No system service is required.

Linux desktop autostart: create `~/.config/autostart/lucifer.desktop`:

```ini
[Desktop Entry]
Type=Application
Name=Lucifer
Exec=/absolute/path/lucifer/.venv/bin/python /absolute/path/lucifer/main.py --startup
Terminal=false
X-GNOME-Autostart-enabled=true
```

Use your actual paths; quote paths containing spaces according to desktop-entry syntax.
Remove this file to disable startup. Desktop autostart is preferable to a generic systemd
service for this milestone because it inherits the graphical session and portal bus.
A dedicated systemd user wake-listener service is future work.

Windows: press Win+R, enter `shell:startup`, then create a shortcut whose target is:

```text
"C:\absolute\path\lucifer\.venv\Scripts\pythonw.exe" "C:\absolute\path\lucifer\main.py" --startup
```

Set its working directory to the Lucifer directory. Remove the shortcut to disable startup.
Use `python.exe` instead of `pythonw.exe` when diagnosing startup errors.

## Wake word and next phases

Voice commands and the login briefing use LiveKit Inference and Cartesia Sonic 3 for output,
with local Speech Dispatcher as fallback. Hands-free listening uses local faster-whisper and requires the wake word before
forwarding text. A future openWakeWord model could reduce CPU use, but a model trained for
“Lucifer” must be supplied; renaming a stock model would be misleading. Safe file search
and OAuth providers remain future work.
Renaming a stock openWakeWord model does not make it recognize “Lucifer”. Windows/macOS
audio output adapters and installers still need verification.

## Troubleshooting

- **Missing application:** only known candidates are supported. Install the app or extend
  the registry; VS Code aliases include `vscode`, `vs code`, `visual studio code`, `code`.
- **UI fails before opening:** launch from a terminal, check Qt platform libraries and the
  graphical display. `QT_QPA_PLATFORM=offscreen` is for tests, not normal use.
- **Screenshot cancelled/unavailable:** grant screen capture permission. On Wayland, use
  your portal backend and finish its interactive dialog; Lucifer does not bypass it.
  macOS additionally requires Screen Recording permission for the Python executable.
- **Browser fails:** configure the OS default browser; requests cannot confirm internet access.
- **Already running:** use the existing Lucifer window. The main launcher prevents duplicates.
- **Cannot close during an action:** finish/cancel the confirmation or desktop portal dialog.
  Closing the app while a worker executes is blocked to prevent losing action results.
- **Storage error:** ensure the configured data directory is writable and has free space.
- **No battery:** desktop machines without a battery display unavailable, never a fake percentage.

Existing Alfred projects in `Desktop/AI_Assistant*` are unchanged. Implementation decisions
and future scope are recorded in `plan.md` and `DESIGN.md`.
