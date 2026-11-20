"""CSV/XLSX import and CSV export for Huf data tables.

Large imports: files with more than ``INLINE_ROW_LIMIT`` (5,000) rows are not run
in the request. ``run_import`` enqueues ``_run_import_job`` on the "long" queue and
returns ``{"queued": True, "job_id": ...}``. The job stores its final result
(same shape as the inline result) in the cache under ``huf_import:<job_id>``, readable
via ``get_import_job_status(job_id)``, and also emits a ``huf_import_done`` realtime event.
Files above ``MAX_ROWS`` (50,000) are refused.
"""

import csv
import datetime
import io
import json
import re
import uuid

import frappe
from frappe import _

from .file_limits import check_import_file_size
from .import_security import _import_error, _max_import_bytes, check_xlsx_size, strip_reserved

MAX_ROWS = 50000
INLINE_ROW_LIMIT = 5000
SAMPLE_ROWS = 5
_SKIP_TYPES = {"Tab Break", "Section Break", "Column Break", "HTML", "Button", "Table", "Table MultiSelect"}
_NUMERIC = {"Int": int, "Float": float, "Currency": float, "Percent": float, "Rating": float}
_DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%m/%d/%Y")
_DATETIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f")
_TRUE = {"1", "true", "yes", "y", "checked", "on"}
_FALSE = {"0", "false", "no", "n", "unchecked", "off", ""}
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


# ---------------------------------------------------------------- pure logic

def parse_csv(raw: bytes | str):
	text = raw.decode("utf-8-sig", errors="replace") if isinstance(raw, bytes) else raw.lstrip("﻿")
	sample = text[:8192]
	try:
		dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
	except csv.Error:
		dialect = csv.excel
	rows = [r for r in csv.reader(io.StringIO(text), dialect)]
	return _split_header(rows)


def parse_xlsx(raw: bytes):
	try:
		import openpyxl
	except ImportError:
		frappe.throw(_("XLSX import is not available on this server. Upload a CSV instead."))
	check_xlsx_size(raw)
	wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
	try:
		ws = wb.worksheets[0]
		rows = []
		for r in ws.iter_rows(values_only=True):
			rows.append([_cell_to_str(c) for c in r])
			if len(rows) > MAX_ROWS + 1:
				break
	finally:
		wb.close()
	return _split_header(rows)


def _cell_to_str(c) -> str:
	if c is None:
		return ""
	if isinstance(c, datetime.datetime):
		return c.strftime("%Y-%m-%d %H:%M:%S") if (c.hour or c.minute or c.second) else c.strftime("%Y-%m-%d")
	if isinstance(c, datetime.date):
		return c.strftime("%Y-%m-%d")
	if isinstance(c, float) and c.is_integer():
		return str(int(c))
	return str(c)


def _split_header(rows):
	rows = [r for r in rows if any((c or "").strip() for c in r)]
	if not rows:
		return [], []
	headers = [(h or "").strip() for h in rows[0]]
	body = []
	for r in rows[1:]:
		r = list(r) + [""] * (len(headers) - len(r))
		body.append([(c or "").strip() for c in r[: len(headers)]])
	return headers, body


def _is_date(v: str) -> bool:
	return _parse_date(v) is not None


def _parse_date(v: str):
	for f in _DATE_FORMATS:
		try:
			return datetime.datetime.strptime(v, f).date()
		except ValueError:
			pass
	return None


def _parse_datetime(v: str):
	for f in _DATETIME_FORMATS:
		try:
			return datetime.datetime.strptime(v, f)
		except ValueError:
			pass
	d = _parse_date(v)
	return datetime.datetime.combine(d, datetime.time()) if d else None


def _is_number(v: str) -> bool:
	try:
		float(v.replace(",", ""))
		return True
	except ValueError:
		return False


def detect_type(values) -> str:
	vals = [v for v in values if v not in (None, "")]
	if not vals:
		return "text"
	low = {v.lower() for v in vals}
	if low <= {"0", "1", "true", "false", "yes", "no"} and low & {"true", "false", "yes", "no"}:
		return "checkbox"
	if all(_is_number(v) for v in vals):
		return "number"
	if all(_parse_datetime(v) for v in vals):
		return "date"
	return "text"


def auto_map(headers, fields) -> dict:
	"""Map header -> fieldname by fieldname or label, case-insensitive. Unmatched -> None."""
	by_key = {}
	for f in fields:
		by_key.setdefault(f["fieldname"].lower(), f["fieldname"])
	for f in fields:
		if f.get("label"):
			by_key.setdefault(f["label"].strip().lower(), f["fieldname"])
	by_key.setdefault("name", "name")
	used, out = set(), {}
	for h in headers:
		fn = by_key.get(h.strip().lower()) or by_key.get(frappe.scrub(h) if h else "")
		if fn in used:
			fn = None
		if fn:
			used.add(fn)
		out[h] = fn
	return out


