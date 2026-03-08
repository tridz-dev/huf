# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

from frappe.model.document import Document


class IntegrationCredential(Document):
	"""
	Integration Credential child table document.
	Stores individual key-value credential pairs for Integration Settings.
	The value field is of type Password for secure storage.
	"""
	
	def validate(self):
		"""Validate that both key and value are provided."""
		if not self.key:
			frappe.throw("Credential Key is required")
		if not self.value:
			frappe.throw("Credential Value is required")
	
	def get_value(self) -> str:
		"""Get the decrypted credential value."""
		return self.get_password("value")
