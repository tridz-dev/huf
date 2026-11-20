"""All-or-nothing replace import for Huf data tables (split out of import_export.py)."""

import re

import frappe
from frappe import _

from .import_security import strip_reserved


def validate_replace_batch(doctype_name, records):
	"""Build and validate every doc up front. Returns (docs, rejected). Writes nothing."""
	unique_fields = [f.fieldname for f in frappe.get_meta(doctype_name).fields if f.get("unique")]
	seen = {fn: {} for fn in unique_fields}
	docs, rejected = [], []
	for rownum, rec, raw in records:
		try:
			doc = frappe.get_doc({**strip_reserved(rec), "doctype": doctype_name})
			doc.run_method("before_validate")
			doc.run_method("validate")
			for fn in unique_fields:
				val = doc.get(fn)
				if val in (None, ""):
					continue
				if val in seen[fn]:
					raise frappe.ValidationError(
						str(_("{0} '{1}' duplicates row {2}").format(fn, val, seen[fn][val]))
					)
				seen[fn][val] = rownum
			docs.append((rownum, doc, raw))
		except Exception as e:
			rejected.append((rownum, re.sub(r"<[^>]+>", "", str(e)), raw))
	return docs, rejected


def do_replace(doctype_name, headers, records, rejected, _result):
	"""All-or-nothing replace: validate everything, then delete+insert under one savepoint."""
	docs, bad = validate_replace_batch(doctype_name, records)
	rejected = sorted([*rejected, *bad], key=lambda t: t[0])
	if rejected:
		return _result(0, 0, rejected, headers, note=str(_("Nothing replaced: fix the rejected rows first.")))
	frappe.db.savepoint("huf_replace")
	try:
		for name in frappe.get_all(doctype_name, pluck="name", limit_page_length=0):
			frappe.delete_doc(doctype_name, name, force=True)
		for _rownum, doc, _raw in docs:
			doc.insert()
	except Exception as e:
		frappe.db.rollback(save_point="huf_replace")
		fail = [(0, re.sub(r"<[^>]+>", "", str(e)), [])]
		return _result(0, 0, fail, headers, note=str(_("Nothing replaced: the import failed and was rolled back.")))
	return _result(len(docs), 0, [], headers)
