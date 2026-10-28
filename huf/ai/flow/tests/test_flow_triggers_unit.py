"""Pure (no bench) tests for flow trigger dispatch, node-schema generation and webhook auth.

  python -m pytest huf/ai/flow/tests/test_flow_triggers_unit.py   (needs croniter, which Frappe ships)

Needs a bench (not covered here): the actual enqueue/run path, doc-event hook firing with real
documents and permissions, the scheduler tick, Flow Run dedup query, flow_webhook over HTTP.
"""

import json
import unittest
from datetime import datetime
from pathlib import Path

from huf.ai.flow import api as flow_api
from huf.ai.flow import triggers as T

SCHEMA = json.loads((Path(T.__file__).parents[1] / "graph" / "graph_ir.schema.json").read_text())


def _webhook(node_id="w", method="POST", secret="s3cret-value"):
	return {"id": node_id, "type": "trigger.webhook", "config": {"method": method, "secret": secret}}


class TestWebhookMatch(unittest.TestCase):
	def defn(self, *nodes):
		return {"entry": [n["id"] for n in nodes], "nodes": list(nodes)}

	def test_ok(self):
		node, why = T.match_webhook_trigger(self.defn(_webhook()), "s3cret-value", "POST")
		self.assertEqual((node["id"], why), ("w", "ok"))

	def test_wrong_or_missing_secret(self):
		d = self.defn(_webhook())
		for presented in ("nope", "", None, "s3cret-valu"):
			self.assertEqual(T.match_webhook_trigger(d, presented, "POST"), (None, "bad_secret"))

	def test_method_enforced_only_after_secret(self):
		d = self.defn(_webhook(method="GET"))
		self.assertEqual(T.match_webhook_trigger(d, "s3cret-value", "POST"), (None, "bad_method"))
		self.assertEqual(T.match_webhook_trigger(d, "wrong", "POST"), (None, "bad_secret"))
		self.assertEqual(T.match_webhook_trigger(d, "s3cret-value", "get")[1], "ok")

	def test_non_http_call_skips_method(self):
		self.assertEqual(T.match_webhook_trigger(self.defn(_webhook()), "s3cret-value", None)[1], "ok")

	def test_fails_closed_on_missing_or_short_secret(self):
		for bad in (None, "", "short", 1234567890):
			node = {"id": "w", "type": "trigger.webhook", "config": {"method": "POST", "secret": bad}}
			self.assertEqual(T.match_webhook_trigger(self.defn(node), bad or "", "POST")[0], None)

	def test_legacy_keys_are_not_read(self):
		node = {"id": "w", "type": "trigger.webhook", "config": {"method": "POST", "auth": "legacy-key-1", "apiKey": "legacy-key-2"}}
		for k in ("legacy-key-1", "legacy-key-2"):
			self.assertIsNone(T.match_webhook_trigger(self.defn(node), k, "POST")[0])

	def test_no_webhook_trigger_and_non_entry_node(self):
		self.assertEqual(T.match_webhook_trigger({"entry": "a", "nodes": [{"id": "a", "type": "output", "config": {}}]}, "x", "POST"), (None, "no_trigger"))
		d = {"entry": "other", "nodes": [_webhook(), {"id": "other", "type": "output", "config": {}}]}
		self.assertEqual(T.match_webhook_trigger(d, "s3cret-value", "POST"), (None, "no_trigger"))

	def test_picks_matching_node_among_several(self):
		d = self.defn(_webhook("a", secret="aaaaaaaa"), _webhook("b", secret="bbbbbbbb"))
		self.assertEqual(T.match_webhook_trigger(d, "bbbbbbbb", "POST")[0]["id"], "b")


