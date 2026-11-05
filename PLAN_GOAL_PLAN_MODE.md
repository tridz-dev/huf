# Plan: Goal Mode & Plan Mode for Huf Agents

> **Scope:** exploration and planning only. No implementation code changes are included.
> **Worktree:** `/Users/safwan/Code/Huf/workspace/Tracks/GoalPlanMode/worktrees/huf` (branch `explore/goal-plan-mode`, isolated from `develop`).
> **Status:** reviewed and corrected against the codebase on this branch (see "Review Summary" at the end).

---

## 1. Objective

Add **Goal Mode** and **Plan Mode** to Huf Agents, matching the pattern used by modern coding-agent CLIs (Kimi `/goal`, Claude `--permission-mode plan`, Codex `/plan`, Cursor agent plans):

- **Goal Mode:** user sets a high-level objective for a conversation; the agent works autonomously across multiple turns/runs toward that objective, with pause/resume/complete lifecycle and optional budgets.
- **Plan Mode:** before autonomous execution, the agent proposes a step-by-step plan; the user approves, edits, or rejects it; approved plans execute incrementally with visibility and stop controls.

The implementation must reuse Huf’s existing **Agent Orchestration** infrastructure where possible and remain isolated from other benches/code/ports via the project worktree + `frappe-multihand` patterns.

---

## 2. Current State Analysis

### 2.1 Existing building blocks (verified against this worktree)

| Component | Location | Relevance |
|-----------|----------|-----------|
| `Agent` DocType | `huf/huf/doctype/agent/agent.json` | Has `enable_multi_run`, `default_plan` (Agent Orchestration Plan child table), `instructions`, `max_turns` (max LLM turns **within one run** — not a run budget), `allow_chat`, `run_immediately`, `allow_guest`, `allowed_users`/`allowed_roles`. |
| `Agent Chat` DocType | `huf/huf/doctype/agent_chat/` | Thin wrapper: `agent`, `conversation`, `chat_ui`. |
| `Agent Conversation` DocType | `huf/huf/doctype/agent_conversation/agent_conversation.json` | Session tracking: `title`, `summary`, `session_id`, `channel`, `is_active`, token/cost metrics, `conversation_data`. Permissions include Huf Manager / Huf User / Huf Viewer — use this as the template for new DocType permissions. |
| `Agent Message` DocType | `huf/huf/doctype/agent_message/agent_message.json` | Messages with `kind` (`Message/Tool Call/Tool Result/Status/Error/Image/Audio/Video`), `role`, `status`, `agent_run`, `tool_call`, `visibility` (`user_visible/model_visible/ui_only/audit_only/developer_only`), `record_kind`, `content_type`. |
| `Agent Run` DocType | `huf/huf/doctype/agent_run/agent_run.json` | Run lifecycle: `status`, `sequence`, `parent_run`, `is_child`, `agent_orchestration`, `run_kind`, `cost` + `cost_calculation_status`. |
| `Agent Orchestration` DocType | `huf/huf/doctype/agent_orchestration/agent_orchestration.json` | Plan execution: `status` (`Planned/Running/Paused/Completed/Failed/Cancelled`), `current_step`, `agent_orchestration_plan`, `scratchpad`, `parent_run`, `conversation`. **Permissions: System Manager only** (json lines 88–101). Controller `agent_orchestration.py` is an empty `Document` subclass. |
| `Agent Orchestration Plan` child table | `huf/huf/doctype/agent_orchestration_plan/agent_orchestration_plan.json` | `step_index`, `status` (`pending/in_progress/done/failed`), `instruction`, `output_ref`. |
| Planning module | `huf/ai/orchestration/planning.py` | `run_planning()` calls `run_agent_sync(..., now=True, channel_id="orchestration_planning")` with a text prompt; `parse_plan_steps()` (in orchestrator.py) is a fragile line-based numbered-list parser. |
| Orchestrator | `huf/ai/orchestration/orchestrator.py` | `create_orchestration` (line 10), `execute_next_step` (line 136), `parse_plan_steps` (line 98), `recreate_orchestration_plan` (line 72), `stop_orchestration` (line 119). |
| Scheduler | `huf/ai/orchestration/scheduler.py` | Minute-cron job `process_orchestrations()`. **It enqueues `execute_next_step` for orchestrations in BOTH `Planned` and `Running` status** (line 20: `filters={"status": ["in", ["Planned", "Running"]]]}`). |
| Multi-run integration | `huf/ai/agent_integration.py:1290-1313` | Inside `_execute_agent_run`: when `agent.enable_multi_run` is true, creates an orchestration and returns `mode: "multi_run"`. **Caveat:** this code runs inside the queued worker for queue-first runs — see 2.2 note below. |
| Queue-first execution | `huf/ai/agent_integration.py:1016` | `is_queued = not agent_doc.run_immediately and not now` — runs are queue-first by default; the HTTP caller gets `{"queued": True, ...}` and `_execute_agent_run` runs later in `_run_queued_agent` under a per-conversation Redis lock. |
| Chat API | `huf/ai/chat_api.py` | `run_agent_sync_chat` (`@frappe.whitelist(allow_guest=True)`) creates conversations and delegates to `run_agent_sync`; guest access is gated by `agent.allow_guest` + `_is_user_allowed`. |
| Frontend chat | `frontend/src/components/chat/` | `ChatWindowV2.tsx`, `ChatWindowHeader.tsx`, `ChatMessageList.tsx` + `chatMessageList.mappers.ts`, `ChatInput.tsx` (no slash-command parsing today), `useRunStatusPolling.ts`. Socket hook is `frontend/src/hooks/useChatSocket.tsx` (note **.tsx**), listening on `conversation:{id}` with typed events (`agent_run_status`, tool updates, new message, title updated). No plan/orchestration awareness anywhere in chat UI or `chatApi.ts`. |
| Hooks/scheduler | `huf/hooks.py:243-266` | Cron `*/1 * * * *` runs `huf.ai.orchestration.scheduler.process_orchestrations` **and** `huf.ai.agent_integration.recover_stalled_agent_runs` (lines 253–257). |

