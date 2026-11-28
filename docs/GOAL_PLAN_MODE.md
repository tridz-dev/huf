# Goal Mode & Plan Mode for Huf Agents

> **Status:** WIP / design draft. Implementation tracked by `PLAN_GOAL_PLAN_MODE.md` in the repository root.
>
> **Scope:** Adds session-level objectives and user-approved execution plans to Agent Chat, bringing Huf closer to the goal/plan UX of modern coding-agent CLIs (Kimi `/goal`, Claude `--permission-mode plan`, Codex `/plan`).

---

## 1. Why

Today, Huf agents are stateless per message. A user can ask a question and get an answer, but multi-step objectives require either:

- manually shepherding the agent turn-by-turn, or
- enabling the agent-wide `enable_multi_run` flag, which auto-generates and auto-executes a plan with no approval gate.

Goal Mode and Plan Mode close that gap:

- **Goal Mode** gives a conversation a persistent objective, lifecycle, and budgets so the agent can work autonomously across many runs.
- **Plan Mode** puts a human-in-the-loop approval gate in front of autonomous execution, matching Huf's existing control-room philosophy of *recorded, permissioned, auditable* agent actions.

---

## 2. Concepts

### 2.1 Goal Mode

A **Goal** is a high-level objective attached to an `Agent Conversation`.

```text
User: /goal reconcile all overdue invoices from last quarter
Agent: [creates goal] → [proposes plan] → [waits for approval]
User: Approve plan
Agent: [executes step 1] → [executes step 2] → … → [marks goal complete]
```

A goal has:

| Attribute | Purpose |
|-----------|---------|
| `objective` | The user-stated objective. |
| `status` | `active`, `paused`, `completed`, `failed`, `blocked`. |
| `orchestration` | The approved `Agent Orchestration` executing the plan. |
| `budgets` | `max_runs`, `max_cost`, `time_limit_minutes`. |
| `completion_criterion` | Optional explicit success condition. |

The chat header surfaces the goal status and controls: **Pause / Resume / Complete / Stop**.

### 2.2 Plan Mode

A **Plan** is a numbered list of steps generated from the objective. Plan Mode can be triggered per-message (`/plan …`) or enabled as an agent default (`Agent.plan_mode`).

Flow:

1. User sends a request while Plan Mode is active.
2. The agent calls the planner and renders a proposed plan in chat.
3. User chooses **Approve**, **Edit**, **Regenerate**, or **Reject**.
4. On approve, the plan becomes an `Agent Orchestration` and the scheduler executes it step-by-step.

---

## 3. User flows

### 3.1 Starting a goal from chat

```text
/goal Reconcile overdue invoices for Q2 and email the summary to finance
```

1. System creates an `Agent Goal` linked to the conversation.
2. System calls `propose_plan` synchronously.
3. A plan card appears in the message thread.
4. User approves the plan.
5. The scheduler executes steps; each completed step appears as a collapsible card.

### 3.2 Approving a plan

```text
/plan Create a weekly sales report from the Deals doctype
```

1. Plan card renders with steps.
2. User clicks **Approve** (or edits steps first).
3. System creates an `Agent Orchestration` in `Running` status.
4. Each step runs as an `Agent Run` with `run_kind = "orchestrator"`.

### 3.3 Goal lifecycle controls

| Control | Effect |
|---------|--------|
| **Pause** | Sets orchestration status to `Paused`; scheduler skips it. |
| **Resume** | Sets orchestration status back to `Running`. |
| **Complete** | Marks goal `completed` immediately, even if steps remain. |
| **Stop** | Cancels the orchestration (`Cancelled`). |

---

## 4. Data model

### 4.1 New DocType: `Agent Goal`

```json
{
  "name": "hash autoname",
  "conversation": "Link → Agent Conversation",
  "agent": "Link → Agent",
  "objective": "Long Text",
  "status": "Select: active | paused | completed | failed | blocked",
  "orchestration": "Link → Agent Orchestration",
  "max_runs": "Int",
  "max_cost": "Currency",
  "time_limit_minutes": "Int",
  "started_at": "Datetime",
  "ended_at": "Datetime",
  "last_activity_at": "Datetime",
  "completion_criterion": "Small Text",
  "blocked_reason": "Small Text"
}
```

