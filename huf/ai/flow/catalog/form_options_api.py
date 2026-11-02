"""Lists the step forms of the Flow editor pick from (UX-12): which records "Create document" may make, which fields
they take, and which people may be named as approvers.

Everything here is read-only and is filtered by what the signed-in person may see, so a picker never offers something
the step would later refuse.
"""

from __future__ import annotations

import frappe
from frappe import _

from huf.ai.flow.create_doc import (
	BLOCKED_FIELDTYPES,
	SYSTEM_FIELDS,
	allowed_doctypes,
)
from huf.ai.flow.support.doctype_catalog import friendly_label

#: Field types a person fills with a plain value, by how the form should ask for them.
_KINDS = {
	"Check": "yesno",
	"Int": "number", "Float": "number", "Currency": "number", "Percent": "number", "Rating": "number",
	"Small Text": "longtext", "Text": "longtext", "Long Text": "longtext", "Text Editor": "longtext",
	"Markdown Editor": "longtext", "HTML Editor": "longtext", "Code": "longtext",
	"Date": "date", "Datetime": "date", "Time": "text",
	"Select": "choice",
}
MAX_USERS = 20


def _need_flow_read() -> None:
	if not frappe.has_permission("Flow Definition", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def create_document_types(conf, can_create) -> list[dict]:
	"""``[{name, label}]``: the allow-listed record types the person may create, ordered by label. Pure over ``conf``."""
	rows = []
	for name in allowed_doctypes(conf):
		if can_create(name):
			rows.append({"name": name, "label": friendly_label(name)})
	rows.sort(key=lambda r: r["label"].lower())
	return rows


def settable_fields(meta_fields) -> list[dict]:
	"""The fields of a record a "Create document" step may set, in the words people use. Required ones come first.

	Mirrors ``create_doc.validate_fields``: system fields, read-only fields, layout and attachment fields are left out, so
	the picker never offers a field the step would refuse at run time.
	"""
	out = []
	for df in meta_fields:
		name = getattr(df, "fieldname", None)
		ftype = getattr(df, "fieldtype", None)
		if not name or name in SYSTEM_FIELDS or name.startswith("_"):
			continue
		if getattr(df, "read_only", 0) or getattr(df, "hidden", 0) or ftype in BLOCKED_FIELDTYPES:
			continue
		kind = _KINDS.get(ftype, "text")
		options = []
		if kind == "choice":
			options = [o for o in str(getattr(df, "options", "") or "").split("\n") if o.strip()]
		out.append(
			{
				"fieldname": name,
				"label": " ".join(str(getattr(df, "label", None) or name.replace("_", " ").title()).split()),
				"fieldtype": ftype,
				"kind": kind,
				"required": bool(getattr(df, "reqd", 0)),
				"options": options,
			}
		)
	out.sort(key=lambda f: (not f["required"],))  # stable: required first, the form's own order after
	return out


@frappe.whitelist()
def get_create_document_types() -> list[dict]:
	"""Record types the "Create document" step can make for the signed-in person."""
	_need_flow_read()
	return create_document_types(frappe.conf, lambda dt: frappe.db.exists("DocType", dt) and frappe.has_permission(dt, "create"))


@frappe.whitelist()
def get_create_document_fields(doctype: str) -> list[dict]:
	"""The fields of ``doctype`` a "Create document" step may fill in (required first)."""
	_need_flow_read()
	if doctype not in allowed_doctypes(frappe.conf) or not frappe.db.exists("DocType", doctype):
		frappe.throw(_("Your administrator has not allowed flows to create {0} records.").format(doctype), frappe.PermissionError)
	if not frappe.has_permission(doctype, "create"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return settable_fields(frappe.get_meta(doctype).fields)


#: Looking people up is limited per person (they type into a search box: a handful of calls a minute is normal).
USER_LOOKUP_LIMIT = 60
USER_LOOKUP_WINDOW_S = 60


def _need_flow_edit_and_rate() -> None:
	"""People lookup is for the people who build flows (write on flows), and a person may ask 60 times a minute.

	Read access to a flow is not enough: the answer is the sign-in address of colleagues, which a viewer has no reason to see.
	"""
	import time

	if not frappe.has_permission("Flow Definition", "write"):
		frappe.throw(_("Only people who can edit flows can look up approvers."), frappe.PermissionError)
	key = f"huf:flow-user-lookup:{frappe.local.site}:{frappe.session.user}:{int(time.time() // USER_LOOKUP_WINDOW_S)}"
	try:
		cache = frappe.cache()
		count = cache.incr(key)
		if count == 1:
			cache.expire(key, USER_LOOKUP_WINDOW_S + 5)
	except Exception:
		return  # a cache hiccup must not stop people building flows
	if count > USER_LOOKUP_LIMIT:
		frappe.throw(_("You are looking people up very quickly. Wait a minute, then try again."), frappe.ValidationError)


def approver_role_names() -> list[str]:
	"""The roles that make someone an approver in a Human Approval step (Huf's own approver-capable roles). Empty if unknown."""
	try:
		from huf.ai.flow.api import _HUF_APPROVER_ROLES

		return list(_HUF_APPROVER_ROLES)
	except Exception:
		return []


def _holders(names: list[str]) -> set[str]:
	"""Which of ``names`` hold at least one approver role (one query)."""
	roles = approver_role_names()
	if not names or not roles:
		return set()
	rows = frappe.get_all("Has Role", filters={"parent": ("in", names), "parenttype": "User", "role": ("in", roles)}, pluck="parent", ignore_permissions=True, limit_page_length=0)
	return set(rows)


def _user_row(row: dict, holders: set[str] | None = None) -> dict:
	"""Only a name and an address. ``has_approver_role`` tells the form who would actually be allowed to approve."""
	full = " ".join(str(row.get("full_name") or "").split())
	email = row.get("email") or row["name"]
	out = {"name": row["name"], "email": email, "full_name": full or row["name"], "label": f"{full} ({email})" if full and full != email else email}
	if holders is not None:
		out["has_approver_role"] = row["name"] in holders
	return out


@frappe.whitelist()
def search_flow_users(query: str = "", limit: int = MAX_USERS) -> list[dict]:
	"""People who can be named as approvers: enabled, signed-in users (never Guest). ``[{name, email, full_name, label, has_approver_role}]``.

	For people who can edit flows only (viewers get a 403), at most 60 lookups a minute each, and nothing but a name and
	an address comes back. ``has_approver_role`` is true for someone who holds one of the approver roles.
	"""
	_need_flow_edit_and_rate()
	limit = max(1, min(int(limit or MAX_USERS), 50))
	text = " ".join(str(query or "").split())[:80]
	filters: dict = {"enabled": 1, "name": ("not in", ["Guest"]), "user_type": "System User"}
	or_filters = None
	if text:
		like = f"%{text}%"
		or_filters = [["name", "like", like], ["full_name", "like", like]]
	rows = frappe.get_all(
		"User", filters=filters, or_filters=or_filters, fields=["name", "full_name", "email"],
		order_by="full_name asc, name asc", limit_page_length=limit, ignore_permissions=True,
	)
	holders = _holders([r["name"] for r in rows])
	return [_user_row(r, holders) for r in rows]


@frappe.whitelist()
def check_flow_users(users) -> list[dict]:
	"""For each name in ``users``: ``{name, found, full_name}``. ``found`` is False for a name nobody has (a typo).

	Same rules as :func:`search_flow_users`: editors only, rate limited. Only enabled people count as found.
	"""
	_need_flow_edit_and_rate()
	if isinstance(users, str):
		import json

		try:
			users = json.loads(users)
		except ValueError:
			users = [u for u in users.split(",")]
	names = [str(u).strip() for u in (users or []) if str(u).strip()][:50]
	out = []
	for name in names:
		row = frappe.db.get_value("User", {"name": name, "enabled": 1, "user_type": "System User"}, ["name", "full_name"], as_dict=True)
		out.append({"name": row.name if row else name, "found": bool(row), "full_name": (row.full_name if row else None) or name})
	return out
