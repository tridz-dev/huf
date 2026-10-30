# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""Security round 2 (DECISIONS 13): credentials never reach a sample, in headers, body, nested objects or name/value pairs.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_ux25_redact
"""

import json

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime

from huf.ai.flow import trigger_samples_api
from huf.ai.flow.support.trigger_sample import MASK, redact_sample
from huf.ai.flow.testrun.step_sample import redact_output

HEADER_NAMES = ["Authorization", "authorization", "Cookie", "Set-Cookie", "X-Huf-Secret", "x_huf_secret", "api-key", "X-API-Key", "Proxy-Authorization", "x-auth-token"]
MASKED_NAMES = ["token", "access_token", "refresh_token", "password", "passwd", "secret", "client_secret", "apiKey", "api_key", "auth", "bearer", "jwt", "csrf_token", "session_id", "access_key", "private_key", "signature", "credentials"]
SECRET_TEXT = "sk-abcdefghijklmnopqrstuvwxyz123456"
BEARER = "Bearer abcdefghijklmnopqrstuvwxyz1234"


def _walk(value):
	if isinstance(value, dict):
		for k, v in value.items():
			yield k
			yield from _walk(v)
	elif isinstance(value, list):
		for v in value:
			yield from _walk(v)
	else:
		yield value


class TestRedaction(IntegrationTestCase):
	def test_header_style_names_are_removed_at_any_depth(self):
		body = {"name": "Ada", **{h: "s3cret-value" for h in HEADER_NAMES}, "meta": {"deep": {**{h: "s3cret-value" for h in HEADER_NAMES}, "ok": 1}}, "list": [{"Authorization": "x", "n": 1}]}
		for fn in (redact_sample, lambda v: redact_output(v)[0]):
			out = fn(body)
			leaves = set(_walk(out))
			for h in HEADER_NAMES:
				self.assertNotIn(h, leaves)
			self.assertNotIn("s3cret-value", leaves)
			self.assertEqual((out["name"], out["meta"]["deep"]["ok"], out["list"][0]["n"]), ("Ada", 1, 1))

	def test_credential_looking_keys_are_hidden_not_shown(self):
		body = {n: "value-123" for n in MASKED_NAMES}
		body["nested"] = {"a": {n: "value-123" for n in MASKED_NAMES}}
		for fn in (redact_sample, lambda v: redact_output(v)[0]):
			out = fn(body)
			for n in MASKED_NAMES:
				self.assertEqual(out[n], MASK, n)
				self.assertEqual(out["nested"]["a"][n], MASK, n)

	def test_ordinary_names_are_kept(self):
		body = {"author": "Ada", "authority": "x", "name": "n", "email": "a@b.co", "order_total": 5, "status": "new"}
		for fn in (redact_sample, lambda v: redact_output(v)[0]):
			self.assertEqual(fn(body), body)

	def test_name_value_pairs_hide_the_value(self):
		body = {"headers": [{"name": "Authorization", "value": BEARER}, {"name": "X-Trace", "value": "abc"}], "settings": [{"key": "api_key", "value": "zzz-123"}]}
		for fn in (redact_sample, lambda v: redact_output(v)[0]):
			out = fn(body)
			self.assertEqual(out["headers"][0]["value"], MASK)
			self.assertEqual(out["headers"][1]["value"], "abc")
			self.assertEqual(out["settings"][0]["value"], MASK)

	def test_token_shaped_values_are_hidden_under_harmless_keys(self):
		body = {"note": f"use {SECRET_TEXT} now", "comment": f"hi {BEARER}", "list": [SECRET_TEXT]}
		for fn in (redact_sample, lambda v: redact_output(v)[0]):
			text = json.dumps(fn(body))
			self.assertNotIn(SECRET_TEXT, text)
			self.assertNotIn("abcdefghijklmnopqrstuvwxyz1234", text)


class TestLastWebhookRequest(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.flow_id = f"_test-ux25-hook-{frappe.generate_hash(length=6)}"
		flow = frappe.get_doc({"doctype": "Flow Definition", "flow_id": self.flow_id, "flow_name": "UX25 hook", "status": "Draft", "definition_json": json.dumps({"nodes": []})})
		flow.flags.ignore_validate = True
		flow.insert(ignore_permissions=True)
		self.run_name = frappe.get_doc(
			{
				"doctype": "Flow Run", "flow_definition": flow.name, "flow_id": self.flow_id, "status": "Success", "trigger_type": "Webhook", "started_at": now_datetime(),
				"trigger_payload": json.dumps({"customer": {"name": "Ada", "token": "tok-123", "Authorization": BEARER}, "Cookie": "sid=1", "x-huf-secret": "hush", "headers": [{"name": "Authorization", "value": BEARER}], "note": SECRET_TEXT, "_trigger": {"x": 1}}),
			}
		).insert(ignore_permissions=True).name

	def tearDown(self):
		frappe.set_user("Administrator")
		for doctype, name in (("Flow Run", self.run_name), ("Flow Definition", self.flow_id)):
			if frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
		frappe.db.commit()

	def test_the_last_request_carries_no_credentials(self):
		out = trigger_samples_api.get_last_webhook_request(self.flow_id)
		self.assertTrue(out["found"])
		text = json.dumps(out["sample"])
		for leaked in ("tok-123", "Bearer", "sid=1", "hush", SECRET_TEXT, "Cookie", "x-huf-secret"):
			self.assertNotIn(leaked, text)
		self.assertEqual(out["sample"]["customer"]["name"], "Ada")
		self.assertEqual(out["sample"]["customer"]["token"], MASK)
		self.assertNotIn("_trigger", out["sample"])
