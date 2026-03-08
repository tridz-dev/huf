# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import json


class IntegrationService(Document):
	"""
	Integration Service document for defining available external services.
	Stores metadata about services like Slack, GitHub, Telegram, etc.
	"""
	
	def validate(self):
		"""Validate the service configuration."""
		if not self.service_name:
			frappe.throw("Service Name is required")
		
		# Validate required_credentials JSON if provided
		if self.required_credentials:
			try:
				creds = json.loads(self.required_credentials)
				if not isinstance(creds, list):
					frappe.throw("Required Credentials must be a JSON array")
			except json.JSONDecodeError:
				frappe.throw("Required Credentials must be valid JSON")
	
	def before_insert(self):
		"""Set is_builtin for known services."""
		builtin_services = [
			"slack", "discord", "telegram", "github", "docker",
			"jira", "linear", "clickup", "trello", "notion",
			"zendesk", "calcom", "zoom", "tavily", "gmail"
		]
		if self.service_name.lower() in builtin_services:
			self.is_builtin = 1