class TestCron(unittest.TestCase):
	def test_due(self):
		m = datetime(2026, 10, 28, 9, 15, 0)
		self.assertTrue(T.cron_is_due("*/15 * * * *", m))
		self.assertTrue(T.cron_is_due("15 9 * * *", m))
		self.assertTrue(T.cron_is_due("* * * * *", m))
		self.assertFalse(T.cron_is_due("*/15 * * * *", datetime(2026, 10, 28, 9, 16)))
		self.assertFalse(T.cron_is_due("0 9 * * *", m))

	def test_seconds_ignored(self):
		self.assertTrue(T.cron_is_due("15 9 * * *", datetime(2026, 10, 28, 9, 15, 42, 5)))

	def test_dow_and_dom(self):
		self.assertTrue(T.cron_is_due("0 0 * * 3", datetime(2026, 10, 28, 0, 0)))  # Wednesday
		self.assertFalse(T.cron_is_due("0 0 * * 1", datetime(2026, 10, 28, 0, 0)))
		self.assertTrue(T.cron_is_due("30 8 28 10 *", datetime(2026, 10, 28, 8, 30)))

	def test_invalid_is_never_due(self):
		for bad in ("", None, "* * * *", "* * * * * *", "61 * * * *", "every day", 5):
			self.assertFalse(T.cron_is_due(bad, datetime(2026, 10, 28, 9, 15)))


class TestDocEventIndex(unittest.TestCase):
	def test_event_map_matches_schema_enum_and_hooks(self):
		enum = SCHEMA["$defs"]["TriggerDocEventNode"]["allOf"][1]["properties"]["config"]["properties"]["event"]["enum"]
		self.assertEqual(set(T.DOC_EVENT_MAP), set(enum))
		hooks = (Path(T.__file__).parents[2] / "hooks.py").read_text()
		star = hooks[hooks.index('    "*": {') :]
		star = star[: star.index("\n    },")]
		for frappe_event in T.DOC_EVENT_MAP.values():
			line = next(l for l in star.splitlines() if l.strip().startswith(f'"{frappe_event}":'))
			self.assertIn("huf.ai.flow.triggers.run_doc_event_flows", line)

	def test_build_index(self):
		node = {"id": "d", "type": "trigger.doc-event", "config": {"doctype": "ToDo", "event": "after_insert"}}
		bad = {"id": "e", "type": "trigger.doc-event", "config": {"doctype": "ToDo", "event": "on_delete"}}
		rows = [
			("f1", "a@x.com", {"entry": ["d", "e"], "nodes": [node, bad]}),
			("f2", "b@x.com", {"entry": "d", "nodes": [node]}),
			("f3", "c@x.com", {"entry": "w", "nodes": [_webhook()]}),
		]
		idx = T.build_doc_event_index(rows)
		self.assertEqual(list(idx), ["ToDo"])
		self.assertEqual([e["flow"] for e in idx["ToDo"]["after_insert"]], ["f1", "f2"])
		self.assertNotIn("on_delete", idx["ToDo"])

	def test_recursion_skip(self):
		for dt in ("Flow Run", "Agent Run", "Flow Definition"):
			self.assertTrue(T.is_recursion_skipped(dt))
		self.assertTrue(T.is_recursion_skipped("Whatever", "Huf"))
		self.assertFalse(T.is_recursion_skipped("ToDo", "Desk"))


