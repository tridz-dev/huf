# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""FX-C: trusted flow sends are scoped and capped, outcomes are never double-sent, keys are scoped."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe

from huf.ai.whatsapp import outbound_policy as policy
from huf.ai.whatsapp import send_scope as scope
from huf.ai.tools import whatsapp

GW = "GW-FXC"
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
		self.outreach = patch.object(policy, "record_template_outreach").start()
		patch.object(whatsapp, "_has_entry", return_value=False, create=True).start()

	def _clean(self):
		frappe.db.delete("WhatsApp Send Key", {"gateway": GW})
		frappe.db.commit()

	def call(self, run="RUN-1", **kw):
		kw.setdefault("to", CONTACT)
		kw.setdefault("message", "hello")
		kw.setdefault("call_id", frappe.generate_hash(length=8))
		with patch.dict(frappe.flags, {"huf_current_agent_run_id": run}):
			return json.loads(whatsapp.handle_action("send_message", **kw))

	def trusted(self, **kw):
		kw.setdefault("message", "hello")
		kw.setdefault("call_id", frappe.generate_hash(length=8))
		with patch.dict(frappe.flags, {"huf_current_agent_run_id": None}):
			with whatsapp.trusted_gateway(GW, run_id="FLOWRUN-1"):
				return json.loads(whatsapp.handle_action("send_message", **kw))


class TestTrustedFlowIsScopedAndCapped(_Base):
	def test_trusted_send_outside_scope_is_refused(self):
		res = self.trusted(to=OTHER)
		self.assertEqual(res["error"], "recipient_not_permitted")
		self.assertEqual(self.sent.call_count, 0)

	def test_trusted_send_inside_widened_scope_is_sent(self):
		self.settings = _settings(scope="Any number")
		self.assertTrue(self.trusted(to=OTHER)["success"])

	def test_trusted_sends_are_capped_per_flow_run(self):
		self.settings = _settings(scope="Any number", per_run=1)
		self.assertTrue(self.trusted(to=OTHER)["success"])
		self.assertEqual(self.trusted(to=OTHER)["error"], "send_cap_exceeded")

	def test_flow_sends_count_in_the_day_cap(self):
		self.settings = _settings(scope="Any number", per_day=1)
		self.assertTrue(self.trusted(to=OTHER)["success"])
		self.assertEqual(self.call(to=CONTACT)["error"], "send_cap_exceeded")

	def test_send_without_a_run_still_claims_a_key(self):
		self.settings = _settings(scope="Any number")
		with patch.dict(frappe.flags, {"huf_current_agent_run_id": None}):
			whatsapp.handle_action("send_message", to=OTHER, message="x")
		self.assertEqual(frappe.db.count("WhatsApp Send Key", {"gateway": GW}), 1)


class TestFlowAuthorGatewayBinding(unittest.TestCase):
	def test_author_without_write_access_cannot_bind_config_gateway(self):
		from huf.ai import flow_engine

		flow_run = SimpleNamespace(owner="nobody@example.com", name="FR", get=lambda k, d=None: None)
		with patch.object(frappe, "has_permission", return_value=False), patch.object(frappe.db, "exists", return_value=True):
			with flow_engine._bound_gateway(flow_run, {"gateway": GW}):
				self.assertEqual(whatsapp._trusted_gateway.get(), "")

	def test_author_with_write_access_binds_config_gateway(self):
		from huf.ai import flow_engine

		flow_run = SimpleNamespace(owner="a@example.com", name="FR", get=lambda k, d=None: None)
		with patch.object(frappe, "has_permission", return_value=True), patch.object(frappe.db, "exists", return_value=True):
			with flow_engine._bound_gateway(flow_run, {"gateway": GW}):
				self.assertEqual(whatsapp._trusted_gateway.get(), GW)


class TestOutreachMarker(_Base):
	def test_successful_free_form_send_to_a_non_entry_records_the_marker(self):
		self.call(to=CONTACT)
		self.outreach.assert_called_with(GW, CONTACT)

	def test_failed_send_records_no_marker(self):
		self.sent.side_effect = lambda kw: json.dumps({"success": False, "error": "opted_out"})
		self.call(to=CONTACT)
		self.outreach.assert_not_called()


