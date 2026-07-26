"""Document event hooks for knowledge system."""

import os
import frappe


def on_knowledge_source_created(doc, method):
	"""Initialize knowledge source after creation."""
	# Initialize SQLite database
	from .backends import get_backend
	
	try:
		backend_class = get_backend(doc.knowledge_type)
		backend = backend_class()
		backend.initialize(doc.name, {
			"chunk_size": doc.chunk_size,
			"chunk_overlap": doc.chunk_overlap,
		})
	except Exception as e:
		frappe.log_error(
			f"Error initializing knowledge source {doc.name}: {str(e)}",
			"Knowledge Source Error"
		)


def on_knowledge_source_updated(doc, method):
	"""Handle knowledge source updates."""
	# Check if chunking settings changed
	old_doc = doc.get_doc_before_save()
	if old_doc:
		if (old_doc.chunk_size != doc.chunk_size or 
			old_doc.chunk_overlap != doc.chunk_overlap):
			# Chunking changed - suggest rebuild
			frappe.msgprint(
				"Chunking settings changed. Consider rebuilding the index.",
				alert=True
			)


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
			f"Error cleaning up knowledge source {doc.name}: {str(e)}",
			"Knowledge Source Cleanup Error"
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
	except Exception as e:
		frappe.log_error(
			f"Error deleting chunks for input {doc.name}: {str(e)}",
			"Knowledge Input Cleanup Error"
		)
