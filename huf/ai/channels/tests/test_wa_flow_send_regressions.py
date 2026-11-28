# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Regressions found by the live WhatsApp pass (B1 template lookup, B3 reference recipient, dynamic URL button).

Real rows on the bench (WhatsApp Templates, Gateway, Channel Outbox); only the Graph send is replaced.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.channels.tests.test_wa_flow_send_regressions
"""

import json
from types import SimpleNamespace
from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.channels.outbound import button_tokens, outbox, recipient_binder
from huf.ai.flow.nodes import send
from huf.ai.flow.runs import preflight
from huf.ai.flow.tests.test_flow_preflight import _codes, _hooks, _send
from huf.ai.graph.executor import GraphContext

ACC = "reg-acc"
GW = "reg-gw"
PHONE = "+15550001234"
REF = {"$from": "input.phone"}


def _need_connector(case):
	if not frappe.db.exists("DocType", "WhatsApp Templates"):
		case.skipTest("frappe_whatsapp not installed")


def _gateway():
	frappe.get_doc(
		{"doctype": "Gateway", "name": GW, "gateway_name": GW, "provider": "WhatsApp", "whatsapp_account": ACC}
	).db_insert()


def _template(template_name: str, buttons=(), language="en") -> str:
	name = f"{template_name}-{language}"
	frappe.get_doc(
		{
			"doctype": "WhatsApp Templates",
			"name": name,
			"template_name": template_name,
			"actual_name": template_name,
			"language_code": language,
			"category": "UTILITY",
			"template": "Hello {{1}}",
			"status": "APPROVED",
			"whatsapp_account": ACC,
		}
	).db_insert()
	for idx, button in enumerate(buttons, 1):
		frappe.get_doc(
			{
				"doctype": "WhatsApp Button",
				"parent": name,
				"parenttype": "WhatsApp Templates",
				"parentfield": "buttons",
				"idx": idx,
				"name": frappe.generate_hash(length=10),
				**button,
			}
		).db_insert()
	return name


class TestTemplateLookup(IntegrationTestCase):
	"""B1: frappe_whatsapp names rows ``<template_name>-<language>``; a send step names the bare template."""

	def setUp(self):
		_need_connector(self)
		frappe.set_user("Administrator")
		_template("regbare")
		self.addCleanup(frappe.db.rollback)

	def test_bare_name_resolves_to_the_language_row(self):
		self.assertTrue(preflight.template_exists("regbare"))
		self.assertTrue(preflight.template_exists("regbare-en"))
		self.assertTrue(preflight.template_exists("regbare", language="en"))

	def test_other_language_or_unknown_name_is_missing(self):
		self.assertFalse(preflight.template_exists("regbare", language="de"))
		self.assertFalse(preflight.template_exists("no-such-reg-template"))

	def test_make_live_check_passes_for_a_bare_template_name(self):
		config = {"gateway": GW, "recipient": "$member", "category": "service", "template": "regbare"}
		with _hooks(), mock.patch.object(preflight, "gateway_channel", return_value="whatsapp"):
			codes = _codes(preflight.run_preflight(_send(config)))
		self.assertNotIn(("TEMPLATE_MISSING", "s"), codes)


class TestReferenceRecipient(IntegrationTestCase):
	"""B3: a reference recipient is stored as text and resolved again at delivery."""

	def setUp(self):
		_gateway()
		self.addCleanup(frappe.db.rollback)

	def _enqueue(self, recipient):
		request = {
			"step_key": "reg-" + frappe.generate_hash(length=10),
			"run_id": "run-reg",
			"node_id": "s",
			"channel": "whatsapp",
			"category": "service",
			"gateway": GW,
			"text_ref": "hi",
			"recipient_ref": recipient,
			"token_names": [],
		}
		return outbox.enqueue(request, deliver_now=False)

	def test_dict_reference_is_stored_as_a_string_ref(self):
		name = self._enqueue(REF)
		stored = frappe.db.get_value("Channel Outbox", name, "recipient_ref")
		self.assertIsInstance(stored, str)
		self.assertEqual(recipient_binder.decode_ref(stored), REF)
		self.assertNotIn(PHONE, stored)

	def test_member_sentinel_stays_plain_text(self):
		name = self._enqueue("$member")
		self.assertEqual(frappe.db.get_value("Channel Outbox", name, "recipient_ref"), "$member")

	def test_literal_number_fails_with_an_explicit_error(self):
		with self.assertRaises(outbox.LiteralRecipient):
			self._enqueue(PHONE)
		with mock.patch.object(outbox, "enqueue", side_effect=outbox.LiteralRecipient("recipient_ref")):
			self.assertEqual(send._enqueue({"channel": "whatsapp", "recipient_ref": PHONE}), "bad_recipient")

	def test_unsupported_reference_shape_is_a_block_not_a_crash(self):
		self.assertEqual(send._enqueue({"channel": "whatsapp", "step_key": "k", "recipient_ref": ["x"]}), "bad_recipient")

	def test_delivery_resolves_the_stored_reference_from_the_run(self):
		name = self._enqueue(REF)
		row = frappe.get_doc("Channel Outbox", name)
		ctx = GraphContext()
		ctx.data["phone"] = PHONE
		with (
			mock.patch.object(frappe, "get_doc", return_value=SimpleNamespace(name="run-reg")) as get_doc,
			mock.patch("huf.ai.flow.engine._context_of", return_value=ctx),
		):
			recipient, text = outbox.resolve_from_run(row)
		get_doc.assert_called_once()
		self.assertEqual((recipient, text), (PHONE, "hi"))


class TestDynamicUrlButton(IntegrationTestCase):
	"""A dynamic URL button takes one token, which goes to the button, never into the body list."""

	URL = {"button_type": "Visit Website", "button_label": "Open", "url_type": "Dynamic", "website_url": "https://x.example/{{1}}"}

	def setUp(self):
		_need_connector(self)
		frappe.set_user("Administrator")
		_template("regurl", [self.URL])
		_gateway()
		self.addCleanup(frappe.db.rollback)

	def test_button_is_a_required_slot(self):
		buttons = button_tokens.required_buttons(GW, "regurl")
		self.assertEqual([(b["sub_type"], b["index"]) for b in buttons], [("url", 0)])

	def test_split_sends_the_last_token_to_the_button(self):
		buttons = button_tokens.required_buttons(GW, "regurl")
		body, params = button_tokens.split(["name", "slug"], buttons, {"name": "Ann", "slug": "abc"})
		self.assertEqual(body, ["name"])
		self.assertEqual(params, [{"index": 0, "sub_type": "url", "text": "abc"}])

	def test_transport_passes_button_params_and_a_clean_body(self):
		row = SimpleNamespace(
			channel="whatsapp", gateway=GW, template="regurl", language="en", run_id="r", step_key="sk",
			token_names=json.dumps(["name", "slug"]), header=None,
		)
		sent = {}

		def fake_send(account, phone, template, body, header, **kw):
			sent.update(body=body, button=kw.get("button_params"))
			return {"message_id": "m"}

		with (
			mock.patch("huf.ai.whatsapp.management._send_authority", return_value=None),
			mock.patch("huf.ai.gateway_adapters.whatsapp_bridge.send_template", side_effect=fake_send),
		):
			outbox.whatsapp_transport(row, PHONE, None, {"name": "Ann", "slug": "abc"})
		self.assertEqual(sent["body"], ["Ann"])
		self.assertEqual(sent["button"], [{"index": 0, "sub_type": "url", "text": "abc"}])