### 2.2 Gaps vs. Goal/Plan Mode

1. **No session-level goal artifact.** `Agent Conversation` has a title/summary but no explicit objective, lifecycle, or budget.
2. **No user approval gate — and the status enum cannot provide one as-is.** Two verified facts combine into the single biggest implementation risk:
   - `create_orchestration` sets `status = "Running"` immediately after insert (orchestrator.py:65); `Planned` is only a transient initial value that never persists.
   - The scheduler executes `Planned` orchestrations too (scheduler.py:20).
   So an orchestration created in `Planned` + `approval_status=pending` **would still be picked up and executed by the next minute-cron tick** unless the scheduler filter or the status model is changed. The approval gate must be enforced in the scheduler (see 5.4), not assumed from the `Planned` status.
3. **Queue-first hides the multi-run response.** The `mode: "multi_run"` payload at agent_integration.py:1307-1313 is only returned to the HTTP caller on the direct path (`now=true` or `agent.run_immediately`). On the default queued path the caller receives `{"queued": True}` and the orchestration is created later, invisibly, by the worker. Plan Mode UX therefore cannot rely on the run response to surface a proposal; it needs a dedicated synchronous `propose_plan` endpoint and/or socket events.
4. **Permissions gap.** `Agent Orchestration` grants rights to **System Manager only**. Chat users (Huf User / Huf Manager) cannot read, approve, or stop orchestrations — even `stop_orchestration` (orchestrator.py:124) fails its `has_permission("Agent Orchestration", "write")` check for them. Approval APIs must either extend the DocType permissions or perform server-side writes with explicit capability checks (`huf.permissions.has_capability`). A new `Agent Goal` DocType must copy the 4-role permission block from `Agent Conversation`.
5. **No plan UI in chat.** Plans live in the desk form for `Agent Orchestration`; chat users cannot see, edit, approve, or stop them. No `kind` values exist for plan/goal messages, and `chatMessageList.mappers.ts` has no mapping for them.
6. **No pause/resume/complete lifecycle.** `Paused` exists in the status enum but nothing sets it, and there is no resume API (only `stop_orchestration` → `Cancelled`, which is terminal). Step failure is also terminal: `execute_next_step` sets the whole orchestration to `Failed` on the first failed step with no retry path.
7. **No budget/limits.** Coding-agent goal modes expose run/token/time budgets to prevent runaway execution. (Note: `Agent.max_turns` limits LLM turns *within one run*; a goal budget is a cap on *runs/steps* — different concept, needs a different field name.)
8. **No realtime progress events for orchestrations.** Step execution publishes nothing to the `conversation:{id}` socket channel; today only `agent_run_status` lifecycle events exist. Step progress in chat requires new emit points.
9. **Stale-document enqueue risk.** The scheduler passes the already-fetched `orch` document object into `frappe.enqueue` (scheduler.py:54-60). `execute_next_step` then mutates and saves that possibly-stale doc, which can overwrite concurrent changes (e.g. a user approval/edit landing between scheduler tick and worker execution).
10. **Planning pollutes chat history.** `run_planning` goes through `run_agent_sync`, which persists the full planning prompt as a user message and the raw plan text as an agent message in the conversation. Without explicit `visibility`/`kind` handling, chat users will see the raw planning prompt inline.