def coerce_value(field: dict, raw: str):
	"""Return (value, error). field is a dict with fieldname, fieldtype, reqd, options."""
	ft = field["fieldtype"]
	v = (raw or "").strip()
	if v == "":
		if field.get("reqd") and ft != "Check":
			return None, _("{0} is required").format(field.get("label") or field["fieldname"])
		return (0 if ft == "Check" else None), None
	if ft == "Check":
		lv = v.lower()
		if lv in _TRUE:
			return 1, None
		if lv in _FALSE:
			return 0, None
		return None, _("{0}: '{1}' is not a valid checkbox value").format(field["fieldname"], v)
	if ft in _NUMERIC:
		try:
			n = float(v.replace(",", ""))
		except ValueError:
			return None, _("{0}: '{1}' is not a number").format(field["fieldname"], v)
		return (int(n) if ft == "Int" and n.is_integer() else n), (
			_("{0}: '{1}' is not a whole number").format(field["fieldname"], v)
			if ft == "Int" and not n.is_integer()
			else None
		)
	if ft == "Date":
		d = _parse_date(v) or (_parse_datetime(v).date() if _parse_datetime(v) else None)
		if not d:
			return None, _("{0}: '{1}' is not a valid date").format(field["fieldname"], v)
		return d.isoformat(), None
	if ft == "Datetime":
		d = _parse_datetime(v)
		if not d:
			return None, _("{0}: '{1}' is not a valid date/time").format(field["fieldname"], v)
		return d.strftime("%Y-%m-%d %H:%M:%S"), None
	if ft == "Select":
		opts = [o.strip() for o in (field.get("options") or "").split("\n") if o.strip()]
		if opts:
			match = next((o for o in opts if o.lower() == v.lower()), None)
			if match is None:
				return None, _("{0}: '{1}' is not one of {2}").format(field["fieldname"], v, ", ".join(opts))
			return match, None
	return v, None


def build_record(headers, row, mapping, fields_by_name):
	"""Return (record dict, [error messages]) for one body row."""
	rec, errors, seen = {}, [], set()
	for i, h in enumerate(headers):
		fn = mapping.get(h)
		if not fn or fn in seen:
			continue
		seen.add(fn)
		raw = row[i] if i < len(row) else ""
		if fn == "name":
			if raw:
				rec["name"] = raw
			continue
		field = fields_by_name.get(fn)
		if not field:
			continue
		val, err = coerce_value(field, raw)
		if err:
			errors.append(str(err))
		elif val is not None:
			rec[fn] = val
	for fn, field in fields_by_name.items():
		if field.get("reqd") and fn not in rec and fn not in seen and field["fieldtype"] != "Check":
			errors.append(str(_("{0} is required").format(field.get("label") or fn)))
	return rec, errors


def to_csv_text(headers, rows) -> str:
	buf = io.StringIO()
	w = csv.writer(buf, lineterminator="\n")
	w.writerow(headers)
	for r in rows:
		w.writerow([_csv_safe(c) for c in r])
	return buf.getvalue()


def _csv_safe(v):
	if v is None:
		return ""
	if isinstance(v, (datetime.datetime, datetime.date, datetime.timedelta)):
		return str(v)
	s = str(v)
	# Neutralise spreadsheet formula injection; leave plain negative numbers alone.
	if s.startswith(_FORMULA_PREFIXES) and not (s[0] in "+-" and _is_number(s)):
		return "'" + s
	return s


def rejected_to_csv(headers, rejected) -> str:
	"""rejected: list of (row_number, message, raw_row)."""
	return to_csv_text(["row", "error", *headers], [[n, m, *r] for n, m, r in rejected])


# ------------------------------------------------------------ frappe wrappers

def _can(cap: str) -> bool:
	from huf.permissions import has_capability

	return has_capability(frappe.session.user, cap)


def _require_import():
	if not any(_can(c) for c in ("data.tables.manage", "data.records.create", "data.records.edit_all", "data.records.edit_own")):
		frappe.throw(_("You don't have permission to import data."), frappe.PermissionError)


def _require_export():
	from .api import _require_read

	_require_read()


