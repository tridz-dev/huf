# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""T8 part 2: ``huf_gateway_pre_send`` inside every bridge send path, plus gateway_name plumbing from callers.

Blocking hook => refused (BridgeError ``blocked_by_hook``) and NO http post / ``WhatsApp Message`` insert.
No hook => unchanged. Raising hook => blocked. ``gateway_name`` None => hook skipped.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

import frappe

from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.gateway_adapters.types import GatewayReply
from huf.ai.gateway_adapters.whatsapp import WhatsAppGatewayAdapter
from huf.ai.whatsapp import management as mgmt
from huf.ai.whatsapp import outbound_policy as policy

MOD = "huf.ai.whatsapp.tests.test_pre_send_bridge"
SEEN: list[dict] = []
GW = "GW-BRIDGE"
ACC = "ACC-1"
TO = "919876543210"
ACCT = {"name": ACC, "phone_id": "111", "access_token": "tok", "token": "tok", "business_id": "b", "url": "https://graph.invalid", "version": "v1"}


def _block(**payload):
	SEEN.append(payload)
	return {"reason": "no"}


def _allow(**payload):
	SEEN.append(payload)
	return None


def _boom(**payload):
	SEEN.append(payload)
	raise RuntimeError("boom")


def _hooks(*handlers):
	paths = [f"{MOD}.{h.__name__}" for h in handlers]
	return patch("huf.ai.gateway_hooks.frappe.get_hooks", side_effect=lambda n, *a, **k: paths if n == "huf_gateway_pre_send" else [])


def _ok():
	r = MagicMock()
	r.status_code = 200
	r.json.return_value = {"messages": [{"id": "wamid.9"}]}
	return r


class _Base(unittest.TestCase):
	def setUp(self):
		SEEN.clear()
		for target, kw in (
			("huf.ai.gateway_hooks.frappe.log_error", {}),
			(f"{bridge.__name__}.is_available", {"return_value": True}),
			(f"{bridge.__name__}._account_or_error", {"return_value": ACCT}),
			(f"{bridge.__name__}._refuse_if_disconnected", {"return_value": None}),
			(f"{bridge.__name__}._preflight_link", {"return_value": None}),
			(f"{bridge.__name__}._may_bypass", {"return_value": True}),
		):
			p = patch(target, **kw)
			p.start()
			self.addCleanup(p.stop)
		self.get_doc = patch("frappe.get_doc", return_value=MagicMock(name="doc", **{"get.return_value": None}))
		self.get_doc_mock = self.get_doc.start()
		self.addCleanup(self.get_doc.stop)
		self.post = MagicMock(return_value=_ok())

	def assertBlocked(self, fn, *args, **kwargs):
		with self.assertRaises(bridge.BridgeError) as cm:
			fn(*args, **kwargs)
		self.assertEqual(cm.exception.payload["error"], "blocked_by_hook")
		self.assertFalse(cm.exception.payload["success"])
		self.post.assert_not_called()
		self.get_doc_mock.assert_not_called()


class TestSendText(_Base):
	def test_blocked_doc_path(self):
		with _hooks(_block):
			self.assertBlocked(bridge.send_text, ACC, TO, "hi", gateway_name=GW, http_post=self.post)
		self.assertEqual((SEEN[0]["gateway"], SEEN[0]["to"], SEEN[0]["kind"]), (GW, TO, "text"))

	def test_blocked_direct_path_no_post(self):
		with _hooks(_block):
			self.assertBlocked(
				bridge.send_text, ACC, TO, "hi", trusted=True, preview_url=True, gateway_name=GW, http_post=self.post
			)

	def test_hook_raising_blocks(self):
		with _hooks(_boom):
			self.assertBlocked(bridge.send_text, ACC, TO, "hi", gateway_name=GW, http_post=self.post)

	def test_no_hook_unchanged_doc_path(self):
		with _hooks():
			bridge.send_text(ACC, TO, "hi", gateway_name=GW)
		self.get_doc_mock.assert_called_once()

	def test_no_hook_unchanged_direct_path(self):
		with _hooks(), patch.object(bridge, "_mirror_direct_send", return_value={"success": True}):
			bridge.send_text(ACC, TO, "hi", trusted=True, preview_url=True, gateway_name=GW, http_post=self.post)
		self.post.assert_called_once()

	def test_gateway_none_skips_hook(self):
		with _hooks(_block):
			bridge.send_text(ACC, TO, "hi")
		self.assertEqual(SEEN, [])
		self.get_doc_mock.assert_called_once()

	def test_consent_confirmation_flagged(self):
		frappe.local.huf_consent_send_scope = (GW, "+91 98765-43210")
		self.addCleanup(lambda: setattr(frappe.local, "huf_consent_send_scope", None))
		with _hooks(_allow):
			bridge.send_text(ACC, TO, "stopped", gateway_name=GW)
			bridge.send_text(ACC, "15550001111", "other", gateway_name=GW)
		self.assertTrue(SEEN[0]["context"]["consent_confirmation"])
		self.assertFalse(SEEN[1]["context"]["consent_confirmation"])


