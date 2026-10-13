# ACP Client: Huf Drives Coding Agents

Status: proposal, no code written yet.

## What

Plan for Huf acting as an **ACP (Agent Client Protocol) client** — the side of the
protocol that spawns and drives coding-agent CLIs (Kimi CLI, OpenCode, Gemini CLI,
Claude Code via a community adapter, Codex via `@zed-industries/codex-acp`) over
JSON-RPC 2.0 on stdio, with bidirectional session/update streaming and the agent
calling back into the client for file I/O, terminal access, and permission prompts.

This is the inverse direction of the PR #661 work, which
is Huf exposing itself / talking HTTP to other Huf instances. That proposal's real-ACP
stubs (`AgentCommunicationProtocolAdapter`, `AgentClientProtocolAdapter`) are
`NotImplementedError` placeholders for a JSON-RPC-over-stdio transport — this proposal is
the design for what actually goes in that gap, but scoped as "Huf drives an external
coding agent," not "Huf and another Huf federate."

## Goal

Decide and document how Huf's server side (Frappe/WSGI) and Huf's desktop side
(Electron `desktop-poc`) each become an ACP client capable of holding open a
bidirectional stdio session with a coding-agent subprocess, including the hardest
unsolved piece: what happens when the agent calls `session/request_permission` and the
human who needs to approve it is not currently looking at a screen.

This document is a plan for the user to approve before implementation starts. The
phased build-out follows below; the section above is the architecture and decision
record.

## Source

- RFC: `docs/rfcs/huf-remote-agent-federation.md` (in the `huf` repo, on the PR #661
  branches) — see doctypes below.
- `huf/ai/voice/sidecar/app.py` — closest existing architectural precedent (separate
  ASGI process pattern).
- `huf/ai/flow_engine.py` — closest existing human-in-the-loop precedent.
- `desktop-poc/src/main/process-manager.ts`, `permission-gate.ts` — closest existing
  local-subprocess and approval-gate precedent.
- `desktop-poc/PLAN.md` — Phase 5 "HUF Executor Protocol" sketch.
- No code in this proposal yet.

## 1. Problem statement

Frappe/Huf's request-handling core is synchronous WSGI: a gunicorn worker handles one
HTTP request, runs a handler, returns, and is free again. ACP needs the opposite shape
— a long-lived child process, spoken to over stdio with JSON-RPC 2.0, where the agent
is not just answering the client's calls but **calling back into the client** mid-run
for `fs/read_text_file`, `fs/write_text_file`, `terminal/create`, and
`session/request_permission`. That is a duplex, stateful, long-held connection to a
subprocess — nothing a WSGI worker can hold without blocking that worker for the
run's entire duration.

Huf has three existing patterns for "work that outlives a single request," and none
of them fit ACP's shape as-is:

1. **Flow Engine's durable state machine** (`huf/ai/flow_engine.py`). `run_flow()`
   (line 366) loops over node executions; `_persist_context` (line 171) commits a
   context blob to the `Flow Run` doctype after each node. State lives entirely in the
   doc (`current_node_id`, a `waiting` JSON blob, `hop_count`). `resume_flow_run()`
   (line 422) and `approve_flow_run()` (line 481) reload the doc, rebuild context, and
   re-enter `run_flow()`. This is re-entrant and durable, but it never holds a live
   process or connection open between steps — it is fundamentally request-scoped,
   stitched together by doc state. An ACP session is the opposite: the value of
   keeping the subprocess alive is that its in-memory state (loaded files, model
   context, partial edits) does not need to round-trip through a doc.

2. **The voice sidecar's separate-ASGI-process pattern** (`huf/ai/voice/sidecar/app.py`).
   The docstring (lines 1-16) is explicit that "WSGI cannot hold a long-lived duplex
   WebSocket" and that the duplex leg has to live outside gunicorn, in a standalone
   FastAPI/uvicorn process. This is the right *shape* — a separate process that can
   hold open bidirectional connections without consuming a WSGI worker — but the wrong
   *mechanism*: it bridges **two WebSockets** (browser and voice provider) via
   `asyncio.create_task`, using Redis for session handoff (`litellm_realtime.py`
   writes a 300s-TTL stash to `frappe.cache()` key
   `huf:voice:realtime:session:{session_id}`; `app.py:175` reads the stash by
   session_id on WebSocket connect). It does not own or spawn a **child subprocess**
   at all — both endpoints of the bridge are things it *connects to*, not things it
   *starts*. ACP needs the sidecar to additionally become a process supervisor
   (`spawn`, own the child's stdin/stdout, frame JSON-RPC messages, route calls both
   directions) — a materially different job than bridging two sockets. Also worth
   noting: `send_to_session` mid-call is unimplemented (`NotImplementedError`) in both
   of the sidecar's existing engines, so even the "push a message into an open
   session" primitive doesn't fully exist yet in this codebase.

