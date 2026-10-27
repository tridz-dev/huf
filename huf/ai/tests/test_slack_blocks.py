"""Unit tests for Block Kit builders (huf/ai/gateways/blocks.py) and the adapter blocks passthrough."""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _stub_env  # noqa: E402

_stub_env.install()
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from huf.ai.gateways import blocks as bk  # noqa: E402


class TestBlocks(unittest.TestCase):
	def test_escape(self):
		self.assertEqual(bk.escape_mrkdwn("a<b>&c"), "a&lt;b&gt;&amp;c")
		self.assertEqual(bk.escape_mrkdwn(None), "")

	def test_section_escapes_and_fallback(self):
		r = bk.section_text("<!channel> hi & bye")
		self.assertEqual(r.blocks[0]["type"], "section")
		self.assertNotIn("<!channel>", r.blocks[0]["text"]["text"])
		self.assertEqual(r.fallback, r.blocks[0]["text"]["text"])

	def test_section_clipped(self):
		r = bk.section_text("x" * 5000)
		self.assertLessEqual(len(r.blocks[0]["text"]["text"]), 3000)

	def test_button_carries_only_session(self):
		b = bk.button("Go", "abc123")
		self.assertEqual(b["value"], "abc123")
		self.assertEqual(b["action_id"], "abc123")
		self.assertEqual(b["type"], "button")

	def test_button_choice_and_parse(self):
		b = bk.button("Yes", "abc123", choice="approve", style="primary")
		self.assertEqual(b["action_id"], "abc123.approve")
		self.assertEqual(bk.parse_action_id(b["action_id"]), ("abc123", "approve"))
		self.assertEqual(bk.parse_action_id("abc123"), ("abc123", None))

	def test_button_validation(self):
		with self.assertRaises(ValueError):
			bk.button("x", "")
		with self.assertRaises(ValueError):
			bk.button("x", "n", style="red")
		with self.assertRaises(ValueError):
			bk.button("x", "n", choice="Bad Choice")

	def test_button_text_clipped(self):
		self.assertLessEqual(len(bk.button("x" * 200, "n")["text"]["text"]), 75)

	def test_confirm_dialog(self):
		c = bk.confirm_dialog("Sure?", "This <b> deletes")
		self.assertEqual(set(c), {"title", "text", "confirm", "deny"})
		self.assertIn("&lt;b&gt;", c["text"]["text"])
		self.assertIn("confirm", bk.button("x", "n", confirm=c))

	def test_actions_block_limits(self):
		with self.assertRaises(ValueError):
			bk.actions_block()
		self.assertEqual(bk.actions_block(bk.button("a", "n"), block_id="b")["block_id"], "b")

	def test_approval_card(self):
		r = bk.approval_card("Deploy *now*", "Ship <it>", "sess1")
		self.assertEqual(r.blocks[0]["type"], "section")
		els = r.blocks[1]["elements"]
		self.assertEqual([e["action_id"] for e in els], ["sess1.approve", "sess1.reject"])
		self.assertEqual({e["value"] for e in els}, {"sess1"})
		self.assertEqual(els[0]["style"], "primary")
		self.assertEqual(els[1]["style"], "danger")
		self.assertIn("&lt;it&gt;", r.blocks[0]["text"]["text"])
		self.assertTrue(r.fallback)
		self.assertNotIn("*", r.fallback)

	def test_status_line(self):
		r = bk.status_line("Approved by <me>", icon=":white_check_mark:")
		self.assertEqual(r.blocks[0]["type"], "context")
		self.assertIn("&lt;me&gt;", r.blocks[0]["text"]["text"] if "text" in r.blocks[0] else r.blocks[0]["elements"][0]["text"])
		self.assertTrue(r.fallback.startswith(":white_check_mark:"))

	def test_buttons_fallback(self):
		r = bk.buttons(bk.button("A", "n", choice="a"), bk.button("B", "n", choice="b"))
		self.assertEqual(r.fallback, "A / B")


@unittest.skipUnless(importlib.util.find_spec("cryptography"), "adapter package needs cryptography")
class TestAdapterBlocks(unittest.TestCase):
	def _adapter(self):
		from huf.ai.gateway_adapters.slack import SlackGatewayAdapter

		return SlackGatewayAdapter

	def test_reply_blocks_default_none(self):
		from huf.ai.gateway_adapters.types import GatewayReply

		self.assertIsNone(GatewayReply("C1", "hi").blocks)
		self.assertEqual(GatewayReply("C1", "hi", blocks=[{"type": "divider"}]).blocks, [{"type": "divider"}])

	def _send(self, **kw):
		import inspect

		from huf.ai.gateway_adapters import slack as mod
		from huf.ai.gateway_adapters.types import GatewayReply

		cls = next(c for _, c in inspect.getmembers(mod, inspect.isclass) if hasattr(c, "send_reply") and c.__module__ == mod.__name__)
		a = cls.__new__(cls)
		a._token = "xoxb-test"
		resp = MagicMock()
		resp.json.return_value = {"ok": True, "ts": "1.2"}
		a._http_post = MagicMock(return_value=resp)
		a.send_reply(GatewayReply("C1", "fallback text", **kw))
		return a._http_post.call_args.kwargs["json_data"]

	def test_adapter_passes_blocks_and_text(self):
		p = self._send(blocks=[{"type": "divider"}])
		self.assertEqual(p["blocks"], [{"type": "divider"}])
		self.assertEqual(p["text"], "fallback text")

	def test_adapter_unchanged_without_blocks(self):
		self.assertNotIn("blocks", self._send())


if __name__ == "__main__":
	unittest.main()
