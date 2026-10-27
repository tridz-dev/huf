"""WhatsApp test-send helper."""

from __future__ import annotations

from typing import Any


WHATSAPP_TEST_TEMPLATE = "hello_world"


def _whatsapp_test_send(adapter, gateway, reply) -> tuple[Any, str]:
	"""Send a WhatsApp test: free text inside the 24h window, else a template.

	Returns ``(delivery, sent_as)`` where ``sent_as`` is ``"message"`` or the template name. Outside the
	window the Gateway's fallback template is used when set, otherwise Meta's ``hello_world`` sample
	template, which every new WhatsApp Business Account starts with.
	"""
	from huf.ai.gateway_adapters import whatsapp_bridge as bridge

	if bridge.window_state(gateway.name, reply.conversation_id).get("open"):
		return adapter.send_reply(reply), "message"
	fallback = str(getattr(gateway, "fallback_template", "") or "").strip()
	if fallback:
		return adapter.send_reply(reply), fallback
	delivery = adapter.send_template(reply.conversation_id, WHATSAPP_TEST_TEMPLATE, "en_US", trusted=True)
	return delivery, WHATSAPP_TEST_TEMPLATE
