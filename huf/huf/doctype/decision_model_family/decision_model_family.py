# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
from frappe.model.document import Document
import frappe

from huf.ai.decision.registry import discover_backends


class DecisionModelFamily(Document):
	def validate(self):
		"""Validate adapter_id against the registry of installed decision backends."""
		if not self.adapter_id:
			return

		available_adapters = discover_backends()
		if self.adapter_id not in available_adapters:
			valid_ids = ", ".join(sorted(available_adapters.keys()))
			frappe.throw(
				f"Adapter ID '{self.adapter_id}' is not registered. "
				f"Valid adapter IDs are: {valid_ids}",
				title="Invalid Adapter ID"
			)
