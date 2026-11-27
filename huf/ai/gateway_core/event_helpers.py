# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Small event helpers split out of ``gateway_service`` (re-imported there)."""

from __future__ import annotations

import hashlib
from typing import Any

import frappe

from huf.ai.gateway_adapters import provider_hooks


def _idempotency_key(gateway_name: str, provider_event_id: str) -> str:
	"""Dedupe key of one provider event: unique per (gateway, provider event ID).

	A hash, not a composite index: the database collation is case-insensitive and provider ids
	(e.g. WhatsApp wamids) are not, so an index on the raw id could drop distinct events.
	"""
	value = f"{gateway_name}:{provider_event_id}".encode()
	return hashlib.sha256(value).hexdigest()


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
