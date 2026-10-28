# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from huf.ai.whatsapp.broadcast import policy


class WhatsAppBroadcastSettings(Document):
	def validate(self):
		raw = {k: self.get(k) for k, lim in policy.BY_KEY.items() if lim.editable}
		try:
			policy.validate_values(raw)
			policy.validate_combination(policy._parse_doc(self))
		except ValueError as exc:
			frappe.throw(str(exc))
