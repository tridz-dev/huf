# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""G2: a registered ``huf_gateway_pre_send`` guard fails closed without a gateway; consent bypass is narrow."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import frappe

from huf.ai.gateway_adapters.whatsapp import WhatsAppGatewayAdapter
from huf.ai.whatsapp import outbound_policy as policy
from huf.ai.whatsapp import pre_send

MOD = "huf.ai.whatsapp.tests.test_pre_send_fail_closed"
SEEN: list[dict] = []
GW = "GW-FC"
TO = "919876543210"
CREDS = {"phone_number_id": "111", "access_token": "tok", "webhook_verify_token": "v", "app_secret": "s"}


def _allow(**payload):
	SEEN.append(payload)


def _hooks(*handlers):
	paths = [f"{MOD}.{h.__name__}" for h in handlers]
	return patch(
		"huf.ai.whatsapp.gateway_hooks.frappe.get_hooks",
		side_effect=lambda n, *a, **k: paths if n == "huf_gateway_pre_send" else [],
	)


class TestFailClosed(unittest.TestCase):
	def setUp(self):
		SEEN.clear()
		p = patch("huf.ai.whatsapp.gateway_hooks.frappe.log_error")
		p.start()
		self.addCleanup(p.stop)

	def test_no_gateway_with_hook_refused_and_not_posted(self):
		post = MagicMock()
		adapter = WhatsAppGatewayAdapter(CREDS, http_post=post)
		with (
			patch("huf.ai.gateway_adapters.whatsapp.account_events_mod.send_refusal", return_value=None),
			_hooks(_allow),
			self.assertRaises(policy.OutboundRefused) as cm,
		):
			adapter._graph_send({"to": TO, "type": "text", "text": {"body": "x"}})
		self.assertEqual(cm.exception.code, "blocked_by_hook")
		post.assert_not_called()
		self.assertEqual(SEEN, [])

	def test_no_gateway_no_hooks_unchanged(self):
		with _hooks():
			policy.check_pre_send(None, TO, "text")

	def test_consent_scope_only_flags_text_kind(self):
		frappe.local.huf_consent_send_scope = (GW, TO)
		self.addCleanup(lambda: setattr(frappe.local, "huf_consent_send_scope", None))
		with _hooks(_allow):
			pre_send.check(GW, TO, "text", "adapter")
			pre_send.check(GW, TO, "template", "adapter")
			pre_send.check(GW, TO, "media", "adapter")
			pre_send.check(GW, TO, "other", "adapter")
		self.assertEqual([s["context"]["consent_confirmation"] for s in SEEN], [True, False, False, False])

	def test_agent_send_inside_scope_not_flagged(self):
		frappe.local.huf_consent_send_scope = (GW, TO)
		self.addCleanup(lambda: setattr(frappe.local, "huf_consent_send_scope", None))
		with _hooks(_allow):
			pre_send.agent_tool_gate(GW, TO, "text", "text")
			pre_send.management_refusal(GW, TO, "text", "text")
		self.assertEqual(len(SEEN), 2)
		self.assertFalse(any(s["context"].get("consent_confirmation") for s in SEEN))
