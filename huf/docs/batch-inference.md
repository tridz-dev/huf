# Batch inference

## What it is, and when to use it

Batch mode submits a scheduled agent run to a provider's batch API instead of
running it immediately in real time. Batch APIs (OpenAI, Anthropic) process
requests asynchronously — typically within the same day, not instantly — in
exchange for a significant discount versus the realtime API (roughly 50%
cheaper per provider pricing).

Use batch mode for schedule-driven, non-urgent agent runs where same-day
turnaround is acceptable: nightly digests, periodic report generation, bulk
classification jobs, or any recurring automation where nobody is waiting on
the response in real time. Do not use it for anything a user is waiting on
interactively — batch has no realtime path.

## How to enable it

On a **Schedule**-type **Automation Trigger**, set **Execution Mode** to
**Batch**. This is the live automation path (`huf/ai/automation_scheduler.py`)
and is the supported way to use batch mode going forward.

Batch mode is **not** available on the legacy **Agent Trigger** doctype's
schedule triggers by default — that legacy scheduler
(`huf/ai/agent_scheduler.py`) only submits batch jobs on a site that has
opted into legacy automation runtime mode via `automation_runtime_flag`
(see `huf/ai/automation_runtime_flag.py`). On a site running the new
automation runtime (the default), use Automation Trigger, not Agent Trigger,
for batch scheduling.

## Provider support

- **OpenAI** — fully wired, via LiteLLM's async batch primitives
  (`acreate_file` / `acreate_batch` / `aretrieve_batch` / `afile_content`).
- **Anthropic** — fully wired, via the direct Anthropic Python SDK's Message
  Batches API (`client.messages.batches`). This intentionally bypasses
  LiteLLM, since LiteLLM's Anthropic batch-create support was unconfirmed/
  mid-flight upstream at the time this was built.
- **Gemini / Google** — **not yet implemented.** A due Schedule+Batch trigger
  on a Google-backed agent fails the submission with a clear, logged error
  (`Batch Job` status is set to `Failed` with an explanatory
  `error_message`); it does not silently fall back to a realtime run. Do not
  advertise batch mode as available for Gemini agents.

## Known limitations and gaps

- **One request per batch job, currently.** Each scheduled trigger fire
  submits a batch of exactly one request. Batching multiple scheduled runs
  together into a single provider-side batch (to amortize further) is a
  planned future enhancement, not yet built.
- **Results are not written back into chat history.** When a batch job
  completes, its results are written into the `Batch Job` record's
  `result_summary` field only (a capped JSON blob: success/error counts plus
  a small sample of responses). They are **not** threaded back into the
  originating `Agent Conversation` / `Agent Message` records. Doing so
  requires understanding `agent_integration.py`'s conversation-lock model in
  more depth than the current implementation covers safely, and is an
  explicitly deferred follow-up.
- **Cost estimates are best-effort, not exact.** `estimated_cost` on a
  completed `Batch Job` is computed by summing token usage across successful
  results, running it through the existing realtime `calculate_cost()`
  helper, then halving it (batch pricing is assumed to be ~50% of realtime
  per provider docs). It is left unset when there's no model to price
  against or no usable usage data — never written as a misleading `0.0`.
- **Polling cadence.** A scheduled job (`huf.ai.batch_poll.poll_pending_batch_jobs`)
  polls every `Submitted` / `In Progress` `Batch Job` on a cron cadence
  (roughly every 15 minutes) and writes back status/results. Given batch SLAs
  are same-day rather than instant, this cadence is intentionally coarse.

## Where the code lives

| File | Purpose |
|---|---|
| `huf/huf/doctype/batch_job/batch_job.json`, `batch_job.py` | The `Batch Job` doctype: tracks provider, provider-side batch id, status, timestamps, result summary, estimated cost, and links back to the originating `Agent Trigger` or `Automation Trigger`. |
| `huf/ai/providers/batch/openai_batch.py` | OpenAI batch submit/poll/fetch via LiteLLM's async batch primitives; JSONL request building, status mapping, and custom_id-keyed result parsing. |
| `huf/ai/providers/batch/anthropic_batch.py` | Anthropic batch submit/poll/fetch via the direct Anthropic SDK's Message Batches API; same request/response shape as the OpenAI module. |
| `huf/ai/batch_poll.py` | The poll/writeback cron job (`poll_pending_batch_jobs`): polls every pending `Batch Job`, maps native provider status onto `Batch Job.status`, and on completion fetches results, builds the capped `result_summary`, and estimates cost. |
| `huf/ai/automation_scheduler.py` | Live automation scheduler. `_submit_batch_job_for_automation_trigger` submits a single-request batch job for a due Schedule+Batch `Automation Trigger`. |
| `huf/ai/agent_scheduler.py` | Legacy agent scheduler. `_submit_batch_job_for_trigger` is the equivalent for legacy `Agent Trigger` schedules, gated behind `automation_runtime_flag`. |
