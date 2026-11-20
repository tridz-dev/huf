# Shared Approval Primitive Proposal

This proposal suggests a single Huf approval primitive that any feature can use to ask a user for a decision or follow-up information. Today, approvals are split across code execution, SSH execution, flow nodes, and a few feature-specific one-off review paths. That works, but it makes every new feature invent its own waiting state, notification path, UI, and audit model.

## Problem

Huf already has real approval flows, but they are feature-shaped rather than platform-shaped:

- Code execution and SSH execution create `Agent Execution Approval` rows when `Execution Profile.approval_mode` is `Ask Every Time` (`huf/ai/tools/code_execution.py:608`, `huf/ai/tools/ssh_execution.py:345`).
- Flow nodes use `human.approval` and pause a `Flow Run`, storing waiting state directly on the run and sending notifications from the flow engine (`huf/ai/flow_engine.py:708`, `huf/ai/flow_api.py:955`).
- The current UI surface is split between the flow approval bell, the flow run viewer, the flow sidebar configuration, and execution-profile settings (`frontend/src/components/ApprovalsBell.tsx:13`, `frontend/src/components/FlowRunViewer.tsx:15`, `frontend/src/components/RightSidebar.tsx:751`, `frontend/src/pages/ExecutionProfileFormPage.tsx:268`).

The result is that Huf can already ask a user for approval, but it cannot yet ask in one uniform way.

## What exists today

### Agent and chat runs

Agent/chat runs can pause when a tool call needs approval, but that pause is tied to the tool execution path, not to a generic approval primitive. The agent run itself is not a standalone approval object. The current pause state is represented by the parked execution plus the linked approval row.

### Flow approvals

Flow approvals are closer to a first-class approval experience. They already have:

- waiting state
- approver targeting by role or user
- notification fan-out
- a visible inbox-like bell popover
- approve/reject action buttons in the run viewer

But they are still specific to flows.

### Other approval-like paths

Huf also has feature-specific approval or gating patterns elsewhere, for example:

- model catalog proposal approval in `huf.ai.hub_api`
- gateway sender pairing approval in `huf.ai.gateway_service`
- execution-policy approval in `Execution Profile`

Those are useful precedents, but they are not yet one shared system.

## Proposed solution

Create a shared `Approval Request` primitive that becomes the common way for Huf features to request a user decision.

### Core shape

The primitive should support:

- a request kind, such as `approval`, `info_request`, or `acknowledgement`
- a subject reference to the thing being acted on
- a target reference back to the owning feature
- one or more assignees
- status, expiry, and decision metadata
- optional decision notes or follow-up text
- a notification hook that can fan out to bell, email, and future channels

### Behavior

When a feature needs input from a human:

1. It creates an `Approval Request`.
2. Huf routes notifications through a common delivery layer.
3. The user sees the request in one inbox surface.
4. The user can approve, reject, or send a clarification response.
5. Huf hands the result back to the owning feature through the target reference.

The owning feature still owns its own business logic. The approval primitive only standardizes the waiting and decision contract.

## Why this direction

### 1. It removes duplicated approval logic

Today each subsystem owns its own version of “wait for human input.” That means repeated state handling, permission checks, notification code, and UI paths. A shared primitive moves that into one place.

### 2. It makes future features easier to ship

If agent runs, flows, apps, gateways, and model-management flows all need user approval, Huf should not make each feature invent its own inbox. A common primitive lets future features plug into the same medium.

### 3. It gives Huf one approval UX

The current bell popover works for flow approvals, but it is not designed as a platform-wide inbox. A shared primitive makes it possible to have one approvals page or panel that lists everything requiring attention.

### 4. It better matches Huf’s platform story

Huf already positions itself as an AI control plane with auditability, permissions, and tool execution. A shared approval primitive fits that story better than feature-local waiting states.

## Suggested UX direction

Keep the current flow approval bell as the first surface, but evolve it into a true `Approvals` inbox:

- a unified list of pending approvals
- filters by feature type, assignee, and status
- a detail drawer with context, decision controls, and comments
- deep links back to the owning feature

That lets the UX grow from “flow approvals only” into “Huf asks you something.”

## Migration path

This should be additive, not a rewrite:

1. Add the shared primitive.
2. Introduce adapters for current flow approvals and execution approvals.
3. Keep existing feature-specific paths working while the new inbox grows.
4. Migrate new features to the primitive first.
5. Backfill older features only when there is no behavior risk.

## Out of scope for the first PR

- Rewriting all existing approval flows
- Removing `Agent Execution Approval`
- Rebuilding every current approval UI at once
- Designing notification delivery for every external channel immediately

The first step should prove the contract, not finish the whole migration.

## Open questions

- Should the primitive live as a new DocType, or start as a service layer over existing records?
- Should `info_request` and `approval` share the same record type?
- Should the inbox be global from day one, or ship first as a flows-plus-executions view?
- Which channel should be the canonical “source of truth” for notifications: bell, email, or the record itself?

## Recommendation

Move toward a shared approval primitive now, but keep it thin and additive. Huf already has the right ingredients for approval workflows; the missing piece is a platform-level contract that makes approvals reusable across agents, flows, apps, and future Huf surfaces.
