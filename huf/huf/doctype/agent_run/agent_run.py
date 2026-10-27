# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _
import re


class AgentRun(Document):
	def validate(self):
		self.guard_runtime_context()
		self.guard_desktop_run_identity()
		self.extract_reference_from_prompt()
		self.validate_reference()

	def guard_runtime_context(self):
		"""``runtime_context`` holds the signed desktop pin (origin, policy, device). It is server
		state: a client (REST ``set_value`` or a document save by a Huf User) may not rewrite it on an
		existing run. The server's own writes use ``db.set_value`` or run as Administrator."""
		if self.is_new() or frappe.flags.in_install or frappe.flags.in_migrate:
			return
		if frappe.session.user == "Administrator" or "System Manager" in frappe.get_roles():
			return
		before = self.get_doc_before_save()
		if before is None:
			return

		def norm(value):
			if isinstance(value, str):
				try:
					return frappe.parse_json(value)
				except Exception:
					return value
			return value

		if norm(before.get("runtime_context")) != norm(self.get("runtime_context")):
			frappe.throw(_("runtime_context of an Agent Run is managed by the server."), frappe.PermissionError)

	# What a desktop pin is bound to, plus the state that decides whether the run is executed again.
	DESKTOP_PINNED_FIELDS = ("status", "prompt", "agent", "conversation")

	def guard_desktop_run_identity(self):
		"""A run that carries a desktop pin, or belongs to a desktop-hosted conversation, keeps its
		``status``, ``prompt``, ``agent`` and ``conversation`` against client writes. Setting a finished
		run back to ``Queued`` re-executes it, and editing its input steers what a desktop-origin run
		does. Workers, the sweeper and the run lifecycle write these with ``db.set_value`` / ``db_set``
		(no ``validate``) or as Administrator; only a client save reaches this check."""
		if self.is_new() or frappe.flags.in_install or frappe.flags.in_migrate:
			return
		if frappe.session.user == "Administrator" or "System Manager" in frappe.get_roles():
			return
		before = self.get_doc_before_save()
		if before is None:
			return
		context = before.get("runtime_context")
		if isinstance(context, str):
			try:
				context = frappe.parse_json(context)
			except Exception:
				context = {}
		pinned = isinstance(context, dict) and bool(context.get("desktop"))
		if not pinned and before.get("conversation"):
			pinned = (
				frappe.db.get_value("Agent Conversation", before.get("conversation"), "execution_host")
				== "desktop"
			)
		if not pinned:
			return
		for field in self.DESKTOP_PINNED_FIELDS:
			if (before.get(field) or "") != (self.get(field) or ""):
				frappe.throw(
					_("{0} of a desktop Agent Run is managed by the server.").format(field),
					frappe.PermissionError,
				)

	def extract_reference_from_prompt(self):
		if not self.reference_doctype or not self.reference_name:
			if self.prompt and isinstance(self.prompt, str):
				doctype_match = re.search(r'reference_doctype\s*=\s*["\']([^"\']+)["\']', self.prompt)
				name_match = re.search(r'reference_name\s*=\s*["\']([^"\']+)["\']', self.prompt)
				if doctype_match and name_match:
					candidate_doctype = doctype_match.group(1).strip()
					candidate_name = name_match.group(1).strip()
					if frappe.db.exists("DocType", candidate_doctype):
						self.reference_doctype = candidate_doctype
						self.reference_name = candidate_name

	def validate_reference(self):
		if self.reference_doctype:
			if not frappe.db.exists("DocType", self.reference_doctype):
				frappe.throw(_("Invalid Reference DocType: {0}").format(self.reference_doctype))
			if self.reference_name:
				if not frappe.db.exists(self.reference_doctype, self.reference_name):
					frappe.throw(_("Invalid Reference Name: {0} for DocType {1}").format(self.reference_name, self.reference_doctype))
		elif self.reference_name:
			frappe.throw(_("Reference DocType is required when Reference Name is specified."))
