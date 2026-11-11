# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Call-site helpers for the external ``huf_gateway_pre_send`` gate (see ``gateway_hooks.gate_hook``).

Every outbound send path (adapter, bridge, agent tool, management API) runs the gate through here, before
anything reaches Meta or the ``WhatsApp Message`` table. ``gateway_name`` None is refused when a hook is registered (see
:func:`outbound_policy.check_pre_send`). A refusal is a policy decision, never retryable.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import frappe

from huf.ai.whatsapp import outbound_policy as policy

MEDIA_TYPES = frozenset({"image", "audio", "video", "document", "sticker"})


def kind_of(msg_type: str) -> str:
	"""Map a Graph message ``type`` to the hook ``kind``: text | template | media | other."""
	return msg_type if msg_type in ("text", "template") else "media" if msg_type in MEDIA_TYPES else "other"


def _digits(value: Any) -> str:
	return "".join(c for c in str(value or "") if c.isdigit())


def consent_confirmed(gateway_name: str | None, to: Any, kind: str = "text") -> bool:
	"""True for a ``text`` send to the recipient of the in-flight consent confirmation on this gateway."""
	token = getattr(frappe.local, "huf_consent_send_scope", None)
	return bool(kind == "text" and token and gateway_name and token[0] == gateway_name and _digits(token[1]) == _digits(to))


def check(
	gateway_name: str | None, to: Any, kind: str, source: str, subtype: str = "", consent_to: Any = None
) -> None:
	"""Run the gate for the bridge / adapter; raises ``OutboundRefused``. ``consent_to``: raw recipient id."""
	policy.check_pre_send(
		gateway_name or None,
		to,
		kind,
		{
			"source": source,
			"consent_confirmation": consent_confirmed(gateway_name, to if consent_to is None else consent_to, kind),
			"subtype": subtype,
		},
	)


def agent_tool_gate(gateway_name: Any, recipient: str, kind: str, subtype: str) -> tuple[str, str] | None:
	"""Gate for an agent-tool send: ``(code, message)`` on refusal, else None. Fails closed without a gateway
	(``handle_action`` always binds ``gateway_name``; reaching a send without one is a bug)."""
	gateway = (gateway_name or "").strip()
	if not gateway:
		return "blocked_by_hook", "Blocked by gateway hook"
	try:
		policy.check_pre_send(gateway, recipient, kind, {"source": "agent_tool", "subtype": subtype})
	except policy.OutboundRefused as e:
		return e.code, str(e)
	return None


def management_refusal(
	gateway_name: str | None, phone: str, kind: str, subtype: str
) -> dict[str, Any] | None:
	"""Gate for a management-API send: the refusal payload, or None to proceed."""
	try:
		policy.check_pre_send(gateway_name, phone, kind, {"source": "management", "subtype": subtype})
	except policy.OutboundRefused as exc:
		return {"success": False, "error": exc.code, "message": str(exc)}
	return None


def check_graph(gateway_name: str | None, data: dict[str, Any]) -> None:
	"""Gate a direct Graph POST body (adapter; bridge mode fires the gate inside the bridge instead)."""
	msg_type = str(data.get("type") or "")
	check(gateway_name, data.get("to"), kind_of(msg_type), "adapter", msg_type)


def via_bridge(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
	"""Call a bridge send; a ``blocked_by_hook`` refusal becomes ``OutboundRefused`` again (as in direct mode)."""
	from huf.ai.gateway_adapters.whatsapp_bridge import BridgeError

	try:
		return fn(*args, **kwargs)
	except BridgeError as exc:
		if (exc.payload or {}).get("error") == "blocked_by_hook":
			raise policy.OutboundRefused(
				str(exc.payload.get("message") or "Blocked by policy."), "blocked_by_hook"
			) from exc
		raise
