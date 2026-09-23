# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
"""Decision Policy Version -- manages immutable published policy versions with fingerprints.

A Policy Version is created as Draft and can be edited. Once published, it becomes immutable:
  - Published versions refuse all edits (before_save guard).
  - Publish transition: Draft -> Published, retires any previous Published version,
    updates Decision Policy.current_version and published_at.
  - Fingerprint is computed server-side per policy definition (semantic, excluding deployment).
"""

import frappe
from frappe import _
from frappe.model.document import Document

from huf.ai.decision.policy import policy_fingerprint, validate_policy_data


class DecisionPolicyVersion(Document):
	"""Published versions are immutable; fingerprint computed server-side on save."""

	def validate(self):
		"""Prevent edits on Published versions; compute fingerprint; validate definition."""
		self._guard_published_immutability()
		self._compute_fingerprint_and_validate()

	def on_update(self):
		"""On publish: retire previous Published, update Decision Policy.current_version."""
		if self.status == "Published":
			self._publish_policy_version()

	def _guard_published_immutability(self):
		"""Refuse edits on Published versions (before_save guard)."""
		if not self.is_new():
			doc_before_save = self.get_doc_before_save()
			if doc_before_save and doc_before_save.status == "Published":
				frappe.throw(
					_("Published Policy Versions are immutable and cannot be edited. "
					  "Create a new Draft version to make changes."),
					title=_("Immutable Version")
				)

	def _compute_fingerprint_and_validate(self):
		"""Compute fingerprint from definition; validate policy."""
		try:
			# Parse and validate the policy definition
			import json
			definition = json.loads(self.definition_json)
			policy = validate_policy_data(definition)

			# Compute fingerprint (excludes deployment identity per A01 §38)
			self.fingerprint = policy_fingerprint(policy)
		except Exception as e:
			frappe.throw(
				_("Invalid policy definition: {0}").format(str(e)),
				title=_("Policy Validation Error")
			)

	def _generate_version_key(self):
		"""Generate version_key from policy and version_number."""
		return f"{self.policy}_v{self.version_number}"

	def _publish_policy_version(self):
		"""On publish: mark previous Published as Retired, update Decision Policy.current_version."""
		# Retire all previous Published versions for this policy (keep only the newest Published)
		prev_published_versions = frappe.db.get_list(
			"Decision Policy Version",
			filters={"policy": self.policy, "status": "Published"},
			fields=["name"],
			order_by="version_number desc"
		)
		for prev in prev_published_versions:
			if prev.name != self.name:
				frappe.db.set_value("Decision Policy Version", prev.name, "status", "Retired")

		# Update Decision Policy.current_version and fingerprint. `published_at` is
		# tracked on this Decision Policy Version (not on Decision Policy, which has
		# no such field) -- see the `published_at` field above.
		frappe.db.set_value(
			"Decision Policy",
			self.policy,
			{
				"current_version": self.name,
				"fingerprint": self.fingerprint,
			}
		)
