# [WIP] Goal Mode & Plan Mode for Huf Agents

> **Draft PR description.** Do not merge — implementation has not started.
>
> **Related design doc:** `docs/GOAL_PLAN_MODE.md`  
> **Related implementation plan:** `PLAN_GOAL_PLAN_MODE.md`

---

## Summary

Adds **Goal Mode** and **Plan Mode** to Agent Chat, enabling users to set high-level objectives and approve step-by-step execution plans before the agent runs autonomously.

- **Goal Mode** gives a conversation a persistent objective, lifecycle (`active` / `paused` / `completed` / `failed` / `blocked`), and optional budgets (`max_runs`, `max_cost`, `time_limit_minutes`).
- **Plan Mode** puts a human-in-the-loop approval gate in front of multi-step execution, similar to Kimi `/goal`, Claude plan mode, and Codex `/plan`.

The feature reuses and extends the existing `Agent Orchestration` infrastructure instead of replacing it.

---

## Motivation

Today Huf supports multi-step execution via the agent-wide `enable_multi_run` flag, but it auto-generates and auto-executes plans with no user approval and no session-level objective artifact. This PR introduces:

1. A user-visible **goal** tied to a conversation.
2. An explicit **plan proposal → approve → execute** flow.
3. Budget and lifecycle controls to prevent runaway autonomous execution.

---

## What changes

### New DocTypes

- `Agent Goal` — session-level objective, status, budgets, and orchestration link.

### Extended DocTypes

- `Agent` — adds `plan_mode`, `goal_mode_default`, `auto_approve_plan`.
- `Agent Orchestration` — adds `goal`, `approval_status`, `proposed_by`, `approved_by`, `approved_at`, and Huf role permissions.
- `Agent Conversation` — adds `active_goal`, `goal_mode_enabled`.
- `Agent Run` — adds `goal` link.
- `Agent Message` — adds `Plan Step`, `Plan Proposal`, `Goal Status`, `Goal Blocked` kinds.

### New backend modules

- `huf/ai/goal_api.py` — goal lifecycle and budget APIs.
- `huf/ai/plan_api.py` — plan proposal, approval, rejection, regeneration, pause/resume APIs.

### Modified backend modules

- `huf/ai/orchestration/planning.py` — structured proposal mode, non-user-visible planning messages.
- `huf/ai/orchestration/orchestrator.py` — two-phase approval flow, pause/resume, budget checks, re-fetch by name.
- `huf/ai/orchestration/scheduler.py` — approval-gate filter; enqueue by name only.
- `huf/ai/agent_integration.py` — link runs to goals, integrate plan mode.
- `huf/ai/chat_api.py` — expose goal/plan params.

### New frontend components

- `frontend/src/components/chat/GoalProgressPanel.tsx`
- `frontend/src/components/chat/PlanProposalCard.tsx`
- `frontend/src/services/goalApi.ts`
- `frontend/src/services/planApi.ts`

### Modified frontend components

- `frontend/src/components/chat/ChatWindowHeader.tsx`
- `frontend/src/components/chat/ChatInput.tsx`
- `frontend/src/components/chat/ChatMessageList.tsx`
- `frontend/src/components/chat/chatMessageList.mappers.ts`
- `frontend/src/hooks/useChatSocket.tsx`

---

## Critical implementation notes

1. **Scheduler approval gate.** The current scheduler (`huf/ai/orchestration/scheduler.py:20`) selects orchestrations in both `Planned` and `Running` status, so a pending-approval plan would be executed by the next cron tick. This PR changes the scheduler to skip orchestrations whose `approval_status != "approved"`.
2. **Queue-first behavior.** `run_agent_sync` is queue-first by default; plan proposals must be delivered via a synchronous `propose_plan` endpoint, not through the run response.
3. **Permissions.** `Agent Orchestration` is currently System Manager-only. This PR adds Huf Manager / Huf User / Huf Viewer permissions so chat users can read, approve, and stop their own plans.
4. **Stale-document safety.** The scheduler currently pickles the fetched orchestration document into the RQ job. This PR makes `execute_next_step` re-fetch by name and re-check status/approval before acting.

---

## Testing plan

- [ ] DocType migration succeeds on a disposable `frappe-multihand` bench.
- [ ] `propose_plan` returns a structured plan without creating a running orchestration.
- [ ] Approving a plan creates an orchestration and the scheduler executes steps.
- [ ] Rejecting a plan leaves no running orchestration.
- [ ] Huf User can approve/stop their own plan (permission test).
- [ ] `max_runs` budget pauses the goal after the limit.
- [ ] Existing `enable_multi_run` agents continue to auto-execute (backward compatibility).
- [ ] Frontend plan card renders and actions call the correct APIs.
- [ ] Realtime events (`plan_proposed`, `step_completed`, `goal_blocked`) flow to chat.

---

## Worktree / isolation

All code lives in the dedicated worktree:

```text
/Users/safwan/Code/Huf/workspace/Tracks/GoalPlanMode/worktrees/huf
Branch: explore/goal-plan-mode
```

Live validation uses a `frappe-multihand` disposable bench with unique ports and Redis DB indexes.

---

## Checklist before merge

- [ ] Implementation complete.
- [ ] Backend tests added/updated.
- [ ] Frontend tests or Playwright e2e added.
- [ ] Documentation updated (`docs/GOAL_PLAN_MODE.md`).
- [ ] `frappe-multihand` validation passed.
- [ ] Backward compatibility with `enable_multi_run` verified.
- [ ] Permissions verified for Huf User / Huf Manager / Huf Viewer.

---

*This is a work-in-progress draft. It will be converted to a real GitHub PR once implementation begins.*
