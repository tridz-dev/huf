"""Page renderer for public/guest access to a HUF App via its alias.

Structural pattern mirrors huf.ai.agent_stream_renderer.AgentStreamRenderer
(BaseRenderer subclass, can_render()/render() only, no __init__ override —
the base class already wires self.path from the resolved endpoint).

Route: `/huf/apps/<alias>` -> resolved to a `HUF App` with `is_public=1`,
`enabled=1`, whose linked Agent also has `allow_guest=1` (checked via the
shared huf.ai.agent_access.check_agent_access, exactly as run_agent_sync
already gates guest text-chat access, A.8/D.9). Both gates must pass.

Anti-enumeration: "no such public app", "app exists but is disabled", and
"app is public but its Agent doesn't allow guests" all resolve to the exact
same frappe.PageDoesNotExistError outcome (NotFoundPage, via
frappe.website.serve.handle_exception) — mirrors the deliberate
same-error-on-every-rejection convention in
huf.ai.voice.api.start_public_session (see its docstring: "Same
PermissionError as every other rejection in this function, so an
unauthenticated caller can't use the response to enumerate valid Agent
docnames"). Do not add a distinct error path for the "agent denies guest"
case — that would leak the existence of a public-but-guest-denied app.
"""

import frappe
from frappe.website.page_renderers.base_renderer import BaseRenderer
from frappe.website.page_renderers.template_page import TemplatePage

from huf.ai.agent_access import check_agent_access

APP_ROUTE_PREFIX = "huf/apps/"


class HufAppPublicRenderer(BaseRenderer):
	"""Page renderer that serves the SPA shell for a public HUF App by alias.

	Routes:
	- `/huf/apps/<alias>` - resolves alias -> HUF App -> Agent, and, only if
	  both `HUF App.is_public` and the Agent's `allow_guest` are true, renders
	  the same SPA shell `/huf` already serves (delegating to the existing
	  `huf` TemplatePage/`www/huf.py:get_context` Guest-branching logic rather
	  than reimplementing boot-data construction here).
	"""

	def can_render(self) -> bool:
		"""Determine if this renderer should handle the current path."""
		return self.path == APP_ROUTE_PREFIX.rstrip("/") or self.path.startswith(APP_ROUTE_PREFIX)

	def render(self):
		alias = frappe.form_dict.get("app_alias")

		if not alias and self.path.startswith(APP_ROUTE_PREFIX):
			alias = self.path[len(APP_ROUTE_PREFIX):]

		if not alias:
			raise frappe.PageDoesNotExistError

		app = frappe.db.get_value(
			"HUF App",
			{"alias": alias, "is_public": 1, "enabled": 1},
			["name", "agent"],
			as_dict=True,
		)
		if not app or not app.agent:
			# Same outcome as "no such alias" — do not distinguish
			# disabled/non-public apps from genuinely nonexistent ones.
			raise frappe.PageDoesNotExistError

		try:
			agent_doc = frappe.get_doc("Agent", app.agent)
		except frappe.DoesNotExistError:
			raise frappe.PageDoesNotExistError

		if not check_agent_access(agent_doc, user="Guest"):
			# Deliberately identical to the "not found" branches above: a
			# public App backed by a guest-denying Agent must not be
			# distinguishable, from the outside, from an App that doesn't
			# exist at all (anti-enumeration, mirrors
			# huf.ai.voice.api.start_public_session).
			raise frappe.PageDoesNotExistError

		# Both gates passed — serve the same SPA shell `/huf` serves,
		# reusing www/huf.py:get_context's existing Guest-branching boot
		# logic rather than reimplementing it.
		return TemplatePage("huf", self.http_status_code).render()
