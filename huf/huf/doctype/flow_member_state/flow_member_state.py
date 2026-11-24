from frappe.model.document import Document


class FlowMemberState(Document):
	"""One row per (flow, member): the member's journey variables, status and history.

	Rows are created and changed only through ``huf.ai.flow.member``. The name is a deterministic hash
	of (flow, member key), so the primary key itself guarantees one row per member.
	"""

	def autoname(self):
		from huf.ai.flow.member import member_name

		self.name = member_name(self.flow, self.member_key)
