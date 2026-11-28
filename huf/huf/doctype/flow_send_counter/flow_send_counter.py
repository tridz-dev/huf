import frappe
from frappe.model.document import Document


class FlowSendCounter(Document):
	"""Sends counted per (member, channel, window length, window start), across all flows.

	Rows are written only through ``huf.ai.flow.policy.frequency_cap``.
	"""

	def autoname(self):
		from huf.ai.flow.policy.frequency_cap import counter_name

		self.name = counter_name(self.member_key, self.channel, self.window_seconds, self.window_start)


def on_doctype_update():
	# add_unique never removes an index: the one without the window length would still make day and week collide.
	if frappe.db.has_index("tabFlow Send Counter", "unique_member_key_channel_window_start"):
		frappe.db.sql_ddl(
			"alter table `tabFlow Send Counter` drop index `unique_member_key_channel_window_start`"
		)
	frappe.db.add_unique("Flow Send Counter", ["member_key", "channel", "window_seconds", "window_start"])
