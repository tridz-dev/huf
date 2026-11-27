import frappe
from frappe.model.document import Document


class FlowSendCounter(Document):
	"""Sends counted per (member, channel, window start), across all flows.

	Rows are written only through ``huf.ai.flow.policy.frequency_cap``.
	"""

	def autoname(self):
		from huf.ai.flow.policy.frequency_cap import counter_name

		self.name = counter_name(self.member_key, self.channel, self.window_start)


def on_doctype_update():
	frappe.db.add_unique("Flow Send Counter", ["member_key", "channel", "window_start"])
