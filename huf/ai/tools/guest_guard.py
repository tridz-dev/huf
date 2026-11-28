"""Scope checks for a Guest tool call that is about to run with ``ignore_permissions``.

With permissions off, the tool's pinned ``reference_doctype`` is the only thing that bounds
what the model can reach, so every caller-chosen doctype or field is checked against it here.
Shared by the agent path (``huf.ai.sdk_tools``) and the deterministic path
(``huf.ai.tools.invocation``). Signed-in callers never come through here.
"""

import frappe

# Handlers of these types take the doctype as ``doctype``, not ``reference_doctype``.
_VALUE_TYPES = ("Get Value", "Set Value")

# Added to the call by the server (run context); handlers do not treat them as document data.
_CONTEXT_KEYS = frozenset({"conversation_id", "agent_run_id", "agent_name", "call_id"})

# Never writable by a Guest, whether or not a doctype declares a field of the same name.
_SYSTEM_KEYS = frozenset({
	"doctype", "name", "owner", "creation", "modified", "modified_by", "docstatus", "idx",
	"parent", "parenttype", "parentfield", "flags",
})

_READABLE_SYSTEM_FIELDS = frozenset({"name", "creation", "modified", "docstatus", "idx"})


def guest_scope_error(tool_type: str | None, extra_args: dict, args: dict) -> str | None:
	"""Why this Guest call must be refused, or None. Pins ``args["doctype"]`` for value tools."""
	doctype = extra_args.get("reference_doctype")
	if not doctype:
		return None  # unpinned document types are refused by the caller; other types take no doctype

	if tool_type in _VALUE_TYPES:
		if args.get("doctype") not in (None, "", doctype):
			return f"Guest access to this tool is limited to {doctype}."
		args["doctype"] = doctype

	if tool_type == "Get Value":
		fields = args.get("fieldname")
		fields = fields if isinstance(fields, list) else [fields]
		if not _readable(doctype, [f for f in fields if f]) or not _filters_stay_on(doctype, args.get("filters")):
			return _field_error(doctype)

	elif tool_type == "Set Value":
		field = args.get("fieldname")
		if not _filters_stay_on(doctype, args.get("filters")) or (
			field and not _writable(doctype, {field: args.get("value")})
		):
			return _field_error(doctype)

	elif tool_type == "Get List":
		if not _filters_stay_on(doctype, args.get("filters")) or not _order_stays_on(args.get("order_by")):
			return _field_error(doctype)

	elif tool_type == "Create Document":
		data = {k: v for k, v in args.items() if k not in ("reference_doctype", "doc")}
		wrapper = args.get("doc")
		if isinstance(wrapper, dict):
			data.update(wrapper)
		elif "doc" in args:
			data["doc"] = wrapper
		if not _writable(doctype, _without_context(doctype, data)):
			return _field_error(doctype)

	elif tool_type == "Update Document":
		data = args.get("data")
		if data is None:
			named = ("document_id", "reference_doctype", "data")
			data = _without_context(doctype, {k: v for k, v in args.items() if k not in named})
		if not isinstance(data, dict) or not _writable(doctype, data):
			return _field_error(doctype)

	return None


def _field_error(doctype: str) -> str:
	return f"Guest access to this tool is limited to the data fields of {doctype}."


def _without_context(doctype: str, data: dict) -> dict:
	meta = frappe.get_meta(doctype)
	return {k: v for k, v in data.items() if k not in _CONTEXT_KEYS or meta.get_field(k)}


def _data_field(meta, fieldname):
	"""The doctype's own permlevel 0 field of this name, else None (Guest holds no higher level)."""
	if not isinstance(fieldname, str) or fieldname in _SYSTEM_KEYS:
		return None
	df = meta.get_field(fieldname)
	return df if df and not df.permlevel else None


def _writable(doctype: str, data: dict) -> bool:
	meta = frappe.get_meta(doctype)
	for fieldname, value in data.items():
		df = _data_field(meta, fieldname)
		if not df:
			return False
		if df.fieldtype in ("Table", "Table MultiSelect"):
			rows = value or []
			if not isinstance(rows, list) or not all(
				isinstance(row, dict) and _writable(df.options, row) for row in rows
			):
				return False
	return True


def _readable(doctype: str, fields: list) -> bool:
	meta = frappe.get_meta(doctype)
	for fieldname in fields:
		if not isinstance(fieldname, str):
			return False
		if fieldname in _READABLE_SYSTEM_FIELDS:
			continue
		df = _data_field(meta, fieldname)
		if not df or df.fieldtype == "Password":
			return False
	return True


def _is_plain(fieldname) -> bool:
	"""A bare column name: no link traversal, table prefix or expression."""
	return isinstance(fieldname, str) and fieldname.isidentifier()


def _filters_stay_on(doctype: str, filters) -> bool:
	"""Filters (a record name, a dict, or a list of conditions) name only this doctype's columns."""
	if not filters or isinstance(filters, str | int):
		return True
	if isinstance(filters, dict):
		# Get List accepts "field operator" keys.
		return all(isinstance(k, str) and k.split() and _is_plain(k.split()[0]) for k in filters)
	if not isinstance(filters, list):
		return False
	for row in filters:
		if not isinstance(row, list) or len(row) not in (3, 4):
			return False
		if len(row) == 4 and row[0] != doctype:
			return False
		if not _is_plain(row[-3]):
			return False
	return True


def _order_stays_on(order_by) -> bool:
	if not order_by:
		return True
	if not isinstance(order_by, str):
		return False
	for part in order_by.split(","):
		words = part.split()
		if not 1 <= len(words) <= 2 or not _is_plain(words[0]):
			return False
		if len(words) == 2 and words[1].lower() not in ("asc", "desc"):
			return False
	return True
