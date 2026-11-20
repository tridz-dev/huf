"""File-size guard for table imports."""

import os

import frappe
from frappe import _


def check_import_file_size(file_doc, limit):
	"""Throw if the file exceeds ``limit`` bytes.

	``file_doc.file_size`` can be 0 or stale, so local files are measured on disk.
	"""
	size = file_doc.file_size or 0
	if not file_doc.is_remote_file:
		try:
			size = max(size, os.path.getsize(file_doc.get_full_path()))
		except OSError:
			frappe.throw(_("The import file could not be read."), frappe.ValidationError)
	if size > limit:
		frappe.throw(_("The import file is too large."), frappe.ValidationError)
