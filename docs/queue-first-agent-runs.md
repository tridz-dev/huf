# Queue-first agent runs (implementation plan)

Agent requests can contain long model calls and multiple tool calls. Running the whole turn in a Frappe web request consumes scarce web-worker capacity and makes bursts of normal API activity compete with long-lived LLM work.

This change introduces a queue-first policy: an agent is queued by default, and a carefully labelled advanced setting can retain direct execution where an existing trusted caller truly requires it. API callers will also be able to override the agent policy with `now`.

## Compatibility contract

Submission must create one `Agent Run` and its user message, enqueue the work immediately, and return `agent_run_id`, `conversation_id`, `status: Queued`, and `queued: true`. The worker must execute that exact run and update its existing lifecycle states. It must not create a second run or user message.

`now=true` takes precedence over the Agent's **Run immediately (advanced)** setting. Direct streaming remains available as an explicit compatibility path while the client migrates to run lifecycle events.

## Conversation ordering

Queueing changes an important assumption: two requests for the same conversation can be accepted before either worker begins. A worker-only lock is not enough if both user messages were already persisted, because the first worker can observe the second turn.

The implementation therefore persists the `Agent Run` immediately but appends the user `Agent Message` only after the queued worker acquires the conversation's execution slot. The client renders the accepted user text optimistically from the queued acknowledgement, then reconciles from run lifecycle events. This serializes one conversation without reducing concurrency across different conversations.

## Rollout order

1. Extract run submission from run execution and add the worker entrypoint.
2. Add lifecycle event publication and run status/result access.
3. Update Console and React chat to consume queued acknowledgements and lifecycle events.
4. Convert schedules/triggers/integrations to submit work; retain direct execution inside flows, orchestration, and nested-agent workers until their suspend/resume contracts are implemented.
5. Enable queue-first defaults with focused test and capacity validation.

The detailed caller inventory, dependency map, and test matrix are maintained in the workspace execution track for the implementation effort.