---

## 3. Target UX

### 3.1 Goal Mode

1. In Agent Chat, the user can toggle a **“Goal”** mode or type `/goal <objective>`.
2. A new `Agent Goal` document is created and linked to the conversation.
3. The agent proposes an initial plan; once approved, it executes autonomously.
4. The chat header shows the goal, status badge, and controls: **Pause / Resume / Complete / Stop**.
5. Each completed step is rendered as a collapsible card in the message list.
6. If the goal is blocked, the agent asks the user a clarifying question and waits.

### 3.2 Plan Mode

1. When Plan Mode is enabled for an agent (or per-message with a `/plan` prefix), the agent first calls the planner.
2. The generated steps are rendered in chat as a numbered plan with **Approve**, **Edit**, **Regenerate**, and **Reject** actions.
3. On approve, the orchestration’s `approval_status` becomes `approved` and its `status` becomes `Running`; the scheduler starts executing **only then** (see 5.4 — scheduler must skip unapproved orchestrations).
4. On edit, the user can reorder/delete/rewrite steps before approval.
5. On reject, the agent falls back to normal single-turn chat.

---

## 4. Proposed Data Model

### 4.1 New DocType: `Agent Goal`

| Field | Type | Purpose |
|-------|------|---------|
| `name` | hash autoname | Unique goal ID. |
| `conversation` | Link → Agent Conversation | One active goal per conversation (enforce singly via `Agent Conversation.active_goal`). |
| `agent` | Link → Agent | Denormalized agent reference. |
| `objective` | Long Text | User-stated high-level goal. |
| `status` | Select: `active`, `paused`, `completed`, `failed`, `blocked` | Goal lifecycle. |
| `orchestration` | Link → Agent Orchestration | Active plan execution for this goal. |
| `max_runs` | Int | Budget: max agent runs/steps before pause. **Named `max_runs`, not `max_turns`** — `Agent.max_turns` already means LLM turns within a single run. |
| `max_cost` | Currency | Budget: estimated cost ceiling (sum of `Agent Run.cost` linked to the goal). |
| `time_limit_minutes` | Int | Budget: wall-clock limit. |
| `warn_only` | Check | If set, exceeding a budget emits a warning event instead of pausing (see Open Question 4). |
| `started_at`, `ended_at`, `last_activity_at` | Datetime | Lifecycle timestamps. |
| `completion_criterion` | Small Text | Optional explicit success condition. |
| `blocked_reason` | Small Text | Why the goal is blocked (user-facing). |
| `owner`, `modified_by` | Standard | Permissions follow conversation/agent rules. |

**Permissions:** copy the 4-role block from `agent_conversation.json` (System Manager + Huf Manager rwc, Huf User rwc, Huf Viewer read-only), so chat users can see their own goals without server-side elevation.

### 4.2 Extend `Agent Orchestration`

| Field | Type | Purpose |
|-------|------|---------|
| `goal` | Link → Agent Goal | Back-reference. |
| `approval_status` | Select: `pending`, `approved`, `rejected`, `revised` | Plan-approval state. **Default `approved` when created via the legacy `enable_multi_run` path** to preserve backward compatibility. |
| `proposed_by` | Link → User | Who generated the plan. |
| `approved_by` | Link → User | Who approved it. |
| `approved_at` | Datetime | Approval timestamp. |

**Permissions:** add Huf Manager (read/write) and Huf User (read, plus write-if-owner or via API) so the chat UI can render plans. Approval mutations still go through the whitelisted API, which re-checks identity/capability server-side — desk-level write access is not strictly required if the API uses controlled writes, but read access is required for list/rendering queries.

### 4.3 Extend `Agent Conversation`

| Field | Type | Purpose |
|-------|------|---------|
| `active_goal` | Link → Agent Goal | Currently active goal for this conversation. |
| `goal_mode_enabled` | Check | Whether this conversation is running in goal mode. |

### 4.4 Extend `Agent`

