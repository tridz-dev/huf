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
		if self.allow_chat == 1 and self.persist_conversation == 0:
			frappe.throw(_("An agent cannot be allowed in Agent Chat when persistent conversation is off."))



	def get_indicator(doc):
		if doc.disabled:
			return _("Disabled"), "red", "disabled,=,Yes"
		else:
			return _("Enabled"), "green", "disabled,=,No"

	def on_update(self):
		clear_doc_event_agents_cache()  

	def on_trash(self):
		clear_doc_event_agents_cache()
		