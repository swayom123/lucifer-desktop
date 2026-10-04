# Lucifer implementation plan

## Inspection
- Workspace starts at /home/swayom, which is not a Git repository.
- Desktop/AI_Assistant has design documents only.
- Desktop/AI_Assistant2 is an existing Next.js/FastAPI Alfred workspace with explicitly unconnected tool providers. Preserve it unchanged.
- Build a separate native application at /home/swayom/lucifer.
- Host: Linux GNOME Wayland, Python 3.12 available through uv, VS Code installed.

## First milestone
1. Configuration, modular packages, typed contracts, state machine and private SQLite history.
2. Validated registry and immutable confirmation requests; reject unknown tools and shell execution.
3. Platform application discovery/launch, browser search, screenshot capture (Wayland portal), system info and constrained folder creation.
4. PySide6 dashboard, floating status overlay, command history, installed apps, policy and truthful settings/status pages.
5. Unit/security tests, offscreen UI test, real desktop smoke test. Document limitations and results.

## Later phases
After this milestone: microphone + local faster-whisper, voice output, trained Lucifer wake model and tray/background listener; structured LLM plans; expanded file and system controls; OAuth Gmail/calendar; packaging and startup integration. No placeholder providers will claim success.

## Milestone outcome — 2026-09-21

Completed the first typed-command milestone in the confirmed /home/swayom/lucifer directory.
Existing Alfred projects were preserved unchanged.

- [x] Config, dependencies, private data directory, SQLite and rotating structured logging.
- [x] Explicit state machine and typed Action/Result contracts.
- [x] Validated registry, conservative offline grammar and expiring single-use confirmations.
- [x] Actual registered app launches, Google/YouTube browser requests and screenshot capture.
- [x] Safe standard folder opening, confirmed folder creation and real system information.
- [x] PySide6 workspace, floating status overlay, feedback, history and policy views.
- [x] 51 automated tests and lint/format checks.
- [x] Normal desktop launch, real VS Code/browser requests and successful consented Wayland capture.
- [x] README, DESIGN, verification record, exact tested dependency lock and live smoke script.
- [x] graphify AST-only graph update.

Next phase: local push-to-talk capture and faster-whisper. Validate microphone behavior before
adding TTS, a real trained Lucifer wake-word model or autonomous multi-step plans.

## Coding-agent phase — 2026-09-21

Completed a guarded code-generation workflow using the configured Groq primary model and Gemini
fallback. Coding requests parse into a confirmation-gated `generate_program` action. The model
returns JSON only; Lucifer validates project/file names and source safety, writes within
`~/LuciferProjects`, selects a fixed compiler/runtime, captures diagnostics, retries once with
diagnostics, and opens VS Code. No model-supplied shell command is executed. Groq was verified
live with a merge-sort C program; Gemini fallback is configured but was unavailable during the
live check. The background process was restarted with the feature enabled.

## Login startup and briefing — 2026-09-21

User requested automatic startup and a briefing. Installed the GNOME/XDG autostart entry at
/home/swayom/.config/autostart/lucifer.desktop. Added --startup with an eight-second UI timer,
a real local date/time/system briefing and asynchronous Speech Dispatcher playback. Normal
manual launches remain quiet; duplicate startup attempts exit silently. No microphone or
external briefing providers are enabled. Verified real UI briefing and speech process exit 0;
56 automated tests pass. No reboot was performed.

## Voice-command phase — 2026-09-21

- Added optional faster-whisper dependencies and explicit model setup.
- Added native microphone selection/capture, live peak meter, eight-second recording cap,
  manual stop, cancellation and local PyAV conversion to Whisper input format.
- Added local-only recognition with speech/silence filtering and domain vocabulary.
- Routed recognized commands through existing validation and confirmation gates.
- Added spoken results, queued speech replies, speaking feedback and feedback-loop prevention.
- No always-on wake-word listener or Gemini API calls; those remain separate work.
- Added voice conversion, silence, cancellation and Qt routing/permission tests.
