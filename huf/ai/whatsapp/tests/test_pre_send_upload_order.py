# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""T8 follow-up: ``huf_gateway_pre_send`` runs BEFORE any media upload to Meta.

A refused media send must not leave an upload on Meta. Every upload-first flow is covered: management
``send_media_message`` / ``send_voice_note`` (private file), agent tool file send, LMS certificate send and the
adapter ``upload_media`` used by voice replies. ``upload_media_file`` has no recipient so no pre-send applies.
With no hook behaviour is unchanged. File flows fire the hook twice for one send (pre-upload + in-bridge send).
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.gateway_adapters.whatsapp import WhatsAppGatewayAdapter
from huf.ai.tools import whatsapp as wtools
from huf.ai.whatsapp import management as mgmt
from huf.ai.whatsapp import outbound_policy as policy

MOD = "huf.ai.whatsapp.tests.test_pre_send_upload_order"
SEEN: list[dict] = []
GW = "GW-UP"
ACC = "ACC-UP"
TO = "919876543210"


def _block(**payload):
	SEEN.append(payload)
	return {"reason": "no"}


def _allow(**payload):
	SEEN.append(payload)
	return None


def _hooks(*handlers):
	paths = [f"{MOD}.{h.__name__}" for h in handlers]
	return patch("huf.ai.gateway_hooks.frappe.get_hooks", side_effect=lambda n, *a, **k: paths if n == "huf_gateway_pre_send" else [])


class _Base(unittest.TestCase):
	def setUp(self):
		SEEN.clear()
		p = patch("huf.ai.gateway_hooks.frappe.log_error")
		p.start()
		self.addCleanup(p.stop)


class TestManagement(_Base):
	def _call(self, hooks, fn=None, **kw):
		fn = fn or mgmt.send_media_message
		file_url = "/private/files/v.ogg" if fn is mgmt.send_voice_note else "/private/files/d.pdf"
		with patch.object(mgmt, "_send_authority", return_value=None), patch.object(
			mgmt, "_gateway_whatsapp_account", return_value=ACC
		), patch.object(mgmt, "_resolve_account_name", return_value=ACC), patch.object(
			bridge, "is_available", return_value=True
		), patch.object(bridge, "window_state", return_value={"open": True}), patch.object(
			mgmt, "_opted_out", return_value=False
		), patch.object(mgmt, "_read_uploaded_file", return_value=(b"%PDF", "d.pdf", "application/pdf")), patch.object(
			bridge, "upload_media", return_value={"success": True, "media_id": "M1"}
		) as up, patch.object(bridge, "send_media", return_value={"success": True}) as sent, hooks:
			out = fn(gateway_name=GW, to=TO, file_url=file_url, **kw)
		return out, up, sent

	def test_blocked_file_send_does_not_upload(self):
		out, up, sent = self._call(_hooks(_block), kind="document")
		self.assertEqual((out["success"], out["error"]), (False, "blocked_by_hook"))
		up.assert_not_called()
		sent.assert_not_called()
		self.assertEqual((SEEN[0]["gateway"], SEEN[0]["kind"], SEEN[0]["context"]["source"]), (GW, "media", "management"))

	def test_blocked_voice_note_does_not_upload(self):
		out, up, sent = self._call(_hooks(_block), fn=mgmt.send_voice_note)
		self.assertEqual(out["error"], "blocked_by_hook")
		up.assert_not_called()
		sent.assert_not_called()

	def test_no_hook_uploads_and_sends(self):
		out, up, sent = self._call(_hooks(), kind="document")
		self.assertTrue(out["success"])
		up.assert_called_once()
		sent.assert_called_once()

	def test_allowing_hook_fires_before_upload_once_here(self):
		out, up, sent = self._call(_hooks(_allow), kind="document")
		self.assertTrue(out["success"])
		self.assertEqual(len(SEEN), 1)  # bridge.send_media is mocked; in the real bridge it fires once more
		up.assert_called_once()