3. **RQ background jobs** (`frappe.enqueue`, used extensively — `agent_integration.py`
   10+ sites, `flow_api.py:547`, `gateway_service.py:627,739`). All fire-and-forget:
   the job runs once and the worker is free again. `meeting_transcription.py:43-45`
   already has a comment flagging RQ workers as a scarce resource, explicitly avoiding
   enqueuing anything that would "tie up an RQ worker thread for the whole
   [duration]." An ACP session that stays open for an entire agent coding run (minutes
   to tens of minutes, waiting on permission prompts) is exactly the kind of
   long-held-worker job the team is already wary of. RQ is the wrong tool for holding
   the subprocess.

**Conclusion:** the voice sidecar is the closest template — a standalone
ASGI/asyncio process outside gunicorn is the right place to own a long-lived duplex
connection — but the actual mechanism (owning a child subprocess, framing JSON-RPC
over its stdio, dispatching bidirectional calls) has no precedent in this codebase and
must be built new. `run_agent_stream` (`agent_integration.py:2845`) is Huf's current
closest thing to "streaming," but it's an async generator scoped to one SSE HTTP
request, not a persistent session object — also not reusable as-is.

## 2. Doctypes

The RFC (`docs/rfcs/huf-remote-agent-federation.md`) already specs four doctypes for
remote-agent federation. Two of them anticipate almost exactly what ACP needs:

- **Remote Agent Connection** (§5.1) already has a `stdio_command` field (Small Text)
  alongside `transport` (`http|websocket|stdio`) and `protocol_type` (which already
  includes the enum value `agent_client_protocol`). This field exists specifically to
  anticipate a local stdio coding agent — it was speced for exactly this proposal's
  use case, just never implemented.
- **Delegated Agent Run** (§5.3) has `remote_session_id` ("if stateful") — the closest
  existing field to an ACP `sessionId` — and a `needs_approval` status value in its
  9-state lifecycle, which is the natural landing spot for a paused
  `session/request_permission` call.
- **Remote Agent Capability** (§5.2) has `stateful`, `long_running`, and
  `supports_streaming` Check fields — these map directly onto ACP agent capabilities
  and likely need no changes, just population from the agent's ACP `initialize`
  response instead of a manifest fetch.
- **Remote Agent Policy** (§5.4) has `requires_human_approval` (Check, default 0,
  "Halts execution until a local user approves the action") — this maps directly onto
  the offline-approval problem in §3 below. Recommend reusing it as the policy toggle
  that decides whether ACP permission prompts require a human at all versus an
  auto-approve/auto-deny default.

**Recommendation: extend, do not fork.** The doctype *shapes* are reusable almost
as-is. Do not invent a parallel set of ACP-specific doctypes. This same doctype layer
(Remote Agent Connection, Delegated Agent Run, Remote Agent Capability, Remote Agent Policy)
is also relevant to the companion "Huf as an MCP provider" proposal, which flags in its own
§9c whether to share or keep separate the connection-registry / policy doctype layer — read
both tracks' open decisions together before deciding on any doctype shape changes.

**Explicit caveat — the shape is reusable, the execution model is not.** RFC §4.2
states plainly that V1 "defers real-time WebSocket/SSE streaming infrastructure" in
favor of "cursor-based polling with synchronous fallback." The event model in §7 (9
lifecycle events: `run.started`, `message.delta`, `message.completed`, `tool.started`,
`tool.completed`, `approval.required`, `run.completed`, `run.failed`, `run.cancelled`)
was designed around a client polling `event_cursor` on `Delegated Agent Run`, not
around a server holding a push channel open. ACP's `session/update` notifications are
inherently push-based — the agent decides when to emit them, over the same open
stdio connection, and Huf must forward them to whatever is watching (desk UI,
desktop app) without the watcher polling for them. The doctype rows can still be the
system of record (what a `Delegated Agent Run` looked like at any point), but the
mechanism that populates them in real time must be rebuilt: something in the sidecar
process pushes updates out (likely via `frappe.publish_realtime`, matching the
pattern in item 5 below) at the same time it persists them to the doc. This is new
work, not a config change to the existing polling loop.

