# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ExecutionProfile(Document):
	def validate(self):
		# Resource limits must be positive; a zero/negative limit would make the
		# sandbox unusable or unbounded. Bounded above by a site-wide ceiling in
		# Phase 2 (dispatcher), not here.
		for fieldname in (
			"max_wall_time_s",
			"max_cpu_seconds",
			"max_memory_mb",
			"max_output_bytes",
		):
			value = self.get(fieldname)
			if value is not None and value <= 0:
				frappe.throw(
					_("{0} must be a positive integer.").format(_(fieldname.replace("_", " ").title())),
					frappe.ValidationError,
				)
