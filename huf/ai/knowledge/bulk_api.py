# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""Thin whitelisted API surface for bulk knowledge ingestion.

The frozen shapes live in docs/bulk-ingestion-contract.md; this module only
validates, creates the header, and enqueues the runner. Row creation and all
bookkeeping belong to bulk_runner.
"""

import json
import re

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from .bulk_runner import (
	compute_progress,
	count_ingestion_items,
	run_ingestion,
	serialize_manifest,
	slice_job_id,
)

CHECKSUM_PATTERN = re.compile(r"^[0-9a-f]{64}$")

ACTIVE_INGESTION_STATUSES = ("Queued", "Running")


@frappe.whitelist()
def submit_files(knowledge_source: str, files):
	"""Submit a batch of files for bulk ingestion into a Knowledge Source.

	``files`` is a list (or JSON string) of
	``{"file": <File docname or file_url>, "external_key": str, "checksum": optional sha256 hex}``.
	"""
	if isinstance(files, str):
		files = json.loads(files)
	if not isinstance(files, list):
		frappe.throw(_("files must be a list of file entries"))
	if not files:
		frappe.throw(_("At least one file entry is required"))

	max_files = cint(frappe.conf.get("huf_bulk_max_files") or 1000)
	if len(files) > max_files:
		frappe.throw(
			_("Too many files: {0} exceeds the huf_bulk_max_files limit of {1}").format(
				len(files), max_files
			)
		)

	if not frappe.db.exists("Knowledge Source", knowledge_source):
		frappe.throw(_("Knowledge Source {0} does not exist").format(knowledge_source))
	source = frappe.get_doc("Knowledge Source", knowledge_source)
	if not frappe.has_permission("Knowledge Source", "write", doc=source):
		frappe.throw(_("Not permitted to write to Knowledge Source {0}").format(knowledge_source), frappe.PermissionError)

	existing = frappe.db.exists(
		"Knowledge Ingestion",
		{"knowledge_source": knowledge_source, "status": ("in", ACTIVE_INGESTION_STATUSES)},
	)
	if existing:
		frappe.throw(
			_("An ingestion ({0}) is already queued or running for this source").format(existing)
		)

	# Per-entry validation and in-request dedup (last valid occurrence wins).
	valid_by_key = {}
	duplicates_in_request = 0
	rejected = []
	for index, raw in enumerate(files):
		entry, error = _validate_entry(raw)
		if error:
			rejected.append({"index": index, "reason": error})
			continue
		if entry["external_key"] in valid_by_key:
			duplicates_in_request += 1
		valid_by_key[entry["external_key"]] = {"index": index, **entry}

	# File resolution + read permission per accepted entry.
	accepted = []
	for external_key, entry in valid_by_key.items():
		file_doc = _resolve_file(entry.get("file"))
		if not file_doc or not frappe.has_permission("File", "read", doc=file_doc):
			rejected.append(
				{
					"index": entry["index"],
					"reason": _("File not found or not readable: {0}").format(entry.get("file")),
				}
			)
			continue
		accepted.append(
			{
				"external_key": external_key,
				"checksum": entry.get("checksum"),
				"file": file_doc.name,
				"file_url": file_doc.file_url,
			}
		)

	if not accepted:
		frappe.throw(_("No valid file entries were accepted"))

	ingestion = frappe.get_doc(
		{
			"doctype": "Knowledge Ingestion",
			"knowledge_source": knowledge_source,
			"status": "Queued",
			"total_items": len(accepted),
			# Persist the accepted manifest so recovery/retry slices can
			# re-materialize without the enqueue args (M1 recovery contract).
			"manifest_json": serialize_manifest(accepted),
		}
	).insert()

	frappe.enqueue(
		run_ingestion,
		queue="long",
		timeout=1500,
		enqueue_after_commit=True,
		deduplicate=True,
		job_id=slice_job_id(ingestion.name, 0),
		ingestion_name=ingestion.name,
		entries=accepted,
		slice=0,
	)

	return {
		"ingestion": ingestion.name,
		"status": "Queued",
		"total_items": len(accepted),
		"duplicates_in_request": duplicates_in_request,
		"rejected": rejected,
	}


def _validate_entry(raw) -> tuple[dict, str | None]:
	if not isinstance(raw, dict):
		return None, _("Each entry must be an object with file and external_key")

	external_key = str(raw.get("external_key") or "").strip()
	if not external_key:
		return None, _("external_key is required")
	if len(external_key) > 255:
		return None, _("external_key must be at most 255 characters")

	checksum = raw.get("checksum")
	if checksum:
		checksum = str(checksum).strip().lower()
		if not CHECKSUM_PATTERN.match(checksum):
			return None, _("checksum must be a 64-character sha256 hex digest")

	return {"external_key": external_key, "checksum": checksum or None, "file": raw.get("file")}, None


def _resolve_file(file_ref):
	"""Resolve a File by docname first, then by file_url (newest wins)."""
	if not file_ref:
		return None
	try:
		return frappe.get_doc("File", file_ref)
	except (frappe.DoesNotExistError, frappe.ValidationError):
		pass
	matches = frappe.get_all(
		"File",
		filters={"file_url": file_ref},
		fields=["name"],
		order_by="creation desc",
		limit=1,
	)
	if matches:
		return frappe.get_doc("File", matches[0].name)
	return None


@frappe.whitelist()
def get_ingestion_status(ingestion: str, include_items: int = 0, item_status=None, limit: int = 50, start: int = 0):
	"""Counts via a single GROUP BY; progress computed only when total > 0."""
	doc = frappe.get_doc("Knowledge Ingestion", ingestion)
	if not frappe.has_permission("Knowledge Ingestion", "read", doc=doc):
		frappe.throw(_("Not permitted to read Ingestion {0}").format(ingestion), frappe.PermissionError)

	counts = count_ingestion_items(ingestion)
	chunks_written = counts.pop("chunks_written", 0)
	total = counts["total"]

	header = frappe.db.get_value(
		"Knowledge Ingestion",
		ingestion,
		["name", "knowledge_source", "status", "total_items", "submitted_by", "started_at", "finished_at", "error_message"],
		as_dict=True,
	)

	items = []
	if cint(include_items):
		filters = {"ingestion": ingestion}
		if item_status:
			filters["status"] = item_status
		items = frappe.get_all(
			"Knowledge Input",
			filters=filters,
			fields=["name", "external_key", "file_name", "status", "chunks_created", "attempts", "error_message", "skip_reason"],
			order_by="creation asc",
			limit=cint(limit) or 50,
			start=cint(start) or 0,
		)

	return {
		"ingestion": header,
		"counts": counts,
		"progress": compute_progress(counts) if total > 0 else 0,
		"chunks_written": chunks_written,
		"items": items,
	}


@frappe.whitelist()
def retry_ingestion(ingestion: str, only_failed: int = 1):
	"""Error rows (and, with only_failed=0, Skipped/No Text rows) -> Pending; re-enqueue."""
	doc = frappe.get_doc("Knowledge Ingestion", ingestion)
	if not frappe.has_permission("Knowledge Ingestion", "write", doc=doc):
		frappe.throw(_("Not permitted to retry Ingestion {0}").format(ingestion), frappe.PermissionError)

	if doc.status == "Running":
		frappe.throw(_("Ingestion {0} is currently running").format(ingestion))

	rescheduled = 0
	for name in frappe.get_all(
		"Knowledge Input", filters={"ingestion": ingestion, "status": "Error"}, pluck="name"
	):
		frappe.db.set_value("Knowledge Input", name, {"status": "Pending", "error_message": None})
		rescheduled += 1

	if not cint(only_failed):
		for name in frappe.get_all(
			"Knowledge Input",
			filters={"ingestion": ingestion, "status": "Skipped", "skip_reason": "No Text"},
			pluck="name",
		):
			frappe.db.set_value("Knowledge Input", name, {"status": "Pending", "skip_reason": None})
			rescheduled += 1

	frappe.db.set_value(
		"Knowledge Ingestion",
		ingestion,
		{"status": "Queued", "finished_at": None, "error_message": None, "slice_seq": 0},
	)
	frappe.db.commit()

	frappe.enqueue(
		run_ingestion,
		queue="long",
		timeout=1500,
		enqueue_after_commit=True,
		deduplicate=True,
		job_id=slice_job_id(ingestion, 0),
		ingestion_name=ingestion,
		entries=None,
		slice=0,
	)

	return {"ingestion": ingestion, "status": "Queued", "rescheduled": rescheduled}


@frappe.whitelist()
def cancel_ingestion(ingestion: str):
	"""Header -> Cancelled + finished_at; the runner checks the header at the slice boundary."""
	doc = frappe.get_doc("Knowledge Ingestion", ingestion)
	if not frappe.has_permission("Knowledge Ingestion", "write", doc=doc):
		frappe.throw(_("Not permitted to cancel Ingestion {0}").format(ingestion), frappe.PermissionError)

	if doc.status not in ACTIVE_INGESTION_STATUSES:
		frappe.throw(_("Ingestion {0} is already {1}").format(ingestion, doc.status))

	frappe.db.set_value(
		"Knowledge Ingestion", ingestion, {"status": "Cancelled", "finished_at": now_datetime()}
	)
	frappe.db.commit()

	return {"ingestion": ingestion, "status": "Cancelled"}


@frappe.whitelist()
def list_ingestions(knowledge_source=None, limit: int = 20):
	if not frappe.has_permission("Knowledge Ingestion", "read"):
		frappe.throw(_("Not permitted to read Ingestions"), frappe.PermissionError)

	filters = {}
	if knowledge_source:
		filters["knowledge_source"] = knowledge_source

	rows = frappe.get_all(
		"Knowledge Ingestion",
		filters=filters,
		fields=[
			"name",
			"knowledge_source",
			"status",
			"total_items",
			"submitted_by",
			"started_at",
			"finished_at",
			"error_message",
			"modified",
		],
		order_by="modified desc",
		limit_page_length=cint(limit) or 20,
	)

	return {"ingestions": rows}