| Field | Type | Purpose |
|-------|------|---------|
| `plan_mode` | Select: `off`, `on_demand`, `always` | Agent-level default for plan approval behavior. Place near `enable_multi_run` in the `multi_run_setting_section`. |
| `goal_mode_default` | Check | Whether new chats with this agent start in goal mode. |
| `auto_approve_plan` | Check | Skip approval for trusted agents (dangerous; default off). |

### 4.5 Extend `Agent Run`

| Field | Type | Purpose |
|-------|------|---------|
| `goal` | Link → Agent Goal | So run counters and cost budgets can be computed with a simple `frappe.db.get_all("Agent Run", filters={"goal": ...})`. (Section 5.5 requires this link; it must exist in the data model.) |

### 4.6 Extend `Agent Message`

Add/select values (no new fields required, reuse existing `kind`/`visibility`):

- `kind`: add `Plan Step`, `Plan Proposal`, `Goal Status`, `Goal Blocked` (current options at agent_message.json: `Message/Tool Call/Tool Result/Status/Error/Image/Audio/Video`).
- Planning-internal messages (the raw planning prompt and raw LLM plan text) must be written with `visibility = "model_visible"` (or `audit_only`) so they never render in chat; only the curated `Plan Proposal` card is `user_visible`.

---

## 5. Backend Changes

### 5.1 Goal lifecycle API (`huf/ai/goal_api.py`)

New whitelisted methods (all must re-verify the caller has access to the underlying agent/conversation via `_is_user_allowed` / `huf.permissions.has_capability`, mirroring `run_agent_sync_chat`):

- `create_goal(agent_name, conversation_id, objective, **budgets)` → creates `Agent Goal` in `active`, sets `conversation.active_goal`.
- `get_goal(goal_name)` → goal + current orchestration + step statuses.
- `update_goal_status(goal_name, status, reason=None)` → pause/resume/complete/fail/block. Pause sets orchestration `status=Paused`; resume sets it back to `Running` (this API does not exist today — only terminal `stop_orchestration`).
- `set_goal_budgets(goal_name, max_runs=None, max_cost=None, time_limit_minutes=None)`.

### 5.2 Plan approval API (`huf/ai/plan_api.py`)

New whitelisted methods:

- `propose_plan(agent_name, conversation_id, objective, override_plan=None)` → **synchronous**: calls `run_planning` directly (or `run_agent_sync(..., now=True)`), builds the orchestration in `Planned` + `approval_status=pending`, and returns the steps in the HTTP response. Do **not** route this through the default queued path of `run_agent_sync`, or the chat client cannot render the proposal (see gap 2.2.3). Planning-internal messages must be persisted with non-user-visible `visibility` (see 4.6).
- `approve_plan(orchestration_id, revised_steps=None)` → sets `approval_status=approved`, `approved_by/at`, `status=Running`; if `revised_steps` provided, rebuild the plan child table. Must verify the caller is allowed to approve (owner of conversation / capability).
- `reject_plan(orchestration_id, reason=None)` → sets `approval_status=rejected`, `status=Cancelled`.
- `regenerate_plan(orchestration_id, updated_objective=None)` → re-runs `run_planning` and replaces the pending proposal; keep the previous plan rows on a superseded orchestration (`approval_status=revised`) for history.

### 5.3 Planner improvements (`huf/ai/orchestration/planning.py`)

- Add structured-output option (JSON) for reliable step parsing — `parse_plan_steps` (orchestrator.py:98-116) is a line-based heuristic that silently drops malformed steps; prefer `response_format`/JSON-schema output with the text parser as fallback.
- Support user-provided constraints/budgets in the planning prompt.
- Ensure the planning call’s messages are written with `visibility="model_visible"` so the raw `PLANNING_PROMPT` does not appear in chat (gap 2.2.10).

### 5.4 Orchestrator changes (`huf/ai/orchestration/orchestrator.py`)

- Refactor `create_orchestration` into two phases:
  1. `build_proposed_orchestration(..., approved=False)` — creates doc in `Planned` + `approval_status=pending`. The legacy `enable_multi_run` call site (agent_integration.py:1294) passes `approved=True` so existing agents keep auto-executing.
  2. `start_orchestration(orch_name)` — flips to `Running` (called by `approve_plan`).
