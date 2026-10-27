from frappe.model.document import Document


class TeamsGatewaySettings(Document):
	"""Teams-specific settings for one Gateway (name == gateway)."""

	def validate(self):
		from huf.ai.gateways.teams_tenant import normalize_tenant_text

		self.allowed_tenants = normalize_tenant_text(self.allowed_tenants)

	def on_update(self):
		from huf.ai.gateways.teams_tenant import clear_cache

		clear_cache(self.gateway)

	def on_trash(self):
		from huf.ai.gateways.teams_tenant import clear_cache

		clear_cache(self.gateway)
