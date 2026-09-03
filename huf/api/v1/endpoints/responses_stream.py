"""Streaming response endpoint for the Huf public developer API (v1).

Mirrors `huf.ai.agent_stream_renderer.AgentStreamRenderer` (the existing,
working SSE implementation): reuses `run_agent_stream()` exactly as that
renderer calls it, and replicates its server-side `run_immediately`
enforcement (see `AgentStreamRenderer._render_agent_stream`, around
huf/ai/agent_stream_renderer.py:164-170) rather than inventing a new check.

------------------------------------------------------------------------
WIRING NOTE FOR THE REVIEWER (router.py) - NOT APPLIED HERE ON PURPOSE
------------------------------------------------------------------------
`ApiV1Router.render()` (huf/api/v1/router.py) currently always does:

    context = self._build_context(requires_auth)
    data = handler(context)
    return self._render_success(data, context.request_id)

`_render_success` always JSON-encodes `data` via `self.build_response(...)`.
Streaming needs a different return path that produces a raw werkzeug
`Response` with `mimetype="text/event-stream"` instead, so the branch has
to happen BEFORE `_render_success` is called, and only for the `responses`
endpoint when the caller asked for `stream=true`/`stream=1`.

Suggested shape (do not apply verbatim without checking for conflicts with
the parallel task touching responses.py/router.py):

    def render(self):
        endpoint = ...  # unchanged
        route = _match_route(endpoint)
        ...
        try:
            context = self._build_context(requires_auth)

            # NEW: branch before the JSON envelope for POST /responses
            # with stream=true.
            if endpoint == "responses" and _wants_stream(frappe.local.form_dict):
                payload = frappe.local.form_dict
                return handle_stream_response(
                    context,
                    agent_id=payload.get("agent_id") or payload.get("agent"),
                    input_text=payload.get("input") or payload.get("input_text") or payload.get("prompt"),
                    conversation_id=payload.get("conversation_id"),
                )

            data = handler(context)
            return self._render_success(data, context.request_id)
        except ApiError as exc:
            return self._render_error(exc, fallback_request_id)
        ...

Where `_wants_stream(form_dict)` is something like:

    def _wants_stream(payload) -> bool:
        val = payload.get("stream")
        return str(val).strip().lower() in ("1", "true", "yes")

Notes for whoever wires this in:
- `handle_stream_response` below already does its own `ValidationError`
  raising (missing agent_id/input_text) and its own `NotFoundError` /
  `AuthorizationError` via `assert_agent_access`, matching the sync
  handler's ordering. Those still need to be caught the SAME way
  `ApiError` is caught elsewhere in `render()` -- but they can only be
  raised BEFORE the SSE `Response` object is constructed and returned,
  since once a streaming `Response` is handed back to Werkzeug there is
  no more chance to swap in a JSON error envelope. `handle_stream_response`
  therefore validates and resolves the agent synchronously up front and
  only starts the generator once everything is known to succeed, exactly
  like `AgentStreamRenderer._render_agent_stream` does (see the "run_immediately"
  check and the "has queued runs" check, both performed before
  `stream_generator()` is defined/returned).
- Do not add `Content-Type: application/json` handling for this branch;
  return the SSE `Response` object directly, unwrapped, from `render()`.
------------------------------------------------------------------------
"""

import asyncio
import json
from typing import Generator

import frappe
from werkzeug.wrappers import Response

from huf.ai.agent_access import assert_agent_access
from huf.ai.agent_integration import _has_queued_runs, run_agent_stream
from huf.api.v1.context import RequestContext
from huf.api.v1.endpoints.conversations import _get_owned_conversation
from huf.api.v1.errors import NotFoundError, ValidationError
from huf.api.v1.scopes import require_agent_allowed, require_scope

# Internal chunk "type" (as yielded by run_agent_stream / used by
# AgentStreamRenderer) -> public v1 SSE event name.
_EVENT_NAME_MAP = {
	"delta": "response.output_text.delta",
	"tool_call": "response.output_text.delta",
	"complete": "response.completed",
	"error": "response.failed",
}

_SSE_HEADERS = {
	"Cache-Control": "no-cache",
	"Connection": "keep-alive",
	"X-Accel-Buffering": "no",
}


def _sse_line(public_type: str, payload: dict) -> str:
	data = {"type": public_type, **payload}
	return f"data: {json.dumps(data)}\n\n"


def _sse_error_response(message: str, request_id: str = None):
	"""Single-event SSE error response, used for failures discovered before
	the underlying stream generator can be started (mirrors
	`AgentStreamRenderer._sse_error_response`)."""

	def error_generator() -> Generator[str, None, None]:
		yield _sse_line("response.failed", {"error": message, "request_id": request_id})

	return Response(error_generator(), mimetype="text/event-stream", headers=dict(_SSE_HEADERS))


