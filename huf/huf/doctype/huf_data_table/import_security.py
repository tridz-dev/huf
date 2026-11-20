"""Security helpers for data table imports: size caps, reserved keys, generic errors."""

import io
import zipfile

import frappe
from frappe import _

DEFAULT_IMPORT_MAX_MB = 20
MAX_XLSX_UNCOMPRESSED = 200 * 1024 * 1024
# Server-controlled keys that incoming row dicts must never set.
RESERVED_KEYS = frozenset(
	("name", "owner", "creation", "modified", "modified_by", "docstatus", "idx", "doctype", "parent", "parentfield", "parenttype")
)


def strip_reserved(values: dict) -> dict:
	return {k: v for k, v in (values or {}).items() if k not in RESERVED_KEYS}


def _import_error():
	# One generic message for every failure so file existence/ownership is not leaked.
	frappe.throw(_("The import file is not available."), frappe.ValidationError)


def _max_import_bytes() -> int:
	try:
		mb = float(frappe.conf.get("huf_table_import_max_mb") or DEFAULT_IMPORT_MAX_MB)
	except (TypeError, ValueError):
		mb = DEFAULT_IMPORT_MAX_MB
	return int(mb * 1024 * 1024)


def check_xlsx_size(raw: bytes):
	"""Refuse zip bombs: cap the declared uncompressed size before openpyxl touches it."""
	try:
		with zipfile.ZipFile(io.BytesIO(raw)) as zf:
			total = sum(i.file_size for i in zf.infolist())
	except zipfile.BadZipFile:
		frappe.throw(_("The file is not a valid XLSX workbook."), frappe.ValidationError)
	if total > MAX_XLSX_UNCOMPRESSED:
		frappe.throw(_("The spreadsheet is too large to import."), frappe.ValidationError)
