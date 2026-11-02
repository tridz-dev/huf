"""Safe document creation for the ``doc.create`` Flow node.

Policy:
* The doctype must be in the allow-list: site config key ``huf_flow_create_doc_doctypes`` (a list),
  default ``["ToDo"]``. The doctype is a literal in the node config (never a reference).
* The insert runs as the session user of the run, with normal permission checks
  (``has_permission(create)`` then a plain ``doc.insert()``): never ``ignore_permissions``.
* Only plain data fields can be set: the field must exist on the doctype, not be read-only, not be a
  layout/Table field, not be a system field (name, owner, docstatus, ...), and the value must be a
  scalar (string/number/bool/null) of bounded length.
"""

from __future__ import annotations

from typing import Any, Iterable

import frappe

CONF_KEY = "huf_flow_create_doc_doctypes"
DEFAULT_DOCTYPES = ["ToDo"]
MAX_FIELD_CHARS = 5_000
MAX_FIELDS = 30

SYSTEM_FIELDS = frozenset(
	{
		"name", "doctype", "owner", "creation", "modified", "modified_by", "docstatus", "idx",
		"parent", "parentfield", "parenttype", "amended_from", "_assign", "_comments", "_liked_by", "_user_tags",
	}
)
BLOCKED_FIELDTYPES = frozenset(
	{
		"Table", "Table MultiSelect", "Section Break", "Column Break", "Tab Break", "HTML", "Button",
		"Heading", "Fold", "Image", "Attach", "Attach Image", "Signature", "Geolocation",
	}
)


class CreateDocError(ValueError):
	"""The doc.create request is not allowed or is malformed."""


def allowed_doctypes(conf: Any) -> list[str]:
	value = conf.get(CONF_KEY) if hasattr(conf, "get") else None
	if isinstance(value, (list, tuple)) and value and all(isinstance(v, str) and v for v in value):
		return list(value)
	return list(DEFAULT_DOCTYPES)


def check_doctype(doctype: Any, allowed: Iterable[str]) -> str:
	if not isinstance(doctype, str) or not doctype:
		raise CreateDocError("Choose which kind of record this step should create.")
	if doctype not in list(allowed):
		raise CreateDocError(
			f'This step is not allowed to create "{doctype}" records on this site. Choose another kind of record, or ask an admin to allow it.'
		)
	return doctype


def validate_fields(meta_fields: Iterable[Any], fields: Any) -> dict:
	if not isinstance(fields, dict):
		raise CreateDocError("The details for the new record are not filled in correctly. Open the step and set each field again.")
	if len(fields) > MAX_FIELDS:
		raise CreateDocError(f"A step can fill in at most {MAX_FIELDS} fields of a new record. Remove some of them.")
	by_name = {f.fieldname: f for f in meta_fields}
	out = {}
	for key, value in fields.items():
		if key in SYSTEM_FIELDS:
			raise CreateDocError(f'The field "{key}" is set by the system, so this step cannot fill it in. Remove it from the step.')
		field = by_name.get(key)
		if field is None:
			raise CreateDocError(f'This kind of record has no field called "{key}". Open the step and pick the fields again.')
		if getattr(field, "read_only", 0) or field.fieldtype in BLOCKED_FIELDTYPES:
			raise CreateDocError(f'The field "{key}" cannot be filled in by a flow. Remove it from the step.')
		if value is not None and not isinstance(value, (str, int, float, bool)):
			raise CreateDocError(f'The field "{key}" needs a single text, number or yes/no value, not a list or a record. Pick a single value.')
		if isinstance(value, str) and len(value) > MAX_FIELD_CHARS:
			raise CreateDocError(f'The value for "{key}" is longer than {MAX_FIELD_CHARS} characters. Use a shorter value.')
		out[key] = value
	return out


def create_document(doctype: Any, fields: Any) -> dict:
	"""Insert the document as the current session user; return ``{"doctype", "name"}``."""
	doctype = check_doctype(doctype, allowed_doctypes(frappe.conf))
	if not frappe.has_permission(doctype, "create"):
		raise frappe.PermissionError(f"Not permitted to create {doctype} as {frappe.session.user}")
	clean = validate_fields(frappe.get_meta(doctype).fields, fields)
	doc = frappe.get_doc({"doctype": doctype, **clean})
	doc.insert()
	return {"doctype": doctype, "name": doc.name}
