import json

import frappe
from frappe.model.document import Document

from huf.ai.gateway_adapters.provider_ids import provider_to_service_id
from huf.ai.gateway_adapters.registered import get_adapter_class


class GatewayTemplate(Document):
	def validate(self):
		self._validate_gateway_supports_templates()
		self._validate_components_json()

	def _validate_gateway_supports_templates(self):
		gateway_name = self.gateway
		gateway_doc = frappe.get_doc("Gateway", gateway_name)
		provider_display = gateway_doc.provider

		provider_id = provider_to_service_id(provider_display)

		try:
			adapter_class = get_adapter_class(provider_id)
		except KeyError:
			frappe.throw(
				f"Gateway provider '{provider_display}' is not registered. "
				f"Cannot validate template support."
			)

		if not adapter_class.capabilities.supports_templates:
			frappe.throw(
				f"Gateway provider '{provider_display}' does not support templates. "
				f"Gateway Template records can only be created for gateways whose provider "
				f"has template capability enabled."
			)

	def _validate_components_json(self):
		if not self.components:
			return

		try:
			json.loads(self.components)
		except (json.JSONDecodeError, ValueError) as e:
			frappe.throw(f"Components field must contain valid JSON. Error: {str(e)}")
