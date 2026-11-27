from frappe.model.document import Document

from huf.ai.gateway_core.event_helpers import _idempotency_key


class GatewayEvent(Document):
    """Immutable audit record for an inbound provider event."""

    def before_insert(self):
        # One row per (gateway, provider event ID), whatever the caller passed: the unique
        # ``idempotency_key`` is derived from the pair. Rows without a provider id keep their own key.
        if self.provider_event_id:
            self.idempotency_key = _idempotency_key(self.gateway, self.provider_event_id)
