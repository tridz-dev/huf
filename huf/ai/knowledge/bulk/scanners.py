"""Scanners that discover source files/objects for an Ingestion Job and

populate its "items" child table, before handing off to the batch processor.
"""

import json
import os

import boto3
import frappe
from frappe import _

from huf.ai.knowledge.bulk.sftp_client import _connect, list_dir_recursive
from huf.ai.tools.credentials import require_credential
from huf.ai.tools.s3 import list_objects_page

BATCH_SIZE = 200


def scan_upload(ingestion_job):
	"""Scan a directory populated by the API layer from an uploaded zip/files."""
	doc = frappe.get_doc("Ingestion Job", ingestion_job)

	try:
		doc.status = "Scanning"
		doc.save(ignore_permissions=True)
		frappe.db.commit()

		_scan_local_directory(doc, doc.directory_path)

		_enqueue_processing(doc)

	except Exception as e:
		_mark_failed(doc, e)
		raise


def scan_directory(ingestion_job):
	"""Scan a directory path directly (no upload extraction step)."""
	doc = frappe.get_doc("Ingestion Job", ingestion_job)

	try:
		doc.status = "Scanning"
		doc.save(ignore_permissions=True)
		frappe.db.commit()

		directory_path = doc.directory_path
		if not directory_path or not os.path.isabs(directory_path) or not os.path.exists(directory_path):
			frappe.throw(_("Ingestion Job directory_path must be an absolute path that exists: {0}").format(directory_path))

		_scan_local_directory(doc, directory_path)

		_enqueue_processing(doc)

	except Exception as e:
		_mark_failed(doc, e)
		raise


def scan_s3(ingestion_job):
	"""Scan an S3 bucket/prefix, resuming from doc.sync_cursor if set."""
	doc = frappe.get_doc("Ingestion Job", ingestion_job)

	try:
		doc.status = "Scanning"
		doc.save(ignore_permissions=True)
		frappe.db.commit()

		access_key_id = require_credential("aws_s3", "access_key_id")
		secret_access_key = require_credential("aws_s3", "secret_access_key")
		region = require_credential("aws_s3", "region")

		client = boto3.client(
			"s3",
			aws_access_key_id=access_key_id,
			aws_secret_access_key=secret_access_key,
			region_name=region,
		)

		continuation_token = doc.sync_cursor or None
		batch = []

		while True:
			page = list_objects_page(
				client,
				doc.s3_bucket,
				doc.s3_prefix or "",
				continuation_token=continuation_token,
			)

			for obj in page["objects"]:
				batch.append(
					{
						"external_path": obj["key"],
						"external_checksum": obj["etag"],
						"size_bytes": obj["size"],
						"status": "Pending",
					}
				)

			next_token = page["next_token"]
			doc.sync_cursor = next_token or ""
			_flush_batch(doc, batch)
			batch = []

			if not next_token:
				break

			continuation_token = next_token

		doc.sync_cursor = ""
		doc.save(ignore_permissions=True)
		frappe.db.commit()

		_enqueue_processing(doc)

	except Exception as e:
		_mark_failed(doc, e)
		raise


def scan_sftp(ingestion_job):
	"""Scan an SFTP tree, resuming from doc.sync_cursor (a JSON directory queue)."""
	doc = frappe.get_doc("Ingestion Job", ingestion_job)

	try:
		doc.status = "Scanning"
		doc.save(ignore_permissions=True)
		frappe.db.commit()

		if doc.sync_cursor:
			dir_queue = json.loads(doc.sync_cursor)
		else:
			dir_queue = [doc.sftp_root_path]

		ssh_client, sftp_client = _connect(doc.sftp_connection)

		try:
			while dir_queue:
				files, dir_queue = list_dir_recursive(sftp_client, dir_queue)

				batch = []
				for entry in files:
					batch.append(
						{
							"external_path": entry["path"],
							"external_checksum": f"{entry['size']}:{entry['mtime']}",
							"size_bytes": entry["size"],
							"status": "Pending",
						}
					)

				doc.sync_cursor = json.dumps(dir_queue)
				_flush_batch(doc, batch)

			doc.sync_cursor = ""
			doc.save(ignore_permissions=True)
			frappe.db.commit()

		finally:
			try:
				sftp_client.close()
			finally:
				ssh_client.close()

		_enqueue_processing(doc)

	except Exception as e:
		_mark_failed(doc, e)
		raise


def _scan_local_directory(doc, root_path):
	"""Walk `root_path` and append discovered files as Ingestion Job Items, in batches."""
	batch = []

	for dirpath, _dirnames, filenames in os.walk(root_path):
		for filename in filenames:
			file_path = os.path.abspath(os.path.join(dirpath, filename))
			stat = os.stat(file_path)

			batch.append(
				{
					"external_path": file_path,
					"external_checksum": f"{stat.st_size}:{stat.st_mtime}",
					"size_bytes": stat.st_size,
					"status": "Pending",
				}
			)

			if len(batch) >= BATCH_SIZE:
				_flush_batch(doc, batch)
				batch = []

	_flush_batch(doc, batch)


def _flush_batch(doc, batch):
	"""Append `batch` rows to doc.items and save, updating discovery/pending counters."""
	if not batch:
		doc.save(ignore_permissions=True)
		frappe.db.commit()
		return

	for row in batch:
		doc.append("items", row)

	doc.total_discovered = (doc.total_discovered or 0) + len(batch)
	doc.pending = (doc.pending or 0) + len(batch)

	doc.save(ignore_permissions=True)
	frappe.db.commit()


def _enqueue_processing(doc):
	"""Kick off the batch processor now that scanning has produced pending items."""
	frappe.enqueue(
		"huf.ai.knowledge.bulk.orchestrator.process_ingestion_batches",
		queue="default",
		ingestion_job=doc.name,
		job_id=f"bulk_process_{doc.name}",
		enqueue_after_commit=True,
	)

	doc.status = "Processing"
	doc.save(ignore_permissions=True)
	frappe.db.commit()


def _mark_failed(doc, error):
	"""Record a scan failure on the Ingestion Job. Caller re-raises after this."""
	frappe.db.rollback()

	doc.reload()
	doc.status = "Failed"
	doc.error_message = str(error)[:500]
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	frappe.log_error(f"Ingestion Job Scan Error: {doc.name}", frappe.get_traceback())


SCANNER_BY_SOURCE_KIND = {
	"Upload": scan_upload,
	"Directory": scan_directory,
	"S3": scan_s3,
	"SFTP": scan_sftp,
}
