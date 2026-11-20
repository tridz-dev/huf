# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Small event helpers split out of ``gateway_service`` (re-imported there)."""

from __future__ import annotations

from typing import Any

import frappe

from huf.ai.gateway_adapters import provider_hooks


def _lang_code(value: Any) -> str:
	return str(value or "").strip().replace("-", "_").split("_")[0].lower()


def _conversation_race_errors() -> tuple[type, ...]:
	return (frappe.QueryDeadlockError, frappe.TimestampMismatchError)


def _flow_trigger_payload(event, gateway, attachments: list[str]) -> dict:
	"""What a Flow gets for a gateway message (see ``huf.ai.flow.gateways.gateway_payload``)."""
	from huf.ai.flow.gateways.gateway_payload import build_payload

	return build_payload(
		event, gateway, attachments, provider_hooks.get(gateway.provider, "extra_event_fields")
	)