- **Stop setting `status="Running"` unconditionally at orchestrator.py:65** — status must remain `Planned` until approval.
- Add `pause_orchestration` / `resume_orchestration` (resume = `Paused` → `Running`; the scheduler already skips `Paused` since it only selects `Planned`/`Running`).
- `execute_next_step` must **re-fetch the document by `orch_name`** instead of trusting the `orch` object pickled through `frappe.enqueue` (scheduler.py:58-59), and re-check `status`/`approval_status` after fetching, so approvals/edits landing between scheduler tick and worker execution are never overwritten and a just-paused orchestration is not advanced.
- Before executing each step, check linked goal budgets (runs used vs `max_runs`, summed `Agent Run.cost` vs `max_cost`, elapsed vs `time_limit_minutes`) and pause + emit event when exceeded. Note: `Agent Run.cost` may be pending (`cost_calculation_status`); treat unknown costs as 0 but do not block on them.
- On goal completion, update `Agent Goal.status = completed` and clear `Agent Conversation.active_goal`.
- On step failure, decide retry policy (today: terminal `Failed` on first failure — orchestrator.py:205-211); for goal mode, set goal `blocked` with `blocked_reason` instead of silently failing.
- Emit socket events on the `conversation:{id}` channel for `plan_proposed`, `step_completed`, `step_failed`, `goal_blocked`, `goal_completed` — reuse the `frappe.publish_realtime` pattern at agent_integration.py:459-468 so `useChatSocket.tsx` can route them.

### 5.5 Scheduler changes (`huf/ai/orchestration/scheduler.py`)

- **Approval gate (critical):** change the filter at scheduler.py:20 to exclude unapproved orchestrations — e.g. select `status == "Running"` only, plus `status == "Planned"` only when `approval_status == "approved"` (legacy rows created before this change have no `approval_status`; a patch or `or`-condition treating empty as approved preserves them).
- Stop passing the full `orch` document into `frappe.enqueue`; pass only `orch_name` (see 5.4).
- Keep the existing stuck-step timeout logic (scheduler.py:36-43) unchanged.

### 5.6 Integration with `run_agent_sync` (`huf/ai/agent_integration.py`)

- Add parameters: `goal_id`, `plan_mode` (and thread them through `run_agent_sync_chat` in `chat_api.py`, which currently forwards an explicit kwarg list).
- When `goal_id` is provided: verify the goal is `active`, increment goal run counters, link the `Agent Run` to the goal (new field, 4.5), check budgets before execution.
- Plan Mode entry should primarily live in the dedicated `propose_plan` endpoint (5.2), **not** as a branch inside the queued run path — inside the worker there is no HTTP caller to return `mode: "plan_proposal"` to.
- Keep existing `enable_multi_run` behavior backward-compatible: it creates orchestrations with `approval_status=approved` (auto-approved plan) so the new scheduler gate does not break current agents.
- Respect the documented constraint (AGENTS.md): direct `now=True` execution must never be invoked from code that may hold the per-conversation lock. Step execution and plan regeneration run in workers without holding the lock — keep it that way.

---

## 6. Frontend Changes

### 6.1 Chat header

- `ChatWindowHeader.tsx` shows active goal title/status badge and controls:
  - **Pause / Resume**, **Complete**, **Stop**.
- Add a **“Set Goal”** / **“New Goal”** button when no goal is active.

### 6.2 Plan proposal card

- New component `PlanProposalCard.tsx`:
  - Renders numbered steps.
  - Buttons: **Approve**, **Edit**, **Regenerate**, **Reject**.
  - Edit mode: inline drag/reorder/delete and text edits.
- Map to new `Agent Message` rows with `kind = "Plan Proposal"`. Register the new kinds in `chatMessageList.mappers.ts` (the kind→UI mapping point) so unknown kinds do not fall through to a broken/default rendering.

### 6.3 Goal/step progress

- New component `GoalProgressPanel.tsx`:
  - Collapsible sidebar or inline section showing current step, completed steps, and budget usage.
  - Render `Plan Step` messages with status icons (pending/done/failed).

### 6.4 Services

- `frontend/src/services/goalApi.ts`: `createGoal`, `getGoal`, `updateGoalStatus`, `setGoalBudgets`.
- `frontend/src/services/planApi.ts`: `proposePlan`, `approvePlan`, `rejectPlan`, `regeneratePlan`.
- Extend socket event types in `frontend/src/hooks/useChatSocket.tsx` (note: **.tsx**, not `.ts`) for `goal_blocked`, `plan_proposed`, `step_completed`, alongside the existing `agent_run_status` routing; keep `useRunStatusPolling.ts`-style polling as the fallback for clients without sockets.

### 6.5 Chat input

