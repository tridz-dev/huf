# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document

from huf.ai.automation import event_alias as runtime

_KEY_RE = re.compile(r"^[A-Za-z0-9_.]+$")
_SOURCE_FIELDS = ("reference_doctype", "doc_event")


class EventAlias(Document):
	def autoname(self):
		self.name = f"{self.app}.{self.key}"

	def validate(self):
		if not _KEY_RE.match(self.key or ""):
			frappe.throw(_("Key may only contain letters, numbers, dots and underscores."))
		self._validate_replacement()
		self._validate_sources()
		self._bump_version_on_breaking_change()

	def _validate_replacement(self):
		if self.status == "Deprecated" and self.replaced_by == self.name:
			frappe.throw(_("An event cannot replace itself."))
		if self.status != "Deprecated":
			self.replaced_by = None

	def _validate_sources(self):
		for row in self.sources or []:
			if row.condition:
				runtime.check_expression(row.condition, "Only When", row.idx)
			if row.dedupe_key:
				runtime.check_expression(row.dedupe_key, "Duplicate Guard", row.idx)
			if row.payload_mapping:
				runtime.parse_mapping(row.payload_mapping, row.idx)

	def _bump_version_on_breaking_change(self):
		"""Adding sources keeps the version; removing or changing one bumps it."""
		if self.is_new():
			self.version = self.version or 1
			return
		before = self.get_doc_before_save()
		if not before:
			return
		old = {tuple(r.get(f) for f in _SOURCE_FIELDS) for r in before.sources or []}
		new = {tuple(r.get(f) for f in _SOURCE_FIELDS) for r in self.sources or []}
		if old - new:
			self.version = (before.version or 1) + 1

	def on_update(self):
		runtime.clear_alias_cache()

	def on_trash(self):
		runtime.clear_alias_cache()
