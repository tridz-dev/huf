# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WP-10: recipient scope and per-run / per-day caps for agent WhatsApp sends (A-002)."""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

import frappe

from huf.ai.whatsapp import send_scope as scope
from huf.ai.tools import whatsapp

GW = "GW-SCOPE"
CONTACT = "15550001111"
OTHER = "15559998888"


def _ok(mid="wamid.1"):
	return json.dumps({"success": True, "data": {"message_id": mid, "recipient": OTHER, "status": "sent"}})


def _settings(**over):
	base = {"scope": "Current contact", "allowlist": [], "per_run": 20, "per_day": 200}
	base.update(over)
	return base


class _Base(unittest.TestCase):
	def setUp(self):
		self._clean()
		self.addCleanup(self._clean)
		self.addCleanup(patch.stopall)
		self.sent = MagicMock(side_effect=lambda kw: _ok())
		self.settings = _settings()
		patch.object(whatsapp, "_run_gateway", return_value=GW).start()
		patch.object(whatsapp, "_authorize", return_value=None).start()
		patch.object(whatsapp, "_send_message", self.sent).start()
		patch.object(scope, "settings", side_effect=lambda gw: self.settings).start()
		patch.object(scope, "current_contact", return_value=CONTACT).start()

	def _clean(self):
		frappe.db.delete("WhatsApp Send Key", {"gateway": GW})
		frappe.db.commit()

	def call(self, run="RUN-1", **kw):
		kw.setdefault("to", CONTACT)
		kw.setdefault("message", "hello")
		kw.setdefault("call_id", frappe.generate_hash(length=8))
		with patch.dict(frappe.flags, {"huf_current_agent_run_id": run}):
			return json.loads(whatsapp.handle_action("send_message", **kw))


class TestDefaultRecipient(_Base):
	def test_send_to_the_current_contact_is_allowed(self):
		self.assertTrue(self.call()["success"])
		self.assertEqual(self.sent.call_count, 1)

	def test_send_to_another_number_is_refused_by_default(self):
		res = self.call(to=OTHER)
		self.assertFalse(res["success"])
		self.assertEqual(res["error"], "recipient_not_permitted")
		self.sent.assert_not_called()

	def test_formatting_of_the_current_contact_still_matches(self):
		self.assertTrue(self.call(to="+1 (555) 000-1111")["success"])

	def test_omitted_recipient_defaults_to_the_current_contact(self):
		res = self.call(to="")
		self.assertTrue(res["success"])
		self.assertEqual(self.sent.call_args[0][0]["to"], CONTACT)

	def test_no_current_contact_refuses_everything_in_default_scope(self):
		with patch.object(scope, "current_contact", return_value=""):
			res = self.call()
		self.assertEqual(res["error"], "recipient_not_permitted")

	def test_a_model_cannot_widen_scope_through_arguments(self):
		res = self.call(to=OTHER, agent_recipient_scope="Any number", scope="Any number")
		self.assertEqual(res["error"], "recipient_not_permitted")

	def test_refusal_names_the_scope_and_is_not_a_bare_error(self):
		res = self.call(to=OTHER)
		self.assertIn("message", res)
		self.assertEqual(res["scope"], "Current contact")


class TestWiderScopes(_Base):
	def test_allow_list_admits_listed_numbers_and_the_contact_only(self):
		self.settings = _settings(scope="Allow-list", allowlist=[OTHER])
		self.assertTrue(self.call(to=OTHER)["success"])
		self.assertTrue(self.call(to=CONTACT)["success"])
		self.assertEqual(self.call(to="15557776666")["error"], "recipient_not_permitted")

	def test_approved_contacts_requires_an_approved_access_entry(self):
		self.settings = _settings(scope="Approved contacts")
		with patch.object(scope, "_is_approved", side_effect=lambda gw, n: n == OTHER):
			self.assertTrue(self.call(to=OTHER)["success"])
			self.assertEqual(self.call(to="15557776666")["error"], "recipient_not_permitted")

	def test_any_number_admits_everyone(self):
		self.settings = _settings(scope="Any number")
		self.assertTrue(self.call(to="15557776666")["success"])

	def test_unknown_scope_value_fails_closed_to_current_contact(self):
		self.settings = _settings(scope="Everyone!")
		self.assertEqual(self.call(to=OTHER)["error"], "recipient_not_permitted")

	def test_wider_scope_does_not_bypass_opt_out(self):
		self.settings = _settings(scope="Any number")
		self.sent.side_effect = lambda kw: json.dumps({"success": False, "error": "opted_out"})
		self.assertEqual(self.call(to=OTHER)["error"], "opted_out")


