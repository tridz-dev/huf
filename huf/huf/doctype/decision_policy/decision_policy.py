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

	def on_trash(self):
		"""Block deletion if policy is referenced by active Flow Definitions.

		Scans active Flow Definitions for router.decision nodes that reference
		this policy by name. If found, raises an exception with the list of
		references, preventing deletion.
		"""
		from huf.ai.decision.policy_references import get_policy_references

		# Check if this policy is referenced by any active Flow Definitions
		references = get_policy_references(self.name)

		if references:
			# Format a readable list of references
			flow_refs = []
			for ref in references:
				flow_refs.append(
					_("Flow: {0} (node: {1})").format(
						frappe.bold(ref["flow_name"]),
						ref["node_id"]
					)
				)

			frappe.throw(
				_("Cannot delete policy {0}: referenced by {1} active Flow(s):\n{2}").format(
					frappe.bold(self.name),
					len(references),
					"\n".join(flow_refs)
				),
				title=_("Policy Referenced by Active Flows")
			)

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
	def get_references(self):
		"""Get all active Flow Definitions that reference this policy.

		Used by the UI to show warnings when disabling a policy or planning
		its deletion. Requires read permission on Decision Policy.

		Returns:
			List of dicts with flow_id, flow_name, node_id, node_label, flow_def_name
		"""
		from huf.ai.decision.policy_references import get_policy_references

		# Permission check: user must have read permission on this policy
		if not frappe.has_permission("Decision Policy", "read", self.name):
			frappe.throw(
				_("You do not have permission to view this policy's references"),
				title=_("Permission Denied")
			)

		return get_policy_references(self.name)

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

		# Retire all previous Published versions (keep only the newest Published)
		prev_published_versions = frappe.db.get_list(
			"Decision Policy Version",
			filters={"policy": self.name, "status": "Published"},
			fields=["name"],
			order_by="version_number desc"
		)
		for prev in prev_published_versions:
			if prev.name != version_key:
				frappe.db.set_value("Decision Policy Version", prev.name, "status", "Retired")

		# Update current_version on self
		self.current_version = version_key
		self.fingerprint = fingerprint
		self.db_update()

		return version_key
