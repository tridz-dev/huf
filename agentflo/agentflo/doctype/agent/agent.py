# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from agentflo.ai.agent_hooks import clear_doc_event_agents_cache


class Agent(Document):
	def validate(self):
		if not self.instructions:
			frappe.throw(_("Please provide an instruction for this AI Agent."))
		if self.is_scheduled and self.is_doc_event:
			frappe.throw(_("An Agent cannot be both Scheduled and Doc Event based. Please choose only one."))

	def get_indicator(doc):
		if doc.disabled:
			return _("Disabled"), "red", "disabled,=,Yes"
		else:
			return _("Enabled"), "green", "disabled,=,No"

	def on_update(self):
		clear_doc_event_agents_cache() #recreate= clear then create 

	def on_trash(self):
		clear_doc_event_agents_cache()