Permissions mirror `Agent Conversation` (System Manager, Huf Manager, Huf User, Huf Viewer).

### 4.2 Extended DocTypes

| DocType | New fields |
|---------|------------|
| `Agent` | `plan_mode` (`off` / `on_demand` / `always`), `goal_mode_default`, `auto_approve_plan` |
| `Agent Conversation` | `active_goal`, `goal_mode_enabled` |
| `Agent Orchestration` | `goal`, `approval_status`, `proposed_by`, `approved_by`, `approved_at`, plus Huf role permissions |
| `Agent Run` | `goal` |
| `Agent Message` | New `kind` options: `Plan Step`, `Plan Proposal`, `Goal Status`, `Goal Blocked` |

---

## 5. Backend APIs

### 5.1 Goal API (`huf/ai/goal_api.py`)

```python
@frappe.whitelist()
def create_goal(agent_name, conversation_id, objective, max_runs=None, max_cost=None, time_limit_minutes=None)

@frappe.whitelist()
def get_goal(goal_name)

@frappe.whitelist()
def update_goal_status(goal_name, status, reason=None)

@frappe.whitelist()
def set_goal_budgets(goal_name, max_runs=None, max_cost=None, time_limit_minutes=None)
```

### 5.2 Plan API (`huf/ai/plan_api.py`)

```python
@frappe.whitelist()
def propose_plan(agent_name, conversation_id, objective, override_plan=None)

@frappe.whitelist()
def approve_plan(orchestration_id, revised_steps=None)

@frappe.whitelist()
def reject_plan(orchestration_id, reason=None)

@frappe.whitelist()
def regenerate_plan(orchestration_id, updated_objective=None)

@frappe.whitelist()
def pause_orchestration(orchestration_id)

@frappe.whitelist()
def resume_orchestration(orchestration_id)
```

### 5.3 Realtime events

Published on `conversation:{conversation_id}`:

| Event type | When |
|------------|------|
| `plan_proposed` | A plan is ready for approval. |
| `step_completed` | An orchestration step finishes. |
| `goal_blocked` | A budget is exhausted or a step failed. |
| `goal_status_changed` | Goal lifecycle changes. |

---

## 6. Frontend

### 6.1 New components

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `GoalProgressPanel` | `frontend/src/components/chat/GoalProgressPanel.tsx` | Header/sidebar goal status, budget bars, step list. |
| `PlanProposalCard` | `frontend/src/components/chat/PlanProposalCard.tsx` | Render proposed steps with approve/edit/regenerate/reject. |

### 6.2 Modified components

| Component | Change |
|-----------|--------|
| `ChatWindowHeader` | Add goal status badge and pause/resume/complete/stop controls. |
| `ChatInput` | Parse `/goal` and `/plan` prefixes; show mode toggle. |
| `ChatMessageList` | Listen for new goal/plan event types. |
| `chatMessageList.mappers.ts` | Map new `Agent Message` kinds to UI. |
| `useChatSocket.tsx` | Add handlers for `plan_proposed`, `step_completed`, `goal_blocked`, `goal_status_changed`. |

### 6.3 New services

- `frontend/src/services/goalApi.ts`
- `frontend/src/services/planApi.ts`

---

## 7. Isolation & testing

All development and validation happens in the dedicated worktree:

```text
/Users/safwan/Code/Huf/workspace/Tracks/GoalPlanMode/worktrees/huf
```

For live testing, use `frappe-multihand` to provision a disposable bench with:

- unique ports (webserver, socketio, file watcher)
- unique Redis DB indexes for cache/queue/socketio
- a separate branch checkout in `apps/huf` (not a symlink to the worktree)
- `BENCH_IDENTITY.md` and a locked registry entry

See `PLAN_GOAL_PLAN_MODE.md` §7 for the full provisioning checklist.

---

## 8. Open questions

1. Should Goal Mode and Plan Mode be separate toggles or one combined mode? (Current design: separate but combinable.)
2. Should budgets be hard stops or warnings? (Current design: hard stops by default, optional `warn_only`.)
3. How many retries should a failed step get before the goal is marked `blocked`?
4. Should plan proposals be cached/reused across conversations for the same agent?

---

*This document is a WIP draft and will evolve as implementation progresses.*
