# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from agentflo.ai.agent_hooks import clear_doc_event_agents_cache
from frappe.utils.safe_exec import get_safe_globals, safe_eval


def get_context(doc):
	return {"doc": frappe._dict(doc), **get_safe_globals()}

class Agent(Document):
	def validate(self):
		if not self.instructions:
			frappe.throw(_("Please provide an instruction for this AI Agent."))
		if self.is_scheduled and self.is_doc_event:
			frappe.throw(_("An Agent cannot be both Scheduled and Doc Event based. Please choose only one."))
		self.validate_condition()

	def get_indicator(doc):
		if doc.disabled:
			return _("Disabled"), "red", "disabled,=,Yes"
		else:
			return _("Enabled"), "green", "disabled,=,No"

	def on_update(self):
		clear_doc_event_agents_cache()  

	def on_trash(self):
		clear_doc_event_agents_cache()
	
	def validate_condition(self):
		if not self.condition:
			return

		temp_doc = frappe.new_doc(self.reference_doctype)
		try:
			frappe.safe_eval(self.condition, None, get_context(temp_doc.as_dict()))
		except Exception:
			frappe.throw(_("The Condition '{0}' is invalid").format(self.condition))
		