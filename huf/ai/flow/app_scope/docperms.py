"""Sync the ``huf_flow_app_access`` hook into Custom DocPerm rows (run from ``after_migrate``).

Rows granted, at permlevel 0 only:

- Flow Definition: read for ``view`` roles, read and write for ``edit`` roles.
- Agent Flow Run and Flow Member State: nothing. They hold raw payloads, so app roles read runs only through the
  masked flow APIs; rows synced for them by an earlier version are removed here.

Never create, delete, share, export, import, report or permlevel 1 (``definition_json`` is saved for editors only
through :mod:`huf.ai.flow.app_scope.drafts`). The scope to ``owner_app`` is applied
by :mod:`huf.ai.flow.app_scope.access`. Rows are upserted (no duplicates on a re-run). A role that was synced
earlier and is no longer declared loses its rows. The synced set is kept in a global default.
"""

import json

import frappe
from frappe.permissions import setup_custom_perms

from huf.ai.flow.app_scope.access import app_grants

STATE_KEY = "huf_flow_app_access_synced"
_FLAGS = (
	"read", "write", "create", "delete", "submit", "cancel", "amend", "report", "export", "import",
	"share", "print", "email", "select", "if_owner",
)  # fmt: skip


def desired_rows() -> dict[tuple[str, str], dict]:
	"""``{(doctype, role): {"read": 1, "write": 0|1}}`` from the installed apps' grants."""
	rows = {}
	for per_action in app_grants().values():
		for role in per_action["view"]:
			if not frappe.db.exists("Role", role):
				continue
			write = 1 if role in per_action["edit"] else 0
			prev = rows.get(("Flow Definition", role), {"write": 0})
			rows[("Flow Definition", role)] = {"read": 1, "write": max(write, prev["write"])}
	return rows


def _synced() -> set[tuple[str, str]]:
	raw = frappe.db.get_default(STATE_KEY)
	try:
		return {tuple(x) for x in json.loads(raw or "[]")}
	except (TypeError, ValueError):
		return set()


def sync_app_flow_docperms() -> None:
	want = desired_rows()
	previous = _synced()
	touched = set()
	for (doctype, role), flags in want.items():
		setup_custom_perms(doctype)
		_upsert(doctype, role, flags)
		touched.add(doctype)
	for doctype, role in previous - set(want):
		frappe.db.delete("Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0})
		touched.add(doctype)
	frappe.db.set_default(STATE_KEY, json.dumps(sorted([list(k) for k in want])))
	for doctype in touched:
		frappe.clear_cache(doctype=doctype)


def _upsert(doctype: str, role: str, flags: dict) -> None:
	values = {f: 0 for f in _FLAGS} | flags
	names = frappe.get_all(
		"Custom DocPerm", filters={"parent": doctype, "role": role, "permlevel": 0}, pluck="name"
	)
	if names:
		frappe.db.set_value("Custom DocPerm", names[0], values)
		for extra in names[1:]:
			frappe.db.delete("Custom DocPerm", {"name": extra})
		return
	frappe.get_doc(
		{
			"doctype": "Custom DocPerm",
			"parent": doctype,
			"parenttype": "DocType",
			"parentfield": "permissions",
			"role": role,
			"permlevel": 0,
			**values,
		}
	).insert(ignore_permissions=True)
