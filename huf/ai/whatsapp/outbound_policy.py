# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""The single outbound policy choke point for WhatsApp sends.

Every send path (adapter text/media/template/fallback, the bridge template send, the agent tools)
calls into this module before anything is written or posted:

* :func:`check_recipient`: STOP (opt-out) and the BSUID refusal (a business-scoped user id is not a
  phone number Meta accepts as ``to``).
* :func:`check_template`: the template must be APPROVED (a paused/rejected/pending one is refused) and
  a MARKETING template is refused for a contact whose latest marketing preference is ``stop``.
* :func:`record_template_outreach` / :func:`has_received_template`: a contact who only ever received a
  proactive template has no access entry; this durable marker lets their STOP be recorded.

Refusals raise :class:`OutboundRefused` with a stable machine-readable ``code``.
"""

from __future__ import annotations

from typing import Any

import frappe

OUTREACH = "template_outreach"  # Gateway Consent category: the contact was sent a proactive template


class OutboundRefused(frappe.ValidationError):
	"""An outbound WhatsApp send was refused by policy. ``code`` is the stable reason."""

	def __init__(self, message: str, code: str):
		super().__init__(message)
		self.code = code


def _is_bsuid(recipient: Any) -> bool:
	from huf.ai.gateway_adapters import whatsapp_bridge as bridge

	return bridge.is_bsuid(recipient)


def check_recipient(gateway: str | None, recipient: Any) -> None:
	"""Refuse a BSUID recipient and a STOPped contact. ``gateway`` None skips only the opt-out lookup."""
	if _is_bsuid(recipient):
		raise OutboundRefused(
			"A business-scoped user id (BSUID) cannot be used as a WhatsApp recipient; send to the contact's phone number.",
			"bsuid_recipient",
		)
	if gateway:
		from huf.ai import gateway_service

		if gateway_service.is_opted_out(gateway, str(recipient or "")):
			raise OutboundRefused(
				"This contact opted out (STOP); no messages are sent until they opt back in (START).",
				"opted_out",
			)


def check_template(gateway: str | None, recipient: Any, row: dict[str, Any] | None) -> None:
	"""Refuse a known template that is not APPROVED, and MARKETING to a contact who stopped marketing."""
	if not row:
		return
	status = str(row.get("status") or "").upper()
	if status and status != "APPROVED":
		raise OutboundRefused(
			f"The template is {status.lower()}, not approved, so it was not sent.", "template_not_approved"
		)
	if gateway and str(row.get("category") or "").upper() == "MARKETING":
		from huf.ai.whatsapp import account_events as events

		if not events.is_marketing_allowed(gateway, recipient):
			raise OutboundRefused(
				"This contact stopped marketing messages; a marketing template was not sent.", "marketing_opted_out"
			)


def gateways_for_account(account: str) -> list[str]:
	if not account:
		return []
	return frappe.get_all(
		"Gateway", filters={"provider": "WhatsApp", "whatsapp_account": account}, pluck="name", limit_page_length=0
	)


def enforce_template(
	account: str, recipient: Any, row: dict[str, Any] | None, gateway: str | None = None
) -> None:
	"""Bridge-level gate: the named gateway, else every gateway linked to the account (fail closed)."""
	gateways = [gateway] if gateway else gateways_for_account(account)
	check_recipient(None, recipient)
	for name in gateways or [None]:
		check_recipient(name, recipient)
		check_template(name, recipient, row)


def has_received_template(gateway: str, recipient: Any) -> bool:
	from huf.ai.whatsapp import account_events as events

	key = events._norm_sender(recipient)
	return bool(key) and events._latest_consent(gateway, key, OUTREACH) is not None


def record_template_outreach(gateway: str, recipient: Any) -> None:
	"""Remember that ``recipient`` was sent a proactive template on ``gateway`` (idempotent)."""
	from huf.ai.whatsapp import account_events as events

	key = events._norm_sender(recipient)
	if not gateway or not key or not frappe.db.exists("Gateway", gateway):
		return
	if events._latest_consent(gateway, key, OUTREACH) is not None:
		return
	try:
		events._insert_consent(gateway, key, OUTREACH, "resume", "proactive template sent")
	except Exception:  # the template was already delivered; a lost marker must not fail the send
		frappe.log_error(title="WhatsApp template outreach marker not recorded")


def note_template_sent(
	account: str,
	recipient: Any,
	gateway: str | None = None,
	template: str | None = None,
	language: str | None = None,
	solution: str | None = None,
) -> None:
	"""After a successful template send: mark the contact as reached on each applicable gateway.

	With ``template`` (and a ``solution``) the usage is also recorded for Solutions; that part never fails a send.
	"""
	for name in [gateway] if gateway else gateways_for_account(account):
		record_template_outreach(name, recipient)
	if template and solution:
		try:
			from huf.ai.solutions import template_usage

			template_usage.record_observed(account, template, language, solution)
		except Exception:
			frappe.log_error(title="Template usage not recorded")
