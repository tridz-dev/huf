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
		_set_fields(ingestion_job, status="Scanning")

		_scan_local_directory(ingestion_job, doc.directory_path)

		_enqueue_processing(ingestion_job)

	except Exception as e:
		_mark_failed(ingestion_job, e)
		raise


def scan_directory(ingestion_job):
	"""Scan a directory path directly (no upload extraction step)."""
	doc = frappe.get_doc("Ingestion Job", ingestion_job)

	try:
		_set_fields(ingestion_job, status="Scanning")

		directory_path = _validate_directory_path(doc.directory_path)

		_scan_local_directory(ingestion_job, directory_path)

		_enqueue_processing(ingestion_job)

	except Exception as e:
		_mark_failed(ingestion_job, e)
		raise


def _validate_directory_path(directory_path):
	"""Resolve and validate a user-supplied Directory-source path.

	Directory imports are admin-triggered but the path itself travels through
	a whitelisted API (huf.ai.knowledge.bulk.api.start_directory_import), so
	it's untrusted input. Require it to resolve (after following symlinks) to
	somewhere under one of the site's configured allow-listed roots, rather
	than just checking it's an absolute path that exists -- otherwise any
	caller of that endpoint could point a job at /etc or the bench's own
	config directory and have it ingested into a knowledge base agents query.
	"""
	if not directory_path or not os.path.isabs(directory_path):
		frappe.throw(_("Ingestion Job directory_path must be an absolute path: {0}").format(directory_path))

	resolved = os.path.realpath(directory_path)
	if not os.path.exists(resolved):
		frappe.throw(_("Ingestion Job directory_path does not exist: {0}").format(directory_path))

	allowed_roots = frappe.conf.get("bulk_ingestion_allowed_directories") or []
	if not allowed_roots:
		frappe.throw(
			_(
				"Directory-source bulk ingestion is disabled: no bulk_ingestion_allowed_directories "
				"are configured in site_config.json. Add the server paths that are safe to ingest from."
			)
		)

	for root in allowed_roots:
		allowed_root = os.path.realpath(root)
		if resolved == allowed_root or resolved.startswith(allowed_root + os.sep):
			return resolved

	frappe.throw(_("Ingestion Job directory_path is not under an allow-listed root: {0}").format(directory_path))


def scan_s3(ingestion_job):
	"""Scan an S3 bucket/prefix, resuming from doc.sync_cursor if set."""
	doc = frappe.get_doc("Ingestion Job", ingestion_job)

	try:
		_set_fields(ingestion_job, status="Scanning")

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
			_flush_batch(ingestion_job, batch, sync_cursor=next_token or "")
			batch = []

			if not next_token:
				break

			continuation_token = next_token

		_enqueue_processing(ingestion_job)

	except Exception as e:
		_mark_failed(ingestion_job, e)
		raise


def scan_sftp(ingestion_job):
	"""Scan an SFTP tree, resuming from doc.sync_cursor (a JSON directory queue)."""
	doc = frappe.get_doc("Ingestion Job", ingestion_job)

	try:
		_set_fields(ingestion_job, status="Scanning")

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

				_flush_batch(ingestion_job, batch, sync_cursor=json.dumps(dir_queue))

		finally:
			try:
				sftp_client.close()
			finally:
				ssh_client.close()

		_enqueue_processing(ingestion_job)

	except Exception as e:
		_mark_failed(ingestion_job, e)
		raise


def _scan_local_directory(ingestion_job, root_path):
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
				_flush_batch(ingestion_job, batch)
				batch = []

	_flush_batch(ingestion_job, batch)


def _flush_batch(ingestion_job, batch, sync_cursor=None):
	"""Insert `batch` as Ingestion Job Item rows and bump discovery/pending counters.

	Deliberately does NOT load the parent Ingestion Job doc, append to its
	in-memory child table, and doc.save() it -- across a scan with many pages
	that would re-serialize the whole, ever-growing child table on every
	single flush (O(n^2) over the full scan). Instead each row is inserted
	directly via Document.db_insert() (Frappe's low-level bulk-child-insert
	API, which doesn't touch the parent's other children) and the counters
	are bumped with one atomic SQL update, mirroring the pattern
	huf.ai.knowledge.bulk.orchestrator already uses for its batch counters.

	Because this bypasses the ORM's child-table sync, nothing else in this
	module may call doc.save() on an Ingestion Job doc once items exist for
	it -- Frappe's save() reconciles child tables against whatever is in the
	in-memory doc, and would delete any rows inserted this way that aren't
	also present there. Status/cursor fields are updated separately via
	frappe.db.set_value(), which only touches the named scalar columns.
	"""
	if batch:
		next_idx = frappe.db.count("Ingestion Job Item", {"parent": ingestion_job}) + 1
		for i, row in enumerate(batch):
			child = frappe.get_doc(
				{
					"doctype": "Ingestion Job Item",
					"parent": ingestion_job,
					"parenttype": "Ingestion Job",
					"parentfield": "items",
					"idx": next_idx + i,
					**row,
				}
			)
			child.db_insert()

		frappe.db.sql(
			"""
			UPDATE `tabIngestion Job`
			SET total_discovered = total_discovered + %(count)s,
				pending = pending + %(count)s
			WHERE name = %(name)s
			""",
			{"count": len(batch), "name": ingestion_job},
		)

	if sync_cursor is not None:
		frappe.db.set_value("Ingestion Job", ingestion_job, "sync_cursor", sync_cursor, update_modified=False)

	frappe.db.commit()


def _set_fields(ingestion_job, **fields):
	"""Update scalar fields on an Ingestion Job without touching its child table."""
	frappe.db.set_value("Ingestion Job", ingestion_job, fields, update_modified=False)
	frappe.db.commit()


def _enqueue_processing(ingestion_job):
	"""Kick off the batch processor now that scanning has produced pending items."""
	frappe.enqueue(
		"huf.ai.knowledge.bulk.orchestrator.process_ingestion_batches",
		queue="default",
		ingestion_job=ingestion_job,
		job_id=f"bulk_process_{ingestion_job}",
		enqueue_after_commit=True,
	)

	_set_fields(ingestion_job, status="Processing")


def _mark_failed(ingestion_job, error):
	"""Record a scan failure on the Ingestion Job. Caller re-raises after this."""
	frappe.db.rollback()

	_set_fields(ingestion_job, status="Failed", error_message=str(error)[:500])

	frappe.log_error(f"Ingestion Job Scan Error: {ingestion_job}", frappe.get_traceback())


SCANNER_BY_SOURCE_KIND = {
	"Upload": scan_upload,
	"Directory": scan_directory,
	"S3": scan_s3,
	"SFTP": scan_sftp,
}
