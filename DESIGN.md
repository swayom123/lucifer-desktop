# Lucifer desktop design

Native PySide6 UI with background worker execution. UI-only slots update widgets; every action enters a validated tool registry. Deterministic parsing handles the first milestone offline. Future LLM planners must emit the same Action contract and have no process execution capability.

## Boundaries
- config: environment settings and documented permission policy.
- core: state, typed actions/results, parsing, execution and confirmations.
- automation: OS detection and discoverable application catalog; launch argv without shell.
- tools: predefined desktop capabilities; no generic shell tool.
- database: local SQLite command metadata with parameterized statements.
- services: structured, rotating privacy-preserving action logs.
- ui: main dashboard, overlay and confirmation dialog.
- voice/ai: local speech recognition, cloud/local speech output, and validated LLM planning.

## Trust model
Tools validate exact argument keys and types before requesting permission. Level 1 executes automatically; levels 2 and 3 require explicit UI confirmation. Confirmation binds an immutable action to a random expiring single-use token. Decline/cancel invalidates the token. Unknown tools fail closed. No destructive tools in milestone 1. Applications use known executable candidates or validated Linux desktop-menu entries; terminal launch is level 2. Desktop Exec fields are parsed with shlex and shell metacharacters are rejected. Folder operations are restricted to resolved home-directory paths, including symlink resolution; hidden paths and sensitive credential paths are disallowed.

History and logs persist canonical tool names, argument names (not values), result codes, time and duration. Free-form commands, search terms, arbitrary exception messages and tool outputs are intentionally not persisted because reliable secret detection is impossible. Live command/response text is session-only. Local data permissions: directory 0700, SQLite and logs 0600 on POSIX.

Conversational follow-ups use a separate in-memory buffer limited to eight turns, 6,000
characters and five minutes. The planner receives this transcript as untrusted context so a
short clarification answer can complete the previous request. It is never written to SQLite or
logs and disappears when the process exits.

## Visual language
Background #070A0F, cards #101720, sky #7DD3FC, aqua #00E5CC, text #F8FAFC, muted #94A3B8. Quiet navigation, spacious command surface, bounded overlay. No fake waveform or microphone animation until microphone capture exists. Settings explicitly distinguish implemented features from planned integrations.

## Platform support
Linux, Windows and macOS application discovery use OS-specific candidates. Wayland screenshots use the desktop Screenshot portal and require OS consent; X11/Windows/macOS use mss with OS permission/error handling. Screenshots are private local PNG files. Browser success means OS/browser accepted a request, not that the remote page loaded. Application success means process launch was accepted, not a verified window-focus operation.

## Verified milestone

`core/state_machine.py` enforces lifecycle transitions. Execution is serialized; a Qt worker
keeps portal waits and desktop I/O off the GUI thread. Modal confirmation is asynchronous,
so the UI event loop continues running. Closing during execution is blocked; OS screenshot
requests have bounded waits and explicit cleanup. See TESTING.md for observed desktop results.

Technical reference: [Qt for Python QScreen](https://doc.qt.io/qtforpython-6/PySide6/QtGui/QScreen.html).
Lucifer uses QWidget.grab only for its own smoke-test UI artifact; real desktop capture is
handled by the screenshot tool's portal/mss adapters.

Login startup uses a user-level XDG desktop entry and --startup flag. The main process schedules
briefing collection after desktop initialization; a worker reads measurements and QProcess
requests LiveKit speech when configured, with local Speech Dispatcher as fallback, without
blocking the UI. Hands-free local microphone recognition begins after the startup delay.

## Explicit voice commands

`voice/microphone.py` uses Qt audio inputs, records the selected device's native format and
converts it to 16 kHz mono with PyAV. Recording is bounded to eight seconds and cancelled
buffers are discarded. A real peak meter reflects recorded samples. Input never runs in the
background. `ui/voice_controls.py` owns recording/transcription state and cancellation; a
worker runs faster-whisper against a pre-downloaded local cache. RMS silence rejection,
Silero VAD and confidence thresholds reduce false commands; they cannot guarantee perfect
recognition. Recognized text goes through the same Assistant/Permissions boundary as typing.

The microphone is unavailable while speech output runs. Confirmation still requires a click,
not a spoken yes. Cancellation during inference waits for inference to finish but discards its
result before any action can execute. Qt audio error enums are checked by their numeric value
because this installed PySide6 version exposes different enum identities for the same value.

The hands-free listener runs short Whisper windows after login, requires the wake word before
forwarding text, pauses during speech output, and routes commands through the same permission
gate. A future openWakeWord model could reduce CPU use, but a model trained for “Lucifer” must
be supplied; renaming a stock model would be misleading.

## Coding agent

`ai/llm.py` uses Groq's OpenAI-compatible chat endpoint first and Gemini's JSON generation
endpoint as fallback. Provider response text is parsed into a strict five-field source plan.
`tools/coding.py` owns all filesystem/compiler decisions: the model cannot choose a path, shell,
compiler flag, or executable. Projects are constrained to `~/LuciferProjects`; source names,
extensions and common process/file/network operations are checked before writing. C/C++ use
GCC/Clang with warnings; Python uses `py_compile`; JavaScript uses Node `--check`. A successful
compile is followed by a five-second run with captured output. The entire workflow is Level 2,
so the user must confirm before it executes. One repair request may include compiler diagnostics.
Generated code remains untrusted and is not a security sandbox; the confirmation dialog is the
required user review point.
