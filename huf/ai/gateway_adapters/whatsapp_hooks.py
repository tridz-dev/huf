# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WhatsApp provider hooks: thin wrappers over the existing gateway_service / gateway_webhook code.

Each wrapper resolves its target at call time so patching the original function still works.
"""

from __future__ import annotations

from huf.ai.gateway_adapters import provider_hooks

PROVIDER = "WhatsApp"


def _svc():
	from huf.ai import gateway_service

	return gateway_service


def _hook(name):
	def deco(fn):
		provider_hooks.register(PROVIDER, name, fn)
		return fn

	return deco


@_hook("inbound_kind")
def inbound_kind(event):
	return _svc()._inbound_media_type(event)


@_hook("media_save")
def media_save(event, gateway):
	return _svc()._save_whatsapp_media(event, gateway)


@_hook("typing")
def typing(event, gateway):
	from huf.ai.gateway_webhook import mark_gateway_read_typing

	enabled = getattr(gateway, "typing_indicator", None)
	if enabled is not None and not int(enabled):
		return None
	return mark_gateway_read_typing(gateway, event)


@_hook("send_reply")
def send_reply(event, gateway, agent_run_id, text):
	return _svc()._send_whatsapp_reply(event, gateway, agent_run_id, text)


@_hook("error_text")
def error_text(exc):
	return _svc()._whatsapp_error_text(exc)


@_hook("send_errors")
def send_errors():
	from huf.ai.gateway_adapters.whatsapp import WhatsAppWindowClosed
	from huf.ai.gateway_adapters.whatsapp_bridge import BridgeError

	return (WhatsAppWindowClosed, BridgeError)


@_hook("normalize_sender")
def normalize_sender(entry_type, external_id):
	if entry_type == "Sender":
		from huf.ai.gateway_adapters.whatsapp_bridge import normalize_phone

		return normalize_phone(external_id) or str(external_id)
	return str(external_id)


@_hook("consent_required")
def consent_required():
	return True


@_hook("extra_event_fields")
def extra_event_fields(event, gateway, sender):
	"""Structured fields for a flow trigger (button, ad, location, contacts, order...); see ``trigger_extras``."""
	from huf.ai.gateway_adapters.trigger_extras import whatsapp_fields as wf

	extras = wf.message_extras(wf.load_raw(event), sender)
	extras["wa_id"] = sender
	try:
		hours = wf.hours_since_previous(gateway.name, sender, event.get("received_at"))
	except Exception:
		hours = None
	if hours is not None:
		extras["hours_since_last_customer_message"] = hours
	return extras


@_hook("recover_reply_parts")
def recover_reply_parts(response):
	from huf.ai.gateway_adapters import whatsapp_format as wf

	return wf.split_body(wf.to_whatsapp(response)) or [response]


@_hook("linked_sender_ids")
def linked_sender_ids(gateway_name, primary):
	return _svc()._whatsapp_linked_sender_ids(gateway_name, primary, PROVIDER)


@_hook("adapter_context")
def adapter_context(gateway, contact_name):
	from huf.ai.gateway_webhook import _fallback_params

	return {
		"gateway_name": gateway.name,
		"whatsapp_account": (gateway.get("whatsapp_account") or "").strip(),
		"fallback_template": (gateway.get("fallback_template") or "").strip(),
		"fallback_template_language": (gateway.get("fallback_template_language") or "").strip(),
		"fallback_template_params": _fallback_params(gateway, contact_name),
		"contact_name": contact_name,
		"preview_url": (gateway.get("preview_url") or "").strip(),
	}


@_hook("reply_target")
def reply_target(event):
	# A2: WhatsApp never fragments conversations by thread; the reply quotes the inbound wamid.
	return None, event.provider_event_id or None


@_hook("send_parts")
def send_parts(gateway, event, parts, quote):
	from huf.ai.gateway_webhook import event_contact_name, get_gateway_adapter

	adapter = get_gateway_adapter(gateway, event_contact_name(event))
	return adapter.send_text_parts(
		event.conversation_id, list(parts), (event.provider_event_id or None) if quote else None
	)


@_hook("webhook_signals")
def webhook_signals():
	return True


@_hook("failed_status")
def failed_status(gateway_name, status):
	from huf.ai.gateway_webhook import _record_failed_status_whatsapp

	return _record_failed_status_whatsapp(gateway_name, status)


@_hook("mark_read_typing")
def mark_read_typing(adapter, provider_event_id):
	return adapter.mark_read_typing(provider_event_id)
