from frappe.model.document import Document


class FlowState(Document):
	"""Small per-(flow, key) JSON value used by ``state.get`` / ``state.set`` nodes.

	Rows are created and read only through ``huf.ai.flow.state``, which scopes every access to the
	running flow's id. The doctype itself is limited to System Manager / Huf Manager.
	"""

	def autoname(self):
		from huf.ai.flow.state import state_name

		self.name = state_name(self.flow_id, self.state_key)
