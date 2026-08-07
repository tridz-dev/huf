# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

import json
import os
import shutil
import zipfile

import frappe


@frappe.whitelist()
def start_upload_import(knowledge_source: str, files: str):
	"""Start an ingestion job from files already uploaded via Frappe's file upload."""
	if isinstance(files, str):
		files = json.loads(files)

	job = frappe.new_doc("Ingestion Job")
	job.knowledge_source = knowledge_source
	job.source_kind = "Upload"
	job.insert(ignore_permissions=True)

	temp_dir = frappe.get_site_path("private", "files", "bulk_import", job.name)
	os.makedirs(temp_dir, exist_ok=True)

	for file_url in files:
		file_doc = frappe.get_doc("File", {"file_url": file_url})
		src_path = file_doc.get_full_path()
		dest_path = os.path.join(temp_dir, file_doc.file_name)
		shutil.copy(src_path, dest_path)

		if dest_path.lower().endswith(".zip"):
			with zipfile.ZipFile(dest_path) as zf:
				zf.extractall(temp_dir)
			os.remove(dest_path)

	job.db_set("directory_path", temp_dir)
	job.reload()
	job.start()

	return {"ingestion_job": job.name}


@frappe.whitelist()
def start_directory_import(knowledge_source: str, directory_path: str):
	"""Start an ingestion job from a directory already reachable on the server."""
	job = frappe.new_doc("Ingestion Job")
	job.knowledge_source = knowledge_source
	job.source_kind = "Directory"
	job.directory_path = directory_path
	job.insert(ignore_permissions=True)
	job.start()

	return {"ingestion_job": job.name}


@frappe.whitelist()
def start_s3_import(knowledge_source: str, bucket: str, prefix: str = ""):
	"""Start an ingestion job from an S3 bucket/prefix."""
	job = frappe.new_doc("Ingestion Job")
	job.knowledge_source = knowledge_source
	job.source_kind = "S3"
	job.s3_bucket = bucket
	job.s3_prefix = prefix
	job.insert(ignore_permissions=True)
	job.start()

	return {"ingestion_job": job.name}


@frappe.whitelist()
def start_sftp_import(knowledge_source: str, sftp_connection: str, root_path: str):
	"""Start an ingestion job from an SFTP connection."""
	job = frappe.new_doc("Ingestion Job")
	job.knowledge_source = knowledge_source
	job.source_kind = "SFTP"
	job.sftp_connection = sftp_connection
	job.sftp_root_path = root_path
	job.insert(ignore_permissions=True)
	job.start()

	return {"ingestion_job": job.name}


@frappe.whitelist()
def get_job_progress(ingestion_job: str):
	"""Return progress counters plus the most relevant failed items for an Ingestion Job."""
	from huf.huf.doctype.ingestion_job.ingestion_job import get_progress as _get_progress

	doc = frappe.get_doc("Ingestion Job", ingestion_job)
	progress = _get_progress(ingestion_job)

	failed_items = [row for row in doc.items if row.status == "Failed"][:50]
	progress["items"] = [
		{
			"external_path": row.external_path,
			"status": row.status,
			"error_message": row.error_message,
		}
		for row in failed_items
	]

	return progress
