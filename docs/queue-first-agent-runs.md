# Queue-first agent runs

Agent requests can contain long model calls and multiple tool calls. Running the whole turn in a Frappe web request consumes scarce web-worker capacity and makes bursts of normal API activity compete with long-lived LLM work.

This change introduces a queue-first policy: an agent is queued by default, and a carefully labelled advanced setting can retain direct execution where an existing trusted caller truly requires it. API callers will also be able to override the agent policy with `now`.

## Compatibility contract

Submission persists one `Agent Run` (status `Queued`, with the prompt stored on the run), enqueues a drainer for the conversation, and returns `agent_run_id`, `conversation_id`, `status: Queued`, `queued: true`, and `sequence` (the per-conversation order of this run). The user message is **not** persisted at submission time (see ordering below). The worker creates exactly one user message for the run, executes that exact run, and updates its existing lifecycle states. It never creates a second run or user message.

`now=true` takes precedence over the Agent's **Run immediately (advanced)** setting; either one selects the direct path, which preserves the legacy behavior: the user message is persisted up front and the run executes inline.

## Run lifecycle event contract

The worker publishes `agent_run_status` events with `frappe.publish_realtime` on event `conversation:<conversation_id>`, targeted at the submitting user (Frappe carries `frappe.session.user` into the worker). Status values are the canonical `Agent Run` doctype spellings — `Queued`, `Started`, `Success`, `Failed` — matching the HTTP acknowledgement and the frontend `AgentRunStatusEvent` union:

```jsonc
{"type": "agent_run_status", "status": "Queued",  "agent_run_id": "...", "conversation_id": "...", "agent": "...", "sequence": 1}
{"type": "agent_run_status", "status": "Started", "agent_run_id": "...", "conversation_id": "...", "agent": "...", "sequence": 1}
{"type": "agent_run_status", "status": "Success", "agent_run_id": "...", "conversation_id": "...", "agent": "...", "sequence": 1,
 "response": "<final assistant text>", "agent_message_id": "<persisted Agent Message name>"}
{"type": "agent_run_status", "status": "Failed",  "agent_run_id": "...", "conversation_id": "...", "agent": "...", "sequence": 1,
 "error": "<error message>"}
```

Clients that cannot receive realtime events (guests, external API consumers) can poll `huf.ai.agent_integration.get_agent_run_status(agent_run_id)` (whitelisted, `allow_guest`; permissions mirror `run_agent_sync`). It returns `status` (canonical), `queued`, `response` (on Success), `error` (on Failed), `agent_message_id`, `conversation_id`, and `agent`. `huf.ai.chat_api.run_agent_sync_chat` accepts the same `now` override as `run_agent_sync`.

## Client behavior: React chat is queue-first by default

The React chat submits turns through the queue-first REST path (`new_conversation` / `send_message_to_conversation`) and reconciles the pending assistant turn from the lifecycle events above: it renders the accepted user text optimistically from the queued acknowledgement, keys the pending assistant bubble by `agent_run_id`, and fills it from the `Success` event's `response`/`agent_message_id` (or shows the `Failed` error). The Console page is an explicit direct-execution surface and always passes `now=true`.

SSE streaming (`POST /huf/stream/<agent>`) remains as the **explicit direct-execution mode**: the chat uses it only when the agent's **Run immediately (advanced)** policy is enabled and the stream endpoint is reachable. The policy is also **enforced server-side**: the stream renderer rejects agents without `run_immediately` with a single SSE `error` event, and refuses to stream into a conversation that has queued runs pending (same ordering rule as the direct REST path). Client-side gating alone is not sufficient — older builds or direct endpoint callers would otherwise bypass the queue. Worker-side token streaming for queued runs is a separate future effort, not part of this contract.

If the realtime socket misses a lifecycle event, the chat falls back to polling `get_agent_run_status` for runs stuck in `Queued`/`Started`, reconciling through the same state transitions as the socket events.

On conversation load (including page reload and switching back to a chat), the React client **hydrates** open runs from the `Agent Run` table (`Queued`/`Started` for that conversation), rebuilds pending user/assistant bubbles, and immediately calls `get_agent_run_status` once per open run so recovery does not depend on in-memory state or the socket grace period. User bubbles submitted in the current session are linked to `agent_run_id` so message merges do not drop them before the worker persists the user `Agent Message`. Streaming (`run_immediately`) uses the same hydration path for in-flight `Started` runs: the client recovers the **final** answer via status polling, not live token replay.

