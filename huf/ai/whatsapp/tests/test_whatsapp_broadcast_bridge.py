"""Broadcast additions to the bridge: force_graph, opaque_ref, wamid + message_status."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from huf.ai.gateway_adapters import whatsapp_bridge as wb

ACCT = {
	"name": "ACC", "phone_id": "111", "business_id": "BIZ", "app_id": "APP", "token": "tok",
	"url": "https://graph.facebook.com", "version": "v25.0", "webhook_verify_token": "v", "status": "Active",
}


class Resp:
	def __init__(self, payload, status=200):
		self.status_code = status
		self._p = payload

	def json(self):
		return self._p


class FakeDoc(SimpleNamespace):
	def get(self, key, default=None):
		return getattr(self, key, default)

	def insert(self, **kwargs):
		self.name = "WAM-1"
		self.status = "Success"
		return self


def recorder(payload):
	calls = []

	def post(url, **kw):
		calls.append((url, kw))
		return Resp(payload)

	return post, calls


class TestBroadcastBridge(unittest.TestCase):
	def _send(self, post, **kw):
		with patch.object(wb, "is_available", return_value=True), patch.object(wb, "resolve_account", return_value=ACCT), \
			patch.object(frappe, "get_doc", return_value=FakeDoc()) as gd, \
			patch.object(wb, "_template_docname", return_value="hello-en_US"), \
			patch("huf.ai.whatsapp.account_events.send_refusal", return_value=None), \
			patch.object(frappe, "has_permission", return_value=True):
			res = wb.send_template("ACC", "+1 415 555 2671", "hello", ["a"], http_post=post, **kw)
		return res, gd

	def test_force_graph_returns_wamid_and_message_status(self):
		post, calls = recorder({"messages": [{"id": "wamid.1", "message_status": "held_for_quality_assessment"}]})
		res, gd = self._send(post, force_graph=True, opaque_ref="BCAST-1-x")
		self.assertEqual(res["wamid"], "wamid.1")
		self.assertEqual(res["message_status"], "held_for_quality_assessment")
		self.assertEqual(len(calls), 1)
		self.assertEqual(gd.call_args.args[0]["message_id"], "wamid.1")  # mirrored, no second send

	def test_message_status_accepted_and_none(self):
		post, _ = recorder({"messages": [{"id": "wamid.2", "message_status": "accepted"}]})
		self.assertEqual(self._send(post, force_graph=True)[0]["message_status"], "accepted")
		post, _ = recorder({"messages": [{"id": "wamid.3"}]})
		self.assertIsNone(self._send(post, force_graph=True)[0]["message_status"])

	def test_force_graph_never_takes_positional_path(self):
		# plain body-only template would otherwise be inserted as use_template WhatsApp Message without a Graph POST
		post, calls = recorder({"messages": [{"id": "wamid.4"}]})
		res, gd = self._send(post, force_graph=True)
		self.assertEqual(len(calls), 1)
		self.assertTrue(calls[0][0].endswith("/111/messages"))
		self.assertEqual(gd.call_args.args[0]["message_id"], "wamid.4")
		# without force_graph the same call does not hit Graph
		post2, calls2 = recorder({"messages": [{"id": "x"}]})
		self._send(post2)
		self.assertEqual(calls2, [])

	def test_opaque_ref_top_level_in_payload(self):
		post, calls = recorder({"messages": [{"id": "w"}]})
		self._send(post, force_graph=True, opaque_ref="BCAST-00001-15551234567")
		body = calls[0][1]["json"]
		self.assertEqual(body["biz_opaque_callback_data"], "BCAST-00001-15551234567")
		self.assertNotIn("biz_opaque_callback_data", body["template"])

	def test_opaque_ref_truncated_to_256_and_empty_omitted(self):
		post, calls = recorder({"messages": [{"id": "w"}]})
		self._send(post, force_graph=True, opaque_ref="x" * 400)
		self.assertEqual(len(calls[0][1]["json"]["biz_opaque_callback_data"]), 256)
		post, calls = recorder({"messages": [{"id": "w"}]})
		self._send(post, force_graph=True, opaque_ref="   ")
		self.assertNotIn("biz_opaque_callback_data", calls[0][1]["json"])
		self.assertEqual(wb._clean_opaque_ref(12345), "12345")
		self.assertIsNone(wb._clean_opaque_ref(None))

	def test_graph_post_message_still_returns_string(self):
		post, _ = recorder({"messages": [{"id": "wamid.9", "message_status": "accepted"}]})
		with patch("huf.ai.whatsapp.account_events.send_refusal", return_value=None):
			self.assertEqual(wb._graph_post_message(ACCT, {}, post), "wamid.9")
			self.assertEqual(wb._graph_post(ACCT, {}, post), {"wamid": "wamid.9", "message_status": "accepted"})

	def test_graph_error_raises_bridge_error(self):
		def post(url, **kw):
			return Resp({"error": {"code": 131050, "message": "stopped"}}, 400)

		with patch("huf.ai.whatsapp.account_events.send_refusal", return_value=None):
			with self.assertRaises(wb.BridgeError):
				wb._graph_post(ACCT, {}, post)