- `ChatInput.tsx` has no slash-command parsing today — add `/goal <objective>` and `/plan <objective>` prefix handling (strip prefix, call the goal/plan API instead of a plain `sendMessage`).
- Show a mode toggle when the agent has `goal_mode_default` or `plan_mode` enabled.
- Follow the AGENTS.md copy rule: user-facing strings must be plain product copy ("Set a goal", "Approve plan") with no Frappe/orchestration jargon.

---

## 7. Isolation & Testing Strategy

### 7.1 Code isolation

- All changes live in the dedicated worktree:
  `/Users/safwan/Code/Huf/workspace/Tracks/GoalPlanMode/worktrees/huf`
- Branch: `explore/goal-plan-mode`.
- No edits to the main `develop` checkout at `/Users/safwan/Code/Huf/huf`.

### 7.2 Runtime isolation (frappe-multihand)

When it is time to test/run, follow the `frappe-multihand` skill (v2.0) precisely:

1. Provision a disposable bench under a bench root, e.g. `${BENCH_ROOT}/huf-goal-plan-<unique>/`, with the track dir `/Users/safwan/Code/Huf/workspace/Tracks/GoalPlanMode/` and the existing worktree at `.../worktrees/huf`.
2. **Registry + lock:** allocate the port tuple and Redis DB indexes through the locked registry (`${BENCH_ROOT}/registry.json` + `.registry.lock`), checking both `benches[]` and `reserved_ports{}`. Reference bench occupies 8080/9000/6787/DB 0 — never touch it (hard-coded teardown guard).
3. **Bench app checkout:** the bench’s `apps/huf` must be a **separate `git clone --branch explore/goal-plan-mode` checkout** — never a symlink or bind-mount of the development worktree.
4. **Procfile port fix (classic footgun):** `bench set-config -g webserver_port N` does **not** update the Procfile’s literal `--port N`. Rewrite the Procfile port and confirm `web:`/`socketio:` lines match the registry allocation before `bench start`, or this bench will steal another bench’s port.
5. **Socket.io hosts fix:** add `127.0.0.1 <site_name>` to the container’s `/etc/hosts`, or all WebSocket connections fail auth — this breaks the chat UI and every socket event this feature depends on.
6. **Scheduler/queue isolation (extra relevant here):** this feature is driven by the `*/1` orchestration cron and RQ workers. Shared Redis queue DBs are not a hard isolation boundary — give this bench its own `redis_cache`/`redis_queue`/`redis_socketio` DB indexes, and `FLUSHDB` (never `FLUSHALL`) those indexes on teardown. Ideally run workers/scheduler only in this disposable bench while testing, never concurrently with another bench on the same queue DB.
7. Use a MariaDB database/user prefixed `huf_goal_plan_` with unique credentials.
8. Write `BENCH_IDENTITY.md` in the bench root; mark registry `ready` only after the `/api/method/ping` health check passes.
9. Teardown: `git worktree remove --force` for the managed worktree (never `rm -rf` a worktree path), drop DB/user, `FLUSHDB` the Redis indexes, archive the registry entry.

### 7.3 Test plan

| Test | Approach |
|------|----------|
| DocType creation/migration | `bench migrate` on disposable bench; verify `Agent Goal`, extended `Agent Orchestration`/`Agent Run`/`Agent Conversation`/`Agent`. |
| **Approval gate** | Create proposal → wait 2+ scheduler ticks → assert **no step executed** while `approval_status=pending`; approve → assert execution starts. This is the regression test for the scheduler.py:20 filter change. |
| Plan proposal API | Unit test via `bench execute huf.ai.plan_api.propose_plan` with a test agent; assert response contains steps and chat history has no user-visible planning prompt. |
| Approval flow | Create proposal → approve → assert `status=Running`, `approved_by/at` set; reject → assert `Cancelled`. |
| Goal lifecycle | Create goal → run steps → pause → assert scheduler skips → resume → complete; assert statuses and `active_goal` clearing. |
| Budget enforcement | Set `max_runs=2`; assert third run pauses the goal and emits `goal_blocked`. |
| Permissions | As a Huf User (non-System-Manager): read own goal, approve own plan, stop own orchestration; assert a different user cannot. |
| Backward compatibility | Existing `enable_multi_run` agents still auto-execute without approval (legacy path sets `approval_status=approved`), on both queued and `run_immediately` paths. |
| Stale-doc safety | Approve/edit a plan while a scheduler tick is in flight; assert the worker re-fetch does not overwrite the approval. |
| Frontend plan card | Manual browser verification in Agent Chat or Playwright e2e (requires the socket.io hosts fix, 7.2.5). |

