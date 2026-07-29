# Memory Policy: Capture Delegation (`capture_mode` + `learning_agent`)

Status: **implemented and live-tested** (background extraction job, enqueued on
run completion, verified end-to-end against a live bench with a real LLM call).

## Why this was pulled out of the base UI PR, then brought back

`Memory Policy.capture_mode` and `Memory Policy.learning_agent` exist as
doctype fields and were originally exposed in the policy edit form (Capture
Mode select: Manual / Agent Suggested / Automatic, plus a Learning Agent
picker). An audit of the runtime found **zero reads** of either field outside
the doctype and the seed data in `install.py` — choosing "Automatic" in the
UI silently behaved identically to "Manual". Shipping a control that looks
live but does nothing is worse than not shipping it, so both fields were
removed from the base UI PR. This follow-up PR wires them up for real and
re-adds them to the form.

## What this feature does

A memory policy previously only supported two capture paths, both driven by
explicit tool calls from the conversation's own agent:

- `save_memory_record` called manually by the user, or
- `save_memory_record` called by the agent mid-conversation (if
  `allow_agent_write` permits it).

`capture_mode` + `learning_agent` add a third path: **background extraction**,
where memory formation isn't bounded by the main agent's context window or
per-turn cost.

- **`capture_mode = "Manual"`**: unchanged — writes only happen via explicit
  tool calls.
- **`capture_mode = "Agent Suggested"`**: after a run completes, a background
  job reviews the transcript and proposes candidate memory records. These
  always land as `Draft`, regardless of `approval_required`, and need human
  approval before becoming active.
- **`capture_mode = "Automatic"`**: same background extraction, but records
  are subject to the policy's normal `approval_required` / `default_status`
  handling — no forced Draft.
- **`learning_agent`**: optional. The agent that runs the background
  extraction job. If unset, falls back to the conversation's own agent. This
  is what makes the feature "limitless" — a cheap, dedicated extraction agent
  can run over every conversation without the main agent's context or budget
  ever being touched.

## How it's implemented

1. `huf/ai/agent_integration.py`, in `run_agent_sync`: immediately after a run
   is marked `"status": "Success"`, `frappe.enqueue`s
   `huf.ai.memory_tools.extract_memory_from_run(run_id=...)`
   (`enqueue_after_commit=True`, `queue="default"`). This call is
   unconditional — it's always cheap to enqueue, because the job itself does
   all the gating.
2. `huf/ai/memory_tools.py`, `extract_memory_from_run(run_id)`:
   - Loads the run's agent and its Memory Policy. No-ops if there's no
     policy, the policy is disabled, or `capture_mode == "Manual"`.
   - Resolves the extraction agent: `policy.learning_agent` if set, else the
     run's own agent.
   - Builds a transcript from `ConversationManager.get_conversation_history`.
   - Calls `run_agent_sync(agent_name=extraction_agent, now=1,
     skip_user_message=True, response_format=<json schema>)` — synchronous
     (since we're already in a background job), and using
     `response_format` to get structured JSON back directly in
     `result["structured"]` rather than parsing free text.
   - For each candidate memory, calls the *existing* `save_memory_record`
     path — no new write path, no new permission model. All the
     write-permission and promotion enforcement already in
     `memory_tools.py` (`_can_write_memory`, `allowed_record_types`,
     `auto_promote_to_knowledge`, the promotion thresholds) applies
     unchanged. `Agent Suggested` forces `status="Draft"` before calling
     `save_memory_record`; `Automatic` passes `status="Active"` as a request
     only — `save_memory_record` already downgrades it to Draft internally
     if `policy.approval_required` is true.
3. Frontend: `capture_mode` + `learning_agent` are back in
   `MemoryPolicyFields.tsx` (Capture card), `memoryPolicyFormSchema.ts`,
   `MemoryPolicyFormPage.tsx` (form value mapping), and
   `memoryPolicyApi.ts` (list fields). The policy card in `MemoryPolicyList.tsx`
   now shows Capture Mode as a metadata badge.

## Live verification performed

Ran against a real bench (`memory-policy-test`, Gemini-backed `AI Provider`):
created a Memory Policy with `capture_mode: "Agent Suggested"`, ran a real
conversation ("My favorite programming language is Rust and I always deploy
on a Tuesday"), and confirmed:

- The extraction job was enqueued and executed (`Job OK` in `worker.log`).
- Two `Memory Record`s were created, `source_type: "Extracted"`,
  `status: "Draft"` (correct — Agent Suggested always forces Draft), with
  accurate, non-hallucinated summaries and sane confidence/importance scores.
- Test data cleaned up afterward.

## TODO: switch the Memory Policy form to tabs

Deliberately **not** part of this PR — filed here for the next one. The form
is now ~19 fields across 6 cards: Policy, Capture (now includes Capture Mode
+ Learning Agent), Retrieval, Write Permissions, Knowledge Projection,
Lifecycle. It's grown past the point a single scroll reads well, and once
Capture is likely to grow further (an extraction schedule, an
extraction-prompt editor), it becomes a surface of its own.

Proposed end state:

- **Policy** — name, enabled, agent, scope
- **Capture** — capture mode, learning agent, approval/default status,
  allowed record types
- **Retrieval** — inject mode, max records, token budget
- **Guardrails** — write permissions (rename from "Write Permissions"),
  knowledge projection, TTL

Reuse the existing tab-with-validation pattern from
`KnowledgeSourceFormPage.tsx` (`tabConfig` / `tabFieldMapping` /
`createFormSubmitHandler`) rather than inventing a new one.
