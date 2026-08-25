# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Gemini Batch API support via the direct REST API (no SDK dependency).

Deliberately does NOT use the `google-genai` SDK's `client.batches.*` helpers:
that package is not among this repo's pinned dependencies (see
pyproject.toml) and is not importable in this environment (`import
google.genai` fails with ModuleNotFoundError here). Adding a brand-new SDK
dependency chain is out of scope for this pass, so this module talks to the
same REST surface the SDK wraps, using `httpx` (already a pinned dependency,
see pyproject.toml) for async HTTP -- mirroring the legacy realtime wrapper's
choice of plain HTTP over an SDK (see huf/ai/providers/google.py, which uses
`requests` directly against `generativelanguage.googleapis.com`).

Also deliberately does NOT target Vertex AI's BatchPredictionJob: the
`AI Provider` doctype (and huf/ai/providers/google.py, the existing realtime
Gemini wrapper) only ever resolves a plain API key -- there are no
project/location/GCS-bucket fields anywhere in this codebase for Google. That
means Vertex batch (which needs a GCP project, region, and a GCS bucket for
I/O) simply isn't wireable today without inventing a whole new credential and
storage model. This module targets the direct Gemini API's batch mode
instead, which needs only the API key HUF already has.

Credential resolution still follows the same AI Provider -> api_key/api_base
pattern as huf/ai/providers/litellm.py (_resolve_api_key/_resolve_api_base),
NOT the ad-hoc `get_password("api_key")` call in the legacy google.py wrapper
-- for consistency with openai_batch.py/anthropic_batch.py, which are the
structural template for this module.

REST shape below is grounded in ai.google.dev/gemini-api/docs/batch-api
(fetched Aug 2026) since the google-genai SDK isn't installed here to verify
against directly:

  POST https://generativelanguage.googleapis.com/v1beta/models/{model}:batchGenerateContent
    body: {"batch": {"display_name": ..., "input_config": {"requests":
           {"requests": [{"request": <GenerateContentRequest>,
                          "metadata": {"key": <custom_id>}}, ...]}}}}
    -> returns a Batch resource: {"name": "batches/<id>", "metadata": {"state": ...}, ...}

  GET https://generativelanguage.googleapis.com/v1beta/{name}
    -> {"name": ..., "metadata": {"state": "JOB_STATE_..."}, "done": bool,
        "response": {"dest": {"inlinedResponses": {"inlinedResponses":
            [{"response": <GenerateContentResponse>, "error": {...},
              "metadata": {"key": <custom_id>}}, ...]}}}}

The exact placement of "state" (top-level vs under "metadata") is documented
inconsistently between the Python/JS SDK docs and the raw REST examples, so
poll_batch() defensively checks both locations -- flag this for review if a
live batch job's actual response shape differs; it has not been verified
against a real API call in this pass.