## 3. Client-side callback methods and the offline-approval problem

Huf, as the ACP client, must implement the client-side JSON-RPC methods the agent
calls: `fs/read_text_file`, `fs/write_text_file`, `terminal/create` /
`terminal/output` / `terminal/wait_for_exit` / `terminal/kill` /
`terminal/release`, and `session/request_permission`. The file and terminal methods
are mechanical (implement against whatever workspace the run is scoped to — see the
open decision below). `session/request_permission` is not mechanical: it is Huf's
only real point of novelty in this whole proposal.

**The offline-user problem.** Huf's only existing human-in-the-loop precedent is Flow
Engine's approval node: `_exec_human_approval` (`flow_engine.py:1099`) sets
`Flow Run.status = "Waiting Approval"`, persists a `waiting` JSON blob (approval_type,
approver_role/approver_users, title, instructions, context_summary), and calls
`_send_approval_notifications` (`flow_engine.py:1813`) — a Frappe Notification Log
plus email, resolved via Has Role → User lookups. Resumption happens through
`approve_flow_run(flow_run_name, decision, comment)` (`flow_engine.py:481`), which is
whitelisted, checks `_verify_approval_permission`, and re-enters `run_flow()`.

This precedent is durable and offline-safe — the approver can respond hours later —
but it works by **parking a state machine** (a doc row plus a notification), not by
keeping anything alive. `run_flow()` has already returned; there is nothing to keep
open. There is no generic "Approval Request" doctype in Huf; this Flow Run
status/waiting pair plus Notification Log is the only production primitive.

ACP's `session/request_permission` is fundamentally different: it is a synchronous-ish
JSON-RPC call over an **already-open connection**, and the agent process is sitting
there (with its own memory, open file handles, partial state) waiting for the
response. If the human is offline, Huf cannot simply "return later" the way
`approve_flow_run` does — something has to decide what happens to the live subprocess
in the meantime. Nothing in Huf today parks a *live subprocess* waiting on human
input; only a state machine between re-entrant invocations. This is new work with no
template. Candidate approaches, to be decided by the user before implementation:

- **(a) Hold the subprocess open with a bounded timeout.** Keep stdio open, send the
  Notification Log/email, and either poll or wait on the reply; if no answer arrives
  within N minutes, deny by default (fail closed) or cancel the run. Simple, matches
  Flow Engine's notification mechanism for the "tell the human" half, but ties up a
  sidecar-process slot (not a WSGI worker, but still a resource) for the whole wait,
  and does not scale if many runs are simultaneously waiting on approval.
- **(b) Checkpoint/suspend if the target CLI supports it.** If the underlying agent
  process can be told to serialize its state and exit (or if the OS-level process can
  be frozen — e.g. `SIGSTOP`/cgroup freeze) then resumed later, Huf could tear down
  the subprocess while waiting and respawn/resume it once approved. Frees resources
  during the wait but depends entirely on features the target agent CLIs may not
  actually offer today (needs verification per agent — Kimi CLI, OpenCode, Gemini CLI
  — before assuming this is viable for any of them).
- **(c) Accept a hard timeout and fail the run.** Simplest possible policy: no
  approval within N minutes (Remote Agent Policy's `max_timeout_seconds`, already
  speced, default 120s — almost certainly too short for a human-approval wait and
  would need a distinct, longer timeout field) means the run fails outright and the
  human has to re-trigger it. Least engineering, worst UX for anything but
  fast-response teams.

This proposal recommends (a) as the default — it directly reuses the Flow Engine
notification mechanism and requires no new capability from target agent CLIs — but
this is presented as a recommendation for the user to confirm, not a decision already
made (see open decisions, item c).

**Workspace/filesystem decision point.** `fs/read_text_file` and `fs/write_text_file`
need a real filesystem to operate against. What is that filesystem for a server-side
(sidecar-hosted) agent run? Two candidate models, not silently resolved:

- **A Huf-managed scratch git checkout per Delegated Agent Run.** Clone/checkout on
  run start, operate in an ephemeral directory, optionally push/PR the result on
  completion, tear down after. Clean isolation, no cross-run state leakage, but
  repeated clone cost and no continuity between runs on the same project (an agent
  starting a new run has to re-orient from scratch every time).
