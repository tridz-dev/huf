# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
"""Decision Policy -- orchestrates policy authoring, versioning, and publishing.

A Policy holds the master definition (definition_json) and references the current published
version. Publishing creates/updates a Policy Version as Published, retires the previous one,
and updates Decision Policy.current_version and fingerprint (from the version's fingerprint).
"""

import frappe
from frappe import _
from frappe.model.document import Document
from datetime import datetime


class DecisionPolicy(Document):
	"""Policy document -- orchestrates versioning and publishing."""

	def validate(self):
		"""Validate policy definition on save."""
		self._validate_definition()

	def _validate_definition(self):
		"""Validate that definition_json is valid if provided."""
		if self.definition_json:
			try:
				from huf.ai.decision.policy import validate_policy_data
				import json
				definition = json.loads(self.definition_json)
				validate_policy_data(definition)
			except Exception as e:
				frappe.throw(
					_("Invalid policy definition: {0}").format(str(e)),
					title=_("Policy Validation Error")
				)

	@frappe.whitelist()
	def publish_version(self):
		"""Publish the current definition as a new Policy Version.

		Creates a new Decision Policy Version with status=Published,
		retires the previous Published version, and updates current_version.
		Returns the version document name.
		"""
		import json
		from huf.ai.decision.policy import validate_policy_data, policy_fingerprint

		# Get next version number
		version_number = frappe.db.count("Decision Policy Version", {"policy": self.name})

		# Create new version
		definition = json.loads(self.definition_json)
		policy = validate_policy_data(definition)
		fingerprint = policy_fingerprint(policy)

		version_key = f"{self.name}_v{version_number}"

		version_doc = frappe.get_doc({
			"doctype": "Decision Policy Version",
			"version_key": version_key,
			"policy": self.name,
			"version_number": version_number,
			"status": "Published",
			"definition_json": self.definition_json,
			"schema_version": "1.0",
			"fingerprint": fingerprint,
			"default_model": self.default_model,
			"published_at": datetime.now(),
		})
		version_doc.insert()

		# Retire previous Published version
		prev_published = frappe.db.get_value(
			"Decision Policy Version",
			{"policy": self.name, "status": "Published"},
			"name"
		)
		if prev_published and prev_published != version_key:
			frappe.db.set_value("Decision Policy Version", prev_published, "status", "Retired")

		# Update current_version on self
		self.current_version = version_key
		self.fingerprint = fingerprint
		self.db_update({"current_version": version_key, "fingerprint": fingerprint})

		return version_key
