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
		if self.trigger_type == "Doc Event":
			self.validate_condition()

		if self.trigger_type == "Doc Event" and (not self.reference_doctype or not self.doc_event):
			frappe.throw(_("Reference Doctype and Doc Event are required for Doc Event triggers."))
		if self.trigger_type == "Schedule" and not self.scheduled_interval:
			frappe.throw(_("Scheduled Interval is required for Schedule triggers."))
		if self.trigger_type == "Webhook":
			self.validate_webhook()

	def validate_webhook(self):
		if not self.webhook_slug or not self.webhook_key:
			frappe.throw(_("Webhook Slug and Webhook Key are required for Webhook triggers."))

		# Slug must be unique across enabled Webhook triggers so the guest
		# endpoint can resolve a request to exactly one trigger.
		filters = {
			"trigger_type": "Webhook",
			"webhook_slug": self.webhook_slug,
			"disabled": 0,
			"name": ["!=", self.name],
		}
		if not self.disabled and frappe.db.exists("Agent Trigger", filters):
			frappe.throw(
				_("Webhook Slug '{0}' is already used by another enabled Webhook trigger.").format(
					self.webhook_slug
				)
			)



	def validate_condition(self):
		if not self.condition:
			return

		temp_doc = frappe.new_doc(self.reference_doctype)
		try:
			frappe.safe_eval(self.condition, None, get_context(temp_doc.as_dict()))
		except Exception:
			frappe.throw(_("The Condition '{0}' is invalid").format(self.condition))
		
	
@frappe.whitelist()
def get_trigger_type():
    options = frappe.get_meta("Agent Trigger").get_field("trigger_type").options
    if options:
        return [{"name": option} for option in options.split("\n")]
    else:
        return []