- **A persistent per-project workspace doctype** (a `Remote Agent Workspace` or
  similar, holding a durable on-disk checkout, one per Huf project/repo). Reused
  across runs, avoids repeated clone cost, gives the agent continuity, but needs
  explicit concurrency control (two runs against the same workspace at once) and a
  cleanup/retention story that scratch checkouts don't need.

This decision has no research answer in this pass — it needs the user's call before
Phase 2 of the plan (§6) can be scoped concretely.

## 4. Per-agent onboarding

Once the ACP client core exists (JSON-RPC framing, method dispatch, the permission
and file/terminal callback implementations), adding a new agent is mostly the spawn
command plus environment/auth, not new client logic:

- `kimi acp` — native ACP, no adapter.
- `opencode acp` — native ACP, no adapter.
- `gemini --acp` — native ACP, no adapter.
- `npx @agentclientprotocol/claude-agent-acp` — community adapter wrapping Claude
  Code; not an official Anthropic package, external dependency risk.
- `@zed-industries/codex-acp` — community adapter wrapping Codex.

This section is deliberately short. It is not where the risk in this proposal lives —
the risk is entirely in the client-core work in §1-§3.

## 5. The frontend/desktop angle

The desktop app (`desktop-poc`) is a **genuinely different deployment shape**, not a
variant of the server-side sidecar case, and should not be treated as an
afterthought.

- `desktop-poc/src/main/process-manager.ts` already spawns real subprocesses —
  `import { spawn, ChildProcess } from 'child_process'`, deliberately `shell: true`
  (the file's own comment: the security boundary is the approval gate, not shell
  escaping — "trusted local dev tool"). `streamOutput()` pipes stdout/stderr to the
  renderer via `win.webContents.send`; `activeProcesses` is a
  `Map<string, ChildProcess>` used for cancellation. This is ~80% of the LOCAL
  mechanics ACP needs on the desktop side.
- `desktop-poc/src/main/permission-gate.ts` already provides a 4-mode gate — `full`
  (always allowed), `sandbox` (process/pty kinds throw outright; file ops are
  separately confined in `workspace.ts`), `ask` (approval every time), `auto`
  (approval once per session per `${workspacePath}:${kind}` key, in-memory `Set`, not
  persisted) — behind a single choke point,
  `ensureExecutionAllowed(win, workspacePath, kind, description, details)`, called
  from `process-manager.ts` and `pty-manager.ts` before spawning, driving a real
  `ApprovalDialog` over an IPC round trip. This is a natural, already-built home for
  `session/request_permission` — the desktop app does not need to invent an approval
  UI, only route ACP's permission request through the gate that already exists.
- **What's still missing, even on desktop:** JSON-RPC framing/dispatch over the
  child's stdio. Today's `process-manager.ts` is raw stdout/stderr streaming,
  one-directional and output-only — there is no message framing, no request/response
  correlation, and no path for the subprocess to call back into the client. This is a
  real extension of `process-manager.ts`, not just wiring two existing pieces
  together.
