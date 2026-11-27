"""Host links for app-owned flows (D-HAPPIOL-EMBED decision 5).

An app declares ``huf_flow_app_links = {"<app>": "<dotted path>"}`` in its own hooks. The function receives
``(kind, flow_id, run_id=None)``, ``kind`` one of ``flow``, ``run``, ``approval``, and returns a site-relative
path. Every Huf-built link (approval email, bell entry, ``view_link``) for an app-owned flow goes through
:func:`flow_link`. A resolver that is missing, raises or returns something unsafe falls back to
:data:`SAFE_FALLBACK`, never ``/huf``. Huf-native flows keep their ``/huf/flows`` links.
"""

from __future__ import annotations

import frappe

from huf.ai.flow.app_scope.ownership import owner_app_of

HOOK = "huf_flow_app_links"
KINDS = ("flow", "run", "approval")
SAFE_FALLBACK = "/app"


def native_link(flow_id: str, run_id: str | None = None) -> str:
	return f"/huf/flows/{flow_id}?run={run_id}" if run_id else f"/huf/flows/{flow_id}"


def flow_link(kind: str, flow_id: str, run_id: str | None = None, owner_app: str | None = None) -> str:
	"""Site-relative link for ``(kind, flow, run)``: the owner app's host route, or the native Huf route."""
	owner = owner_app or owner_app_of(flow_id)
	if not owner:
		return native_link(flow_id, run_id)
	return _resolve(owner, kind, flow_id, run_id)


def _resolve(app: str, kind: str, flow_id: str, run_id: str | None) -> str:
	path = (frappe.get_hooks(HOOK, app_name=app) or {}).get(app)
	path = path[-1] if isinstance(path, list) and path else path
	if not isinstance(path, str) or not path:
		return _fallback(app, "no resolver declared")
	try:
		link = frappe.get_attr(path)(kind, flow_id, run_id)
	except Exception as exc:  # noqa: BLE001 - any resolver failure must fall back, never break a notification
		return _fallback(app, f"resolver raised {exc!r}")
	return link if _is_safe(link) else _fallback(app, "resolver returned an unsafe link")


def _fallback(app: str, reason: str) -> str:
	frappe.logger("huf").warning(f"Flow link resolver for app {app}: {reason}; using {SAFE_FALLBACK}")
	return SAFE_FALLBACK


def _is_safe(link) -> bool:
	"""Site-relative only (no scheme, no ``//host``), and never a Huf screen."""
	if not isinstance(link, str) or not link.startswith("/") or link.startswith("//") or "\\" in link:
		return False
	return not (
		link == "/huf" or link.startswith(("/huf/", "/huf?", "/app/agent-flow-run", "/app/flow-definition"))
	)
