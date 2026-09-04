"""Page renderer / router for the Huf public developer API (v1).

Follows the same `BaseRenderer` pattern as `huf.ai.agent_stream_renderer
.AgentStreamRenderer` so it plugs into Frappe's website routing via the
`page_renderer` hook, rather than `frappe.whitelist`. This keeps the API
on a clean `/huf/api/v1/<endpoint>` path (no `/api/method/...` prefix)
and gives Phase 2+ endpoints a single dispatch point to add to.

Each endpoint is a plain callable `(context: RequestContext) -> dict`.
Static (parameter-free) routes are looked up in `_STATIC_ENDPOINTS`;
path-templated routes (e.g. `/agents/{agent_id}`) are matched in order
against `_PATH_ENDPOINTS`. The renderer resolves the principal, builds
the `RequestContext`, calls the matched handler, and wraps the result
(or any `ApiError`) in the standard response envelope.
"""

import json

import frappe
from frappe.website.page_renderers.base_renderer import BaseRenderer

from huf.api.v1.auth import resolve_principal
from huf.api.v1.context import AuthMode, RequestContext
from huf.api.v1.endpoints.agents import handle_get_agent, handle_list_agents
from huf.api.v1.endpoints.conversations import (
	handle_create_conversation,
	handle_get_conversation,
	handle_list_conversations,
	handle_list_messages,
)
from huf.api.v1.endpoints.identity import handle_me
from huf.api.v1.endpoints.responses import handle_create_response
from huf.api.v1.endpoints.responses_stream import handle_stream_response
from huf.api.v1.endpoints.runs import handle_get_run
from huf.api.v1.errors import ApiError, NotFoundError, ValidationError, error_response
from huf.api.v1.responses import success_response

ROUTE_PREFIX = "huf/api/v1/"


def _handle_ping(context: RequestContext) -> dict:
	"""GET /huf/api/v1/ping - unauthenticated health check."""
	return {"status": "ok", "version": "v1"}


def _handle_conversations(context: RequestContext) -> dict:
	"""POST creates a conversation, GET lists the caller's own conversations."""
	if frappe.request and frappe.request.method == "POST":
		payload = frappe.local.form_dict
		agent_id = payload.get("agent_id") or payload.get("agent")
		if not agent_id:
			raise ValidationError("agent_id is required to create a conversation.")
		return handle_create_conversation(context, agent_id=agent_id, title=payload.get("title"))
	return handle_list_conversations(context, agent_id=frappe.local.form_dict.get("agent_id"))


def _handle_responses(context: RequestContext) -> dict:
	"""POST /huf/api/v1/responses - run an agent turn (sync, queue-first)."""
	payload = frappe.local.form_dict
	agent_id = payload.get("agent_id") or payload.get("agent")
	input_text = payload.get("input") or payload.get("input_text") or payload.get("prompt")
	if not agent_id:
		raise ValidationError("agent_id is required.")
	if not input_text:
		raise ValidationError("input is required.")
	return handle_create_response(
		context, agent_id=agent_id, input_text=input_text, conversation_id=payload.get("conversation_id")
	)


# Static (parameter-free) endpoints: route suffix -> (handler, requires_auth).
# Every handler is called as `handler(context)`.
_STATIC_ENDPOINTS = {
	"ping": (_handle_ping, False),
	"me": (lambda context: handle_me(context), True),
	"agents": (lambda context: handle_list_agents(context), True),
	"conversations": (_handle_conversations, True),
	"responses": (_handle_responses, True),
}

# Path-templated routes, matched in order after the static table misses.
# Each entry: (matcher(segments) -> bool, handler(context, segments) -> dict, requires_auth).
_PATH_ENDPOINTS = [
	(
		lambda s: len(s) == 3 and s[0] == "conversations" and s[2] == "messages",
		lambda context, s: handle_list_messages(context, s[1]),
		True,
	),
	(
		lambda s: len(s) == 2 and s[0] == "conversations",
		lambda context, s: handle_get_conversation(context, s[1]),
		True,
	),
	(
		lambda s: len(s) == 2 and s[0] == "agents",
		lambda context, s: handle_get_agent(context, s[1]),
		True,
	),
	(
		lambda s: len(s) == 2 and s[0] == "runs",
		lambda context, s: handle_get_run(context, s[1]),
		True,
	),
]


