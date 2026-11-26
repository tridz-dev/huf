"""Document event hooks for knowledge system."""

import os

import frappe


def on_knowledge_source_created(doc, method):
	"""Initialize knowledge source after creation."""
	from .backends import get_backend
	from .indexer import _build_backend_config

	try:
		backend_class = get_backend(doc.knowledge_type)
		backend = backend_class()
		backend.initialize(doc.name, _build_backend_config(doc))
	except Exception as e:
		frappe.log_error(
			title="Knowledge Source Error",
			message=f"Error initializing knowledge source {doc.name}: {e!s}",
		)


def on_knowledge_source_updated(doc, method):
	"""Handle knowledge source updates."""
	# Check if chunking settings changed
	old_doc = doc.get_doc_before_save()
	if old_doc:
		if old_doc.chunk_size != doc.chunk_size or old_doc.chunk_overlap != doc.chunk_overlap:
			# Chunking changed - suggest rebuild
			frappe.msgprint("Chunking settings changed. Consider rebuilding the index.", alert=True)


def on_knowledge_source_deleted(doc, method):
	"""Cleanup when knowledge source is deleted."""
	# Delete SQLite file
	from frappe.utils import get_files_path

	try:
		files_path = get_files_path(is_private=True)
		safe_name = frappe.scrub(doc.name)
		db_path = os.path.join(files_path, "knowledge", f"{safe_name}.sqlite3")

		if os.path.exists(db_path):
			os.remove(db_path)

		# Also remove WAL and SHM files if they exist
		for ext in ["-wal", "-shm"]:
			wal_path = db_path + ext
			if os.path.exists(wal_path):
				os.remove(wal_path)
	except Exception as e:
		frappe.log_error(
			title="Knowledge Source Cleanup Error",
			message=f"Error cleaning up knowledge source {doc.name}: {e!s}",
		)


def on_knowledge_input_deleted(doc, method):
	"""Remove chunks when input is deleted."""
	from .backends import get_backend

	try:
		source = frappe.get_doc("Knowledge Source", doc.knowledge_source)

		backend_class = get_backend(source.knowledge_type)
		backend = backend_class()
		backend.initialize(source.name, {})
		backend.delete_chunks(doc.name)

		# Update source stats
		from .indexer import update_source_stats

		update_source_stats(source, backend)
		recompute_source_status(source.name, exclude_input=doc.name)
	except Exception as e:
		frappe.log_error(
			title="Knowledge Input Cleanup Error",
			message=f"Error deleting chunks for input {doc.name}: {e!s}",
		)


def recompute_source_status(source_name, exclude_input=None):
	"""Derive source status/error from its remaining inputs.

	Error if any other input is in Error (latest message wins), else Ready.
	Concurrent Indexing/Rebuilding states are left alone. `exclude_input` is
	the input being deleted (on_trash still sees it).
	"""
	status = frappe.db.get_value("Knowledge Source", source_name, "status")
	if status in ("Indexing", "Rebuilding"):
		return
	filters = {"knowledge_source": source_name, "status": "Error"}
	if exclude_input:
		filters["name"] = ["!=", exclude_input]
	failed = frappe.get_all(
		"Knowledge Input", filters=filters, fields=["error_message"], order_by="modified desc", limit=1
	)
	if failed:
		values = {"status": "Error", "error_message": failed[0].error_message}
	else:
		values = {"status": "Ready", "error_message": None}
	frappe.db.set_value("Knowledge Source", source_name, values)