---

## 8. Phased Rollout

### Phase 1 — Data model & API (no UI)
- Create `Agent Goal` DocType (with 4-role permissions).
- Extend `Agent Orchestration` (goal link, approval fields, permissions), `Agent Conversation`, `Agent Run` (goal link), `Agent`.
- Implement `goal_api.py` and `plan_api.py` with capability checks.
- Add backend tests.

### Phase 2 — Orchestrator integration
- Refactor `create_orchestration` for the two-phase approval flow.
- **Change the scheduler filter to enforce the approval gate** and stop pickling documents into `frappe.enqueue`.
- Add pause/resume, budget checks, and socket event emission.
- Integrate goal/plan params into `run_agent_sync` + `chat_api.py`.
- Verify backward compatibility with `enable_multi_run` (queued and direct paths).

### Phase 3 — Frontend
- Chat header goal controls.
- Plan proposal card + `chatMessageList.mappers.ts` kind mapping.
- Goal progress panel.
- `/goal` and `/plan` input prefixes in `ChatInput.tsx`.
- New socket event types in `useChatSocket.tsx`.

### Phase 4 — Isolated validation
- Provision disposable bench via `frappe-multihand` (section 7.2).
- Run full manual and automated tests, including the approval-gate regression test.
- Teardown bench (worktree removal via `git worktree remove`).

---

## 9. Open Questions / Decisions

1. **Should Goal Mode and Plan Mode be separate toggles or one combined mode?** (recommendation: separate but combinable — plan mode is an approval gate; goal mode is a session lifecycle).
2. **Should plan approval be required per conversation or per agent run?** (recommendation: per conversation goal, with agent-level default).
3. **Where do revised plans store history?** (recommendation: keep prior `Agent Orchestration` versions with `approval_status=revised` and link from goal).
4. **Should budgets be hard stops or warnings?** (recommendation: hard stop by default, with the `warn_only` flag on `Agent Goal` for power users).
5. **Do we need real-time socket events for plan step progress, or is the existing run-status polling enough?** (recommendation: add the new event types on the existing `conversation:{id}` channel; keep polling as fallback).
6. **Is a synchronous planning LLM call in the `propose_plan` HTTP request acceptable latency-wise?** (recommendation: yes for v1 — return a "planning…" state immediately via socket if needed; do not hide the proposal inside a queued run where the caller cannot see it).
7. **Step failure policy in goal mode: retry, skip, or block?** (recommendation: block the goal with a user-facing `blocked_reason` and let the user resume/skip — silent terminal `Failed` is a poor goal-mode UX).
8. **Who may approve a plan in shared/guest chats?** (recommendation: the conversation owner; guest sessions can approve only their own session’s plans, gated by the same `allow_guest` + `_is_user_allowed` checks used in `chat_api.py`).

---

## 10. Files to Touch (implementation checklist)

### New files
- `huf/huf/doctype/agent_goal/agent_goal.json`
- `huf/huf/doctype/agent_goal/agent_goal.py`
- `huf/ai/goal_api.py`
- `huf/ai/plan_api.py`
- `frontend/src/components/chat/PlanProposalCard.tsx`
- `frontend/src/components/chat/GoalProgressPanel.tsx`
- `frontend/src/services/goalApi.ts`
- `frontend/src/services/planApi.ts`

### Modified files
- `huf/huf/doctype/agent/agent.json` — add `plan_mode`, `goal_mode_default`, `auto_approve_plan` (in/near `multi_run_setting_section`).
- `huf/huf/doctype/agent/agent.py` — validation for new fields.
- `huf/huf/doctype/agent_orchestration/agent_orchestration.json` — add goal link + approval fields + Huf role permissions.
- `huf/huf/doctype/agent_conversation/agent_conversation.json` — add `active_goal`, `goal_mode_enabled`.
- `huf/huf/doctype/agent_run/agent_run.json` — add `goal` link.
- `huf/huf/doctype/agent_message/agent_message.json` — add `kind` options.
- `huf/ai/orchestration/planning.py` — structured proposal mode, visibility handling.
- `huf/ai/orchestration/orchestrator.py` — two-phase approval flow, pause/resume, budget checks, doc re-fetch, socket events.
- `huf/ai/orchestration/scheduler.py` — **approval-gate filter (critical)**, enqueue by name only.
- `huf/ai/agent_integration.py` — goal/plan integration, link runs to goals.
- `huf/ai/chat_api.py` — expose goal/plan params.
- `frontend/src/components/chat/ChatWindowHeader.tsx`
- `frontend/src/components/chat/ChatInput.tsx`
- `frontend/src/components/chat/ChatMessageList.tsx`
- `frontend/src/components/chat/chatMessageList.mappers.ts` — new kind mappings.
- `frontend/src/hooks/useChatSocket.tsx` — new event types (correct extension is `.tsx`).

