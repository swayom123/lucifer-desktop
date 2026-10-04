# Verification record

Validated on 2026-09-21 with Python 3.12.13, PySide6 6.11.2, Linux GNOME/Wayland.

## Automated checks

- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`: **51 passed**.
- `.venv/bin/ruff check .`: passed.
- `.venv/bin/ruff format --check .`: passed.

Coverage includes parser commands and rejection, exact tool schemas, duplicate registration,
permissions at levels 2/3, expiration/cancellation/replay and forged tokens, immutable approved
arguments, state transitions, privacy of history/logs, safe error handling, application discovery
and argv construction, OS detection, URL encoding/scheme/credentials rejection, resolved path
and symlink escapes, invalid folder names, screenshot denial and browser launch failure.
Qt tests exercise command submission, feedback, SQLite history, confirmation cancellation and
navigation without executing real desktop side effects.

## Live desktop checks

- Started `.venv/bin/python main.py` normally on the active desktop; native UI remained running.
- `Open VS Code`: actual registered executable launch returned `LAUNCH_REQUESTED`.
- `Search Google for Python decorators`: default-browser request returned `BROWSER_REQUESTED`.
- Initial screenshot attempt returned `SCREENSHOT_DENIED` after no completed portal approval.
- Repeated screenshot via `scripts/desktop_smoke.py --screenshot-only`, submitting text through
  the real MainWindow. User completed GNOME consent; returned `SCREENSHOT_SAVED` in 4.55 seconds.
- Saved PNG decoded successfully as a 480 × 270 user-selected capture, 25,819 bytes.
- SQLite recorded the actual screenshot result and duration; no query or raw command was stored.
- Visually inspected Lucifer's captured window: readable palette, navigation, command input,
  saved-file feedback and idle status; no placeholder telemetry or voice animation.

Live artifacts are local, outside source:

- `~/.local/share/lucifer/desktop-smoke.json`
- `~/.local/share/lucifer/desktop-smoke-ui.png`
- `~/.local/share/lucifer/screenshots/lucifer-23275dfb24e343d28f26d769716f8e23.png`

## Limits

Windows/macOS adapters have not been run on those operating systems. Launch acceptance does
not verify focus or remote browser page loading. The screenshot portal and screen permissions
are controlled by the OS. Voice/LLM/OAuth/background listening and installer packaging are
future work, not verified features. This is a working first milestone, not a claim that all
28 sections of the longer roadmap are complete.

## Startup extension

- Desktop entry validated by `desktop-file-validate`.
- Main launcher exercised with `--startup` in an isolated test data directory on the real desktop.
- Briefing contained live local time/date, battery and memory/disk usage; local Speech Dispatcher
  completed playback with exit code 0. No audio was sent to a cloud provider.
- 56 automated tests pass, including startup display, measurement formatting, missing voice
  fallback, absent battery and duplicate startup lock handling.
- Actual reboot/login has not been performed; persistent autostart entry is installed and valid.

## Push-to-talk voice extension

- 64 automated tests pass; lint/format checks pass.
- Native Qt input enumerated the laptop's two microphone inputs and Bluetooth earbuds.
- Live capture returned 22,528 mono samples at 16 kHz; no recording was saved.
- Fixed Qt audio enum-identity compatibility and captured native device formats before resampling.
- Installed faster-whisper and downloaded base.en followed by small.en; small.en is selected.
- Real small.en recognition of an in-memory synthesized “System status” recording went through
  the actual UI recognition worker, parser, permission boundary and system_info tool. The tool
  returned SYSTEM_INFO; local spoken playback exited with code 0.
- User participated in a microphone test and reported the correct words appeared. The restricted
  live test did not independently confirm the complete spoken phrase/tool match; do not treat it
  as an accuracy benchmark. Synthetic fixtures and live audio capture are separate checks.
- No cloud recognition or Gemini requests were made. Wake-word detection is not implemented.


## Hands-free wake listener

- Wake listener starts automatically after the desktop opens (3 seconds normally, 12 seconds after the login briefing).
- It records short native microphone windows, skips quiet windows, and transcribes locally.
- Only transcripts containing “Lucifer” are forwarded; “Lucifer” alone produces “Yes?”, while “Lucifer open …” routes the remainder through the normal parser.
- It pauses during spoken output and resumes afterward.
- 70 automated tests pass, including wake-word gating and arbitrary transcript rejection.
- The currently running Linux desktop process was restarted with the hands-free code.
- The wake listener is Whisper-based and consumes more CPU than a dedicated wake-word model; a trained Lucifer openWakeWord model remains a future optimization.

## Background mode

- Autostart entry now uses `--startup --background`.
- Background mode hides the window, keeps the tray icon and wake listener alive, and shows the
  window/overlay automatically when the wake word or a wake command is recognized.
- Closing the window hides it; the tray Quit action stops the listener and exits.
- A six-second `--background` smoke run reached the event loop without a startup exception;
  the current background process holds the private instance lock.

## Coding workflow

- Groq key/model connectivity verified against the current Groq models endpoint and
  `openai/gpt-oss-120b` chat model. Gemini fallback model is configured as `gemini-3.6-flash`;
  its endpoint was temporarily unavailable during verification, so it was not used.
- Live Groq generation returned a structured C merge-sort plan. Lucifer normalized escaped
  source line breaks, rejected no unsafe operations, compiled it with GCC, ran it successfully,
  and opened `/home/swayom/LuciferProjects/Merge_Sort_Example` in VS Code.
- Generated run output contained the expected sorted sequence. No shell command was generated
  or executed. Provider keys were not printed, logged or persisted in history.
- Compiler failures trigger one repair request with diagnostics, then a structured failure.
- `76` automated tests pass, including parser, provider JSON, guarded coding/compile/repair,
  unsafe-source rejection, UI and voice workflows.

## Natural-language AI workflows (September 22, 2026)

- 99 automated tests cover planning validation, sequential approval and cancellation,
  stop-on-failure behavior, source indices, research retries, React build/runtime repair,
  restricted imports, and clicking only visible, enabled ad-skip buttons.
- Live configured-provider checks mapped the three requested examples to factual answers,
  React generation and YouTube playback; a combined editor/search request yielded two actions.
- A live student-form generation installed the fixed dependencies, built successfully and
  rendered in headless Chrome. Editor/default-browser launch was substituted during this
  isolated test; the same existing launch adapters are used in the desktop app.
- The final fixed Vite import policy was verified again with a real build and browser check.
- Live YouTube search and video playback were verified headlessly; available ad-button
  clicking was tested with controlled controls. Consent/login/verification and unskippable
  ads are not bypassed. YouTube layout or playback-policy changes can require adapter updates.
- Live factual research returned a dated, sourced answer after refined searches; search
  snippets can be stale, so the app may report that it cannot verify a current fact.
- Temporary generated test projects were removed by their temporary-directory contexts.
  Browser verification processes were closed. No keys were printed or written to logs.