def _table_fields(doctype_name):
	meta = frappe.get_meta(doctype_name)
	return [
		{
			"fieldname": f.fieldname, "label": f.label, "fieldtype": f.fieldtype,
			"reqd": f.reqd, "options": f.options,
		}
		for f in meta.fields
		if f.fieldtype not in _SKIP_TYPES
	]


def _load(table_id, file_url):
	doctype_name = frappe.db.get_value("Huf Data Table", table_id, "doctype_name")
	if not doctype_name:
		frappe.throw(_("Table not found"), frappe.DoesNotExistError)
	url = str(file_url or "")
	if not url.startswith(("/files/", "/private/files/")) or ".." in url:
		_import_error()
	file_name = frappe.db.get_value("File", {"file_url": url}, "name") or _import_error()
	file_doc = frappe.get_doc("File", file_name)
	try:
		file_doc.check_permission("read")
	except frappe.PermissionError:
		_import_error()
	if file_doc.is_private and file_doc.owner != frappe.session.user and not _can("data.tables.manage"):
		_import_error()
	limit = _max_import_bytes()
	check_import_file_size(file_doc, limit)
	raw = file_doc.get_content()
	raw = raw.encode("utf-8") if isinstance(raw, str) else raw
	if len(raw) > limit:
		frappe.throw(_("The import file is too large."), frappe.ValidationError)
	fname = (file_doc.file_name or file_url).lower()
	headers, rows = parse_xlsx(raw) if fname.endswith((".xlsx", ".xlsm")) else parse_csv(raw)
	if not headers:
		frappe.throw(_("The file is empty."))
	if len(rows) > MAX_ROWS:
		frappe.throw(_("The file has {0} rows; the limit is {1}.").format(len(rows), MAX_ROWS))
	return doctype_name, headers, rows


@frappe.whitelist(methods=["POST"])
def preview_import(table_id: str, file_url: str) -> dict:
	"""Parse a CSV/XLSX, auto-map columns and validate every row. Writes nothing.

	Requires: data.tables.manage or data.records.create/edit.
	"""
	_require_import()
	doctype_name, headers, rows = _load(table_id, file_url)
	fields = _table_fields(doctype_name)
	by_name = {f["fieldname"]: f for f in fields}
	mapping = auto_map(headers, fields)
	col_issues = [0] * len(headers)
	invalid = []
	valid = 0
	for idx, row in enumerate(rows):
		_rec, errs = build_record(headers, row, mapping, by_name)
		if errs:
			invalid.append({"row": idx + 2, "message": "; ".join(errs)})
			for i, h in enumerate(headers):
				fn = mapping.get(h)
				if fn and any(e.startswith(fn + ":") or e == str(_("{0} is required").format(by_name.get(fn, {}).get("label") or fn)) for e in errs):
					col_issues[i] += 1
		else:
			valid += 1
	columns = [
		{
			"header": h,
			"detected_type": detect_type([r[i] for r in rows[:1000]]),
			"mapped_field": mapping.get(h),
			"issues": col_issues[i],
		}
		for i, h in enumerate(headers)
	]
	return {
		"columns": columns,
		"sample_rows": rows[:SAMPLE_ROWS],
		"total_rows": len(rows),
		"valid_rows": valid,
		"invalid_rows": invalid,
	}


@frappe.whitelist(methods=["POST"])
def run_import(
	table_id: str,
	file_url: str,
	mapping: str | dict,
	mode: str = "insert",
	key_field: str | None = None,
	confirm_replace: bool | str = False,
) -> dict:
	"""Import rows. mode: insert | update (match on key_field) | replace (delete all, then insert).

	replace requires confirm_replace=True. More than 5,000 rows run as a background job
	and return {"queued": True, "job_id"}; poll get_import_job_status(job_id).

	Requires: data.tables.manage or data.records.create/edit.
	"""
	_require_import()
	mapping = frappe.parse_json(mapping) if isinstance(mapping, str) else (mapping or {})
	if mode not in ("insert", "update", "replace"):
		frappe.throw(_("Invalid import mode"))
	if mode == "update" and not key_field:
		frappe.throw(_("Choose a key field to match existing records."))
	if mode == "replace":
		if not frappe.parse_json(confirm_replace):
			frappe.throw(_("Replacing all records requires confirmation."))
		if not _can("data.tables.manage") and not _can("data.records.edit_all"):
			frappe.throw(_("You don't have permission to replace all records."), frappe.PermissionError)
	doctype_name, headers, rows = _load(table_id, file_url)
	if len(rows) > INLINE_ROW_LIMIT:
		job_id = uuid.uuid4().hex
		frappe.enqueue(
			"huf.huf.doctype.huf_data_table.import_export._run_import_job",
			queue="long", timeout=3600, job_id=job_id, user=frappe.session.user,
			table_id=table_id, file_url=file_url, mapping=mapping, mode=mode, key_field=key_field,
		)
		return {"queued": True, "job_id": job_id}
	return _do_import(doctype_name, headers, rows, mapping, mode, key_field)


