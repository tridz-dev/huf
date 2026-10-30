# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class AgentToolCall(Document):
	def validate(self):
		# Credentials must never persist in run logs (see huf.ai.secrets).
		from huf.ai.secrets import redact_json_field

		for fieldname in ("tool_args", "tool_result", "error_message"):
			value = self.get(fieldname)
			if value:
				self.set(fieldname, redact_json_field(value))
