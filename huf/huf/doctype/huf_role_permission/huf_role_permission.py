# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

from frappe.model.document import Document
from huf.permissions import CAPABILITIES


class HufRolePermission(Document):
	def before_save(self):
		"""Populate the human-readable label from the CAPABILITIES catalogue."""
		self.label = CAPABILITIES.get(self.capability, self.capability)
