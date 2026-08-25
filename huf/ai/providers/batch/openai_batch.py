# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
OpenAI Batch API support via LiteLLM.

Uses LiteLLM's async batch primitives (acreate_file / acreate_batch /
aretrieve_batch / afile_content), available in litellm>=1.74.7 (this repo's
pinned floor, see pyproject.toml) — confirmed present in 1.83.7, the top of
this repo's pinned range. Credential resolution follows the same
AI Provider -> api_key/api_base pattern as huf/ai/providers/litellm.py; do not
re-derive credentials differently here.
"""

import json

import frappe
import litellm

from huf.ai.providers.litellm import (
	ProviderUnavailableError,
	_resolve_api_base,
	_resolve_api_key,
)

_BATCH_ENDPOINT = "/v1/chat/completions"
_BATCH_COMPLETION_WINDOW = "24h"
_CUSTOM_LLM_PROVIDER = "openai"

_SUBMIT_ERROR = "Could not submit the batch job to OpenAI. Please try again."
_POLL_ERROR = "Could not check the batch job status with OpenAI. Please try again."
_FETCH_ERROR = "Could not download the batch job results from OpenAI. Please try again."

# Batch Job.status options: Pending, Submitted, In Progress, Completed, Failed,
# Cancelled, Expired. Callers (the poll/writeback job in a later phase) map
# OpenAI's native strings (validating/in_progress/finalizing/completed/failed/
# expired/cancelling/cancelled) onto these — this module intentionally returns
# the native strings so that mapping isn't duplicated here.

_OPENAI_STATUS_TO_BATCH_JOB_STATUS = {
	"validating": "Submitted",
	"in_progress": "In Progress",
	"finalizing": "In Progress",
	"completed": "Completed",
	"failed": "Failed",
	"expired": "Expired",
	"cancelling": "In Progress",
	"cancelled": "Cancelled",
}


def _get_agent_attr(agent, key, default=None):
	if isinstance(agent, dict):
		return agent.get(key, default)
	return getattr(agent, key, default)


def _resolve_openai_credentials_for_agent(agent) -> dict:
	"""Resolve api_key/api_base for the AI Provider linked to `agent`."""
	provider_name = _get_agent_attr(agent, "provider")
	if not provider_name:
		frappe.throw("Agent is missing a linked AI Provider for batch submission.")

	provider_doc = frappe.get_doc("AI Provider", provider_name)
	api_key = _resolve_api_key(provider_doc)
	if not api_key:
		frappe.throw("API key not configured in AI Provider.")

	kwargs = {"api_key": api_key}
	api_base = _resolve_api_base(provider_doc)
	if api_base:
		kwargs["api_base"] = api_base
	return kwargs


def _resolve_openai_credentials_fallback(batch_job: str | None = None) -> dict:
	"""Resolve credentials for poll/fetch calls.

	`batch_job` is the `Batch Job` docname that owns this provider_batch_id —
	its linked `agent` tells us the exact AI Provider to use, the same as
	submit_batch(). Pass it whenever the caller has it (the poll/writeback job
	in Phase 3 always will, since it iterates Batch Job records). Falling back
	to "the first configured openai-brand AI Provider" only when no batch_job
	is given (e.g. ad-hoc debugging) — with multiple OpenAI-brand providers
	that fallback can resolve the wrong key, so callers should prefer passing
	batch_job.
	"""
	if batch_job:
		agent_name = frappe.db.get_value("Batch Job", batch_job, "agent")
		if agent_name:
			return _resolve_openai_credentials_for_agent(frappe.get_doc("Agent", agent_name))

	provider_name = frappe.db.get_value(
		"AI Provider", {"provider_brand": "openai", "is_local_llm": 0}, "name"
	)
	if not provider_name:
		frappe.throw("No OpenAI AI Provider is configured to check this batch job.")

	provider_doc = frappe.get_doc("AI Provider", provider_name)
	api_key = _resolve_api_key(provider_doc)
	if not api_key:
		frappe.throw("API key not configured in AI Provider.")

	kwargs = {"api_key": api_key}
	api_base = _resolve_api_base(provider_doc)
	if api_base:
		kwargs["api_base"] = api_base
	return kwargs


def _build_jsonl(requests: list[dict]) -> bytes:
	lines = []
	for req in requests:
		custom_id = req.get("custom_id")
		if not custom_id:
			frappe.throw("Each batch request requires a custom_id.")

		body = {k: v for k, v in req.items() if k != "custom_id"}
		lines.append(
			json.dumps({"custom_id": custom_id, "method": "POST", "url": _BATCH_ENDPOINT, "body": body})
		)
	return ("\n".join(lines) + "\n").encode("utf-8")


async def submit_batch(agent, requests: list[dict]) -> dict:
	"""Upload a JSONL batch file and create an OpenAI batch job via LiteLLM.

	Returns {"provider_batch_id": ..., "status": ..., "input_file_id": ...}.
	"""
	if not requests:
		frappe.throw("At least one request is required to submit a batch.")

	kwargs = _resolve_openai_credentials_for_agent(agent)
	jsonl_bytes = _build_jsonl(requests)

	try:
		file_obj = await litellm.acreate_file(
			file=("batch_input.jsonl", jsonl_bytes),
			purpose="batch",
			custom_llm_provider=_CUSTOM_LLM_PROVIDER,
			**kwargs,
		)

		batch_obj = await litellm.acreate_batch(
			completion_window=_BATCH_COMPLETION_WINDOW,
			endpoint=_BATCH_ENDPOINT,
			input_file_id=file_obj.id,
			custom_llm_provider=_CUSTOM_LLM_PROVIDER,
			**kwargs,
		)
	except Exception as e:  # boundary exception handler: external provider/tool boundary
		raw_msg = f"Failed to submit OpenAI batch: {e!s}"
		frappe.log_error(message=f"{raw_msg}\n\n{frappe.get_traceback()}", title="OpenAI Batch Submit")
		raise ProviderUnavailableError(_SUBMIT_ERROR, log_message=raw_msg) from e

	return {
		"provider_batch_id": batch_obj.id,
		"status": batch_obj.status,
		"input_file_id": file_obj.id,
	}


async def poll_batch(provider_batch_id: str, batch_job: str | None = None) -> dict:
	"""Retrieve current status of an OpenAI batch job via LiteLLM.

	Returns the native LiteLLM/OpenAI batch object fields we care about:
	{"provider_batch_id", "status", "output_file_id", "error_file_id",
	"request_counts"}. `status` is OpenAI's native string — use
	_OPENAI_STATUS_TO_BATCH_JOB_STATUS to map it onto Batch Job.status.
	"""
	kwargs = _resolve_openai_credentials_fallback(batch_job)

	try:
		batch_obj = await litellm.aretrieve_batch(
			batch_id=provider_batch_id,
			custom_llm_provider=_CUSTOM_LLM_PROVIDER,
			**kwargs,
		)
	except Exception as e:  # boundary exception handler: external provider/tool boundary
		raw_msg = f"Failed to poll OpenAI batch '{provider_batch_id}': {e!s}"
		frappe.log_error(message=f"{raw_msg}\n\n{frappe.get_traceback()}", title="OpenAI Batch Poll")
		raise ProviderUnavailableError(_POLL_ERROR, log_message=raw_msg) from e

	request_counts = getattr(batch_obj, "request_counts", None)
	return {
		"provider_batch_id": batch_obj.id,
		"status": batch_obj.status,
		"output_file_id": getattr(batch_obj, "output_file_id", None),
		"error_file_id": getattr(batch_obj, "error_file_id", None),
		"request_counts": dict(request_counts) if request_counts else {},
	}


async def fetch_results(provider_batch_id: str, batch_job: str | None = None) -> list[dict]:
	"""Download a completed batch's output (and error) file content.

	Returns a list of {"custom_id", "response", "error"} dicts, one per line
	of the output/error JSONL files. Never assume line order matches
	submission order — callers must key results by custom_id.
	"""
	kwargs = _resolve_openai_credentials_fallback(batch_job)

	try:
		batch_obj = await litellm.aretrieve_batch(
			batch_id=provider_batch_id,
			custom_llm_provider=_CUSTOM_LLM_PROVIDER,
			**kwargs,
		)

		results_by_custom_id = {}

		output_file_id = getattr(batch_obj, "output_file_id", None)
		if output_file_id:
			output_content = await litellm.afile_content(
				file_id=output_file_id,
				custom_llm_provider=_CUSTOM_LLM_PROVIDER,
				**kwargs,
			)
			for line in output_content.text.splitlines():
				line = line.strip()
				if not line:
					continue
				record = json.loads(line)
				custom_id = record.get("custom_id")
				response_body = (record.get("response") or {}).get("body")
				results_by_custom_id[custom_id] = {
					"custom_id": custom_id,
					"response": response_body,
					"error": record.get("error"),
				}

		error_file_id = getattr(batch_obj, "error_file_id", None)
		if error_file_id:
			error_content = await litellm.afile_content(
				file_id=error_file_id,
				custom_llm_provider=_CUSTOM_LLM_PROVIDER,
				**kwargs,
			)
			for line in error_content.text.splitlines():
				line = line.strip()
				if not line:
					continue
				record = json.loads(line)
				custom_id = record.get("custom_id")
				existing = results_by_custom_id.get(custom_id, {"custom_id": custom_id, "response": None})
				existing["error"] = record.get("error") or existing.get("error")
				results_by_custom_id[custom_id] = existing

	except Exception as e:  # boundary exception handler: external provider/tool boundary
		raw_msg = f"Failed to fetch OpenAI batch results for '{provider_batch_id}': {e!s}"
		frappe.log_error(message=f"{raw_msg}\n\n{frappe.get_traceback()}", title="OpenAI Batch Fetch Results")
		raise ProviderUnavailableError(_FETCH_ERROR, log_message=raw_msg) from e

	return list(results_by_custom_id.values())
