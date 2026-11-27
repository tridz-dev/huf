import frappe
from frappe.model.document import Document


class FlowMemberState(Document):
	"""One row per (flow, member): the member's journey variables, status and history.

	Rows are created and changed only through ``huf.ai.flow.runs.member``. The name is a deterministic hash
	of (flow, member key), so the primary key itself guarantees one row per member.
	"""

	def autoname(self):
		from huf.ai.flow.runs.member import member_name

		self.name = member_name(self.flow, self.member_key)


def on_doctype_update():
	"""Composite indexes. ``member_key`` alone is indexed through ``search_index`` on the field, because schema
	sync drops single-column indexes the field does not declare."""
	frappe.db.add_unique("Flow Member State", ["flow", "member_key"], "unique_flow_member_key")
	frappe.db.add_index("Flow Member State", ["flow", "status"], "flow_status_index")
