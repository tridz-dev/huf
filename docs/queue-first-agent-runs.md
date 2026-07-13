# Queue-first agent runs

Agent requests can contain long model calls and multiple tool calls. Running the whole turn in a Frappe web request consumes scarce web-worker capacity and makes bursts of normal API activity compete with long-lived LLM work.

This change introduces a queue-first policy: an agent is queued by default, and a carefully labelled advanced setting can retain direct execution where an existing trusted caller truly requires it. API callers will also be able to override the agent policy with `now`.

## Compatibility contract

Submission persists one `Agent Run` (status `Queued`, with the prompt stored on the run), enqueues a private worker for that exact run, and returns `agent_run_id`, `conversation_id`, `status: Queued`, and `queued: true`. The user message is **not** persisted at submission time (see ordering below). The worker creates exactly one user message for the run, executes that exact run, and updates its existing lifecycle states. It never creates a second run or user message.

`now=true` takes precedence over the Agent's **Run immediately (advanced)** setting; either one selects the direct path, which preserves the legacy behavior: the user message is persisted up front and the run executes inline.

## Run lifecycle event contract

The worker publishes `agent_run_status` events with `frappe.publish_realtime` on event `conversation:<conversation_id>`, targeted at the submitting user (Frappe carries `frappe.session.user` into the worker). Status values are the canonical `Agent Run` doctype spellings — `Queued`, `Started`, `Success`, `Failed` — matching the HTTP acknowledgement and the frontend `AgentRunStatusEvent` union:

```jsonc
{"type": "agent_run_status", "status": "Queued",  "agent_run_id": "...", "conversation_id": "...", "agent": "..."}
{"type": "agent_run_status", "status": "Started", "agent_run_id": "...", "conversation_id": "...", "agent": "..."}
{"type": "agent_run_status", "status": "Success", "agent_run_id": "...", "conversation_id": "...", "agent": "...",
 "response": "<final assistant text>", "agent_message_id": "<persisted Agent Message name>"}
{"type": "agent_run_status", "status": "Failed",  "agent_run_id": "...", "conversation_id": "...", "agent": "...",
 "error": "<error message>"}
```

Clients that cannot receive realtime events (guests, external API consumers) can poll `huf.ai.agent_integration.get_agent_run_status(agent_run_id)` (whitelisted, `allow_guest`; permissions mirror `run_agent_sync`). It returns `status` (canonical), `queued`, `response` (on Success), `error` (on Failed), `agent_message_id`, `conversation_id`, and `agent`. `huf.ai.chat_api.run_agent_sync_chat` accepts the same `now` override as `run_agent_sync`.

## Client behavior: React chat is queue-first by default

The React chat submits turns through the queue-first REST path (`new_conversation` / `send_message_to_conversation`) and reconciles the pending assistant turn from the lifecycle events above: it renders the accepted user text optimistically from the queued acknowledgement, keys the pending assistant bubble by `agent_run_id`, and fills it from the `Success` event's `response`/`agent_message_id` (or shows the `Failed` error). The Console page is an explicit direct-execution surface and always passes `now=true`.

SSE streaming (`POST /huf/stream/<agent>`) remains as the **explicit direct-execution mode**: the chat uses it only when the agent's **Run immediately (advanced)** policy is enabled and the stream endpoint is reachable. Worker-side token streaming for queued runs is a separate future effort, not part of this contract.

File and audio turns persist their user message in the prepare/transcribe step; those endpoints forward `skip_user_message` (and `files`) so the worker never creates a second user message and file content still reaches the run.

## Conversation ordering

Queueing changes an important assumption: two requests for the same conversation can be accepted before either worker begins. If both user messages were persisted at submission time, the first worker's history snapshot could observe (or trim) the second turn.

The implementation therefore persists the `Agent Run` immediately but appends the user `Agent Message` only after the queued worker acquires the conversation's execution slot:

- The worker locks with the cache `set nx ex` convention used by `huf/ai/knowledge/indexer.py` (`agent_run_conv_<conversation_id>`, TTL 600s). The lock serializes queued runs for one conversation without blocking other conversations.
- Under the lock, the worker verifies the run is still `Queued`, creates exactly one user message (guarded by an `Agent Message` lookup on `agent_run`), then loads history and executes. Because the lock is held, the trailing user message in history is guaranteed to be this run's own turn, so the original history semantics are restored.
- If the lock is busy, the worker re-enqueues itself (bounded attempts with a short delay) instead of dropping the turn; the lock TTL bounds a stuck worker.
- The lock is always released in a `finally` block.

The client renders the accepted user text optimistically from the queued acknowledgement, then reconciles from run lifecycle events. This serializes one conversation without reducing concurrency across different conversations.

## Rollout order

1. Extract run submission from run execution and add the worker entrypoint.
2. Add lifecycle event publication and run status/result access.
3. Update Console and React chat to consume queued acknowledgements and lifecycle events.
4. Convert schedules/triggers/integrations to submit work; retain direct execution inside flows, orchestration, and nested-agent workers until their suspend/resume contracts are implemented.
5. Enable queue-first defaults with focused test and capacity validation.

The detailed caller inventory, dependency map, and test matrix are maintained in the workspace execution track for the implementation effort.
