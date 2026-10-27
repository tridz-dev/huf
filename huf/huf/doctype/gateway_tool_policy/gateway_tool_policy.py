from frappe.model.document import Document


class GatewayToolPolicy(Document):
	"""Optional per-gateway / per-channel tool allow or deny list (see huf.ai.gateways.tool_policy)."""
