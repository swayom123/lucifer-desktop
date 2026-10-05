# Task lifecycle (Phase 2)

The orchestrator handles one root goal per call. It validates a flat plan of 1–32
tasks, persists children in one transaction, then runs ready children sequentially.
Dependency keys are resolved to persisted task IDs before execution. A child receives
its input and completed dependency outputs; it cannot invoke the tool registry.

| Current state | Allowed next states | Trigger |
| --- | --- | --- |
| `PENDING` | `READY`, `BLOCKED`, `CANCELLED` | Dependencies complete, fail, or goal is cancelled. |
| `READY` | `RUNNING`, `BLOCKED`, `CANCELLED` | Agent starts, route is unavailable, or goal is cancelled. |
| `RUNNING` | `READY`, `BLOCKED`, `FAILED`, `COMPLETED`, `CANCELLED` | Retry, stalled graph, exhausted attempts, verification success, or cancellation. |
| `WAITING_APPROVAL` | none | Reserved; no Phase 2 path enters it. |
| `BLOCKED` | none | Terminal until a later recovery design exists. |
| `FAILED` | none | Terminal. |
| `COMPLETED` | none | Terminal. |
| `CANCELLED` | none | Terminal. |

The root goal moves `PENDING → READY → RUNNING`, then reaches `COMPLETED` when
every child completes, `FAILED` if any child fails or planning fails, `BLOCKED`
if routing or dependencies block the graph, or `CANCELLED` on coroutine cancellation.

A child starts `PENDING`, becomes `READY` when all dependencies are `COMPLETED`,
then `RUNNING` for each attempt. A failed attempt returns it to `READY` and increments
`retries` only when another attempt is allowed. The agent's `max_attempts` includes
the first attempt and is limited to 1–10. An exception, timeout, or failed
verification exhausts the same retry budget. A failed or blocked prerequisite
marks its dependent `BLOCKED`; it is never run.

Status writes use an expected previous status so a stale worker cannot overwrite a
changed task. The scheduler is sequential in this phase. Restarting a process while
a goal is `RUNNING` requires manual recovery; automatic crash recovery and parallel
execution are later work. No agent or model provider is registered by default.
