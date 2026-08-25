# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Anthropic Message Batches API support via the direct Anthropic Python SDK.

Deliberately does NOT go through LiteLLM: LiteLLM's Anthropic batch-create
support is unconfirmed/mid-flight upstream (a Dec 2025 PR added retrieve-only
support; full create parity is unverified as of this writing). Client
construction follows the same anthropic.AsyncAnthropic(api_key=...) pattern
used by the legacy realtime wrapper in huf/ai/providers/anthropic.py, and
credential resolution follows the same AI Provider -> api_key/api_base
pattern as huf/ai/providers/litellm.py; do not re-derive credentials
differently here.
"""

import anthropic
import frappe

from huf.ai.providers.litellm import (
	ProviderUnavailableError,
	_resolve_api_base,
	_resolve_api_key,
)

_PROVIDER_BRAND = "anthropic"

_SUBMIT_ERROR = "Could not submit the batch job to Anthropic. Please try again."
_POLL_ERROR = "Could not check the batch job status with Anthropic. Please try again."
_FETCH_ERROR = "Could not download the batch job results from Anthropic. Please try again."

# Batch Job.status options: Pending, Submitted, In Progress, Completed, Failed,
# Cancelled, Expired. Anthropic's native processing_status values are only
# in_progress / canceling / ended -- "ended" does NOT by itself distinguish
# success/failure/expiry, that distinction only exists per-request in the
# results stream (see fetch_results). We map "ended" to "Completed" as the
# batch-level status here; deciding whether every individual request actually
# succeeded is a job-level concern deferred to a later phase (the
# poll/writeback job), not a bug in this mapping.
_ANTHROPIC_STATUS_TO_BATCH_JOB_STATUS = {
	"in_progress": "In Progress",
	"canceling": "In Progress",
	"ended": "Completed",
}


def _get_agent_attr(agent, key, default=None):
	if isinstance(agent, dict):
		return agent.get(key, default)
	return getattr(agent, key, default)


def _build_anthropic_client_kwargs(provider_doc) -> dict:
	api_key = _resolve_api_key(provider_doc)
	if not api_key:
		frappe.throw("API key not configured in AI Provider.")

	kwargs = {"api_key": api_key}
	api_base = _resolve_api_base(provider_doc)
	if api_base:
		kwargs["base_url"] = api_base
	return kwargs


def _resolve_anthropic_credentials_for_agent(agent) -> dict:
	"""Resolve client kwargs for the AI Provider linked to `agent`."""
	provider_name = _get_agent_attr(agent, "provider")
	if not provider_name:
		frappe.throw("Agent is missing a linked AI Provider for batch submission.")

	provider_doc = frappe.get_doc("AI Provider", provider_name)
	return _build_anthropic_client_kwargs(provider_doc)


def _resolve_anthropic_credentials_fallback(batch_job: str | None = None) -> dict:
	"""Resolve client kwargs for poll/fetch calls.

	`batch_job` is the `Batch Job` docname that owns this provider_batch_id --
	its linked `agent` tells us the exact AI Provider to use, the same as
	submit_batch(). Pass it whenever the caller has it (the poll/writeback job
	in Phase 3 always will, since it iterates Batch Job records). Falling back
	to "the first configured anthropic-brand AI Provider" only when no
	batch_job is given (e.g. ad-hoc debugging) -- with multiple Anthropic-brand
	providers that fallback can resolve the wrong key, so callers should
	prefer passing batch_job.
	"""
	if batch_job:
		agent_name = frappe.db.get_value("Batch Job", batch_job, "agent")
		if agent_name:
			return _resolve_anthropic_credentials_for_agent(frappe.get_doc("Agent", agent_name))

	provider_name = frappe.db.get_value(
		"AI Provider", {"provider_brand": _PROVIDER_BRAND, "is_local_llm": 0}, "name"
	)
	if not provider_name:
		frappe.throw("No Anthropic AI Provider is configured to check this batch job.")

	provider_doc = frappe.get_doc("AI Provider", provider_name)
	return _build_anthropic_client_kwargs(provider_doc)


def _build_batch_requests(requests: list[dict]) -> list[dict]:
	batch_requests = []
	for req in requests:
		custom_id = req.get("custom_id")
		if not custom_id:
			frappe.throw("Each batch request requires a custom_id.")

		params = {k: v for k, v in req.items() if k != "custom_id"}
		# "stream" is invalid for individual requests inside a batch -- strip
		# it defensively in case a caller copy-pasted realtime request kwargs.
		params.pop("stream", None)
		batch_requests.append({"custom_id": custom_id, "params": params})
	return batch_requests


async def submit_batch(agent, requests: list[dict]) -> dict:
	"""Create an Anthropic Message Batch via the direct Anthropic SDK.

	Returns {"provider_batch_id": ..., "status": ...}.
	"""
	if not requests:
		frappe.throw("At least one request is required to submit a batch.")

	client_kwargs = _resolve_anthropic_credentials_for_agent(agent)
	batch_requests = _build_batch_requests(requests)

	client = anthropic.AsyncAnthropic(**client_kwargs)

	try:
		batch = await client.messages.batches.create(requests=batch_requests)
	except Exception as e:  # boundary exception handler: external provider/tool boundary
		raw_msg = f"Failed to submit Anthropic batch: {e!s}"
		frappe.log_error(message=f"{raw_msg}\n\n{frappe.get_traceback()}", title="Anthropic Batch Submit")
		raise ProviderUnavailableError(_SUBMIT_ERROR, log_message=raw_msg) from e

	return {
		"provider_batch_id": batch.id,
		"status": batch.processing_status,
	}


async def poll_batch(provider_batch_id: str, batch_job: str | None = None) -> dict:
	"""Retrieve current status of an Anthropic batch job via the direct SDK.

	Returns {"provider_batch_id", "status", "request_counts"}. `status` is
	Anthropic's native processing_status string -- use
	_ANTHROPIC_STATUS_TO_BATCH_JOB_STATUS to map it onto Batch Job.status.
	"""
	client_kwargs = _resolve_anthropic_credentials_fallback(batch_job)
	client = anthropic.AsyncAnthropic(**client_kwargs)

	try:
		batch = await client.messages.batches.retrieve(provider_batch_id)
	except Exception as e:  # boundary exception handler: external provider/tool boundary
		raw_msg = f"Failed to poll Anthropic batch '{provider_batch_id}': {e!s}"
		frappe.log_error(message=f"{raw_msg}\n\n{frappe.get_traceback()}", title="Anthropic Batch Poll")
		raise ProviderUnavailableError(_POLL_ERROR, log_message=raw_msg) from e

	request_counts = getattr(batch, "request_counts", None)
	return {
		"provider_batch_id": batch.id,
		"status": batch.processing_status,
		"request_counts": dict(request_counts) if request_counts else {},
	}


async def fetch_results(provider_batch_id: str, batch_job: str | None = None) -> list[dict]:
	"""Stream a completed Anthropic batch's results via the direct SDK.

	Unlike OpenAI, Anthropic has no separate file-download step -- results
	come back as a JSONL stream from `client.messages.batches.results(...)`.
	Returns a list of {"custom_id", "response", "error"} dicts, one per
	result line. Never assume line order matches submission order -- callers
	must key results by custom_id.
	"""
	client_kwargs = _resolve_anthropic_credentials_fallback(batch_job)
	client = anthropic.AsyncAnthropic(**client_kwargs)

	results_by_custom_id = {}

	try:
		results_stream = await client.messages.batches.results(provider_batch_id)
		async for entry in results_stream:
			custom_id = entry.custom_id
			result = entry.result
			result_type = getattr(result, "type", None)

			if result_type == "succeeded":
				response = getattr(result, "message", None)
				error = None
			else:
				response = None
				error = getattr(result, "error", None) or {"type": result_type}

			results_by_custom_id[custom_id] = {
				"custom_id": custom_id,
				"response": response,
				"error": error,
			}
	except Exception as e:  # boundary exception handler: external provider/tool boundary
		raw_msg = f"Failed to fetch Anthropic batch results for '{provider_batch_id}': {e!s}"
		frappe.log_error(
			message=f"{raw_msg}\n\n{frappe.get_traceback()}", title="Anthropic Batch Fetch Results"
		)
		raise ProviderUnavailableError(_FETCH_ERROR, log_message=raw_msg) from e

	return list(results_by_custom_id.values())