Gemini's batch API DOES support a per-request correlation key via
`metadata: {"key": ...}` on each request, echoed back on each result's
`metadata.key` -- so, unlike the naive "no custom_id" assumption, this module
keys results by that field, same invariant openai_batch.py/anthropic_batch.py
hold (never assume result order matches submission order).
"""

import frappe
import httpx

from huf.ai.providers.litellm import (
	ProviderUnavailableError,
	_resolve_api_base,
	_resolve_api_key,
)

_API_BASE_DEFAULT = "https://generativelanguage.googleapis.com/v1beta"

_SUBMIT_ERROR = "Could not submit the batch job to Gemini. Please try again."
_POLL_ERROR = "Could not check the batch job status with Gemini. Please try again."
_FETCH_ERROR = "Could not download the batch job results from Gemini. Please try again."

_NO_REQUESTS_ERROR = "At least one request is required to submit a batch."
_MISSING_CUSTOM_ID_ERROR = "Each batch request requires a custom_id."
_MISSING_PROVIDER_ERROR = "Agent is missing a linked AI Provider for batch submission."
_MISSING_API_KEY_ERROR = "API key not configured in AI Provider."
_NO_PROVIDER_CONFIGURED_ERROR = "No Gemini AI Provider is configured to check this batch job."
_MISSING_MODEL_ERROR = "Each batch request requires a model."

_PROVIDER_BRAND = "google"

# Batch Job.status options: Pending, Submitted, In Progress, Completed, Failed,
# Cancelled, Expired. Gemini's native job states, per ai.google.dev's batch-api
# docs (unverified against a live/importable SDK in this environment -- flag
# for review once a real batch job's response can be inspected).
_GEMINI_STATE_TO_BATCH_JOB_STATUS = {
	"JOB_STATE_PENDING": "Submitted",
	"JOB_STATE_RUNNING": "In Progress",
	"JOB_STATE_SUCCEEDED": "Completed",
	"JOB_STATE_FAILED": "Failed",
	"JOB_STATE_CANCELLED": "Cancelled",
	"JOB_STATE_EXPIRED": "Expired",
}


def _get_agent_attr(agent, key, default=None):
	if isinstance(agent, dict):
		return agent.get(key, default)
	return getattr(agent, key, default)


def _resolve_gemini_credentials_for_agent(agent) -> dict:
	"""Resolve {"api_key", "api_base"} for the AI Provider linked to `agent`."""
	provider_name = _get_agent_attr(agent, "provider")
	if not provider_name:
		frappe.throw(_MISSING_PROVIDER_ERROR)

	provider_doc = frappe.get_doc("AI Provider", provider_name)
	api_key = _resolve_api_key(provider_doc)
	if not api_key:
		frappe.throw(_MISSING_API_KEY_ERROR)

	return {"api_key": api_key, "api_base": _resolve_api_base(provider_doc) or _API_BASE_DEFAULT}


def _resolve_gemini_credentials_fallback(batch_job: str | None = None) -> dict:
	"""Resolve credentials for poll/fetch calls.

	`batch_job` is the `Batch Job` docname that owns this provider_batch_id --
	its linked `agent` tells us the exact AI Provider to use, the same as
	submit_batch(). Pass it whenever the caller has it (the poll/writeback job
	always will, since it iterates Batch Job records). Falling back to "the
	first configured google-brand AI Provider" only when no batch_job is given
	(e.g. ad-hoc debugging) -- with multiple Google-brand providers that
	fallback can resolve the wrong key, so callers should prefer passing
	batch_job. Mirrors openai_batch.py/anthropic_batch.py's fallback shape.
	"""
	if batch_job:
		agent_name = frappe.db.get_value("Batch Job", batch_job, "agent")
		if agent_name:
			return _resolve_gemini_credentials_for_agent(frappe.get_doc("Agent", agent_name))

	provider_name = frappe.db.get_value(
		"AI Provider", {"provider_brand": _PROVIDER_BRAND, "is_local_llm": 0}, "name"
	)
	if not provider_name:
		frappe.throw(_NO_PROVIDER_CONFIGURED_ERROR)

	provider_doc = frappe.get_doc("AI Provider", provider_name)
	api_key = _resolve_api_key(provider_doc)
	if not api_key:
		frappe.throw(_MISSING_API_KEY_ERROR)

	return {"api_key": api_key, "api_base": _resolve_api_base(provider_doc) or _API_BASE_DEFAULT}


def _messages_to_contents(messages: list[dict]) -> list[dict]:
	"""Translate OpenAI-style {"role", "content"} messages into Gemini `contents`.

	Gemini's native API has no "messages"/roles-as-OpenAI concept -- it uses
	`contents: [{"role": "user"|"model", "parts": [{"text": ...}]}]` (see
	huf/ai/providers/google.py, which builds this shape inline for realtime
	calls; there is no shared translation helper elsewhere in this repo, e.g.
	sdk_tools.py/tool_serializer.py, to reuse -- confirmed by search). "system"
	messages are folded into the first user turn's text since Phase 1 scope is
	single-request scheduled batches (a single prompt), not multi-turn
	conversations or tool use -- this is a deliberate simplification, not a
	general-purpose translator.
	"""
	contents = []
	system_prefix = ""
	for msg in messages:
		role = msg.get("role")
		content = msg.get("content") or ""
		if role == "system":
			system_prefix += f"{content}\n\n"
			continue
		gemini_role = "model" if role == "assistant" else "user"
		text = f"{system_prefix}{content}" if gemini_role == "user" and system_prefix else content
		if gemini_role == "user":
			system_prefix = ""
		contents.append({"role": gemini_role, "parts": [{"text": text}]})
	return contents


def _build_batch_requests(requests: list[dict]) -> tuple[list[dict], str]:
	"""Build the `input_config.requests.requests` list plus resolve the shared model.

	Every request in a single Gemini batch job targets the same `model` (it's
	part of the URL path, not the per-request body) -- this repo's Phase 1
	scope only ever submits single-request batches (see agent_scheduler.py /
	automation_scheduler.py's `_submit_batch_job_for_*` callers), so using the
	first request's model for the whole batch is safe today; a future
	multi-request batch spanning models would need per-model batches instead.
	"""
	if not requests:
		frappe.throw(_NO_REQUESTS_ERROR)

	model = None
	batch_requests = []
	for req in requests:
		custom_id = req.get("custom_id")
		if not custom_id:
			frappe.throw(_MISSING_CUSTOM_ID_ERROR)

		req_model = req.get("model")
		if not req_model:
			frappe.throw(_MISSING_MODEL_ERROR)
		model = model or req_model.replace("google/", "").split(":")[0]

		if "contents" in req:
			contents = req["contents"]
		else:
			contents = _messages_to_contents(req.get("messages") or [])

		batch_requests.append({"request": {"contents": contents}, "metadata": {"key": custom_id}})

	return batch_requests, model


async def submit_batch(agent, requests: list[dict]) -> dict:
	"""Create a Gemini batch job via the direct REST API.

	Inline-only for Phase 1 scope: every caller today (agent_scheduler.py /
	automation_scheduler.py's scheduled-trigger batch jobs) submits exactly one
	request per batch, far under Gemini's <20MB inline request-list cap, so
	the file-upload path (`client.files.upload` + a JSONL `input_config.
	file_name` reference, for up to 2GB/file) is unused complexity for now --
	not built here, left as a documented gap if a future caller ever needs to
	submit many requests in one batch job.

	Returns {"provider_batch_id": "batches/<id>", "status": <native state>}.
	"""
	creds = _resolve_gemini_credentials_for_agent(agent)
	batch_requests, model = _build_batch_requests(requests)

	url = f"{creds['api_base']}/models/{model}:batchGenerateContent"
	body = {
		"batch": {
			"display_name": requests[0].get("custom_id", "huf-batch"),
			"input_config": {"requests": {"requests": batch_requests}},
		}
	}

	try:
		async with httpx.AsyncClient(timeout=60.0) as client:
			resp = await client.post(url, params={"key": creds["api_key"]}, json=body)
			resp.raise_for_status()
			batch_obj = resp.json()
	except Exception as e:  # boundary exception handler: external provider/tool boundary
		raw_msg = f"Failed to submit Gemini batch: {e!s}"
		frappe.log_error(message=f"{raw_msg}\n\n{frappe.get_traceback()}", title="Gemini Batch Submit")
		raise ProviderUnavailableError(_SUBMIT_ERROR, log_message=raw_msg) from e

	native_status = batch_obj.get("metadata", {}).get("state") or batch_obj.get("state")
	return {"provider_batch_id": batch_obj.get("name"), "status": native_status}


async def poll_batch(provider_batch_id: str, batch_job: str | None = None) -> dict:
	"""Retrieve current status of a Gemini batch job via the direct REST API.

	Returns {"provider_batch_id", "status"}. `status` is Gemini's native
	JOB_STATE_* string -- use _GEMINI_STATE_TO_BATCH_JOB_STATUS to map it onto
	Batch Job.status. `provider_batch_id` may already be the full "batches/<id>"
	resource name (as returned by submit_batch) or a bare id -- both are
	accepted here.
	"""
	creds = _resolve_gemini_credentials_fallback(batch_job)
	name = provider_batch_id if provider_batch_id.startswith("batches/") else f"batches/{provider_batch_id}"
	url = f"{creds['api_base']}/{name}"

	try:
		async with httpx.AsyncClient(timeout=30.0) as client:
			resp = await client.get(url, params={"key": creds["api_key"]})
			resp.raise_for_status()
			batch_obj = resp.json()
	except Exception as e:  # boundary exception handler: external provider/tool boundary
		raw_msg = f"Failed to poll Gemini batch '{provider_batch_id}': {e!s}"
		frappe.log_error(message=f"{raw_msg}\n\n{frappe.get_traceback()}", title="Gemini Batch Poll")
		raise ProviderUnavailableError(_POLL_ERROR, log_message=raw_msg) from e

	# The docs are inconsistent about whether "state" lives at the top level or
	# under "metadata" -- check both defensively rather than assume one.
	native_status = batch_obj.get("metadata", {}).get("state") or batch_obj.get("state")
	return {"provider_batch_id": batch_obj.get("name", provider_batch_id), "status": native_status}


async def fetch_results(provider_batch_id: str, batch_job: str | None = None) -> list[dict]:
	"""Fetch a completed Gemini batch's inline results via the direct REST API.

	Returns a list of {"custom_id", "response", "error"} dicts, one per
	inlined result. Gemini DOES support a per-request correlation key (unlike
	a naive "no custom_id" assumption): each request's `metadata.key` is
	echoed back on its result under the same field, so -- same invariant
	openai_batch.py/anthropic_batch.py hold -- results are keyed by that
	custom_id, never by list position.

	File-output batches (`dest.file_name` instead of inline responses) are not
	handled here -- Phase 1 only ever submits small inline batches (see
	submit_batch's docstring), so Gemini has no reason to route output to a
	file for these; this is a real, documented gap if that assumption changes.
	"""
	creds = _resolve_gemini_credentials_fallback(batch_job)
	name = provider_batch_id if provider_batch_id.startswith("batches/") else f"batches/{provider_batch_id}"
	url = f"{creds['api_base']}/{name}"

	try:
		async with httpx.AsyncClient(timeout=60.0) as client:
			resp = await client.get(url, params={"key": creds["api_key"]})
			resp.raise_for_status()
			batch_obj = resp.json()
	except Exception as e:  # boundary exception handler: external provider/tool boundary
		raw_msg = f"Failed to fetch Gemini batch results for '{provider_batch_id}': {e!s}"
		frappe.log_error(message=f"{raw_msg}\n\n{frappe.get_traceback()}", title="Gemini Batch Fetch Results")
		raise ProviderUnavailableError(_FETCH_ERROR, log_message=raw_msg) from e

	dest = (batch_obj.get("response") or {}).get("dest") or batch_obj.get("dest") or {}
	inlined = (dest.get("inlinedResponses") or {}).get("inlinedResponses") or []

	results_by_custom_id = {}
	for entry in inlined:
		custom_id = (entry.get("metadata") or {}).get("key")
		results_by_custom_id[custom_id] = {
			"custom_id": custom_id,
			"response": entry.get("response"),
			"error": entry.get("error"),
		}

	return list(results_by_custom_id.values())
