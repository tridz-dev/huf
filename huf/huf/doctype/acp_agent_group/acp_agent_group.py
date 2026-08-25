# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

from __future__ import annotations

from frappe.model.document import Document


class AcpAgentGroup(Document):
	def validate(self):
		self._validate_timeouts()
		self._validate_success_count()

	def _validate_timeouts(self) -> None:
		if self.per_child_timeout is not None:
			self.per_child_timeout = max(1, int(self.per_child_timeout))
		if self.overall_timeout is not None:
			self.overall_timeout = max(1, int(self.overall_timeout))

	def _validate_success_count(self) -> None:
		if self.min_success_count is not None:
			self.min_success_count = max(0, int(self.min_success_count))
