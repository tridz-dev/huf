# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Batch Job poller (Phase 3).

Periodically polls provider-side status for every `Batch Job` that is
`Submitted` or `In Progress`, maps the provider's native status onto
`Batch Job.status`, and, once a job completes, fetches results and writes a
minimal, capped summary into `result_summary`.

Conversation writeback: once a job completes, its per-request results are
also written into a brand-new `Agent Conversation` (one `Agent Message` per
result), so a user can find batch output the same place they'd look for any
other agent output. This is intentionally minimal: it does NOT create an
`Agent Run` record for these messages, so a batch result thread does not have
the queue-first bookkeeping (Agent Run status/lifecycle) that a real,
interactively-run agent conversation gets -- it is readable message history
only, not a full replica of a live chat run. This writeback never calls
`run_agent_sync`/`run_automation` and never touches the conversation lock (see
`agent_integration.py`'s `_conversation_lock_key`); it only inserts plain
Document records, so it carries none of the deadlock risk that path has. It
is best-effort and wrapped in its own try/except so a failure here never
prevents `result_summary`/`estimated_cost`/`completed_at` from being saved.
"""

from uuid import uuid4

import frappe
from frappe.utils import now_datetime

from huf.ai.agent_integration import _run_async_safely
from huf.ai.cost_calculator import calculate_cost

_RESULT_SAMPLE_SIZE = 5

_TERMINAL_NO_RESULTS_STATUSES = {"Failed", "Cancelled", "Expired"}

_BATCH_DISCOUNT_FACTOR = 0.5


def _get_provider_module(provider: str):
	"""Return (poll_batch, fetch_results, status_map) for a Batch Job's provider.

	Returns None for providers with no recognized batch poll support -- this
	guards defensively so an unexpected/future provider row can't crash the
	poll loop.
	"""
	if provider == "Gemini":
		from huf.ai.providers.batch.gemini_batch import (
			_GEMINI_STATE_TO_BATCH_JOB_STATUS,
			fetch_results,
			poll_batch,
		)

		return poll_batch, fetch_results, _GEMINI_STATE_TO_BATCH_JOB_STATUS
	if provider == "OpenAI":
		from huf.ai.providers.batch.openai_batch import (
			_OPENAI_STATUS_TO_BATCH_JOB_STATUS,
			fetch_results,
			poll_batch,
		)

		return poll_batch, fetch_results, _OPENAI_STATUS_TO_BATCH_JOB_STATUS
	if provider == "Anthropic":
		from huf.ai.providers.batch.anthropic_batch import (
			_ANTHROPIC_STATUS_TO_BATCH_JOB_STATUS,
			fetch_results,
			poll_batch,
		)

		return poll_batch, fetch_results, _ANTHROPIC_STATUS_TO_BATCH_JOB_STATUS

	return None


def _extract_token_usage(response: dict | None) -> tuple[int, int]:
	"""Best-effort (input_tokens, output_tokens) extraction from a single
	batch response body. OpenAI responses carry a "usage" dict with
	prompt_tokens/completion_tokens; Anthropic responses (SDK message objects
	or their dict form) carry a "usage" attribute/key with
	input_tokens/output_tokens. Returns (0, 0) if usage can't be found —
	cost estimation is best-effort and must never crash the poller.
	"""
	if not response:
		return 0, 0

	usage = response.get("usage") if isinstance(response, dict) else getattr(response, "usage", None)
	if not usage:
		return 0, 0

	if isinstance(usage, dict):
		input_tokens = usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0
		output_tokens = usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0
	else:
		input_tokens = getattr(usage, "prompt_tokens", getattr(usage, "input_tokens", 0)) or 0
		output_tokens = getattr(usage, "completion_tokens", getattr(usage, "output_tokens", 0)) or 0

	return int(input_tokens), int(output_tokens)


def _estimate_batch_cost(model: str | None, results: list[dict]) -> float | None:
	"""Rough estimated_cost for a completed batch job.

	Sums token usage across all successful results, runs it through the
	existing realtime calculate_cost() helper, then halves it — batch
	pricing is ~50% of realtime per provider docs (Phase 1 research).
	Returns None if there's no model to price against or no usable usage
	data, so callers can leave estimated_cost unset rather than write a
	misleading 0.0.
	"""
	if not model:
		return None

	total_input = 0
	total_output = 0
	for result in results:
		in_tok, out_tok = _extract_token_usage(result.get("response"))
		total_input += in_tok
		total_output += out_tok

	if total_input == 0 and total_output == 0:
		return None

	try:
		realtime_cost, _source = calculate_cost(
			model_name=model,
			input_tokens=total_input,
			output_tokens=total_output,
		)
	except (ValueError, TypeError, AttributeError, KeyError):
		# Cost calculation is best-effort; leave estimated_cost unset on failure.
		return None

	return round(float(realtime_cost) * _BATCH_DISCOUNT_FACTOR, 6)


def _build_result_summary(results: list[dict]) -> dict:
	"""Cap what gets inlined into the JSON result_summary field.

	This stores counts plus a small sample; the full per-request results are
	written separately into a new Agent Conversation/Agent Message thread by
	`_write_batch_results_to_conversation` (best-effort, see module docstring).
	"""
	succeeded = [r for r in results if not r.get("error")]
	errored = [r for r in results if r.get("error")]

	return {
		"succeeded": len(succeeded),
		"errored": len(errored),
		"sample": results[:_RESULT_SAMPLE_SIZE],
	}


def _extract_openai_response_text(response: dict | None) -> str:
	"""Extract assistant text from an OpenAI chat-completion-shaped batch response body.

	`response` is the JSON body under `record["response"]["body"]` from the
	output JSONL file (see openai_batch.fetch_results) -- a plain dict shaped
	like a Chat Completions response: `{"choices": [{"message": {"content": ...}}], ...}`.
	Falls back to a JSON dump of the whole response if the expected shape isn't there,
	so nothing is silently dropped.
	"""
	if not isinstance(response, dict):
		return frappe.as_json(response) if response is not None else ""

	try:
		content = response["choices"][0]["message"]["content"]
	except (KeyError, IndexError, TypeError):
		return frappe.as_json(response)

	return content or ""


def _extract_anthropic_response_text(response) -> str:
	"""Extract assistant text from an Anthropic Messages-API-shaped batch response.

	`response` is the `message` attribute of a succeeded batch result entry
	(see anthropic_batch.fetch_results) -- an SDK `Message` object, not a
	dict, whose `.content` is a list of content blocks. Text blocks carry a
	`.text` attribute; other block types (e.g. tool_use) are skipped. Falls
	back to `str(response)` if no text blocks are found.
	"""
	if response is None:
		return ""

	content = getattr(response, "content", None)
	if not content:
		return str(response)

	texts = [block.text for block in content if getattr(block, "text", None)]
	return "\n".join(texts) if texts else str(response)


def _extract_response_text(provider: str, response) -> str:
	"""Dispatch to the provider-specific response-text extractor."""
	if provider == "OpenAI":
		return _extract_openai_response_text(response)
	if provider == "Anthropic":
		return _extract_anthropic_response_text(response)
	return frappe.as_json(response) if response is not None else ""


def _write_batch_results_to_conversation(
	job_name: str, agent_name: str | None, provider: str, results: list[dict]
) -> str | None:
	"""Create one new Agent Conversation plus one Agent Message per batch result.

	A batch run is its own standalone unit -- this always creates a brand-new
	conversation rather than threading into an existing (possibly live) one,
	to avoid confusing interleaving with real-time chat messages. Returns the
	new Agent Conversation's name, or None if the Batch Job has no `agent`
	(so there's nothing to attribute the conversation to).

	No Agent Run record is created here -- see module docstring: this is
	minimal, readable message history, not a full agent-run replica.
	"""
	if not agent_name:
		return None

	session_id = f"batch:{job_name}:{uuid4().hex[:8]}"
	conversation = frappe.get_doc(
		{
			"doctype": "Agent Conversation",
			"title": f"Batch Job {job_name} results",
			"agent": agent_name,
			"session_id": session_id,
			"created_at": now_datetime(),
			"last_activity": now_datetime(),
			"is_active": 0,
			"model": frappe.db.get_value("Agent", agent_name, "model"),
		}
	)
	conversation.insert(ignore_permissions=True)

	for index, result in enumerate(results):
		error = result.get("error")
		if error:
			content = f"custom_id: {result.get('custom_id')}\n\nError: {error}"
			kind = "Error"
		else:
			content = _extract_response_text(provider, result.get("response"))
			kind = "Message"

		frappe.get_doc(
			{
				"doctype": "Agent Message",
				"conversation": conversation.name,
				"conversation_index": index,
				"content": content,
				"kind": kind,
				"role": "agent",
				"is_agent_message": 1,
				"agent": agent_name,
				"session_id": session_id,
			}
		).insert(ignore_permissions=True)

	return conversation.name


def _process_batch_job(job: dict) -> None:
	"""Poll and, if completed, fetch/writeback results for a single Batch Job.

	Raises on unexpected failure; the caller wraps each job in its own
	try/except so one job's failure never stops the rest of the batch from
	being polled (mirrors the pattern in agent_scheduler.run_scheduled_agents).
	"""
	provider = job.get("provider")
	provider_batch_id = job.get("provider_batch_id")
	job_name = job.get("name")

	if not provider_batch_id:
		frappe.log_error(
			title="Batch Job Poll",
			message=f"Batch Job {job_name} is {job.get('status')} but has no provider_batch_id.",
		)
		return

	provider_module = _get_provider_module(provider)
	if not provider_module:
		frappe.log_error(
			title="Batch Job Poll",
			message=f"Batch Job {job_name} has unsupported/unexpected provider '{provider}'; skipping poll.",
		)
		return

	poll_batch, fetch_results, status_map = provider_module

	poll_result = _run_async_safely(poll_batch(provider_batch_id, batch_job=job_name))
	native_status = poll_result.get("status")
	mapped_status = status_map.get(native_status)
	if not mapped_status:
		frappe.log_error(
			title="Batch Job Poll",
			message=f"Batch Job {job_name}: unrecognized native status '{native_status}' from {provider}.",
		)
		return

	doc = frappe.get_doc("Batch Job", job_name)
	doc.status = mapped_status

	if mapped_status == "Completed":
		results = _run_async_safely(fetch_results(provider_batch_id, batch_job=job_name))
		doc.result_summary = _build_result_summary(results)
		doc.completed_at = now_datetime()

		model = frappe.db.get_value("Agent", doc.agent, "model") if doc.agent else None
		estimated_cost = _estimate_batch_cost(model, results)
		if estimated_cost is not None:
			doc.estimated_cost = estimated_cost

		try:
			conversation_name = _write_batch_results_to_conversation(job_name, doc.agent, provider, results)
			if conversation_name:
				summary = dict(doc.result_summary or {})
				summary["result_conversation"] = conversation_name
				doc.result_summary = summary
		except Exception as e:  # noqa: BLE001 -- boundary catch: conversation writeback is best-effort and
			# must never block result_summary/estimated_cost/completed_at from being saved
			frappe.log_error(
				title="Batch Job Poll",
				message=f"Batch Job {job_name}: failed to write results to Agent Conversation: {e}",
			)
	elif mapped_status in _TERMINAL_NO_RESULTS_STATUSES:
		doc.completed_at = now_datetime()
		error_info = poll_result.get("error") or poll_result.get("errors")
		if error_info:
			doc.error_message = str(error_info)

	doc.save(ignore_permissions=True)
	frappe.db.commit()  # nosemgrep: justified background-job commit


@frappe.whitelist()
def poll_pending_batch_jobs():
	"""Poll every Submitted/In Progress Batch Job and write back its status.

	Meant to be called periodically via Frappe's scheduler (see
	scheduler_events["cron"] in hooks.py). Batch SLAs are same-day, not
	instant, so a 10-15 minute cadence is plenty.
	"""
	jobs = frappe.get_all(
		"Batch Job",
		filters={"status": ("in", ["Submitted", "In Progress"])},
		fields=["name", "provider", "provider_batch_id", "status", "agent"],
	)

	for job in jobs:
		try:
			_process_batch_job(job)
		except Exception:  # noqa: BLE001 -- boundary catch: one job's failure must not stop the rest
			frappe.log_error(frappe.get_traceback(), "Batch Job Poll")
			frappe.db.rollback()
			continue
