"""Bulk ingestion orchestrator.

Splits an Ingestion Job's pending items into batches, fans them out to the
background queue, and lets each batch report back into the job's counters
and, once the last batch lands, finalize the job's status.
"""

import os
import tempfile
import time

import frappe
from frappe.utils import now_datetime

from huf.ai.knowledge.indexer import process_knowledge_input
from huf.ai.tools.credentials import require_credential

BATCH_SIZE = 50


def process_ingestion_batches(ingestion_job: str) -> None:
	"""Split an Ingestion Job's pending items into batches and enqueue them.

	Each batch is processed by ``process_batch`` in its own background job.
	Because multiple batches for the same job run concurrently, we can't
	tell "was this the last batch?" from inside a single batch just by
	looking at the job doc (it could be stale). Instead we stash the total
	batch count in cache up front, and each batch atomically decrements it
	when it finishes; whichever batch drives the counter to zero is -- by
	construction -- the one that finalizes the job.
	"""
	job = frappe.get_doc("Ingestion Job", ingestion_job)

	pending_item_names = [item.name for item in job.items if item.status == "Pending"]

	if not pending_item_names:
		_finalize_ingestion_job(ingestion_job)
		return

	chunks = [
		pending_item_names[i : i + BATCH_SIZE] for i in range(0, len(pending_item_names), BATCH_SIZE)
	]

	frappe.cache().set_value(_remaining_batches_key(ingestion_job), len(chunks))

	for i, item_names in enumerate(chunks):
		frappe.enqueue(
			"huf.ai.knowledge.bulk.orchestrator.process_batch",
			queue="default",
			ingestion_job=ingestion_job,
			item_names=item_names,
			job_id=f"bulk_batch_{ingestion_job}_{i}",
			enqueue_after_commit=True,
		)


def process_batch(ingestion_job: str, item_names: list) -> None:
	"""Process one batch of Ingestion Job Item rows.

	Runs as its own background job, so this is where a chunk of raw
	source files (Upload/Directory paths, S3 keys, or SFTP paths) actually
	get pulled down, registered as Knowledge Inputs, and indexed.
	"""
	job = frappe.get_doc("Ingestion Job", ingestion_job)
	items_by_name = {item.name: item for item in job.items}
	items = [items_by_name[name] for name in item_names if name in items_by_name]

	succeeded = failed = skipped = 0
	tmpdir = tempfile.mkdtemp(prefix=f"bulk_ingest_{ingestion_job}_")
	sftp = ssh_client = None

	try:
		if job.source_kind == "SFTP":
			# One SFTP session for the whole batch, not per-file, so we
			# don't pay a fresh handshake per item.
			from huf.ai.knowledge.bulk.sftp_client import _connect

			ssh_client, sftp = _connect(job.sftp_connection)

		for item in items:
			try:
				item.db_set("status", "Processing", update_modified=False)

				if frappe.db.exists(
					"Knowledge Input",
					{
						"knowledge_source": job.knowledge_source,
						"external_checksum": item.external_checksum,
					},
				):
					item.db_set("status", "Skipped", update_modified=False)
					skipped += 1
					continue

				local_path = _fetch_local_file(job, item, tmpdir, sftp)

				with open(local_path, "rb") as f:
					content = f.read()

				file_doc = frappe.get_doc(
					{
						"doctype": "File",
						"file_name": os.path.basename(item.external_path),
						"content": content,
						"is_private": 1,
					}
				).insert(ignore_permissions=True)

				knowledge_input = frappe.get_doc(
					{
						"doctype": "Knowledge Input",
						"knowledge_source": job.knowledge_source,
						"input_type": "File",
						"file": file_doc.file_url,
						"external_source_path": item.external_path,
						"external_checksum": item.external_checksum,
						"ingestion_job": ingestion_job,
					}
				).insert(ignore_permissions=True)

				process_knowledge_input(knowledge_input.name, skip_lock=False)

				item.db_set("status", "Succeeded", update_modified=False)
				item.db_set("knowledge_input", knowledge_input.name, update_modified=False)
				succeeded += 1

			except Exception as e:
				frappe.db.rollback()
				item.db_set("status", "Failed", update_modified=False)
				item.db_set("error_message", str(e)[:500], update_modified=False)
				failed += 1
				frappe.log_error(f"Bulk Ingestion Item Error: {item.name}", frappe.get_traceback())

	finally:
		if ssh_client is not None:
			ssh_client.close()
		_cleanup_tmpdir(tmpdir)

	# Counters are shared across concurrent batches of the same job, so we
	# fold this batch's deltas in with a single atomic SQL update rather
	# than loading/mutating/saving the whole job doc (which would race
	# with the other batches running in parallel).
	if succeeded or failed or skipped:
		frappe.db.sql(
			"""
			UPDATE `tabIngestion Job`
			SET succeeded = succeeded + %(succeeded)s,
				failed = failed + %(failed)s,
				skipped = skipped + %(skipped)s,
				pending = pending - %(processed)s
			WHERE name = %(name)s
			""",
			{
				"succeeded": succeeded,
				"failed": failed,
				"skipped": skipped,
				"processed": succeeded + failed + skipped,
				"name": ingestion_job,
			},
		)
	frappe.db.commit()

	if _decrement_remaining_batches(ingestion_job) <= 0:
		_finalize_ingestion_job(ingestion_job)