- **The key asymmetry versus the server-side case:** the desktop path has **no
  worker-model problem at all**. The Electron main process can hold a subprocess open
  natively for as long as it wants — there is no WSGI constraint, no gunicorn worker
  being tied up, no need for a separate sidecar process. The entire problem described
  in §1 (why none of Huf's three existing patterns fit) simply does not apply to
  desktop.

**Recommended sequencing: desktop-side ACP client first, server-side sidecar
second.** Justification: the desktop gap is materially smaller (extend
`process-manager.ts`'s framing; the approval UI and subprocess spawning already
exist) and requires no new process/worker architecture. The server-side sidecar
requires building the child-process-owning mechanism from scratch (no precedent, per
§1) *and* solving the offline-approval-with-live-process problem from §3, which has
no clean answer yet. Proving the ACP client core on desktop first — where the
approval UI is already live and a human is, by construction, sitting at the machine
— de-risks the harder server-side work by validating the JSON-RPC framing and method
dispatch logic in the easier environment before it has to also solve offline
approval and process supervision.

**Open, not assumed:** `desktop-poc/PLAN.md`'s own Phase 5, "HUF Executor Protocol"
(`register_desktop_executor` / `request_desktop_execution` via
`frappe.publish_realtime` to a `desktop:{executor_id}` room / `report_desktop_result`)
is sketched in that plan but was explicitly not built —
the desktop-poc local-execution work states "this
proposal only builds the local execution plane; wiring it to HUF's agent tool-call loop
is a follow-up." Whether wiring desktop-side ACP results back into Huf's `Agent Run`
audit trail should reuse that Phase 5 sketch, or be designed fresh for ACP
specifically, is an open decision (§7c is the closest existing analogue — flagged
here, not resolved).

## 6. Phased plan

See the phased plan below for the full breakdown with relative sizing and
dependency edges. Summary: desktop-side ACP client core and permission-gate wiring
come first (small-to-medium, no new server architecture needed); server-side sidecar
process-supervision and offline-approval handling come second and are larger,
building on lessons from the desktop phase; doctype extension (Delegated Agent Run /
Remote Agent Capability / Remote Agent Policy) and per-agent onboarding can happen in
parallel with either once the client core's shape is settled.

## 7. Open decisions for the user

These are asked, not resolved, in this document:

- **(a) Which agent(s) to support first?** Recommendation: Kimi CLI and/or OpenCode
  first — both speak ACP natively, no adapter dependency. Claude Code (via
  `@agentclientprotocol/claude-agent-acp`, a community adapter, not an official
  Anthropic package) as a later addition once the client core is proven, given the
  extra external-dependency risk. Confirm or override.
- **(b) Desktop-first vs. server-first vs. parallel?** §5 recommends desktop-first.
  Present as a recommendation to confirm, not a decision already made.
- **(c) Default offline-permission-prompt policy?** §3 lists three candidates (bounded
  timeout with notification / checkpoint-suspend if the CLI supports it / hard
  timeout and fail). Recommendation is (a) (bounded timeout), but needs explicit
  sign-off since it directly shapes the sidecar's resource model.
- **(d) Confirm extending (not forking) the PR #661 doctype shapes.** §2 recommends
  extending Remote Agent Connection, Delegated Agent Run, Remote Agent Capability, and
  Remote Agent Policy rather than inventing parallel ACP-specific doctypes. Confirm this
  shape-reuse approach before any doctype changes land, since PR #661 is still an open
  DRAFT with unresolved issues (see Risks below) — changes here would land on top of an
  unmerged, security-flagged branch. Also reconcile with the companion "Huf as an MCP provider" proposal's
  own doctype-sharing decision (§9c there) — the connection-registry / policy layer may
  be shared across both tracks or kept separate, decided together, not siloed.

## Risks

**The #661 bug class — mandatory reading before any new whitelisted doc method.**
PR #661 has an unresolved CRITICAL security finding: a read-only Huf
User can exfiltrate a stored `auth_secret` via whitelisted doc methods
(`test_connection`, `refresh_manifest`) that trust client-supplied doc state instead
of checking permission against the actual stored record, and that bypass `validate()`
entirely. Any new whitelisted doc method this proposal adds — on `Delegated Agent Run`
or any doctype it touches — **must**:

1. Check write-permission explicitly as the first line of the method, not rely on
   DocType-level read/write defaults.
2. Never trust a client-supplied doc payload for anything security-relevant —
   re-read the record from the database inside the method.
3. Never let a manually-triggered method bypass `validate()`.

Name this pattern "the #661 bug class" in code review for this proposal so reviewers
recognize it on sight.

**Dead precedent to avoid: `huf/ai/tools/gateway_pairing_tools.py`.** This proposal will add whitelisted doc methods for offline-approval handling and permission gating. Do NOT model new whitelisted methods on `gateway_pairing_tools.py` — it has no `@frappe.whitelist()` decorators and unconditionally uses `ignore_permissions=True` on every write, making it a concrete instance of the #661 bug class. See the companion "Huf as an MCP provider" proposal for the full detail and the correct template to follow instead (`gateway_service.approve_gateway_pairing`).

**Other risks:**
- The offline-approval mechanism (§3) is genuinely unsolved design, not an
  implementation detail — do not let an implementer silently pick one of the three
  candidate approaches without the user's sign-off (§7c).
- The community ACP adapters (Claude Code, Codex) are external dependencies Huf does
  not control; their protocol-compliance and maintenance status should be spot-checked
  before committing to them as anything more than a later addition.
- RFC §4.2's polling-based event model is a known mismatch for ACP's push model (§2);
  underestimating this rebuild is the most likely way this proposal's estimate goes
  wrong.

## Before implementation starts

1. Read this document in full, including the phased plan below.
2. Read the PR #661 write-up in full — the doctype recommendations here depend on
   that work's current (unmerged, draft) state.
3. Get the user's answers to the open decisions below before starting implementation.
4. Any implementation must treat PR #661's security finding as a blocking precedent,
   not a separate concern — see Risks above.

---

## Phased plan

Sizing is relative (small/medium/large), not
time-estimated — this codebase has no reliable basis for time estimates on unbuilt
protocol work. Dependency edges are explicit: "blocks" means the target phase cannot
start in any real sense until the source phase's core interface is settled, not that
every line must be merged first.

Sequencing follows the recommendation above: desktop first, server second,
because desktop has no worker-model problem and ~80% of its local mechanics
(`process-manager.ts`, `permission-gate.ts`) already exist.

## Phase 0 — Decisions (blocks everything)

Size: small (no code; a decision record).

Get explicit user answers to the open decisions above (a-d) before any other phase starts:
agent(s) to support first, desktop-first vs. server-first vs. parallel, default
offline-permission policy, fork-vs-reuse for the the PR #661 work doctypes. Phase 1 in
particular is blocked on (a) — you need to know which agent's ACP wire behavior to
prototype against.

## Phase 1 — Desktop ACP client core

Size: medium. Depends on: Phase 0.

- Extend `desktop-poc/src/main/process-manager.ts` (or a new sibling module,
  `acp-client.ts`, spawned alongside it) with JSON-RPC 2.0 framing over the child's
  stdio: message parsing/serialization, request/response correlation by id, and
  notification dispatch (`session/update` and friends) distinct from request/response.
  Today's `process-manager.ts` is raw stdout/stderr streaming only — this is new
  code, not a wiring change.
- Implement the ACP `initialize` handshake and capability negotiation against one
  agent (whichever Phase 0 picked — likely `kimi acp` or `opencode acp`, native ACP,
  no adapter).
- Implement the client-side methods the agent calls back into:
  `fs/read_text_file`, `fs/write_text_file` (scoped to the existing
  `desktop-poc` workspace model — reuse `workspace.ts`'s path confinement, do not
  invent a new one), `terminal/create`/`terminal/output`/`terminal/wait_for_exit`/
  `terminal/kill`/`terminal/release` (can likely reuse or extend `pty-manager.ts`).
- Route `session/request_permission` through the existing
  `ensureExecutionAllowed` choke point in `permission-gate.ts`, extending its 4-mode
  gate (`full`/`sandbox`/`ask`/`auto`) to cover ACP permission requests as a new
  `kind`, reusing the existing `ApprovalDialog` IPC round trip rather than building a
  new approval UI.

Exit criterion: a real ACP agent process, spawned from the desktop app, can complete
one full coding task end to end — read a file, propose an edit, get a live approval
click, write the file, run a terminal command, report completion — with no server-side
component involved at all.

## Phase 2 — Desktop UX surface

Size: small-to-medium. Depends on: Phase 1.

- Session UI: something in `desktop-poc`'s renderer to start an ACP session, show
  streamed `session/update` events (message deltas, tool calls) — likely extending
  the existing `ExecutionPanel`/`TerminalPanel` side-drawer pattern noted in
  `DesktopToolAccess/CONTEXT.md` rather than building new panel chrome.
- Session lifecycle controls: cancel, and resuming a session if the agent process
  supports it.

Exit criterion: a user can drive a full ACP coding session from the desktop app UI
without touching the preload API directly (today's only reachable surface, per
`DesktopToolAccess/CONTEXT.md`'s known gaps).

## Phase 3 — Server-side sidecar: process supervision

Size: large. Depends on: Phase 0; benefits from (but is not strictly blocked by)
Phase 1's proven JSON-RPC framing code, which should be extracted into a
transport-agnostic module reusable from both the Electron main process and the
Python/asyncio sidecar if the framing logic is ported rather than reimplemented from
scratch in Python.

- Extend `huf/ai/voice/sidecar/app.py` (or a new sibling ASGI app under
  `huf/ai/*/sidecar/`) to spawn and own a child subprocess per `Delegated Agent Run`
  — `asyncio.create_subprocess_exec`, own its stdin/stdout, frame JSON-RPC over it.
  This is new capability; the existing sidecar only bridges two WebSockets it
  connects to (`app.py:175`'s Redis-stash-driven bridge), it does not spawn anything.
- Implement the same client-side methods as Phase 1
  (`fs/*`, `terminal/*`) but scoped to whichever workspace model Phase 0 /
  §3's open decision lands on (scratch git checkout per run, or a
  persistent per-project workspace doctype) — this decision must be made before this
  phase can be scoped precisely; do not default silently.
- Decide and implement the push mechanism for forwarding `session/update` events to
  watchers (desk UI, or a status page) — likely `frappe.publish_realtime`, matching
  the pattern already sketched (unbuilt) in `desktop-poc/PLAN.md` Phase 5, while also
  persisting each event onto the `Delegated Agent Run` doc so the RFC's existing
  polling fallback keeps working for anything not listening live.

Exit criterion: a `Delegated Agent Run` triggered from Huf can drive a real ACP agent
subprocess end to end when the approving human is present and responsive (no offline
gap yet — that's Phase 4).

## Phase 4 — Offline-approval handling

Size: large, and the highest-uncertainty phase in this plan. Depends on: Phase 3;
blocked on Phase 0(c)'s policy decision.

- Implement whichever of §3's three candidate approaches Phase 0 chose
  as the default (bounded timeout + notification is the recommendation, reusing the
  Flow Engine notification mechanism — `_send_approval_notifications`,
  `flow_engine.py:1813` — for the "tell the human" half).
- If checkpoint/suspend is chosen instead, first spike whether any Phase-0-selected
  agent CLI actually supports it — this is a research spike before it is an
  implementation task, since nothing gathered so far confirms any target CLI has
  this capability.
- Wire the resolution path: however the human responds (new endpoint, or reuse
  `approve_flow_run`'s pattern adapted for `Delegated Agent Run`), it must apply the
  "#661 bug class" checks from the Risks section (explicit write-permission
  check first, re-read from DB, no `validate()` bypass) since this is exactly the
  shape of whitelisted doc method that produced that bug on `Remote Agent Connection`.

Exit criterion: a `Delegated Agent Run` that hits `session/request_permission` while
its approver is offline behaves according to the chosen policy without leaking
resources (a stuck subprocess, an orphaned sidecar slot) indefinitely.

## Phase 5 — Doctype extension

Size: small-to-medium. Depends on: Phase 0(d); can run in parallel with Phases 1-2
once decided, must land before Phase 3 needs real doc rows.

- Extend (not fork) `Remote Agent Connection`, `Delegated Agent Run`, `Remote Agent Capability`,
  `Remote Agent Policy` per §2 — populate `stdio_command`,
  `remote_session_id`, `stateful`/`long_running`/`supports_streaming`, and reuse
  `requires_human_approval` for the Phase 4 policy toggle. Add whatever new field(s)
  Phase 4 needs (e.g. a longer approval-specific timeout distinct from
  `max_timeout_seconds`, which the RFC defaults to 120s — too short for a
  human-approval wait). §2 recommends reuse/extend to avoid parallel
  doctype layers — confirm this before landing any changes.
- This work depends on the PR #661 work PR #661's current DRAFT state — read that
  proposal's write-up before touching these doctypes, since the RFC doctypes do not
  exist in `develop` yet, only on the PR #661 branches. Also coordinate with
  the companion "Huf as an MCP provider" proposal on whether the connection-registry / policy doctype
  layer is shared or kept separate (their open decision §9c) — decide together, not
  siloed.

## Phase 6 — Per-agent onboarding (remaining agents)

Size: small per agent. Depends on: Phase 1 (desktop) or Phase 3 (server), whichever
core landed first.

- Per §4, mostly spawn-command and env/auth wiring once the core exists:
  `opencode acp`, `gemini --acp`, `npx @agentclientprotocol/claude-agent-acp` (Claude
  Code, community adapter), `@zed-industries/codex-acp` (Codex, community adapter).
  Not a source of architectural risk — sequence opportunistically alongside other
  phases.

## Dependency summary

```
Phase 0 (decisions)
  |-- blocks --> Phase 1 (desktop ACP client core)
  |                  |-- blocks --> Phase 2 (desktop UX)
  |                  |-- feeds (framing code) --> Phase 3
  |-- blocks --> Phase 3 (server sidecar process supervision)
  |                  |-- blocks --> Phase 4 (offline-approval handling)
  |-- blocks --> Phase 5 (doctype extension) --> feeds Phase 3 and Phase 4
  |-- blocks --> Phase 6 (remaining agent onboarding), also depends on Phase 1 or 3
```