---

## 11. Review Summary

This plan was verified against the actual code on branch `explore/goal-plan-mode` and corrected/extended as follows:

**Corrections (facts the original plan got wrong or stated imprecisely):**

1. **Scheduler executes `Planned` orchestrations.** The original plan said the scheduler enqueues steps "for Running orchestrations" and assumed a plan could safely sit in `Planned` until approval. In reality `scheduler.py:20` selects both `Planned` and `Running`, and `create_orchestration` (orchestrator.py:65) flips to `Running` immediately, so `Planned` never persists. Without an explicit scheduler change, the proposed approval gate would be bypassed by the next cron tick. This is now gap 2.2.2 and the critical scheduler change in 5.5, with a dedicated regression test in 7.3.
2. **`mode: "multi_run"` is not returned on the default path.** `run_agent_sync` is queue-first (agent_integration.py:1016); the multi-run branch at 1290-1313 executes inside the worker, so HTTP callers normally see only `{"queued": True}`. Consequence: plan proposals must be delivered via a synchronous `propose_plan` endpoint, not via the run response (now 2.2.3, 5.2, 5.6, and Open Question 6).
3. **Frontend file extension:** the socket hook is `frontend/src/hooks/useChatSocket.tsx`, not `.ts` (fixed in 6.4 and section 10). Also added `chatMessageList.mappers.ts` as the required kind-mapping touch point.

**Additions (gaps the original plan missed):**

4. **Permissions gap.** `Agent Orchestration` is System Manager-only (agent_orchestration.json), so chat users cannot read/approve/stop plans, and `stop_orchestration`’s own permission check fails for Huf Users. The plan now specifies permission changes for `Agent Orchestration`, a 4-role permission block for the new `Agent Goal` DocType (copied from `Agent Conversation`), and server-side capability checks in every new API (2.2.4, 4.1, 4.2, 5.1, 5.2).
5. **Stale-document enqueue risk.** The scheduler pickles the fetched `orch` document into `frappe.enqueue` (scheduler.py:58-59); `execute_next_step` must re-fetch by name and re-check status/approval to avoid overwriting concurrent approvals (2.2.9, 5.4, 5.5, plus a test in 7.3).
6. **Planning pollutes chat history.** `run_planning` persists the raw planning prompt and plan text as ordinary conversation messages; the plan now requires `visibility="model_visible"` for planning-internal messages (2.2.10, 4.6, 5.3).
7. **Budget field naming.** Renamed the goal budget `max_turns` → `max_runs` to avoid collision with the existing `Agent.max_turns` (LLM turns within one run) (2.2.7, 4.1).
8. **Missing `Agent Run.goal` link.** Section 5.5 of the original plan required linking runs to goals, but the data model had no such field; added in 4.5 so run/cost budgets are computable.
9. **Pause/resume and failure semantics.** Nothing sets `Paused` today and there is no resume API; step failure is terminal. Added explicit pause/resume APIs and a blocked-goal policy (2.2.6, 5.1, 5.4, Open Question 7).
10. **Realtime progress events.** Orchestration steps publish nothing today; added emit points on the existing `conversation:{id}` channel reusing the `agent_run_status` pattern (2.2.8, 5.4, 6.4).

**Sharpened isolation guidance (frappe-multihand v2.0):**

11. Section 7.2 now spells out the locked registry allocation, the separate branch checkout inside the bench (no symlink/bind-mount of the worktree), the Procfile `--port` literal fix, the socket.io `/etc/hosts` fix (without which the chat UI and all new socket events fail), scheduler/queue Redis isolation (directly relevant because this feature is cron+worker driven), `FLUSHDB`-only teardown, and `git worktree remove --force` for worktree cleanup.

**Testing:**

12. Section 7.3 gained regression tests for the approval gate, non-System-Manager permissions, queued/direct backward compatibility, and stale-doc safety — the four areas where this feature is most likely to break silently.
