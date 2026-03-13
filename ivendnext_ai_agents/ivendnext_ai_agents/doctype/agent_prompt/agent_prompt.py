# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class AgentPrompt(Document):
	def before_insert(self):
		self._generate_slug()
		self._set_prompt_group()

	def validate(self):
		if not self.prompt_body:
			frappe.throw(_("Prompt body is required."))

		if not self.version:
			self.version = 1

	def _generate_slug(self):
		"""Auto-generate slug from title if not provided."""
		if not self.slug and self.title:
			slug = frappe.scrub(self.title).replace("_", "-")
			# Ensure uniqueness by appending version
			if self.version and cint(self.version) > 1:
				slug = f"{slug}-v{self.version}"
			# Check for duplicates
			if frappe.db.exists("Agent Prompt", {"slug": slug}):
				slug = f"{slug}-v{self.version or 1}"
				if frappe.db.exists("Agent Prompt", {"slug": slug}):
					slug = f"{slug}-{frappe.generate_hash(length=4)}"
			self.slug = slug

	def _set_prompt_group(self):
		"""Set prompt_group to tie versions together.

		For a brand-new prompt lineage the group is the document name itself.
		When a new version is created from an existing prompt the group is
		inherited from the previous version so all versions share the same
		identifier.
		"""
		if self.previous_version:
			parent_group = frappe.db.get_value(
				"Agent Prompt", self.previous_version, "prompt_group"
			)
			self.prompt_group = parent_group or self.previous_version
		elif not self.prompt_group:
			# Will be set to self.name after insert via after_insert
			self.prompt_group = ""

	def after_insert(self):
		"""Finalise prompt_group for brand-new lineages (no previous_version)."""
		if not self.prompt_group:
			frappe.db.set_value(
				"Agent Prompt", self.name, "prompt_group", self.name, update_modified=False
			)
			self.prompt_group = self.name