class TestSendTemplate(_Base):
	def _call(self, **kw):
		with patch.object(bridge, "_template_row", return_value=None), patch.object(
			policy, "enforce_template", return_value=None
		), patch.object(bridge, "_template_docname", return_value="tpl-en"), patch.object(
			bridge.policy, "note_template_sent"
		), patch.object(bridge, "_mirror_template_send", return_value={"success": True, "message_id": "wamid.9"}):
			return bridge.send_template(
				ACC, TO, "hello", ["x"], force_graph=True, http_post=self.post, gateway_name=kw.pop("gateway_name", GW), **kw
			)

	def test_blocked_after_enforce_template(self):
		with _hooks(_block):
			self.assertBlocked(lambda: self._call())
		self.assertEqual(SEEN[0]["kind"], "template")

	def test_hook_raising_blocks(self):
		with _hooks(_boom):
			self.assertBlocked(lambda: self._call())

	def test_enforce_template_refusal_still_first(self):
		with _hooks(_block), patch.object(policy, "enforce_template", side_effect=policy.OutboundRefused("x", "opted_out")):
			with self.assertRaises(bridge.BridgeError) as cm:
				bridge.send_template(ACC, TO, "hello", ["x"], gateway_name=GW, http_post=self.post)
		self.assertEqual(cm.exception.payload["error"], "opted_out")
		self.assertEqual(SEEN, [])

	def test_no_hook_unchanged(self):
		with _hooks():
			self._call()
		self.post.assert_called_once()

	def test_gateway_none_skips(self):
		with _hooks(_block):
			self._call(gateway_name=None)
		self.assertEqual(SEEN, [])
		self.post.assert_called_once()


class TestSendMedia(_Base):
	def test_blocked_plain_link_branch(self):
		with _hooks(_block):
			self.assertBlocked(bridge.send_media, ACC, TO, "image", link="https://x.invalid/a.jpg", gateway_name=GW, http_post=self.post)
		self.assertEqual(SEEN[0]["kind"], "media")

	def test_blocked_media_id_branch_fires_once(self):
		with _hooks(_block):
			self.assertBlocked(bridge.send_media, ACC, TO, "image", media_id="m1", gateway_name=GW, http_post=self.post)
		self.assertEqual(len(SEEN), 1)

	def test_hook_raising_blocks(self):
		with _hooks(_boom):
			self.assertBlocked(bridge.send_media, ACC, TO, "image", link="https://x.invalid/a.jpg", gateway_name=GW, http_post=self.post)

	def test_no_hook_unchanged_and_single_fire(self):
		with _hooks(_allow), patch.object(bridge, "_mirror_direct_send", return_value={"success": True}):
			bridge.send_media(ACC, TO, "image", media_id="m1", gateway_name=GW, http_post=self.post)
		self.post.assert_called_once()
		self.assertEqual(len(SEEN), 1)  # send_media -> _send_payload must not double-fire

	def test_plain_link_no_hook_inserts(self):
		with _hooks():
			bridge.send_media(ACC, TO, "image", link="https://x.invalid/a.jpg", gateway_name=GW)
		self.get_doc_mock.assert_called_once()

	def test_voice_note_carries_gateway(self):
		with _hooks(_block):
			self.assertBlocked(bridge.send_voice_note, ACC, TO, media_id="m1", gateway_name=GW, http_post=self.post)
		self.assertEqual(SEEN[0]["gateway"], GW)

	def test_gateway_none_skips(self):
		with _hooks(_block), patch.object(bridge, "_mirror_direct_send", return_value={"success": True}):
			bridge.send_media(ACC, TO, "image", media_id="m1", http_post=self.post)
		self.assertEqual(SEEN, [])


