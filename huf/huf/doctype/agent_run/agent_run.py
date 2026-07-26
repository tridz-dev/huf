# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _
import re


class AgentRun(Document):
	def validate(self):
		self.extract_reference_from_prompt()
		self.validate_reference()

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
