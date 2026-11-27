"""Which Gateways the editors of an app-owned flow may pick.

An app names them in its own ``hooks.py``::

	huf_flow_app_gateways = {"<app>": "<dotted path>"}

The function is called as ``handler(app=..., user=...)`` and returns a list of Gateway names. It is read only from the
hooks of the app it names. Fails closed: no hook, an exception, a bad path or any other answer means no Gateway is
offered, so a flow keeps only the ones it already stores. Several paths: a name must be in every answer.
Privileged users (:func:`huf.ai.flow.app_scope.access.is_privileged`) are not limited by this.
"""

import frappe

HOOK = "huf_flow_app_gateways"


def app_gateways(app: str, user: str) -> set[str]:
	"""The Gateway names ``app`` lets ``user`` pick; empty when it says nothing or its answer cannot be trusted."""
	path = None
	try:
		paths = (frappe.get_hooks(HOOK, app_name=app) or {}).get(app) or []
		allowed = None
		for path in [paths] if isinstance(paths, str) else paths:
			names = frappe.get_attr(path)(app=app, user=user)
			if not isinstance(names, list | tuple) or not all(isinstance(n, str) for n in names):
				frappe.logger("huf").warning(f"{HOOK} {path}: not a list of names; none offered")
				return set()
			allowed = set(names) if allowed is None else allowed & set(names)
		return allowed or set()  # noqa: TRY300
	except Exception as exc:  # noqa: BLE001 - any failure offers nothing; the message may carry data, so only the class
		frappe.logger("huf").warning(f"{HOOK} {path or app}: {type(exc).__name__}; none offered")
		return set()