class TestSendPayloadAndWrappers(_Base):
	def test_send_payload_blocked(self):
		payload = {"messaging_product": "whatsapp", "to": TO, "type": "location", "location": {}}
		with _hooks(_block):
			self.assertBlocked(bridge._send_payload, ACC, payload, True, self.post, GW)
		self.assertEqual((SEEN[0]["kind"], SEEN[0]["context"]["subtype"]), ("other", "location"))

	def test_send_payload_hook_raising_blocks(self):
		payload = {"messaging_product": "whatsapp", "to": TO, "type": "text", "text": {"body": "x"}}
		with _hooks(_boom):
			self.assertBlocked(bridge._send_payload, ACC, payload, True, self.post, GW)

	def test_send_payload_no_hook_unchanged(self):
		payload = {"messaging_product": "whatsapp", "to": TO, "type": "location", "location": {}}
		with _hooks(), patch.object(bridge, "_mirror_direct_send", return_value={"success": True}):
			bridge._send_payload(ACC, payload, True, self.post, GW)
		self.post.assert_called_once()

	def test_send_payload_gateway_none_skips(self):
		payload = {"messaging_product": "whatsapp", "to": TO, "type": "location", "location": {}}
		with _hooks(_block), patch.object(bridge, "_mirror_direct_send", return_value={"success": True}):
			bridge._send_payload(ACC, payload, True, self.post)
		self.assertEqual(SEEN, [])

	def test_wrappers_block_end_to_end(self):
		calls = (
			lambda: bridge.send_location(ACC, TO, 1, 2, trusted=True, http_post=self.post, gateway_name=GW),
			lambda: bridge.send_contacts(
				ACC, TO, [{"name": {"formatted_name": "A", "first_name": "A"}, "phones": [{"phone": "+15550001111"}]}],
				trusted=True, http_post=self.post, gateway_name=GW,
			),
			lambda: bridge.send_reaction(ACC, TO, "wamid.1", "👍", trusted=True, http_post=self.post, gateway_name=GW),
			lambda: bridge.send_interactive(
				ACC, TO, "buttons", {"body": "b", "buttons": [{"id": "1", "title": "t"}]},
				trusted=True, http_post=self.post, gateway_name=GW,
			),
			lambda: bridge.send_sticker(ACC, TO, media_id="m1", trusted=True, http_post=self.post, gateway_name=GW),
		)
		for call in calls:
			SEEN.clear()
			with _hooks(_block):
				self.assertBlocked(call)
			self.assertEqual(len(SEEN), 1)  # send_sticker -> _send_payload must not double-fire
			self.assertEqual(SEEN[0]["gateway"], GW)

	def test_sticker_kind_is_media(self):
		with _hooks(_block):
			self.assertBlocked(bridge.send_sticker, ACC, TO, media_id="m1", gateway_name=GW, http_post=self.post)
		self.assertEqual(SEEN[0]["kind"], "media")