File and audio turns persist their user message in the prepare/transcribe step; those endpoints forward `skip_user_message` (and `files`) so the worker never creates a second user message and file content still reaches the run.

## Conversation ordering and strict FIFO

Queueing changes an important assumption: two requests for the same conversation can be accepted before either worker begins. If both user messages were persisted at submission time, the first worker's history snapshot could observe (or trim) the second turn. The implementation therefore persists the `Agent Run` immediately but appends the user `Agent Message` only after the queued worker holds the conversation's execution slot.

The ordering guarantee is enforced by a **DB-as-queue drainer** rather than by racing workers:

1. **Per-conversation sequence.** Each submission atomically claims the next sequence number for its conversation via Redis `INCR` (`agent_run_seq:<conversation_id>`). The sequence is stored on `Agent Run.sequence` and indexed together with `conversation` and `status` so the drain loop can select the oldest queued run in O(log n) time.
2. **Single-flight drain loop.** Submission enqueues one Frappe RQ job (`huf.ai.agent_integration._run_queued_agent`) per conversation. The first drainer to acquire the Redis lock `agent_run_conv_<conversation_id>` (set `nx`/`ex`, TTL 600s) becomes the sole executor for that conversation. It repeatedly selects the oldest `Queued` run (`ORDER BY sequence ASC, creation ASC`), executes it, and then selects again. Other would-be drainers see the lock is taken and exit immediately — no work is duplicated and no run is pushed to the back of the RQ queue.
3. **Heartbeat during execution.** A background thread refreshes the Redis lock TTL every three minutes while a run is inside `_execute_agent_run`, so long model calls cannot outlive the lock.
4. **Post-release sweeper.** After the last queued run is processed and the lock is released, the drainer checks once more for newly queued runs (submissions that arrived between the final `SELECT` and the `DELETE`). If any exist, it enqueues a follow-up drainer so nothing is orphaned.
5. **Direct path participates in the same lock discipline.** `now=true` or an agent's **Run immediately (advanced)** setting still uses the direct path, but it is rejected when any queued runs exist for that conversation, re-checks for queued runs **after** acquiring the `agent_run_conv_<conversation_id>` lock (closing the check-then-lock race), runs the same heartbeat as the drainer so a long direct run cannot outlive the lock TTL, and wakes a drainer on release if runs queued up meanwhile.
6. **Recovery scheduler.** `recover_stalled_agent_runs` runs every minute via `scheduler_events` in `huf/hooks.py`. For each conversation whose lock has disappeared (TTL check via `frappe.cache().ttl`) it resets **every** stale `Started` run back to `Queued` and enqueues one drainer, and wakes orphaned `Queued` runs that have no active lock, so crashed workers do not stall a conversation forever.
7. **No self-awaken via the direct path.** Sub-agent completion hooks enqueue the parent-conversation awaken **without** `now=1`: the worker finishing the sub-agent still holds the parent conversation lock, so a direct awaken would deadlock against it and be lost. The queued drainer and post-release sweeper deliver the awaken instead.

Because one drainer processes all queued runs for a conversation in strict sequence order, queued runs execute in submission order. The lock only coordinates the single active drainer; runs are not reordered by RQ queue races. Concurrency across different conversations is unchanged — each conversation has its own lock and its own sequence counter.

The client renders the accepted user text optimistically from the queued acknowledgement, then reconciles from run lifecycle events. Lifecycle events (`agent_run_status`) and the HTTP queued acknowledgement now include `sequence` so clients can detect gaps and order pending turns if they choose to.

## Rollout order

1. Extract run submission from run execution and add the worker entrypoint.
2. Add lifecycle event publication and run status/result access.
3. Update Console and React chat to consume queued acknowledgements and lifecycle events.
4. Convert schedules/triggers/integrations to submit work; retain direct execution inside flows, orchestration, and nested-agent workers until their suspend/resume contracts are implemented.
5. Enable queue-first defaults with focused test and capacity validation.

The detailed caller inventory, dependency map, and test matrix are maintained in the workspace execution track for the implementation effort.