class TestCaps(_Base):
	def test_per_run_cap_refuses_with_retry_after_key(self):
		self.settings = _settings(per_run=2)
		self.call()
		self.call()
		res = self.call()
		self.assertFalse(res["success"])
		self.assertEqual(res["error"], "send_cap_exceeded")
		self.assertEqual(res["cap"], "run")
		self.assertIn("retry_after", res)
		self.assertEqual(self.sent.call_count, 2)

	def test_per_run_cap_is_per_run(self):
		self.settings = _settings(per_run=1)
		self.call(run="RUN-A")
		self.assertTrue(self.call(run="RUN-B")["success"])

	def test_per_day_cap_spans_runs_and_gives_positive_retry_after(self):
		self.settings = _settings(per_day=2)
		self.call(run="RUN-A")
		self.call(run="RUN-B")
		res = self.call(run="RUN-C")
		self.assertEqual(res["error"], "send_cap_exceeded")
		self.assertEqual(res["cap"], "day")
		self.assertGreater(res["retry_after"], 0)
		self.assertLessEqual(res["retry_after"], 24 * 3600)

	def test_zero_disables_a_cap(self):
		self.settings = _settings(per_run=0, per_day=0)
		for _ in range(3):
			self.assertTrue(self.call()["success"])

	def test_a_deduplicated_retry_does_not_count(self):
		self.settings = _settings(per_run=1)
		self.assertTrue(self.call(call_id="same")["success"])
		again = self.call(call_id="same")
		self.assertTrue(again["success"])
		self.assertTrue(again["deduplicated"])

	def test_a_failed_send_does_not_use_the_cap(self):
		self.settings = _settings(per_run=1)
		self.sent.side_effect = [json.dumps({"success": False, "error": "opted_out"}), _ok()]
		self.assertFalse(self.call()["success"])
		self.assertTrue(self.call()["success"])

	def test_a_refused_recipient_does_not_use_the_cap(self):
		self.settings = _settings(per_run=1)
		self.call(to=OTHER)
		self.assertTrue(self.call()["success"])


class TestTrustedFlowCaller(_Base):
	def test_trusted_flow_send_follows_the_gateway_scope(self):
		self.settings = _settings(scope="Any number")
		with patch.object(scope, "current_contact", return_value=""):
			with whatsapp.trusted_gateway(GW):
				res = json.loads(whatsapp.handle_action("send_message", to=OTHER, message="hi"))
		self.assertTrue(res["success"])


class TestSettingsParsing(unittest.TestCase):
	def test_allowlist_is_normalised_and_deduplicated(self):
		self.assertEqual(
			scope.parse_allowlist("+1 555 000 1111, 15550001111\n00442071234567"), ["15550001111", "442071234567"]
		)

	def test_defaults_are_safe(self):
		row = {}
		with patch.object(frappe.db, "get_value", return_value=frappe._dict(row)):
			s = scope.settings(GW)
		self.assertEqual(s["scope"], "Current contact")
		self.assertGreater(s["per_run"], 0)
		self.assertGreater(s["per_day"], 0)

	def test_unreadable_gateway_fails_closed(self):
		with patch.object(frappe.db, "get_value", side_effect=Exception("db")):
			self.assertEqual(scope.settings(GW)["scope"], "Current contact")


class TestGatewayValidation(unittest.TestCase):
	def _gw(self, **fields):
		from huf.huf.doctype.gateway.gateway import Gateway

		gw = Gateway.__new__(Gateway)
		base = {"provider": "WhatsApp", "name": "GW-V"}
		base.update(fields)
		gw.__dict__.update(base)
		gw.get = lambda key, default=None: base.get(key, default)
		return gw

	def test_valid_settings_pass(self):
		self._gw(agent_recipient_scope="Allow-list", agent_recipient_allowlist="15550001111",
			agent_send_cap_per_run=5, agent_send_cap_per_day=50)._validate_send_scope()

	def test_allow_list_scope_needs_numbers(self):
		with self.assertRaises(frappe.ValidationError):
			self._gw(agent_recipient_scope="Allow-list", agent_recipient_allowlist=" ")._validate_send_scope()

	def test_allow_list_rejects_non_numbers(self):
		with self.assertRaises(frappe.ValidationError):
			self._gw(agent_recipient_scope="Allow-list", agent_recipient_allowlist="not-a-number")._validate_send_scope()

	def test_unknown_scope_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self._gw(agent_recipient_scope="Everyone")._validate_send_scope()

	def test_negative_caps_rejected(self):
		for field in ("agent_send_cap_per_run", "agent_send_cap_per_day"):
			with self.assertRaises(frappe.ValidationError):
				self._gw(**{field: -1})._validate_send_scope()

	def test_fields_exist_in_schema_and_field_order(self):
		meta = frappe.get_meta("Gateway")
		for name in ("agent_recipient_scope", "agent_recipient_allowlist", "agent_send_cap_per_run", "agent_send_cap_per_day"):
			self.assertTrue(meta.has_field(name), name)
		self.assertEqual(meta.get_field("agent_recipient_scope").default, "Current contact")
