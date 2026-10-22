"""Telegram inline mode: admission, results, limits, paging, resolvers, chosen record (fakes only)."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from huf.ai.gateway_adapters import telegram_ingest as ing
from huf.ai.gateway_adapters import telegram_inline as ti
from huf.ai.tests.telegram_fakes import load_fixture


def gw(policy="Pairing", user="agent@example.com"):
	g = {"name": "GW", "direct_policy": policy, "execution_user": user}
	return SimpleNamespace(**g, get=lambda k, d=None: g.get(k, d))


def parsed_for(raw):
	return SimpleNamespace(kind="unsupported", raw=raw, bot_blocked=False, bot_unblocked=False)


class Base(unittest.TestCase):
	def setUp(self):
		self.saved = dict(ti._RESOLVERS)
		self.adapter = MagicMock()
		p1 = patch("huf.ai.gateway_service._sender_negative_state", return_value=None)
		p2 = patch("huf.ai.gateway_service._has_access_entry", return_value=True)
		p3 = patch.object(ti.frappe, "set_user")
		self.admit = p2.start()
		p1.start(), p3.start()
		self.addCleanup(patch.stopall)

	def tearDown(self):
		ti._RESOLVERS.clear()
		ti._RESOLVERS.update(self.saved)

	def run_query(self, raw=None, gateway=None):
		raw = raw or load_fixture("inline_query")
		res = ti.handle_inline_query(gateway or gw(), self.adapter, parsed_for(raw), None)
		return res, self.adapter.client.call.call_args


class TestInline(Base):
	def test_unpaired_gets_pair_button_and_no_data(self):
		self.admit.return_value = False
		res, call = self.run_query()
		method, payload = call.args
		self.assertEqual(method, "answerInlineQuery")
		self.assertEqual(len(payload["results"]), 1)
		self.assertEqual(payload["results"][0]["title"], "Pair this bot")
		self.assertEqual(payload["button"]["start_parameter"], "pair")
		self.assertNotIn("weekly", str(payload))
		self.assertEqual(payload["cache_time"], 0)

	def test_blocked_sender_is_not_admitted(self):
		with patch("huf.ai.gateway_service._sender_negative_state", return_value="Blocked"):
			self.assertFalse(ti.is_admitted(gw(), "111"))

	def test_paired_gets_default_ask_result(self):
		res, call = self.run_query()
		payload = call.args[1]
		r = payload["results"][0]
		self.assertEqual(r["type"], "article")
		self.assertIn("Ask the assistant: weekly report", r["title"])
		self.assertEqual(r["reply_markup"]["inline_keyboard"][0][0]["text"], "Run")
		self.assertEqual(payload["cache_time"], 30)
		self.assertTrue(payload["is_personal"])
		self.assertNotIn("button", payload)

	def test_empty_query_returns_no_default(self):
		raw = load_fixture("inline_query")
		raw["inline_query"]["query"] = ""
		res, call = self.run_query(raw)
		self.assertEqual(call.args[1]["results"], [])

	def test_admin_execution_user_gets_nothing(self):
		res, call = self.run_query(gateway=gw(user="Administrator"))
		self.assertEqual(call.args[1]["results"], [])

	def test_bot_sender_ignored(self):
		raw = load_fixture("inline_query")
		raw["inline_query"]["from"]["is_bot"] = True
		res, call = self.run_query(raw)
		self.assertIsNone(call)

	def test_resolver_registration_runs_as_execution_user(self):
		seen = {}

		def fn(query, ctx):
			seen.update(ctx)
			return [{"type": "article", "id": "x1", "title": "T", "input_message_content": {"message_text": "t"}}]

		ti.register_resolver("mine", fn)
		self.assertIn("mine", ti.resolver_names())
		self.run_query()
		self.assertEqual(seen["user"], "agent@example.com")
		ti.frappe.set_user.assert_any_call("agent@example.com")

	def test_failing_resolver_skipped_and_dupes_dropped(self):
		def boom(q, c):
			raise RuntimeError("x")

		dup = lambda q, c: [{"type": "article", "id": "d", "title": "a"}, {"type": "article", "id": "d", "title": "b"}]
		ti.register_resolver("boom", boom)
		ti.register_resolver("dup", dup)
		out = ti.collect_results("q", {"user": "u@x.com"})
		self.assertEqual([r["id"] for r in out].count("d"), 1)

	def test_limit_and_paging(self):
		many = [{"type": "article", "id": f"r{i}", "title": "t"} for i in range(120)]
		ti.register_resolver("many", lambda q, c: many)
		payload = ti.build_answer("iq", many, 0)
		self.assertEqual(len(payload["results"]), 50)
		self.assertEqual(payload["next_offset"], "50")
		p2 = ti.build_answer("iq", many, 100)
		self.assertEqual(len(p2["results"]), 20)
		self.assertNotIn("next_offset", p2)
		self.assertEqual(ti.parse_offset("abc"), 0)
		self.assertEqual(ti.parse_offset("50"), 50)

	def test_paging_via_handler(self):
		many = [{"type": "article", "id": f"r{i}", "title": "t"} for i in range(60)]
		ti._RESOLVERS.clear()
		ti.register_resolver("many", lambda q, c: many)
		raw = load_fixture("inline_query")
		raw["inline_query"]["offset"] = "50"
		res, call = self.run_query(raw)
		self.assertEqual(len(call.args[1]["results"]), 10)

	def test_answer_failure_is_acked(self):
		self.adapter.client.call.side_effect = RuntimeError("boom")
		res, _ = self.run_query()
		self.assertTrue(res["success"])

	def test_chosen_recorded_without_agent_run_or_query_text(self):
		raw = load_fixture("chosen_inline_result")
		with patch.object(ti.frappe, "logger") as lg:
			res = ti.handle_chosen_inline_result(gw(), self.adapter, parsed_for(raw), None)
		self.assertEqual(res["handled"], "chosen_inline_result")
		self.assertNotIn("weekly", str(lg.return_value.info.call_args))
		self.adapter.client.call.assert_not_called()

	def test_hooks_registered_and_dispatch_via_ingest(self):
		import huf.ai.gateway_adapters.telegram_inline_hooks  # noqa: F401

		for key in ("inline_query", "chosen_inline_result", "unsupported"):
			self.assertIn(key, ing._UPDATE_HANDLERS)
		self.assertIsNone(ti.dispatch(gw(), self.adapter, parsed_for({"update_id": 1}), None))
		self.assertEqual(
			ti.dispatch(gw(), self.adapter, parsed_for(load_fixture("chosen_inline_result")), None)["handled"],
			"chosen_inline_result",
		)


if __name__ == "__main__":
	unittest.main()
