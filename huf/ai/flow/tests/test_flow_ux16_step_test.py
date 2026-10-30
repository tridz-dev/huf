# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""UX-16 on a bench: trying one step on its own. Reads run, sends are simulated, agents say so, nothing is stored.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_ux16_step_test
"""

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime

from huf.ai.flow import engine as flow_engine
from huf.ai.flow.support.trigger_sample import MASK, MAX_SAMPLE_BYTES, cap_node_samples
from huf.ai.flow.testrun import step_test as st
from huf.ai.flow.testrun import step_test_api as api
from huf.ai.flow.testrun.step_sample import clean_sample_input, pin_value, redact_output
from huf.testing.factories import make_user

SECRET = "s" * 40
BOGUS = "nobody@bogus-address.invalid"


def _graph(trigger_sample=None, steps=None):
	trigger = {"id": "t", "type": "trigger.webhook", "_label": "New order", "config": {"method": "POST", "secret": SECRET}, "next": "fetch"}
	if trigger_sample is not None:
		trigger["_sample"] = trigger_sample
	return {
		"entry": "t",
		"nodes": [
			trigger,
			{"id": "fetch", "type": "transform", "_label": "Pick fields", "config": {"op": "pick", "input": {"value": {"$from": "input"}, "fields": ["email"]}}, "next": "cond"},
			{
				"id": "cond", "type": "condition", "_label": "Big order?",
				"config": {"expression": "input['total'] > 100", "on_true": "mail", "on_false": "end"},
			},
			{
				"id": "mail", "type": "tool.call", "_label": "Send email",
				"config": {"tool_id": "gmail_send_email", "input": {"to": {"$from": "input.email"}, "subject": "Hello", "body": "Hi"}},
				"next": "end",
			},
			{"id": "end", "type": "output", "config": {}},
			*(steps or []),
		],
	}


class Base(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._docs = []
		self.flow_id = None

	def tearDown(self):
		frappe.set_user("Administrator")
		for doctype, name in reversed(self._docs):
			if frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _flow(self, graph):
		self.flow_id = f"_test-ux16-{frappe.generate_hash(length=8)}"
		doc = frappe.get_doc(
			{"doctype": "Flow Definition", "flow_id": self.flow_id, "flow_name": "UX16", "status": "Draft", "definition_json": json.dumps(graph)}
		)
		doc.flags.ignore_validate = True
		doc.insert(ignore_permissions=True)
		self._docs.append(("Flow Definition", doc.name))
		return doc.name

	def _run(self, payload=None, outputs=None, status="Success"):
		run = frappe.get_doc(
			{
				"doctype": "Flow Run", "flow_definition": self.flow_id, "flow_id": self.flow_id, "status": status, "trigger_type": "Webhook",
				"started_at": now_datetime(), "trigger_payload": json.dumps(payload or {}),
				"context_json": json.dumps({**(payload or {}), "__node_outputs__": outputs or {}}),
			}
		)
		run.insert(ignore_permissions=True)
		self._docs.append(("Flow Run", run.name))

	def _runs(self):
		return frappe.db.count("Flow Run", {"flow_id": self.flow_id})


class TestRealAndSimulated(Base):
	def setUp(self):
		super().setUp()
		self._flow(_graph({"email": "ada@example.com", "total": 450}))

	def test_a_condition_runs_for_real_and_says_where_it_goes(self):
		out = api.test_step(self.flow_id, "cond")
		self.assertEqual(out["status"], "success", out)
		self.assertEqual(out["mode"], "real")
		self.assertIs(out["output"], True)
		self.assertEqual(out["branch"], "Yes")
		self.assertEqual(out["goes_to"], "Send email")

	def test_an_edited_sample_changes_the_answer(self):
		out = api.test_step(self.flow_id, "cond", {"input": {"total": 5}})
		self.assertEqual((out["status"], out["branch"], out["goes_to"]), ("success", "No", "End"))

	def test_a_step_that_sends_is_simulated_and_the_tool_never_runs(self):
		with patch.object(flow_engine, "execute_tool") as tool:
			out = api.test_step(self.flow_id, "mail")
		tool.assert_not_called()
		self.assertEqual((out["status"], out["mode"], out["effect"]), ("success", "simulated", "sends"))
		self.assertEqual(out["summary"], "Would send email to ada@example.com")
		self.assertTrue(out["output"]["simulated"])

	def test_a_pinned_copy_of_a_skipped_step_keeps_the_sample_fields_not_the_wording(self):
		out = api.test_step(self.flow_id, "mail")
		self.assertEqual(out["pin_value"], {"id": "sample-0001", "threadId": "sample-0001", "labelIds": ["SENT"]})

	def test_a_read_tool_runs_for_real(self):
		graph = _graph({"email": "ada@example.com"}, [{"id": "look", "type": "tool.call", "config": {"tool_id": "gsheets_read", "input": {"spreadsheet_id": "abc"}}, "next": "end"}])
		self._flow(graph)
		with patch.object(flow_engine, "execute_tool", return_value={"success": True, "result": {"values": [[1]]}}) as tool:
			out = api.test_step(self.flow_id, "look")
		tool.assert_called_once()
		self.assertEqual((out["status"], out["mode"], out["effect"]), ("success", "real", "reads"))
		self.assertEqual(out["output"], {"values": [[1]]})

	def test_a_failing_step_gives_a_readable_error_and_a_fix_hint(self):
		graph = _graph({"x": 1}, [{"id": "bad", "type": "transform", "config": {"op": "pick", "input": {}}, "next": "end"}])
		graph["nodes"].append({"id": "nolist", "type": "foreach", "config": {"items": {"$from": "input.x"}, "body": [], "max_iterations": 3, "on_item_error": "fail"}, "next": "end"})
		self._flow(graph)
		out = api.test_step(self.flow_id, "nolist")
		self.assertEqual(out["status"], "failed")
		self.assertTrue(out["error"] and "Traceback" not in out["error"])
		self.assertTrue(out["fix_hint"])

	def test_state_writes_are_skipped(self):
		graph = _graph({"x": 1}, [{"id": "save", "type": "state.set", "config": {"key": "k1", "value": 1}, "next": "end"}])
		self._flow(graph)
		with patch("huf.ai.flow.state.set_state") as setter:
			out = api.test_step(self.flow_id, "save")
		setter.assert_not_called()
		self.assertEqual((out["mode"], out["effect"]), ("simulated", "changes"))
		self.assertEqual(out["summary"], 'Would save data for later as "k1"')

	def test_a_code_step_is_not_run_here(self):
		graph = _graph({"x": 1}, [{"id": "code", "type": "code.run", "config": {"code": "result = 1", "profile": "Flow Scratch"}, "next": "end"}])
		self._flow(graph)
		out = api.test_step(self.flow_id, "code")
		self.assertEqual((out["status"], out["mode"]), ("success", "simulated"))

	def test_an_approval_shows_the_card_and_never_pauses(self):
		graph = _graph(
			{"customer": "Ada", "amount": 450},
			[{"id": "ask", "type": "human.approval", "config": {"message": "Please check", "title": "Refund for {input.customer}", "approver_type": "role", "approver_role": "System Manager", "details": [{"label": "Amount", "value": {"$from": "input.amount"}}]}, "next": "end"}],
		)
		self._flow(graph)
		out = api.test_step(self.flow_id, "ask")
		self.assertEqual((out["status"], out["mode"]), ("success", "preview"))
		self.assertEqual(out["preview"]["title"], "Refund for Ada")
		self.assertEqual(out["preview"]["facts"], [{"label": "Amount", "value": "450"}])
		self.assertEqual(out["preview"]["who_can_decide"], "Anyone with the role System Manager")

	def test_no_flow_run_is_created(self):
		before = self._runs()
		api.test_step(self.flow_id, "cond")
		api.test_step(self.flow_id, "mail")
		self.assertEqual(self._runs(), before)

	def test_a_flow_that_is_not_ours_to_edit_is_refused(self):
		viewer = make_user(roles=["Huf Viewer"])
		self._docs.append(("User", viewer.name))
		frappe.set_user(viewer.name)
		with self.assertRaises(frappe.PermissionError):
			api.test_step(self.flow_id, "cond")
		with self.assertRaises(frappe.PermissionError):
			api.get_step_test_info(self.flow_id, "cond")


class TestSampleInput(Base):
	def test_pinned_beats_last_run_and_says_where_it_came_from(self):
		graph = _graph({"email": "pinned@example.com", "total": 1})
		graph["nodes"][1]["_sample"] = {"email": "pinned-step@example.com"}
		graph["nodes"][2]["config"]["expression"] = "input['total'] > 1 and fetch['email'] != ''"
		self._flow(graph)
		self._run(payload={"email": "run@example.com", "total": 9}, outputs={"fetch": {"email": "run-step@example.com"}})
		info = api.get_step_test_info(self.flow_id, "cond")
		parts = {p["key"]: p for p in info["parts"]}
		self.assertEqual(parts["input"]["source"], "trigger_sample")
		self.assertEqual(parts["fetch"]["source"], "pinned")
		self.assertEqual(parts["fetch"]["value"], {"email": "pinned-step@example.com"})

	def test_last_run_is_used_when_nothing_is_pinned(self):
		self._flow(_graph())
		self._run(payload={"email": "run@example.com", "total": 9, "password": "hunter2"})
		parts = {p["key"]: p for p in api.get_step_test_info(self.flow_id, "cond")["parts"]}
		self.assertEqual(parts["input"]["source"], "last_run")
		self.assertEqual(parts["input"]["value"]["email"], "run@example.com")
		self.assertEqual(parts["input"]["value"]["password"], MASK)

	def test_no_data_at_all_is_said_plainly(self):
		self._flow(_graph())
		parts = api.get_step_test_info(self.flow_id, "cond")["parts"]
		self.assertEqual([(p["key"], p["source"], p["value"]) for p in parts], [("input", "none", None)])

	def test_only_the_steps_this_step_reads_are_listed(self):
		self._flow(_graph({"total": 1}))
		self.assertEqual([p["key"] for p in api.get_step_test_info(self.flow_id, "cond")["parts"]], ["input"])

	def test_setting_names_are_not_data(self):
		graph = _graph({"total": 1}, [{"id": "look", "type": "tool.call", "config": {"tool_id": "list_agents", "input": {}}, "next": "end"}])
		self._flow(graph)
		self.assertEqual(api.get_step_test_info(self.flow_id, "look")["parts"], [])

	def test_a_result_warns_when_the_sample_was_empty(self):
		self._flow(_graph())
		out = api.test_step(self.flow_id, "cond")
		self.assertEqual(len(out["warnings"]), 1)
		self.assertIn("no sample", out["warnings"][0])
		self.assertEqual(api.test_step(self.flow_id, "cond", {"input": {"total": 1}})["warnings"], [])

	def test_info_says_how_the_step_behaves(self):
		self._flow(_graph({"total": 1}))
		mail = api.get_step_test_info(self.flow_id, "mail")
		self.assertEqual((mail["effect"], mail["simulated"], mail["calls_ai"]), ("sends", True, False))
		self.assertFalse(api.get_step_test_info(self.flow_id, "cond")["simulated"])


class TestAgentAndLimits(Base):
	def test_an_agent_step_is_marked_as_calling_the_model_and_its_tools_are_gated(self):
		graph = _graph({"x": 1}, [{"id": "ai", "type": "agent.run", "config": {"agent": "Nobody", "prompt": "Say hi"}, "next": "end"}])
		self._flow(graph)
		self.assertTrue(api.get_step_test_info(self.flow_id, "ai")["calls_ai"])
		with st.gate.step_test_scope():
			self.assertTrue(st.gate.agent_run_is_test(None))
			self.assertIn("Would send email", st.gate.agent_tool_gate("gmail_send_email", {"to": BOGUS}, {"agent_run_id": None}))
			self.assertIsNone(st.gate.agent_tool_gate("gsheets_read", {}, {"agent_run_id": None}))
		self.assertFalse(st.gate.agent_run_is_test(None))

	def test_an_agent_step_runs_through_the_real_executor(self):
		graph = _graph({"x": 1}, [{"id": "ai", "type": "agent.run", "config": {"agent": "Some Agent", "prompt": "Say hi"}, "next": "end"}])
		self._flow(graph)
		fake = {"success": True, "response": "Hi there", "agent_run_id": None}
		with patch("huf.ai.agent.integration.run_agent_sync", return_value=fake) as run:
			out = api.test_step(self.flow_id, "ai")
		run.assert_called_once()
		self.assertEqual((out["status"], out["output"], out["calls_ai"]), ("success", "Hi there", True))
		self.assertIsNone(run.call_args.kwargs.get("flow_run_id"))

	def test_the_twenty_first_test_in_a_minute_is_refused(self):
		self._flow(_graph({"total": 1}))
		with patch("frappe.cache") as cache:
			cache.return_value.incr.side_effect = list(range(1, 30))
			for _ in range(20):
				api.test_step(self.flow_id, "cond")
			with self.assertRaises(frappe.ValidationError):
				api.test_step(self.flow_id, "cond")

	def test_a_bad_sample_is_a_plain_failure(self):
		self._flow(_graph({"total": 1}))
		out = api.test_step(self.flow_id, "cond", {"input": [1, 2]})
		self.assertEqual(out["status"], "failed")
		self.assertIn("object", out["error"])


class TestRedaction(IntegrationTestCase):
	def test_secrets_are_hidden_in_keys_and_values(self):
		out, _ = redact_output({"ok": 1, "api_key": "abc", "nested": {"Authorization": "Bearer abcdefghijklmnop12345"}, "note": "use sk-abcdefghijklmnopqrstuvwx now"})
		self.assertEqual(out["api_key"], MASK)
		self.assertEqual(out["nested"]["Authorization"], MASK)
		self.assertNotIn("sk-abc", out["note"])
		self.assertEqual(out["ok"], 1)

	def test_output_is_capped_at_64kb(self):
		huge = {f"k{i}": "z" * 3000 for i in range(80)}
		out, shortened = redact_output(huge)
		self.assertTrue(shortened)
		self.assertLessEqual(len(json.dumps(out).encode()), 64 * 1024)

	def test_a_pin_is_at_most_8kb_and_keeps_text_and_lists(self):
		self.assertLessEqual(len(json.dumps(pin_value({f"f{i}": "y" * 190 for i in range(300)})).encode()), MAX_SAMPLE_BYTES)
		self.assertEqual(pin_value("Hello"), "Hello")
		self.assertEqual(pin_value([{"a": 1}]), [{"a": 1}])
		self.assertEqual(pin_value({"password": "x"}), {"password": MASK})

	def test_the_server_trims_an_oversized_or_secret_sample_on_save(self):
		graph = {"nodes": [{"id": "a", "_sample": {"token": "t", "big": "x" * 5000}}, {"id": "b"}]}
		self.assertTrue(cap_node_samples(graph))
		self.assertEqual(graph["nodes"][0]["_sample"]["token"], MASK)
		self.assertFalse(cap_node_samples(graph))

	def test_a_sample_must_be_an_object_of_known_parts(self):
		with self.assertRaises(ValueError):
			clean_sample_input({"surprise": 1})
		with self.assertRaises(ValueError):
			clean_sample_input("[1]")
		self.assertEqual(clean_sample_input('{"input": {"a": 1}}'), {"input": {"a": 1}, "steps": {}})


class TestTriggers(Base):
	def test_a_schedule_tick_is_simulated(self):
		graph = _graph()
		graph["nodes"][0] = {"id": "t", "type": "trigger.schedule", "config": {"cron": "0 9 * * *"}, "next": "fetch"}
		self._flow(graph)
		out = api.test_step(self.flow_id, "t")
		self.assertEqual((out["status"], out["mode"]), ("success", "simulated"))
		self.assertEqual(out["output"]["cron"], "0 9 * * *")

	def test_a_webhook_without_any_request_says_so(self):
		self._flow(_graph())
		out = api.test_step(self.flow_id, "t")
		self.assertEqual(out["status"], "failed")
		self.assertIn("No request", out["error"])

	def test_a_webhook_uses_the_last_request(self):
		self._flow(_graph())
		self._run(payload={"email": "a@b.co", "token": "x"})
		out = api.test_step(self.flow_id, "t")
		self.assertEqual(out["status"], "success")
		self.assertEqual(out["output"], {"email": "a@b.co", "token": MASK})

	def test_a_data_trigger_lists_five_recent_readable_documents_and_builds_a_sample(self):
		graph = _graph()
		graph["nodes"][0] = {"id": "t", "type": "trigger.doc-event", "config": {"doctype": "ToDo", "event": "after_insert"}, "next": "fetch"}
		self._flow(graph)
		for i in range(7):
			doc = frappe.get_doc({"doctype": "ToDo", "description": f"_ux16 {i}"}).insert(ignore_permissions=True)
			self._docs.append(("ToDo", doc.name))
		docs = api.list_recent_documents(self.flow_id, "t")["documents"]
		self.assertEqual(len(docs), 5)
		sample = api.get_document_sample(self.flow_id, "t", docs[0]["name"])["sample"]
		self.assertTrue(sample["description"].startswith("_ux16"))
		self.assertNotIn("_trigger", sample)
		self.assertEqual(api.test_step(self.flow_id, "t")["status"], "success")

	def test_a_viewer_gets_no_documents(self):
		graph = _graph()
		graph["nodes"][0] = {"id": "t", "type": "trigger.doc-event", "config": {"doctype": "ToDo", "event": "after_insert"}, "next": "fetch"}
		self._flow(graph)
		viewer = make_user(roles=["Huf Viewer"])
		self._docs.append(("User", viewer.name))
		frappe.set_user(viewer.name)
		with self.assertRaises(frappe.PermissionError):
			api.list_recent_documents(self.flow_id, "t")