class TestNodeSchemas(unittest.TestCase):
	def setUp(self):
		self.out = flow_api.build_node_schemas(SCHEMA)

	def test_all_flow_node_types_advertised(self):
		defs = SCHEMA["$defs"]
		expected = set()
		for entry in defs["FlowNode"]["oneOf"]:
			expected.add(flow_api._node_config_schema(defs[entry["$ref"].rsplit("/", 1)[-1]])[0])
		self.assertEqual(set(self.out), expected)
		self.assertEqual(len(expected), 19)

	def test_fields_match_schema_exactly(self):
		for node_type, desc in self.out.items():
			names = {f["name"] for f in desc["config_schema"]}
			self.assertEqual(names, set(desc["json_schema"].get("properties", {})), node_type)
			required = {f["name"] for f in desc["config_schema"] if f["required"]}
			self.assertEqual(required, set(desc["json_schema"].get("required", [])), node_type)

	def test_contract_fields(self):
		f = lambda t: {x["name"]: x for x in self.out[t]["config_schema"]}
		wh = f("trigger.webhook")
		self.assertEqual(set(wh), {"method", "secret"})
		self.assertEqual(wh["method"]["options"], ["GET", "POST"])
		self.assertTrue(wh["secret"]["required"])
		self.assertEqual(wh["secret"]["min_length"], 8)
		self.assertEqual(f("trigger.doc-event")["event"]["options"], ["after_insert", "on_update", "on_submit", "on_cancel", "on_trash"])
		self.assertEqual(set(f("trigger.schedule")), {"cron"})
		self.assertEqual(set(f("condition")), {"expression", "on_true", "on_false"})
		self.assertEqual(f("foreach")["body"]["type"], "node_list")
		self.assertEqual(f("human.approval")["approver_users"]["type"], "string_list")
		self.assertEqual(set(f("agent.run")), {"agent", "prompt", "prompt_bindings"})
		self.assertEqual(f("tool.call")["tool_id"]["type"], "tool_select")

	def test_no_legacy_names(self):
		blob = json.dumps(self.out)
		for legacy in ('"auth"', "apiKey", "schedule_name", "timezone", "true_node", "iterate_over", "transformations", "tool_name", "router_agent_name"):
			self.assertNotIn(legacy, blob)

	def test_routing_flags(self):
		for t in ("output", "condition", "router.llm", "human.approval"):
			self.assertFalse(self.out[t]["routing"]["next"], t)
		self.assertTrue(self.out["transform"]["routing"]["next"])


if __name__ == "__main__":
	unittest.main()


class TestExpireDueApprovals(unittest.TestCase):
	NOW = datetime(2026, 10, 28, 12, 0, 0)

	def test_only_past_deadlines_are_due(self):
		rows = [
			{"name": "past", "waiting": json.dumps({"timeout_at": "2026-10-28T11:59:00"})},
			{"name": "future", "waiting": json.dumps({"timeout_at": "2026-10-28T12:30:00"})},
			{"name": "none", "waiting": json.dumps({"timeout_at": None})},
			{"name": "bad", "waiting": "{oops"},
			{"name": "empty", "waiting": None},
		]
		self.assertEqual(T.due_approval_run_names(rows, self.NOW), ["past"])


class TestLatestDueMinute(unittest.TestCase):
	def test_catches_up_a_due_minute_inside_the_tick_window(self):
		# A 4 minute tick lands at 09:03 for a cron due at 09:00.
		self.assertEqual(T.latest_due_minute("0 9 * * *", datetime(2026, 10, 28, 9, 3, 40), 240), datetime(2026, 10, 28, 9, 0))

	def test_a_due_minute_outside_the_window_is_not_replayed(self):
		self.assertIsNone(T.latest_due_minute("0 9 * * *", datetime(2026, 10, 28, 9, 4, 5), 240))

	def test_every_minute_cron_returns_the_current_minute_once_per_tick(self):
		self.assertEqual(T.latest_due_minute("*/1 * * * *", datetime(2026, 10, 28, 9, 7, 30), 240), datetime(2026, 10, 28, 9, 7))

	def test_invalid_cron_is_never_due(self):
		self.assertIsNone(T.latest_due_minute("61 25 * * *", datetime(2026, 10, 28, 9, 0), 240))


class TestWebhookHttpStatus(unittest.TestCase):
	"""Frappe answers with the exception's http_status_code, so the rejection classes must carry 403 / 405."""

	def test_denied_is_403_and_still_an_authentication_error(self):
		import frappe

		self.assertEqual(flow_api.WebhookDenied.http_status_code, 403)
		self.assertTrue(issubclass(flow_api.WebhookDenied, frappe.AuthenticationError))

	def test_wrong_method_is_405(self):
		self.assertEqual(flow_api.WebhookMethodNotAllowed.http_status_code, 405)