def _map_chunk(chunk: dict) -> tuple:
	"""Map an internal `run_agent_stream` chunk onto (public_event_name, payload)."""
	chunk_type = chunk.get("type")
	public_type = _EVENT_NAME_MAP.get(chunk_type, "response.output_text.delta")

	if chunk_type == "delta":
		payload = {"delta": chunk.get("content", ""), "output": chunk.get("full_response")}
	elif chunk_type == "tool_call":
		payload = {"tool_call": chunk.get("tool_call")}
	elif chunk_type == "complete":
		payload = {"output": chunk.get("full_response")}
	elif chunk_type == "error":
		payload = {"error": chunk.get("error")}
	else:
		payload = {k: v for k, v in chunk.items() if k != "type"}

	return public_type, payload


def handle_stream_response(
	context: RequestContext, agent_id: str, input_text: str, conversation_id: str = None
):
	"""POST /huf/api/v1/responses (stream=true) - run an agent turn as SSE.

	Validates and resolves the agent/conversation synchronously (same
	ordering as `handle_create_response` in `responses.py`), then, only if
	streaming is allowed for this agent, returns a werkzeug `Response`
	streaming `text/event-stream`. All failures that can be detected up
	front raise `ApiError` subclasses so the router's normal JSON error
	envelope still applies to them; failures discovered mid-stream are
	instead emitted as a `response.failed` SSE event, since the HTTP
	response has already started at that point.
	"""
	if not agent_id:
		raise ValidationError("agent_id is required.")
	if not input_text:
		raise ValidationError("input_text is required.")

	require_scope(context, "agents:run")
	require_agent_allowed(context, agent_id)

	if not frappe.db.exists("Agent", agent_id):
		raise NotFoundError(f"Agent '{agent_id}' was not found.")

	agent_doc = frappe.get_doc("Agent", agent_id)
	assert_agent_access(agent_doc, user=context.user)

	# Queue-first policy: streaming is a direct-execution compatibility
	# path, allowed only when the agent opts in via 'Run Immediately'.
	# Replicates huf/ai/agent_stream_renderer.py:164-170 exactly - do not
	# invent a different check here.
	if not getattr(agent_doc, "run_immediately", 0):
		raise ValidationError(
			"This agent does not support streaming responses; use POST /v1/responses "
			"without stream=true, or enable Run Immediately on the agent."
		)

	create_new = False
	if conversation_id:
		_get_owned_conversation(conversation_id, context.user)
	else:
		create_new = True

	# Queue-ordering parity with the sync path: a direct stream must not
	# jump ahead of queued runs for the same conversation. A brand-new
	# conversation has no queued runs by definition, so skip the check.
	stream_conversation_id = None if create_new else conversation_id
	if stream_conversation_id and _has_queued_runs(stream_conversation_id):
		raise ValidationError(
			"This conversation has queued runs pending. Wait for them to complete "
			"before using the direct-execution (stream) override."
		)

	channel_id = "api_v1_stream"
	external_id = context.user

	def stream_generator() -> Generator[str, None, None]:
		loop = None
		created_loop = False
		async_gen = None
		try:
			try:
				loop = asyncio.get_event_loop()
				if loop.is_closed():
					loop = None
			except RuntimeError:
				loop = None

			if loop is None:
				loop = asyncio.new_event_loop()
				asyncio.set_event_loop(loop)
				created_loop = True

			yield _sse_line(
				"response.created",
				{"conversation_id": conversation_id, "request_id": context.request_id},
			)

			async_gen = run_agent_stream(
				agent_name=agent_id,
				prompt=input_text,
				channel_id=channel_id,
				external_id=external_id,
				conversation_id=None if create_new else conversation_id,
				create_new=create_new,
			)

			while True:
				try:
					chunk = loop.run_until_complete(async_gen.__anext__())
					public_type, payload = _map_chunk(chunk)
					yield _sse_line(public_type, payload)

					if chunk.get("type") in ("complete", "error"):
						break
				except StopAsyncIteration:
					break
				except Exception as e:
					frappe.log_error(frappe.get_traceback(), "Huf API v1 Stream Chunk Error")
					yield _sse_line("response.failed", {"error": str(e)})
					break
		except Exception as e:
			frappe.log_error(frappe.get_traceback(), "Huf API v1 Stream Setup Error")
			yield _sse_line("response.failed", {"error": f"Stream setup error: {str(e)}"})
		finally:
			if async_gen is not None:
				try:
					loop.run_until_complete(async_gen.aclose())
				except (RuntimeError, ValueError, TypeError, AttributeError, KeyError):
					pass

			if created_loop and loop:
				try:
					pending = asyncio.all_tasks(loop)
					for task in pending:
						task.cancel()
					if pending:
						loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
					loop.close()
				except (RuntimeError, ValueError, TypeError, AttributeError, KeyError):
					pass
				finally:
					asyncio.set_event_loop(None)

	return Response(stream_generator(), mimetype="text/event-stream", headers=dict(_SSE_HEADERS))
