"""Maintenance tasks for knowledge system."""

import os
import frappe
from frappe.utils import get_files_path


def cleanup_orphaned_files():
	"""Remove orphaned SQLite files without corresponding Knowledge Source."""
	files_path = get_files_path(is_private=True)
	knowledge_dir = os.path.join(files_path, "knowledge")
	
	if not os.path.exists(knowledge_dir):
		return
	
	# Get all existing knowledge sources
	existing_sources = set(
		frappe.scrub(name) 
		for name in frappe.get_all("Knowledge Source", pluck="name")
	)
	
	# Check each file in knowledge directory
	for filename in os.listdir(knowledge_dir):
		if filename.endswith(".sqlite3"):
			source_name = filename[:-8]  # Remove .sqlite3
			if source_name not in existing_sources:
				file_path = os.path.join(knowledge_dir, filename)
				try:
					os.remove(file_path)
					# Also remove WAL and SHM files
					for ext in ["-wal", "-shm"]:
						wal_path = file_path + ext
						if os.path.exists(wal_path):
							os.remove(wal_path)
					frappe.log_error(
						f"Removed orphaned knowledge file: {filename}",
						"Knowledge Maintenance"
					)
				except Exception as e:
					frappe.log_error(
						f"Error removing orphaned file {filename}: {str(e)}",
						"Knowledge Maintenance"
					)


def optimize_indexes():
	"""Optimize SQLite indexes for all knowledge sources."""
	import sqlite3
	
	sources = frappe.get_all(
		"Knowledge Source",
		filters={"status": "Ready", "disabled": 0},
		fields=["name", "sqlite_file_path"]
	)
	
	for source in sources:
		if source.sqlite_file_path and os.path.exists(source.sqlite_file_path):
			try:
				conn = sqlite3.connect(source.sqlite_file_path)
				conn.execute("PRAGMA optimize")
				conn.execute("VACUUM")
				conn.close()
			except Exception as e:
				frappe.log_error(
					f"Error optimizing {source.name}: {str(e)}",
					"Knowledge Maintenance"
				)
