"""What a data trigger adds to a run so a flow can read "Customer > Credit limit" (see ``doc_fields``)."""

import json

import frappe

from huf.ai.flow.catalog.doc_fields import LINK_KEY, link_targets, plain_fields

__all__ = ["LINK_KEY", "linked_values"]


def linked_values(doc, owner: str, filter_row) -> dict:
	"""Plain fields of the records a document links to: ``{link fieldname: {field: value}}``.

	Only the first few Link fields, only records ``owner`` may open, and only the fields the "Use data" picker offers
	(``plain_fields``) after ``filter_row`` (the trigger's own permission-level filter) has run. Never raises: a missing
	or unreadable link is just left out.
	"""
	out: dict = {}
	try:
		for fieldname, _label, linked_doctype in link_targets(frappe.get_meta(doc.doctype).fields):
			name = doc.get(fieldname)
			if not name or not isinstance(name, str):
				continue
			try:
				if not frappe.has_permission(linked_doctype, "read", doc=name, user=owner):
					continue
				row = filter_row(json.loads(frappe.as_json(frappe.get_cached_doc(linked_doctype, name).as_dict())), linked_doctype, owner)
				wanted = {df.fieldname for df in plain_fields(frappe.get_meta(linked_doctype).fields)}
				out[fieldname] = {k: v for k, v in row.items() if k in wanted and not isinstance(v, (dict, list))}
			except Exception:
				continue
	except Exception:
		return {}
	return out
