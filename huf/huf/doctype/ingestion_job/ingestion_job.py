# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _

from huf.ai.knowledge.bulk.scanners import SCANNER_BY_SOURCE_KIND


class IngestionJob(Document):
	def start(self):
		"""Resolve the scanner for this source kind and enqueue it."""
		scanner = SCANNER_BY_SOURCE_KIND.get(self.source_kind)
		if not scanner:
			frappe.throw(_("No scanner registered for source kind: {0}").format(self.source_kind))

		self.status = "Queued"
		self.started_at = frappe.utils.now_datetime()
		self.save()

		frappe.enqueue(
			scanner,
			queue="long",
			job_id=f"bulk_scan_{self.name}",
			ingestion_job=self.name,
			enqueue_after_commit=True,
		)


@frappe.whitelist()
def get_progress(ingestion_job: str):
	"""Return progress counters for an Ingestion Job."""
	doc = frappe.get_doc("Ingestion Job", ingestion_job)

	return {
		"status": doc.status,
		"total_discovered": doc.total_discovered,
		"pending": doc.pending,
		"processing": doc.processing,
		"succeeded": doc.succeeded,
		"failed": doc.failed,
		"skipped": doc.skipped,
		"error_message": doc.error_message,
	}