def _run_import_job(job_id, user, table_id, file_url, mapping, mode, key_field):
	frappe.set_user(user)
	try:
		doctype_name, headers, rows = _load(table_id, file_url)
		result = _do_import(doctype_name, headers, rows, mapping, mode, key_field)
	except Exception as e:
		result = {"error": str(e)}
		frappe.db.rollback()
	frappe.cache.set_value(f"huf_import:{job_id}", result, expires_in_sec=3600)
	frappe.publish_realtime("huf_import_done", {"job_id": job_id, **result}, user=user)


@frappe.whitelist()
def get_import_job_status(job_id: str) -> dict:
	"""Result of a queued import: {done: false} until the job finishes."""
	_require_import()
	res = frappe.cache.get_value(f"huf_import:{job_id}")
	return {"done": True, **res} if res else {"done": False}


def _do_import(doctype_name, headers, rows, mapping, mode, key_field):
	fields = _table_fields(doctype_name)
	by_name = {f["fieldname"]: f for f in fields}
	if mode == "update" and key_field not in mapping.values():
		frappe.throw(_("The key field must be mapped to a column."))
	rejected, records = [], []
	for idx, row in enumerate(rows):
		rec, errs = build_record(headers, row, mapping, by_name)
		if mode == "update":
			errs = [e for e in errs if "required" not in e]
			if not rec.get(key_field):
				errs.append(str(_("Key field {0} is empty").format(key_field)))
		if errs:
			rejected.append((idx + 2, "; ".join(errs), row))
		else:
			records.append((idx + 2, rec, row))
	if mode == "replace":
		from .import_replace import do_replace
		return do_replace(doctype_name, headers, records, rejected, _result)
	inserted = updated = 0
	for rownum, rec, raw in records:
		try:
			if mode == "update":
				name = frappe.db.get_value(doctype_name, {key_field: rec[key_field]}, "name")
				if not name:
					raise frappe.DoesNotExistError(str(_("No record with {0} = {1}").format(key_field, rec[key_field])))
				doc = frappe.get_doc(doctype_name, name)
				doc.update(strip_reserved(rec))
				doc.save()
				updated += 1
			else:
				frappe.get_doc({**strip_reserved(rec), "doctype": doctype_name}).insert()
				inserted += 1
		except Exception as e:
			rejected.append((rownum, re.sub(r"<[^>]+>", "", str(e)), raw))
	rejected.sort(key=lambda t: t[0])
	return _result(inserted, updated, rejected, headers)


def _result(inserted, updated, rejected, headers, note=None):
	out = {
		"inserted": inserted,
		"updated": updated,
		"rejected": len(rejected),
		"rejected_rows": [{"row": n, "message": m} for n, m, _r in rejected],
		"rejected_csv": rejected_to_csv(headers, rejected) if rejected else "",
	}
	if note:
		out["note"] = note
	return out


@frappe.whitelist()
def export_rows(
	table_id: str,
	filters: str | list | dict | None = None,
	fields: str | list | None = None,
	names: str | list | None = None,
) -> dict:
	"""Export records as CSV text. Creates no File doc.

	Requires: any data records view capability.
	"""
	_require_export()
	registry = frappe.get_doc("Huf Data Table", table_id)
	doctype_name = registry.doctype_name
	filters = frappe.parse_json(filters) if isinstance(filters, str) and filters else filters
	fields = frappe.parse_json(fields) if isinstance(fields, str) and fields else fields
	names = frappe.parse_json(names) if isinstance(names, str) and names else names
	valid = {f["fieldname"]: f for f in _table_fields(doctype_name)}
	cols = [f for f in (fields or list(valid)) if f in valid]
	if not cols:
		frappe.throw(_("No exportable fields selected."))
	flt = filters or {}
	if names:
		flt = [["name", "in", names]]
	data = frappe.get_list(doctype_name, fields=["name", *cols], filters=flt, order_by="creation asc", limit_page_length=0)
	headers = ["name", *[valid[c]["label"] or c for c in cols]]
	rows = [[d.get("name"), *[d.get(c) for c in cols]] for d in data]
	return {
		"filename": f"{registry.table_name or doctype_name}-export.csv",
		"content": to_csv_text(headers, rows),
		"count": len(rows),
	}
