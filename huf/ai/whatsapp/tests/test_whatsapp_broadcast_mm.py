# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WP-10: Marketing Messages API send path (endpoint switch, refusal for non-marketing, default unchanged)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from huf.ai.gateway_adapters import whatsapp_bridge as wb
from huf.ai.whatsapp import broadcast_send as bs
from huf.ai.whatsapp.tests.test_whatsapp_broadcast_send import ROW, _Base

ACCT = {"url": "https://graph.facebook.com", "version": "v21.0", "phone_id": "123", "token": "t"}


def _recorder():
	calls = []

	def post(url, **kw):
		calls.append(url)
		r = MagicMock()
		r.status_code = 200
		r.json.return_value = {"messages": [{"id": "wamid.1", "message_status": "accepted"}]}
		return r

	return post, calls


class TestEndpointSwitch(unittest.TestCase):
	def test_default_posts_to_messages(self):
		post, calls = _recorder()
		with patch("huf.ai.whatsapp.account_events.send_refusal", return_value=None):
			out = wb._graph_post(ACCT, {}, post)
		self.assertTrue(calls[0].endswith("/123/messages"))
		self.assertEqual(out, {"wamid": "wamid.1", "message_status": "accepted"})

	def test_marketing_api_posts_to_marketing_messages(self):
		post, calls = _recorder()
		with patch("huf.ai.whatsapp.account_events.send_refusal", return_value=None):
			out = wb._graph_post(ACCT, {}, post, marketing_api=True)
		self.assertTrue(calls[0].endswith("/123/marketing_messages"))
		self.assertEqual(out["wamid"], "wamid.1")

	def test_marketing_api_requires_force_graph(self):
		with self.assertRaises(wb.BridgeError):
			wb.send_template("ACC", "15550001111", "promo", marketing_api=True)


class TestBroadcastPassThrough(_Base):
	def test_default_send_via_not_marketing_api(self):
		self.assertEqual(bs.send_one(ROW), "sent")
		self.assertFalse(self.post.call_args.kwargs["marketing_api"])

	def test_marketing_template_uses_mm(self):
		self.store.bc.update(send_via="marketing_messages", category="MARKETING")
		self.assertEqual(bs.send_one(ROW), "sent")
		self.assertTrue(self.post.call_args.kwargs["marketing_api"])

	def test_non_marketing_refused_without_post(self):
		self.store.bc.update(send_via="marketing_messages", category="UTILITY")
		self.assertEqual(bs.send_one(ROW), "failed")
		self.assertEqual(self.store.row["error_code"], "mm_requires_marketing_template")
		self.post.assert_not_called()
