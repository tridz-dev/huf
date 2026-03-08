# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class IntegrationSettings(Document):
	"""
	Integration Settings document for storing credentials for external services.
	Links to Integration Service and stores credentials in a child table.
	"""
	
	def validate(self):
		"""Validate that credentials are provided when service is set."""
		if not self.service:
			frappe.throw("Integration Service is required")
		
		# Ensure at least one credential is provided
		if not self.credentials:
			frappe.throw("At least one credential is required")
	
	def get_credential(self, key: str) -> str:
		"""Get a specific credential value by key."""
		for cred in self.credentials:
			if cred.key == key:
				return cred.get_password("value")
		return None
	
	def get_all_credentials(self) -> dict:
		"""Get all credentials as a dictionary."""
		return {cred.key: cred.get_password("value") for cred in self.credentials}