def _wants_stream(payload) -> bool:
	return str(payload.get("stream", "")).strip().lower() in ("1", "true", "yes")


def _match_route(endpoint: str):
	"""Resolve `endpoint` (the path after ROUTE_PREFIX) to a (handler, requires_auth) pair.

	`handler` is always callable as `handler(context)`. Returns None if no route matches.
	"""
	static_entry = _STATIC_ENDPOINTS.get(endpoint)
	if static_entry is not None:
		return static_entry

	segments = [s for s in endpoint.split("/") if s]
	for matches, handler, requires_auth in _PATH_ENDPOINTS:
		if matches(segments):
			return (lambda context, _h=handler, _s=segments: _h(context, _s)), requires_auth

	return None


class ApiV1Router(BaseRenderer):
	"""Page renderer that dispatches requests under `/huf/api/v1/<endpoint>`."""

	def can_render(self) -> bool:
		"""Determine if this renderer should handle the current path."""
		return self.path == "huf/api/v1" or self.path.startswith(ROUTE_PREFIX)

	def render(self):
		"""Resolve the endpoint, build a RequestContext, and dispatch."""
		endpoint = frappe.form_dict.get("endpoint")
		if not endpoint and self.path.startswith(ROUTE_PREFIX):
			endpoint = self.path[len(ROUTE_PREFIX):]
		endpoint = (endpoint or "").strip("/")

		route = _match_route(endpoint)
		fallback_request_id = RequestContext(
			user=frappe.session.user, auth_mode=AuthMode.SESSION
		).request_id

		if route is None:
			return self._render_error(NotFoundError(f"Unknown endpoint: '{endpoint}'"), fallback_request_id)

		handler, requires_auth = route

		try:
			context = self._build_context(requires_auth)

			if endpoint == "responses" and _wants_stream(frappe.local.form_dict):
				payload = frappe.local.form_dict
				agent_id = payload.get("agent_id") or payload.get("agent")
				input_text = payload.get("input") or payload.get("input_text") or payload.get("prompt")
				if not agent_id:
					raise ValidationError("agent_id is required.")
				if not input_text:
					raise ValidationError("input is required.")
				return handle_stream_response(
					context,
					agent_id=agent_id,
					input_text=input_text,
					conversation_id=payload.get("conversation_id"),
				)

			data = handler(context)
			return self._render_success(data, context.request_id)
		except ApiError as exc:
			return self._render_error(exc, fallback_request_id)
		except Exception as exc:
			frappe.log_error(frappe.get_traceback(), "Huf API v1 Router Error")
			generic_error = ApiError(f"Internal error. Request ID: {fallback_request_id}")
			return self._render_error(generic_error, fallback_request_id)

	def _build_context(self, requires_auth: bool) -> RequestContext:
		"""Resolve the request's principal, or fall back to an anonymous
		Guest context for endpoints that do not require auth."""
		if not requires_auth:
			try:
				return resolve_principal(frappe.request)
			except ApiError:
				return RequestContext(user=frappe.session.user, auth_mode=AuthMode.SESSION)

		# For auth-required endpoints, AuthenticationError propagates to the
		# caller (render()), which supplies its own fallback request_id.
		return resolve_principal(frappe.request)

	def _render_success(self, data: dict, request_id: str):
		body = success_response(data, request_id)
		headers = {"Content-Type": "application/json; charset=utf-8"}
		return self.build_response(json.dumps(body), headers=headers)

	def _render_error(self, exc: ApiError, request_id: str = None):
		body = error_response(exc, request_id=request_id)
		headers = {"Content-Type": "application/json; charset=utf-8"}
		return self.build_response(
			json.dumps(body), headers=headers, http_status_code=exc.status_code
		)
