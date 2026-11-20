# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""Bulk ingestion materialization: manifest entries -> Knowledge Input rows
(idempotency/duplicate rules from docs/bulk-ingestion-contract.md)."""

from __future__ import annotations

import hashlib

import frappe

from .bulk_runner import (
	decide_idempotency,
	should_adopt_row,
)

# Source scanners pre-classify files they will not index (no File doc is
# created for them): the manifest entry carries the skip_reason.
PRESET_SKIP_REASONS = ("Too Large", "Unsupported", "Unsafe", "No Text")


def _materialize_preset_skip(ingestion_name: str, source_name: str, entry: dict, stats: dict) -> None:
	name = frappe.db.get_value(
		"Knowledge Input", {"knowledge_source": source_name, "external_key": entry.get("external_key")}
	)
	if name:
		if frappe.db.get_value("Knowledge Input", name, "status") in ("Pending", "Processing"):
			return
		frappe.db.set_value(
			"Knowledge Input",
			name,
			{"ingestion": ingestion_name, "status": "Skipped", "skip_reason": entry["skip_reason"]},
		)
	else:
		_insert_input(ingestion_name, source_name, entry, status="Skipped", skip_reason=entry["skip_reason"])
	stats["skipped_preset"] = stats.get("skipped_preset", 0) + 1


# --- Materialization -------------------------------------------------------

def materialize(ingestion_name: str, entries: list) -> dict:
	"""Create/reuse Knowledge Input rows for the accepted manifest entries.

	Implements the contract's duplicate/idempotency rules. Rows are only ever
	created by the runner, sequentially, under the ingestion lock (single-writer
	invariant). Permission is enforced at submit time; bookkeeping here runs
	with ignore_permissions.
	"""
	prev_flag = getattr(frappe.flags, "huf_bulk_ingestion", False)
	frappe.flags.huf_bulk_ingestion = True
	source_name = frappe.db.get_value("Knowledge Ingestion", ingestion_name, "knowledge_source")

	stats = {"created": 0, "reused": 0, "skipped_unchanged": 0, "skipped_duplicate": 0}
	seen_checksums = set()

	try:
		for entry in entries:
			external_key = entry.get("external_key")
			checksum = entry.get("checksum") or (
				None if entry.get("skip_reason") else _file_checksum(entry.get("file"))
			)
			entry = {**entry, "checksum": checksum}
			if entry.get("skip_reason") in PRESET_SKIP_REASONS:
				_materialize_preset_skip(ingestion_name, source_name, entry, stats)
				continue
			existing_name = frappe.db.get_value(
				"Knowledge Input",
				{"knowledge_source": source_name, "external_key": external_key},
			)
			existing_status = existing_checksum = None
			if existing_name:
				existing_status, existing_checksum = frappe.db.get_value(
					"Knowledge Input", existing_name, ["status", "external_checksum"]
				)
			decision = decide_idempotency(existing_status, existing_checksum, checksum)

			if decision == "create":
				# Rule 4: within one ingestion, a second entry with identical
				# external_checksum -> Skipped / Duplicate.
				if checksum and checksum in seen_checksums:
					_insert_input(
						ingestion_name,
						source_name,
						entry,
						status="Skipped",
						skip_reason="Duplicate",
					)
					stats["skipped_duplicate"] += 1
				else:
					_insert_input(ingestion_name, source_name, entry)
					stats["created"] += 1
			elif decision == "skip_unchanged":
				frappe.db.set_value(
					"Knowledge Input",
					existing_name,
					{
						"ingestion": ingestion_name,
						"external_checksum": checksum,
						"status": "Skipped",
						"skip_reason": "Unchanged",
					},
				)
				stats["skipped_unchanged"] += 1
			elif decision == "reset_pending":
				frappe.db.set_value(
					"Knowledge Input",
					existing_name,
					{
						"ingestion": ingestion_name,
						"external_checksum": checksum,
						"file": entry.get("file_url"),
						"status": "Pending",
						"skip_reason": None,
						"error_message": None,
					},
				)
				stats["reused"] += 1
			else:  # leave_alone: idempotent replay
				# Adopt the row into this ingestion only when it is unclaimed
				# or its current batch is terminal (Cancelled/Failed/…);
				# never steal a row from a live (Queued/Running) batch.
				row_ingestion = frappe.db.get_value("Knowledge Input", existing_name, "ingestion")
				header_status = None
				if row_ingestion:
					header_status = frappe.db.get_value(
						"Knowledge Ingestion", row_ingestion, "status"
					)
				if should_adopt_row(row_ingestion, header_status):
					frappe.db.set_value(
						"Knowledge Input",
						existing_name,
						{
							"ingestion": ingestion_name,
							"external_checksum": checksum or existing_checksum,
						},
					)
				stats["reused"] += 1

			if checksum:
				seen_checksums.add(checksum)

		frappe.db.commit()
		return stats
	finally:
		frappe.flags.huf_bulk_ingestion = prev_flag


def _file_checksum(file_name: str | None) -> str | None:
	"""Server-side SHA-256 of the File content when the caller sent none, so
	re-submitting unchanged files is skipped instead of re-embedded. Computed
	here (background) to keep submit_files a fast ack."""
	if not file_name:
		return None
	try:
		content = frappe.get_doc("File", file_name).get_content()
	except Exception:
		return None
	if isinstance(content, str):
		content = content.encode()
	return hashlib.sha256(content).hexdigest() if content else None


def _insert_input(ingestion_name: str, source_name: str, entry: dict, status: str = "Pending", skip_reason: str | None = None) -> None:
	"""Create one bulk Knowledge Input row (no auto-enqueue under the flag)."""
	doc = frappe.get_doc(
		{
			"doctype": "Knowledge Input",
			"knowledge_source": source_name,
			"input_type": "File",
			"file": entry.get("file_url"),
			"ingestion": ingestion_name,
			"external_key": entry.get("external_key"),
			"external_checksum": entry.get("checksum") or None,
			"status": status,
			# NOTE: empty string, never None -- Frappe v16 get_default_value()
			# substitutes the FIRST option of a Select when the value is
			# missing, which would brand every row "Duplicate".
			"skip_reason": skip_reason or "",
		}
	)
	if status == "Skipped" and not entry.get("file_url"):
		# Preset-skipped rows have no File doc; the File-type validation
		# ("File is required") does not apply to a row that is never read.
		doc.flags.ignore_validate = True
	doc.insert(ignore_permissions=True)
