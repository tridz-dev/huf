"""``doc.get`` and ``doc.update`` nodes: read or change one existing document as the run's user.

Policy (same shape as ``doc.create``, see :mod:`huf.ai.flow.create_doc`):
* The doctype must be declared in the flow's permission envelope (read for ``doc.get``, write for
  ``doc.update``) and the run's user must have the matching permission. Nothing uses ``ignore_permissions``.
* Only plain data fields are read or set (field must exist, not be a layout/Table field; values are scalars).
* ``doc.update`` never submits, cancels or changes a submitted document, and counts against the graph's
  ``limits.max_writes`` like ``doc.create`` does.

``doc.get`` config: ``doctype``, ``name`` or ``filters`` (one dict), ``fields`` (list, default ``["name"]``),
``on_missing`` (``error`` | ``empty``, default ``error``). Output ``{"doc": {...}}``, or ``{"found": False}``
when ``on_missing`` is ``empty``.

``doc.update`` config: ``doctype``, ``name``, ``values`` (object of field values). Output ``{"doctype", "name"}``.
"""

from __future__ import annotations

import frappe

from huf.ai.flow import create_doc as flow_create_doc
from huf.ai.graph.permissions import envelope_declares

GET_KEYS = frozenset({"doctype", "name", "filters", "fields", "on_missing"})
UPDATE_KEYS = frozenset({"doctype", "name", "values"})
META_FIELDS = frozenset({"name", "owner", "creation", "modified"})
ON_MISSING = ("error", "empty")
VERBS = {"read": "read", "write": "change"}


def _failed(message: str) -> dict:
	return {"status": "failed", "error": message}


def _run_policy(run_ctx) -> tuple[dict, dict]:
	contract = (run_ctx.definition.get("contract") or {}) if run_ctx is not None else {}
	return contract.get("permission_envelope") or {}, contract.get("limits") or {}


def _access_error(doctype, ptype: str, envelope: dict) -> str | None:
	"""Why the run may not ``ptype`` this doctype, or None when it may."""
	if not isinstance(doctype, str) or not doctype:
		return "Choose which kind of record this step should use."
	verb = VERBS[ptype]
	if not envelope_declares(envelope, ptype=ptype, doctype=doctype):
		return f'This step is not allowed to {verb} "{doctype}" records. Ask an admin to allow it for this flow.'
	if not frappe.db.exists("DocType", doctype) or not frappe.has_permission(doctype, ptype):
		return f'You do not have permission to {verb} "{doctype}" records. Ask an admin for access.'
	return None


def _readable_fields(doctype: str, requested) -> list[str] | str:
	if requested is None:
		return ["name"]
	if not isinstance(requested, list) or not requested or len(requested) > flow_create_doc.MAX_FIELDS:
		return f"Pick between 1 and {flow_create_doc.MAX_FIELDS} fields to read from the record."
	by_name = {f.fieldname: f for f in frappe.get_meta(doctype).fields}
	for key in requested:
		if key in META_FIELDS:
			continue
		field = by_name.get(key) if isinstance(key, str) else None
		if field is None:
			return f'This kind of record has no field called "{key}". Open the step and pick the fields again.'
		if field.fieldtype in flow_create_doc.BLOCKED_FIELDTYPES:
			return f'The field "{key}" cannot be read by a flow. Remove it from the step.'
	return list(requested)


def exec_doc_get(node: dict, config: dict, context, run_ctx) -> dict:
	unknown = sorted(set(config) - GET_KEYS)
	if unknown or "doctype" not in config:
		return _failed("Choose the kind of record to read, and remove any settings this step does not use.")
	doctype = config["doctype"]
	on_missing = config.get("on_missing", "error")
	if on_missing not in ON_MISSING:
		return _failed('Choose what happens when no record is found: "error" or "empty".')
	envelope, _limits = _run_policy(run_ctx)
	if error := _access_error(doctype, "read", envelope):
		return _failed(error)

	name = context.resolve(config["name"]) if "name" in config else None
	filters = context.resolve(config["filters"]) if "filters" in config else None
	if (name is None) == (filters is None):
		return _failed("Find the record either by its name or by one filter, not both. Open the step and pick one.")
	if name is not None:
		if not isinstance(name, str) or not name:
			return _failed("Choose the record to read by its name.")
		filters = {"name": name}
	elif not isinstance(filters, dict) or not filters or len(filters) > flow_create_doc.MAX_FIELDS:
		return _failed("Set the filter to find the record with, as field and value pairs.")

	fields = _readable_fields(doctype, config.get("fields"))
	if isinstance(fields, str):
		return _failed(fields)

	rows = frappe.get_list(doctype, filters=filters, fields=fields, limit=2)
	if len(rows) > 1:
		return _failed(f'More than one "{doctype}" record matches. Use a filter that picks exactly one record.')
	if not rows:
		if on_missing == "empty":
			return {"status": "success", "result": {"found": False}, "output": {"found": False}}
		return _failed(f'No "{doctype}" record matches. Check the name or filter in this step.')
	out = {"doc": rows[0]}
	return {"status": "success", "result": out, "output": out}


def exec_doc_update(node: dict, config: dict, context, run_ctx) -> dict:
	from huf.ai.flow.engine import _WRITES_KEY  # the write budget is shared with doc.create

	unknown = sorted(set(config) - UPDATE_KEYS)
	if unknown or not {"doctype", "name", "values"} <= set(config):
		return _failed("Choose the record to change, its name and the fields to set, and remove any settings this step does not use.")
	doctype = config["doctype"]
	envelope, limits = _run_policy(run_ctx)
	if error := _access_error(doctype, "write", envelope):
		return _failed(error)
	max_writes = limits.get("max_writes") or 0
	done = context.get(_WRITES_KEY) or 0
	if done >= max_writes:
		return _failed(f"This flow is not allowed to change or create more records than this ({max_writes}). Ask an admin to raise the limit.")

	name = context.resolve(config["name"])
	values = context.resolve(config["values"])
	if not isinstance(name, str) or not name:
		return _failed("Choose the record to change by its name.")
	if not isinstance(values, dict) or not values:
		return _failed("Choose at least one field to change.")
	try:
		doc = frappe.get_doc(doctype, name)
		doc.check_permission("write")
		if doc.docstatus != 0:
			return _failed(f'"{name}" is submitted, so this step cannot change it.')
		clean = flow_create_doc.validate_fields(frappe.get_meta(doctype).fields, values)
	except frappe.DoesNotExistError:
		return _failed(f'No "{doctype}" record named "{name}" exists. Check the name in this step.')
	except frappe.PermissionError:
		return _failed(f'You do not have permission to change this "{doctype}" record. Ask an admin for access.')
	except flow_create_doc.CreateDocError as exc:
		return _failed(str(exc))
	doc.update(clean)
	doc.save()
	context.set(_WRITES_KEY, done + 1)
	out = {"doctype": doctype, "name": doc.name}
	return {"status": "success", "result": out, "output": out}
