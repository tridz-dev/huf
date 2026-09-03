# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils.safe_exec import get_safe_globals, safe_eval
from frappe import _


def get_context(doc):
	return {"doc": frappe._dict(doc), **get_safe_globals()}


class AgentTrigger(Document):
	def validate(self):
		# Default target_type for triggers created before this field existed.
		if not self.target_type:
			self.target_type = "Agent"

		if self.trigger_type == "Doc Event":
			self.validate_condition()

		if self.trigger_type == "Doc Event" and (not self.reference_doctype or not self.doc_event):
			frappe.throw(_("Reference Doctype and Doc Event are required for Doc Event triggers."))
		if self.trigger_type == "Schedule" and not self.scheduled_interval:
			frappe.throw(_("Scheduled Interval is required for Schedule triggers."))

		if self.target_type == "Agent" and not self.agent:
			frappe.throw(_("Agent is required when Target Type is Agent."))
		if self.target_type == "Flow" and not self.flow:
			frappe.throw(_("Flow is required when Target Type is Flow."))

		if self.target_type == "Flow" and self.flow:
			flow_status = frappe.db.get_value("Flow Definition", self.flow, "status")
			if flow_status and flow_status != "Active" and not self.disabled:
				frappe.msgprint(
					_("Flow '{0}' is not Active (status: {1}). This trigger will not run until the flow is activated.").format(
						self.flow, flow_status
					),
					indicator="orange",
					alert=True,
				)

	def validate_condition(self):
		if not self.condition:
			return

		temp_doc = frappe.new_doc(self.reference_doctype)
		try:
			frappe.safe_eval(self.condition, None, get_context(temp_doc.as_dict()))
		except (SyntaxError, NameError, TypeError, ValueError):
			frappe.throw(_("The Condition '{0}' is invalid").format(self.condition))


@frappe.whitelist()
def get_trigger_type():
    options = frappe.get_meta("Agent Trigger").get_field("trigger_type").options
    if options:
        return [{"name": option} for option in options.split("\n")]
    else:
        return []
