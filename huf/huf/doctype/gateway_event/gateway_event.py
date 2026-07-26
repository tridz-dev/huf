from frappe.model.document import Document


class GatewayEvent(Document):
    """Immutable audit record for an inbound provider event."""