class TestUnknownOutcomeKeepsClaim(_Base):
	def test_timeout_keeps_the_claim_so_a_retry_does_not_double_send(self):
		self.sent.side_effect = lambda kw: json.dumps(
			{"success": False, "error": "Failed to send WhatsApp message: Read timed out"}
		)
		self.call(call_id="c1")
		again = self.call(call_id="c1")
		self.assertEqual(again["error"], "send_in_progress")
		self.assertEqual(self.sent.call_count, 1)

	def test_bridge_send_failed_without_graph_answer_keeps_the_claim(self):
		self.sent.side_effect = lambda kw: json.dumps({"success": False, "error": "send_failed", "graph_code": None})
		self.call(call_id="c1")
		self.assertEqual(self.call(call_id="c1")["error"], "send_in_progress")

	def test_definite_refusal_releases_the_claim(self):
		self.sent.side_effect = [json.dumps({"success": False, "error": "opted_out"}), _ok()]
		self.assertFalse(self.call(call_id="c1")["success"])
		self.assertTrue(self.call(call_id="c1")["success"])

	def test_graph_4xx_releases_the_claim(self):
		self.sent.side_effect = [
			json.dumps({"success": False, "error": "send_failed", "graph_code": 100, "retryable": False}), _ok()
		]
		self.call(call_id="c1")
		self.assertTrue(self.call(call_id="c1")["success"])


class TestExplicitKeyScope(_Base):
	def test_same_explicit_key_in_another_run_is_not_deduplicated(self):
		a = self.call(run="RUN-A", idempotency_key="k")
		b = self.call(run="RUN-B", idempotency_key="k")
		self.assertNotIn("deduplicated", b)
		self.assertEqual(self.sent.call_count, 2)
		self.assertTrue(a["success"])

	def test_same_explicit_key_for_another_recipient_is_not_deduplicated(self):
		self.settings = _settings(scope="Any number")
		self.call(to=CONTACT, idempotency_key="k")
		b = self.call(to=OTHER, idempotency_key="k")
		self.assertNotIn("deduplicated", b)
		self.assertEqual(self.sent.call_count, 2)

	def test_same_explicit_key_same_run_and_recipient_deduplicates(self):
		self.call(idempotency_key="k")
		self.assertTrue(self.call(idempotency_key="k")["deduplicated"])


class TestCallIdFromSdk(unittest.TestCase):
	def test_model_supplied_call_id_is_overwritten(self):
		from huf.ai import sdk_tools

		ctx = SimpleNamespace(context={}, tool_call_id="call_real")
		out = sdk_tools._merge_run_context({"call_id": "call_forged"}, ctx)
		self.assertEqual(out["call_id"], "call_real")


class TestOptOutOnEveryBranch(unittest.TestCase):
	"""Text and template check opt-out themselves; every typed send (media, location, contact, reaction,
	interactive) funnels through ``_deliver_typed``, whose gate runs before any bridge call."""

	def test_typed_sends_refuse_an_opted_out_contact_before_the_bridge(self):
		bridge_call = MagicMock()
		with patch.object(whatsapp, "_is_opted_out", return_value=True):
			res = json.loads(whatsapp._deliver_typed({"gateway_name": GW}, CONTACT, ({"type": "x"}, []), bridge_call, "a reaction"))
		self.assertEqual(res["error"], "opted_out")
		bridge_call.assert_not_called()

	def test_text_and_template_refuse_an_opted_out_contact(self):
		with patch.object(whatsapp, "_is_opted_out", return_value=True):
			for action, extra in (("send_message", {"message": "x"}), ("send_template", {"template_name": "t"})):
				with self.subTest(action=action):
					res = json.loads(whatsapp._dispatch(action, {"to": CONTACT, "gateway_name": GW, **extra}))
					self.assertEqual(res["error"], "opted_out")

	def test_every_typed_action_is_routed_through_deliver_typed(self):
		for action, extra in (
			("send_reaction", {"message_id": "wamid.x", "emoji": "x"}),
			("send_buttons", {"body": "b", "buttons": [{"id": "1", "title": "t"}]}),
			("send_image", {"link": "https://e.com/a.png"}),
			("send_location", {"latitude": 1, "longitude": 2}),
			("send_contact", {"contacts": [{"name": {"formatted_name": "A"}}]}),
		):
			with self.subTest(action=action), patch.object(whatsapp, "_deliver_typed", return_value="routed") as gate:
				whatsapp._dispatch(action, {"to": CONTACT, "gateway_name": GW, **extra})
				self.assertTrue(gate.called, action)
