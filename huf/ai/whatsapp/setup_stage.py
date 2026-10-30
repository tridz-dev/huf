# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt
"""The server-computed WhatsApp ``setup_stage`` of a gateway (PLAN section 4.1)."""

from __future__ import annotations

from typing import Any

SETUP_STAGES = (
	"not_connected",
	"connected_unverified",
	"receiving",
	"live_unrouted",
	"live",
	"degraded",
	"blocked",
	"off",
)


def compute_setup_stage(
	*,
	enabled: bool,
	health: str,
	credentials_ok: bool,
	webhook_verified: bool,
	inbound_seen: bool,
	outbound_ok: bool,
	bound: bool,
	access_policy_chosen: bool,
) -> str:
	"""Pure: the PLAN section 4.1 setup stage of one gateway, from the health payload.

	Inputs are the existing signals of :func:`evaluate` / :func:`build_health`:

	* ``enabled``: ``Gateway.is_enabled``. Disabled gateways are ``off`` whatever else is true.
	* ``health``: the ``health`` value (``healthy``, ``degraded``, ``blocked``, ``not_set_up``, ``disabled``).
	* ``credentials_ok``: access token, phone number id and verify token are all present
	  (the ``credentials`` checklist step is ``done`` or ``blocked`` on a mismatch or rejected token).
	* ``webhook_verified``: the ``webhook`` checklist step is ``done`` (``last_verify_ok_at``,
	  ``last_event_at`` or any Gateway Event). This is the "first signed request received" signal.
	* ``inbound_seen``: the ``subscribed`` checklist step is ``done`` (at least one Gateway Event).
	* ``outbound_ok``: the ``test_message`` checklist step is ``done`` (a reply with reply_status
	  sent/delivered/read exists). ``inbound_seen and outbound_ok`` is the test round-trip.
	* ``bound``: a default target (Agent or Flow) is set on the gateway (``policy.default_target``).
	* ``access_policy_chosen``: a direct-message policy is set (``policy.direct_policy``). Note that
	  the field defaults to "Allow list", so today this is effectively always true.

	Derivation, checked in this order (first match wins):

	1. ``off``: not enabled (``health == "disabled"``).
	2. ``not_connected``: credentials not all saved (the ``credentials`` step is not done).
	3. ``blocked``: health ``blocked`` with credentials saved. Any error-severity reason counts:
	   rejected or expired token (``access_token_invalid``), account disconnected
	   (``gateway_disconnected``), account/phone mismatch, and also a missing app secret or a
	   failed signature check, which the health layer already treats as errors.
	4. ``degraded``: health ``degraded`` (warning-severity reasons such as delivery failures,
	   a recent error, a rejected fallback template, or senders waiting for approval).
	5. ``connected_unverified``: credentials saved but the webhook has not been verified and no
	   event has arrived yet.
	6. ``receiving``: the webhook is verified, but the test round-trip is not complete.
	7. ``live``: round-trip complete, a default target is bound and an access policy is set.
	8. ``live_unrouted``: round-trip complete, but no agent/Solution is bound or no policy is set.
	"""
	if not enabled:
		return "off"
	if not credentials_ok:
		return "not_connected"
	if health == "blocked":
		return "blocked"
	if health == "degraded":
		return "degraded"
	if not webhook_verified:
		return "connected_unverified"
	if not (inbound_seen and outbound_ok):
		return "receiving"
	if bound and access_policy_chosen:
		return "live"
	return "live_unrouted"


def for_payload(payload: dict[str, Any]) -> str:
	"""PLAN 4.1 ``setup_stage`` from a built gateway payload (see :func:`compute_setup_stage`)."""
	steps = {c.get("code"): c.get("state") for c in payload.get("checklist") or []}
	policy = payload.get("policy") or {}
	return compute_setup_stage(
		enabled=bool(payload.get("enabled")),
		health=str(payload.get("health") or ""),
		# the checklist's credentials step is "blocked" on a mismatch or a rejected token, which still counts as saved
		credentials_ok=bool(
			payload.get("access_token_present") and payload.get("verify_token_present") and payload.get("phone_number_id")
		),
		webhook_verified=steps.get("webhook") == "done",
		inbound_seen=steps.get("subscribed") == "done",
		outbound_ok=steps.get("test_message") == "done",
		bound=bool(policy.get("default_target")),
		access_policy_chosen=bool(policy.get("direct_policy")),
	)
