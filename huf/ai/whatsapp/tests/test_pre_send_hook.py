# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""T8: ``huf_gateway_pre_send`` at the adapter, agent-tool and management Graph POST sites (HUFWA-14).

One test per insertion point: a blocking hook refuses the send and the network post is NOT made; no hook leaves
behaviour unchanged. Plus: a raising hook blocks, gateway None skips, consent_confirmation passes through,
and blocked_by_hook is non-retryable and mapped by reply_api / broadcast.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

import frappe

from huf.ai.gateway_adapters.types import GatewayReply
from huf.ai.gateway_adapters.whatsapp import WhatsAppGatewayAdapter
from huf.ai.tools import whatsapp as wtools
from huf.ai.whatsapp import management as mgmt
from huf.ai.whatsapp import outbound_policy as policy

MOD = "huf.ai.whatsapp.tests.test_pre_send_hook"
SEEN: list[dict] = []
GW = "GW-PRE"
TO = "919876543210"
CREDS = {"phone_number_id": "111", "access_token": "tok", "webhook_verify_token": "v", "app_secret": "s"}


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
	return patch(
		"huf.ai.gateway_hooks.frappe.get_hooks",
		side_effect=lambda n, *a, **k: paths if n == "huf_gateway_pre_send" else [],
	)


class _Base(unittest.TestCase):
	def setUp(self):
		SEEN.clear()
		p = patch("huf.ai.gateway_hooks.frappe.log_error")
		p.start()
		self.addCleanup(p.stop)


def _ok_response():
	r = MagicMock()
	r.status_code = 200
	r.json.return_value = {"messages": [{"id": "wamid.1"}]}
	return r


class TestCheckPreSend(_Base):
	def test_no_hook_allows(self):
		with _hooks():
			policy.check_pre_send(GW, TO, "text")

	def test_blocking_hook_raises_blocked_by_hook_with_payload(self):
		with _hooks(_block), self.assertRaises(policy.OutboundRefused) as cm:
			policy.check_pre_send(GW, TO, "template", {"source": "x"})
		self.assertEqual(cm.exception.code, "blocked_by_hook")
		self.assertEqual(SEEN[0]["gateway"], GW)
		self.assertEqual(SEEN[0]["to"], TO)
		self.assertEqual(SEEN[0]["kind"], "template")
		self.assertEqual(SEEN[0]["context"], {"source": "x"})

	def test_raising_hook_blocks(self):
		with _hooks(_boom), self.assertRaises(policy.OutboundRefused) as cm:
			policy.check_pre_send(GW, TO, "text")
		self.assertEqual(cm.exception.code, "blocked_by_hook")

	def test_gateway_none_skipped(self):
		with _hooks(_block):
			policy.check_pre_send(None, TO, "text")
		self.assertEqual(SEEN, [])

	def test_not_retryable(self):
		from huf.ai.gateways.teams.webhook import _is_transient_send_error

		self.assertFalse(_is_transient_send_error(policy.OutboundRefused("x", "blocked_by_hook")))

	def test_reply_api_and_broadcast_map_the_code(self):
		from huf.ai.channels import reply_api
		from huf.ai.whatsapp.broadcast import send as bsend

		self.assertIn("blocked_by_hook", reply_api._POLICY_CODES)
		self.assertIn("blocked_by_hook", bsend._SKIP_CODES)


class TestAdapterGraphSend(_Base):
	def _adapter(self, post):
		return WhatsAppGatewayAdapter(CREDS, http_post=post, gateway_context={"gateway_name": GW})

	def _reply(self):
		return GatewayReply(conversation_id=TO, text="hello")

	def _patches(self):
		return (
			patch("huf.ai.gateway_adapters.whatsapp.bridge.window_state", return_value={"open": True}),
			patch.object(policy, "check_recipient"),
			patch("huf.ai.gateway_adapters.whatsapp.account_events_mod.send_refusal", return_value=None),
		)

	def test_in_window_concierge_text_reply_blocked_and_not_posted(self):
		post = MagicMock(return_value=_ok_response())
		a, b, c = self._patches()
		with a, b, c, _hooks(_block), self.assertRaises(policy.OutboundRefused) as cm:
			self._adapter(post).send_reply(self._reply())
		self.assertEqual(cm.exception.code, "blocked_by_hook")
		post.assert_not_called()
		self.assertEqual(SEEN[0]["kind"], "text")
		self.assertFalse(SEEN[0]["context"]["consent_confirmation"])

	def test_no_hook_sends(self):
		post = MagicMock(return_value=_ok_response())
		a, b, c = self._patches()
		with a, b, c, _hooks():
			delivery = self._adapter(post).send_reply(self._reply())
		post.assert_called_once()
		self.assertEqual(delivery.provider_message_id, "wamid.1")

	def test_raising_hook_blocks_send(self):
		post = MagicMock(return_value=_ok_response())
		a, b, c = self._patches()
		with a, b, c, _hooks(_boom), self.assertRaises(policy.OutboundRefused):
			self._adapter(post).send_reply(self._reply())
		post.assert_not_called()

	def test_gateway_none_skips(self):
		post = MagicMock(return_value=_ok_response())
		adapter = WhatsAppGatewayAdapter(CREDS, http_post=post)
		with (
			patch("huf.ai.gateway_adapters.whatsapp.account_events_mod.send_refusal", return_value=None),
			_hooks(_block),
		):
			adapter._graph_send({"to": TO, "type": "text", "text": {"body": "x"}})
		post.assert_called_once()
		self.assertEqual(SEEN, [])

	def test_consent_confirmation_flag_passes_through(self):
		post = MagicMock(return_value=_ok_response())
		frappe.local.huf_consent_send_scope = (GW, TO)
		self.addCleanup(lambda: setattr(frappe.local, "huf_consent_send_scope", None))
		a, b, c = self._patches()
		with a, b, c, _hooks(_allow):
			self._adapter(post).send_reply(self._reply())
		self.assertTrue(SEEN[0]["context"]["consent_confirmation"])
		# a different recipient under the same scope is not flagged
		SEEN.clear()
		with (
			_hooks(_allow),
			patch("huf.ai.gateway_adapters.whatsapp.account_events_mod.send_refusal", return_value=None),
		):
			self._adapter(post)._graph_send({"to": "15550001111", "type": "text", "text": {"body": "x"}})
		self.assertFalse(SEEN[0]["context"]["consent_confirmation"])

	def test_template_kind(self):
		post = MagicMock(return_value=_ok_response())
		with (
			_hooks(_block),
			patch("huf.ai.gateway_adapters.whatsapp.account_events_mod.send_refusal", return_value=None),
		):
			with self.assertRaises(policy.OutboundRefused):
				self._adapter(post)._graph_send({"to": TO, "type": "template", "template": {"name": "t"}})
		post.assert_not_called()
		self.assertEqual(SEEN[0]["kind"], "template")