class TestAgentTool(_Base):
	PREP = {"kind": "document", "mime": "application/pdf", "content": b"%PDF", "filename": "d.pdf", "voice": False}

	def _call(self, hooks):
		kwargs = {"gateway_name": GW, "to": TO, "file_id": "F1"}
		with patch.object(wtools, "_free_form_refusal", return_value=None), patch.object(
			wtools.send_file, "resolve_file", return_value=MagicMock()
		), patch.object(wtools.send_file, "prepare_upload", return_value=dict(self.PREP)), patch.object(
			wtools.send_file, "split_caption", return_value=("", "")
		), patch.object(wtools, "_resolve_bridge_account", return_value={"name": ACC}), patch.object(
			bridge, "upload_media", return_value={"success": True, "media_id": "M1"}
		) as up, patch.object(wtools, "_send_media", return_value=json.dumps({"success": True})) as sent, patch.object(
			wtools.requests, "post"
		) as rpost, hooks:
			out = json.loads(wtools._send_media_file(kwargs, TO))
		return out, up, sent, rpost

	def test_blocked_does_not_upload(self):
		out, up, sent, rpost = self._call(_hooks(_block))
		self.assertEqual((out["success"], out["error"]), (False, "blocked_by_hook"))
		up.assert_not_called()
		sent.assert_not_called()
		rpost.assert_not_called()
		self.assertEqual((SEEN[0]["gateway"], SEEN[0]["kind"], SEEN[0]["context"]["source"]), (GW, "media", "agent_tool"))

	def test_no_hook_unchanged(self):
		out, up, sent, _ = self._call(_hooks())
		self.assertTrue(out["success"])
		up.assert_called_once()
		sent.assert_called_once()


class TestLms(_Base):
	def test_blocked_certificate_does_not_upload(self):
		from huf.ai.channels.tools import lms as lms_tool

		src = open(lms_tool.__file__).read()
		self.assertLess(src.index("_pre_send_refusal({"), src.index("bridge.upload_media(account"))
		with patch.object(wtools, "_resolve_bridge_account", return_value={"name": ACC}), _hooks(_block):
			out = json.loads(lms_tool._pre_send_refusal({"gateway_name": GW}, TO, "media", "document"))
		self.assertEqual(out["error"], "blocked_by_hook")


class TestAdapterUpload(_Base):
	def _adapter(self):
		creds = {"phone_number_id": "111", "access_token": "tok", "webhook_verify_token": "v", "app_secret": "s"}
		return WhatsAppGatewayAdapter(creds, gateway_context={"gateway_name": GW})

	def test_blocked_upload_for_recipient_posts_nothing(self):
		adapter = self._adapter()
		with patch.object(adapter, "_bridge_mode", return_value=False), patch.object(
			bridge, "post_media_upload"
		) as post, _hooks(_block), self.assertRaises(policy.OutboundRefused) as cm:
			adapter.upload_media(b"OggS", "audio/ogg; codecs=opus", "v.ogg", "audio", True, to=TO)
		self.assertEqual(cm.exception.code, "blocked_by_hook")
		post.assert_not_called()
		self.assertEqual(SEEN[0]["kind"], "media")

	def test_bridge_mode_blocked_before_bridge_upload(self):
		adapter = self._adapter()
		with patch.object(adapter, "_bridge_mode", return_value=True), patch.object(bridge, "upload_media") as up, _hooks(
			_block
		), self.assertRaises(policy.OutboundRefused):
			adapter.upload_media(b"x", "image/png", "p.png", "image", False, to=TO)
		up.assert_not_called()

	def test_no_recipient_or_no_hook_unchanged(self):
		adapter = self._adapter()
		with patch.object(adapter, "_bridge_mode", return_value=False), patch.object(
			bridge, "post_media_upload", return_value="MID"
		) as post, patch.object(bridge.wm, "normalize_mime", return_value="audio/ogg"), patch.object(
			bridge.wm, "validate_upload", return_value=("audio", [])
		):
			with _hooks(_block):
				self.assertEqual(adapter.upload_media(b"x", "audio/ogg", "v.ogg", "audio", True), "MID")  # no `to`: no hook
			with _hooks():
				self.assertEqual(adapter.upload_media(b"x", "audio/ogg", "v.ogg", "audio", True, to=TO), "MID")
		self.assertEqual(post.call_count, 2)


if __name__ == "__main__":
	unittest.main()
