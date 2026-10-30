"""``list_messages`` action of the WhatsApp agent tool (``huf.ai.tools.whatsapp``).

The tool's response helpers are imported lazily: that module imports this one.
"""

import json
from typing import Any

import frappe

from huf.ai.gateway_adapters import whatsapp_bridge as bridge

_LIST_DEFAULT_LIMIT = 20
_LIST_MAX_LIMIT = 50


def _clamp_limit(value: Any) -> int:
	try:
		number = int(value)
	except (TypeError, ValueError):
		number = _LIST_DEFAULT_LIMIT
	return max(1, min(number, _LIST_MAX_LIMIT))


def list_messages(kwargs: dict) -> str:
	"""Messages exchanged with ONE contact through the run's own gateway (newest first, cursor paged).

	Built on ``list_message_log`` so it is gateway scoped and permission checked for the run user;
	each item carries the wamid in ``message_id``.
	"""
	from huf.ai.tools.whatsapp import _error, _refused, _success

	contact = bridge.normalize_phone(kwargs.get("to") or kwargs.get("recipient") or kwargs.get("phone_number") or "")
	if not contact:
		return _refused("contact_required", "Name the contact ('to') whose messages should be listed.")
	from huf.ai.whatsapp import management as mgmt

	try:
		result = mgmt.list_message_log(
			gateway_name=kwargs["gateway_name"],
			phone=contact,
			cursor=(kwargs.get("cursor") or "").strip() or None,
			limit=_clamp_limit(kwargs.get("limit")),
		)
	except frappe.PermissionError:
		return _refused("permission_denied", "Not permitted to read WhatsApp messages")
	except Exception as e:
		return _error(f"Failed to fetch WhatsApp messages: {str(e)}")
	if not result.get("success"):
		return json.dumps(result, default=str)
	return _success(
		{"items": result.get("items") or [], "next_cursor": result.get("next_cursor"), "has_more": bool(result.get("has_more"))}
	)