def _fetch_local_file(job, item, tmpdir: str, sftp) -> str:
	"""Get a local filesystem path for an item's content.

	Upload/Directory items already point at a local path. S3/SFTP items
	need to be downloaded into the batch's temp directory first.
	"""
	if job.source_kind in ("Upload", "Directory"):
		return item.external_path

	if job.source_kind == "S3":
		local_path = os.path.join(tmpdir, os.path.basename(item.external_path))
		client = _get_s3_client()
		client.download_file(job.s3_bucket, item.external_path, local_path)
		return local_path

	if job.source_kind == "SFTP":
		from huf.ai.knowledge.bulk.sftp_client import read_file

		local_path = os.path.join(tmpdir, os.path.basename(item.external_path))
		read_file(sftp, item.external_path, local_path)
		return local_path

	frappe.throw(f"Unsupported source_kind for bulk ingestion: {job.source_kind}")


def _get_s3_client():
	"""Build a boto3 S3 client the same way huf.ai.tools.s3._get_client() does."""
	import boto3

	access_key_id = require_credential("aws_s3", "access_key_id")
	secret_access_key = require_credential("aws_s3", "secret_access_key")
	region = require_credential("aws_s3", "region")

	return boto3.client(
		"s3",
		aws_access_key_id=access_key_id,
		aws_secret_access_key=secret_access_key,
		region_name=region,
	)


def _cleanup_tmpdir(tmpdir: str) -> None:
	import shutil

	shutil.rmtree(tmpdir, ignore_errors=True)


def _remaining_batches_key(ingestion_job: str) -> str:
	return f"bulk_ingestion_batches_remaining_{ingestion_job}"


def _decrement_remaining_batches(ingestion_job: str) -> int:
	"""Atomically decrement the remaining-batch counter for this job.

	Mirrors the per-source Redis lock pattern in
	huf.ai.knowledge.indexer.process_knowledge_input: a short-lived nx
	lock guards the read-modify-write of the counter so concurrent
	process_batch workers can't both read the same value and step on
	each other's decrement.
	"""
	counter_key = _remaining_batches_key(ingestion_job)
	lock_key = f"{counter_key}_lock"

	while not frappe.cache().set(lock_key, 1, ex=30, nx=True):
		time.sleep(0.05)

	try:
		remaining = frappe.cache().get_value(counter_key) or 0
		remaining = int(remaining) - 1
		frappe.cache().set_value(counter_key, remaining)
		return remaining
	finally:
		frappe.cache().delete(lock_key)


def _finalize_ingestion_job(ingestion_job: str) -> None:
	"""Mark the job Completed / Completed with Errors once all batches are done."""
	job = frappe.get_doc("Ingestion Job", ingestion_job)
	job.status = "Completed" if not job.failed else "Completed with Errors"
	job.finished_at = now_datetime()
	job.save(ignore_permissions=True)
	frappe.db.commit()