class TestCallerPlumbing(_Base):
	"""Gateway name reaches the bridge hook from each production caller; a refusal is a clean policy result."""

	def test_adapter_bridge_mode_text_reply_blocked(self):
		adapter = WhatsAppGatewayAdapter(
			{"phone_number_id": "111", "access_token": "t", "webhook_verify_token": "v", "app_secret": "s"},
			http_post=self.post, gateway_context={"gateway_name": GW, "whatsapp_account": ACC},
		)
		self.assertTrue(adapter._bridge_mode())
		with patch.object(bridge, "window_state", return_value={"open": True}), patch.object(policy, "check_recipient"), _hooks(
			_block
		), self.assertRaises(policy.OutboundRefused) as cm:
			adapter.send_reply(GatewayReply(conversation_id=TO, text="hello"))
		self.assertEqual(cm.exception.code, "blocked_by_hook")
		self.assertEqual(SEEN[0]["gateway"], GW)
		self.assertEqual(len(SEEN), 1)  # fired once in the bridge, not again by the adapter
		self.post.assert_not_called()
		self.get_doc_mock.assert_not_called()

	def test_adapter_bridge_mode_no_hook_sends(self):
		adapter = WhatsAppGatewayAdapter(
			{"phone_number_id": "111", "access_token": "t", "webhook_verify_token": "v", "app_secret": "s"},
			http_post=self.post, gateway_context={"gateway_name": GW, "whatsapp_account": ACC},
		)
		with patch.object(bridge, "window_state", return_value={"open": True}), patch.object(policy, "check_recipient"), patch.object(
			bridge, "_graph_post_message", return_value="wamid.9"
		) as gpm, patch.object(bridge, "_mirror_direct_send", return_value={"success": True, "message_id": "wamid.9"}), _hooks():
			adapter.send_reply(GatewayReply(conversation_id=TO, text="hello"))
		gpm.assert_called_once()

	def _mgmt(self, hooks, fn, **kwargs):
		with patch.object(mgmt, "_send_authority", return_value=None), patch.object(
			mgmt, "_gateway_whatsapp_account", return_value=ACC
		), patch.object(mgmt, "_resolve_account_name", return_value=ACC), patch.object(
			bridge, "window_state", return_value={"open": True}
		), patch.object(mgmt, "_opted_out", return_value=False), patch.object(
			bridge, "_template_row", return_value=None
		), patch.object(policy, "enforce_template", return_value=None), patch.object(
			bridge, "_template_docname", return_value="t-en"
		), hooks:
			return fn(gateway_name=GW, to=TO, **kwargs)

	def test_management_send_text_message_blocked(self):
		out = self._mgmt(_hooks(_block), mgmt.send_text_message, text="hi")
		self.assertEqual((out["success"], out["error"]), (False, "blocked_by_hook"))
		self.assertEqual(SEEN[0]["gateway"], GW)
		self.get_doc_mock.assert_not_called()

	def test_management_send_text_message_no_hook(self):
		self._mgmt(_hooks(), mgmt.send_text_message, text="hi")
		self.get_doc_mock.assert_called_once()

	def test_management_send_template_message_blocked(self):
		out = self._mgmt(_hooks(_block), mgmt.send_template_message, template_name="hello", body_params=["x"])
		self.assertEqual((out["success"], out["error"]), (False, "blocked_by_hook"))
		self.assertEqual((SEEN[0]["gateway"], SEEN[0]["kind"]), (GW, "template"))
		self.get_doc_mock.assert_not_called()

	def test_management_send_media_message_blocked(self):
		out = self._mgmt(_hooks(_block), mgmt.send_media_message, kind="image", media_id="m1")
		self.assertEqual((out["success"], out["error"]), (False, "blocked_by_hook"))
		self.assertEqual((SEEN[0]["gateway"], SEEN[0]["kind"]), (GW, "media"))

	def test_management_send_location_message_blocked(self):
		out = self._mgmt(_hooks(_block), mgmt.send_location_message, latitude=1, longitude=2)
		self.assertEqual(out["error"], "blocked_by_hook")
		self.assertEqual(SEEN[0]["gateway"], GW)

	def test_tool_send_message_blocked(self):
		from huf.ai.tools import whatsapp as wtools

		kwargs = {"gateway_name": GW, "to": TO, "message": "hi"}
		with patch.object(wtools, "_free_form_refusal", return_value=None), patch.object(
			wtools, "_resolve_bridge_account", return_value={"name": ACC}
		), _hooks(_block):
			out = json.loads(wtools._send_message(kwargs))
		self.assertEqual((out["success"], out["error"]), (False, "blocked_by_hook"))
		self.assertNotIn("definite", out)  # a policy refusal, not retryable
		self.assertEqual(SEEN[0]["gateway"], GW)
		self.get_doc_mock.assert_not_called()

	def test_tool_send_location_carries_gateway(self):
		from huf.ai.tools import whatsapp as wtools

		kwargs = {"gateway_name": GW, "to": TO, "latitude": 1, "longitude": 2}
		with patch.object(wtools, "_free_form_refusal", return_value=None), patch.object(
			wtools, "_resolve_bridge_account", return_value={"name": ACC}
		), _hooks(_block):
			out = json.loads(wtools._send_location(kwargs))
		self.assertEqual(out["error"], "blocked_by_hook")
		self.assertEqual(SEEN[0]["gateway"], GW)

	def test_reply_api_template_refusal_is_refused_not_failed(self):
		from huf.ai.channels import reply_api

		doc = MagicMock(status="open", gateway=GW, contact_handle=TO)
		doc.get.return_value = "whatsapp"
		with patch.object(reply_api, "_load", return_value=doc), patch.object(
			reply_api.conv, "window_applies", return_value=True
		), patch.object(reply_api.frappe.db, "get_value", return_value=ACC), patch.object(
			bridge, "_template_row", return_value=None
		), patch.object(bridge, "_template_docname", return_value="t-en"), patch.object(
			policy, "enforce_template", return_value=None
		), _hooks(_block):
			out = reply_api.deliver_reply(doc, template="hello", params=["x"])
		self.assertEqual((out["status"], out["error"]), ("refused", "blocked_by_hook"))
		self.assertEqual((SEEN[0]["gateway"], SEEN[0]["kind"]), (GW, "template"))
		self.get_doc_mock.assert_not_called()

	def test_reply_api_text_refusal_is_refused(self):
		from huf.ai.channels import reply_api

		doc = MagicMock(status="open", gateway=GW, contact_handle=TO)
		doc.get.return_value = "whatsapp"
		with patch.object(reply_api, "_load", return_value=doc), patch.object(
			reply_api.conv, "window_applies", return_value=True
		), patch.object(reply_api.conv, "is_within_24h", return_value=True), patch.object(
			reply_api, "send_free_text", side_effect=policy.OutboundRefused("no", "blocked_by_hook")
		):
			out = reply_api.deliver_reply(doc, text="hello")
		self.assertEqual((out["status"], out["error"]), ("refused", "blocked_by_hook"))

	def test_broadcast_blocked_by_hook_is_skipped_not_retried(self):
		from huf.ai.whatsapp.broadcast import send as bsend

		with patch.object(bsend, "_write") as write:
			outcome = bsend._after_bridge_error("RCPT-1", 1, {"success": False, "error": "blocked_by_hook", "message": "no"}, GW, TO)
		self.assertEqual(outcome, "skipped")
		self.assertEqual(write.call_args.kwargs["skip_reason"], "blocked_by_hook")
		self.assertEqual(write.call_args.kwargs["status"], "skipped")

	def test_wa_flows_passes_gateway_to_bridge(self):
		from huf.ai.channels import wa_flows

		flow = frappe._dict(name="F", flow_id="1", status="PUBLISHED")
		with patch.object(wa_flows.frappe.db, "get_value", return_value=flow), patch.object(
			policy, "check_recipient"
		), patch.object(mgmt, "_free_form_gate", return_value=None), patch.object(
			mgmt, "_resolve_account_name", return_value=ACC
		), patch.object(mgmt, "_gateway_whatsapp_account", return_value=ACC), _hooks(_block):
			out = wa_flows.send_flow(GW, TO, "flow", "go")
		self.assertEqual((out["success"], out["error"]), (False, "blocked_by_hook"))
		self.assertEqual(SEEN[0]["gateway"], GW)
		self.get_doc_mock.assert_not_called()

	def test_lms_certificate_and_commerce_pass_gateway(self):
		src = []
		for rel in ("channels/tools/lms.py", "channels/commerce/messages.py"):
			import os

			path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), rel)
			with open(path) as fh:
				src.append(fh.read())
		self.assertIn("gateway_name=gateway or None", src[0])
		self.assertIn('kwargs.get("gateway_name") or None', src[1])


if __name__ == "__main__":
	unittest.main()
