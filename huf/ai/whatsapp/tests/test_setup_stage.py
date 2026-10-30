# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt
"""Unit tests for the server-computed WhatsApp ``setup_stage`` (PLAN section 4.1)."""

import unittest
from unittest.mock import MagicMock, patch

import frappe

if isinstance(frappe, MagicMock):
	frappe.whitelist = lambda *args, **kwargs: (lambda fn: fn)
	frappe.PermissionError = PermissionError

from huf.ai.whatsapp import setup_stage as wh  # noqa: E402
from huf.ai.whatsapp import management as mgmt  # noqa: E402

STAGES = {
	"not_connected",
	"connected_unverified",
	"receiving",
	"live_unrouted",
	"live",
	"degraded",
	"blocked",
	"off",
}


def stage(**over):
	"""compute_setup_stage with a fully working gateway, overridden per test."""
	base = {
		"enabled": True,
		"health": "healthy",
		"credentials_ok": True,
		"webhook_verified": True,
		"inbound_seen": True,
		"outbound_ok": True,
		"bound": True,
		"access_policy_chosen": True,
	}
	base.update(over)
	return wh.compute_setup_stage(**base)


class TestComputeSetupStage(unittest.TestCase):
	def test_off_when_disabled(self):
		self.assertEqual(stage(enabled=False, health="disabled"), "off")

	def test_off_wins_over_missing_credentials(self):
		self.assertEqual(stage(enabled=False, health="disabled", credentials_ok=False), "off")

	def test_not_connected_without_saved_credentials(self):
		self.assertEqual(stage(credentials_ok=False, health="blocked", webhook_verified=False), "not_connected")

	def test_connected_unverified_when_credentials_saved_but_no_webhook(self):
		self.assertEqual(
			stage(health="not_set_up", webhook_verified=False, inbound_seen=False, outbound_ok=False, bound=False),
			"connected_unverified",
		)

	def test_receiving_when_webhook_verified_without_round_trip(self):
		self.assertEqual(stage(inbound_seen=True, outbound_ok=False, bound=False), "receiving")

	def test_receiving_when_only_webhook_verified(self):
		self.assertEqual(
			stage(health="not_set_up", inbound_seen=False, outbound_ok=False, bound=False), "receiving"
		)

	def test_live_unrouted_after_round_trip_without_agent(self):
		self.assertEqual(stage(bound=False), "live_unrouted")

	def test_live_unrouted_when_policy_missing(self):
		self.assertEqual(stage(access_policy_chosen=False), "live_unrouted")

	def test_live_when_agent_bound_and_policy_chosen(self):
		self.assertEqual(stage(), "live")

	def test_degraded_when_health_degraded(self):
		self.assertEqual(stage(health="degraded"), "degraded")

	def test_degraded_on_a_live_gateway_with_warnings(self):
		self.assertEqual(stage(health="degraded", bound=True, access_policy_chosen=True), "degraded")

	def test_blocked_when_health_blocked(self):
		self.assertEqual(stage(health="blocked"), "blocked")

	def test_blocked_on_a_live_gateway_whose_token_was_rejected(self):
		self.assertEqual(stage(health="blocked", webhook_verified=True), "blocked")

	def test_precedence_off_then_not_connected_then_blocked_then_degraded(self):
		self.assertEqual(stage(enabled=False, credentials_ok=False, health="blocked"), "off")
		self.assertEqual(stage(credentials_ok=False, health="blocked"), "not_connected")
		self.assertEqual(stage(health="blocked", inbound_seen=False), "blocked")
		self.assertEqual(stage(health="degraded", inbound_seen=False, outbound_ok=False), "degraded")

	def test_every_stage_is_reachable(self):
		cases = {
			"off": {"enabled": False, "health": "disabled"},
			"not_connected": {"credentials_ok": False, "health": "not_set_up", "webhook_verified": False},
			"blocked": {"health": "blocked"},
			"degraded": {"health": "degraded"},
			"connected_unverified": {"webhook_verified": False, "inbound_seen": False, "outbound_ok": False},
			"receiving": {"inbound_seen": False, "outbound_ok": False},
			"live_unrouted": {"bound": False},
			"live": {},
		}
		seen = {stage(**over) for over in cases.values()}
		self.assertEqual(seen, STAGES)
		for name, over in cases.items():
			self.assertEqual(stage(**over), name)


def _checklist(**states):
	codes = ("meta_app", "credentials", "webhook", "subscribed", "app_secret", "enabled", "approve_sender", "test_message")
	return [{"code": c, "state": states.get(c, "todo"), "action_url": None} for c in codes]


class TestSetupStageInStatus(unittest.TestCase):
	"""get_setup_status exposes ``setup_stage`` on the detail and on every summary row (no Meta calls)."""

	GATEWAYS = {
		"GW-A": {"name": "GW-A", "is_enabled": 1, "integration_settings": "IS-A", "phone_number_id": "111"},
		"GW-B": {"name": "GW-B", "is_enabled": 0, "integration_settings": "IS-B", "phone_number_id": "222"},
	}

	def setUp(self):
		p = patch("huf.ai.whatsapp.management.frappe")
		self.frappe = p.start()
		self.addCleanup(p.stop)
		self.frappe.PermissionError = PermissionError
		self.frappe.get_roles.return_value = ["System Manager"]

		def get_all(doctype, **kw):
			filters = kw.get("filters") or {}
			if doctype == "Gateway":
				return [dict(g) for n, g in self.GATEWAYS.items() if filters.get("name") in (None, n)]
			return []

		self.frappe.get_all.side_effect = get_all
		self.frappe.db.get_value.return_value = ""
		for target, value in (("is_available", True),):
			q = patch.object(mgmt.bridge, target, return_value=value)
			q.start()
			self.addCleanup(q.stop)
		h = patch("huf.ai.whatsapp.health.build_health", side_effect=self._fake_health)
		h.start()
		self.addCleanup(h.stop)

	@staticmethod
	def _fake_health(gateway, presence, **kw):
		if not gateway["is_enabled"]:
			return {"health": "disabled", "checklist": _checklist(), "policy": {"direct_policy": "Allow list", "default_target": None}}
		return {
			"health": "healthy",
			"checklist": _checklist(webhook="done", subscribed="done", test_message="done"),
			"policy": {"direct_policy": "Allow list", "default_target": {"type": "Agent", "name": "AG-1"}},
			"access_token_present": True,
			"phone_number_id_present": True,
			"verify_token_present": True,
		}

	def test_detail_includes_setup_stage(self):
		result = mgmt.get_setup_status("GW-A")
		self.assertEqual(result["gateway"]["setup_stage"], "live")

	def test_summary_rows_include_setup_stage(self):
		result = mgmt.get_setup_status()
		self.assertEqual(
			result["gateways"],
			[
				{"name": "GW-A", "health": "healthy", "enabled": True, "setup_stage": "live"},
				{"name": "GW-B", "health": "disabled", "enabled": False, "setup_stage": "off"},
			],
		)