class TestToolDirectPosts(_Base):
	KW = {"gateway_name": GW, "to": TO, "message": "hi"}

	def _common(self):
		return (
			patch.object(wtools, "_free_form_refusal", return_value=None),
			patch.object(wtools, "_allowlist_refusal", return_value=None),
			patch.object(wtools, "_is_opted_out", return_value=False),
			patch.object(wtools, "_resolve_bridge_account", return_value=None),
			patch.object(wtools, "_get_whatsapp_credentials", return_value=("111", "tok")),
			patch.object(wtools, "_graph_root", return_value="https://graph.invalid/v1"),
		)

	def _run(self, fn, kwargs, hooks, *args):
		ps = self._common()
		with (
			ps[0],
			ps[1],
			ps[2],
			ps[3],
			ps[4],
			ps[5],
			hooks,
			patch.object(wtools.requests, "post", return_value=_ok_response()) as post,
		):
			out = json.loads(fn(kwargs, *args))
		return out, post

	def test_text_post_blocked(self):
		out, post = self._run(wtools._send_message, dict(self.KW), _hooks(_block))
		post.assert_not_called()
		self.assertEqual(out["error"], "blocked_by_hook")
		self.assertEqual(SEEN[0]["kind"], "text")

	def test_text_post_no_hook(self):
		out, post = self._run(wtools._send_message, dict(self.KW), _hooks())
		post.assert_called_once()
		self.assertTrue(out["success"])

	def test_text_post_hook_raising_blocks(self):
		out, post = self._run(wtools._send_message, dict(self.KW), _hooks(_boom))
		post.assert_not_called()
		self.assertEqual(out["error"], "blocked_by_hook")

	def test_typed_post_blocked(self):
		built = (
			{"messaging_product": "whatsapp", "to": TO, "type": "image", "image": {"link": "https://x"}},
			[],
		)
		out, post = self._run(
			lambda kw: wtools._deliver_typed(kw, TO, built, None, "image"), dict(self.KW), _hooks(_block)
		)
		post.assert_not_called()
		self.assertEqual(out["error"], "blocked_by_hook")
		self.assertEqual(SEEN[0]["kind"], "media")

	def test_typed_post_no_hook(self):
		built = ({"messaging_product": "whatsapp", "to": TO, "type": "location", "location": {}}, [])
		out, post = self._run(
			lambda kw: wtools._deliver_typed(kw, TO, built, None, "location"), dict(self.KW), _hooks()
		)
		post.assert_called_once()
		self.assertTrue(out["success"])

	def test_template_post_blocked(self):
		kw = {"gateway_name": GW, "to": TO, "template_name": "hello"}
		out, post = self._run(wtools._send_template, kw, _hooks(_block))
		post.assert_not_called()
		self.assertEqual(out["error"], "blocked_by_hook")
		self.assertEqual(SEEN[0]["kind"], "template")

	def test_template_post_no_hook(self):
		kw = {"gateway_name": GW, "to": TO, "template_name": "hello"}
		out, post = self._run(wtools._send_template, kw, _hooks())
		post.assert_called_once()


class TestManagementCallPermission(_Base):
	def _call(self, hooks):
		graph = MagicMock()
		graph.send_permission_request.return_value = {"ok": 1}
		with (
			patch.object(mgmt, "_calls_graph", return_value=graph),
			patch.object(mgmt, "_validate_recipient", return_value=TO),
			patch.object(mgmt.wcalls, "permission_request_payload"),
			patch.object(mgmt, "_free_form_gate", return_value=None),
			hooks,
		):
			out = mgmt.send_call_permission_request(gateway_name=GW, to=TO, text="t")
		return out, graph

	def test_blocked(self):
		out, graph = self._call(_hooks(_block))
		graph.send_permission_request.assert_not_called()
		self.assertEqual(out["error"], "blocked_by_hook")
		self.assertFalse(out["success"])
		self.assertEqual(SEEN[0]["context"]["subtype"], "call_permission_request")

	def test_no_hook(self):
		out, graph = self._call(_hooks())
		graph.send_permission_request.assert_called_once()
		self.assertTrue(out["success"])

	def test_hook_raising_blocks(self):
		out, graph = self._call(_hooks(_boom))
		graph.send_permission_request.assert_not_called()
		self.assertEqual(out["error"], "blocked_by_hook")


if __name__ == "__main__":
	unittest.main()
