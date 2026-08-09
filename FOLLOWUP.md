# Follow-up: real backend endpoint for chat tool-call approval

| Field | Value |
|---|---|
| Branch | `follow-up-tool-call-approval-api` |
| Branched from | `design-v3` @ `8f7fdcff` |
| Origin | [tridz-dev/huf#589](https://github.com/tridz-dev/huf/pull/589) (draft) — AppleQuietDesignSystem wave 8 |
| Track | `Tracks/AppleQuietDesignSystem` (this is a scoped-out follow-up of that track, not a separate track of its own) |
| Status | **Not started.** Branch exists with this doc; no implementation yet. UI-side Allow/Deny buttons already exist and currently only toast + `console.warn` — see below. |
| Merge target | `develop`, but only makes sense **after `design-v3`/PR #589 merges** — this branch's frontend diff (`tool.tsx`, `ChatMessage.tsx`) is `design-v3`'s tool-call rendering plus a real API call. Backend-only work (a new endpoint + `Agent Run` pause/resume mechanism) is independent of #589 and could in principle be built and merged first if useful, but the frontend half needs #589's UI to already exist, so land #589 before finishing/merging this branch's frontend side. |

## Why this exists

Wave 8 rewrote chat tool-call rendering (`frontend/src/components/ai-elements/tool.tsx`, `frontend/src/components/chat/ChatMessage.tsx`) to match the design spec's "needs approval" state: amber shield-lock icon, "needs approval" text, an "Allow" (filled) button and a "Deny" (outline) button, inline in the same 24px tool-call row. This UI is fully built and shipped in PR #589.

But there is **no backend endpoint** for a chat/agent-run tool call to actually pause and wait for a human decision. The `ExtendedToolState` type has an `approval-requested` state and the socket status mapping recognizes it, but nothing server-side ever produces it today — it's dead state in practice. The Allow/Deny buttons are wired to stub handlers:

```ts
// frontend/src/components/chat/ChatMessage.tsx (~line 93)
// TODO(tool-call-approval-api): there is no backend/socket endpoint yet to
// approve or deny a pending tool call (only flow-run-level approvals exist,
// see ApprovalsBell.tsx / flowApi.ts). These are UI-only stubs so the
// "approval-requested" state is visually complete; wire them to a real
// call/agent-run approve-deny endpoint once one exists.
```

## What already exists (don't rebuild, reuse the pattern)

- **A working analog already exists for Flows**, not chat: `huf/ai/flow_engine.py::_exec_human_approval` (~line 756) pauses a flow run at a human-approval node, and `huf/ai/flow_api.py::approve_flow_run`/`reject_flow_run` (~lines 275-330) resume it. `get_pending_approvals` (~line 1113) lists what's waiting. This is the closest prior art for "pause execution, wait for a human, resume" in this codebase — read it before designing the agent-run/tool-call version, since the resume/state-machine shape may transfer directly.
- **Tool-call plumbing already exists**: `huf/ai/agent_integration.py::process_tool_call` (~line 628) is where a tool call's lifecycle (pending → running → done/error) is already tracked server-side, keyed by `tool_call_id`/`agent_run_id`. An approval gate would most naturally slot in here, before a tool actually executes, not as a separate subsystem.
- **Frontend approval UI is fully built**: `tool.tsx`'s `ToolHeader` (single call) and `ToolGroup` (grouped calls) both already render the amber icon/text/Allow/Deny buttons for `state === "approval-requested"` — including a review-pass fix ensuring the disclosure chevron stays visible in this state so a reviewer can inspect the call's arguments before deciding. None of this needs to change; only the two handlers in `ChatMessage.tsx` (`handleToolCallApprove`/`handleToolCallDeny`) need to call a real API instead of stubbing.
- **Client-side duration/timing capture** (`chatMessageList.mappers.ts::computeToolTiming`) already exists from the same wave — not directly relevant here, but shows the mapper file where any new socket event handling for an approval-requested push would likely also need a case added.

## Design questions to resolve before implementing (not yet decided)

1. **Which tool calls require approval?** Presumably a subset marked sensitive (e.g. destructive actions, external sends) — check if `huf/ai/permissions.py` or a tool's own definition already has an `is_sensitive`/`requires_approval`-style flag, or if this needs to be added per-tool.
2. **How does the agent run actually pause?** The orchestrator (wherever `process_tool_call` is invoked from mid-run) needs to block/checkpoint execution until a decision arrives, then resume — mirroring `flow_engine.py`'s waiting-node pattern is the leading candidate, but agent runs and flow runs may have different execution models; verify before assuming they're the same.
3. **Push vs poll**: does the frontend learn about a pending approval via the existing chat socket (push), or does it need to poll a `get_pending_tool_approvals`-style endpoint like flows' `get_pending_approvals`? The socket already carries tool-call status updates, so push is likely simpler and more consistent — but confirm the socket's server-side emit path can be triggered from mid-tool-execution.

## Implementation checklist (not yet started)

- [ ] Read `flow_engine.py`'s human-approval node + `flow_api.py`'s approve/reject endpoints end-to-end as prior art.
- [ ] Decide and document answers to the 3 design questions above (as a short addendum to this file, before writing code).
- [ ] Backend: add an approve/deny endpoint (naming convention to match existing style, e.g. `huf/ai/agent_run_approval_api.py::approve_tool_call`/`deny_tool_call`) plus whatever pause/resume mechanism `process_tool_call`/the orchestrator needs.
- [ ] Backend: emit the `approval-requested` state over the existing chat socket when a gated tool call is reached, so the frontend's already-built UI actually activates.
- [ ] Frontend: replace the stub bodies of `handleToolCallApprove`/`handleToolCallDeny` in `ChatMessage.tsx` with real calls to the new endpoint, passing `tool_call_id`/`agent_run_id`. Remove the `TODO(tool-call-approval-api)` comment and the stub's `console.warn`/`toast.info` once wired.
- [ ] `tsc --noEmit` + `npm run build` clean, and a live end-to-end test: trigger a gated tool call, confirm Allow/Deny actually resumes/aborts the run.

## Context you'll need

- Design spec section 32 "Tool calls": `Tracks/AppleQuietDesignSystem/DesignSystem/huf-design/project/HUF UI System.dc.html` (search for `id="toolcalls"`).
- Full wave 8 writeup, including this gap and why it was scoped out: `Tracks/AppleQuietDesignSystem/CONTEXT.md`, wave 8 entry.
- PR #589 diff for the full tool-call rendering (single-call line, grouped "Ran N tools" line) this builds on top of.
