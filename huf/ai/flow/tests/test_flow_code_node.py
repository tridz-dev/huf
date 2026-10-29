# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WP19 on a real bench: Execute code in Flows (``code.run``).

Covers the two switches, who may add / publish / run a code step, the trust rule (code and profile
come from the published definition; ``inputs`` are data), the sandbox limits, scratch-folder cleanup,
the approval park / resume, the single audit row and the child environment.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_code_node
"""

import asyncio
import json
import os
import time
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import api as flow_api
from huf.ai.flow import code_node
from huf.ai.flow import engine as flow_engine
from huf.ai.tools import code_execution

LIMITS = {
	"max_nodes": 20,
	"max_rows": 1000,
	"max_output_bytes": 100_000,
	"max_parallel_calls": 1,
	"max_foreach_iterations": 1,
	"max_external_calls": 5,
	"max_writes": 5,
	"max_wall_time_ms": 5000,
	"fail_closed": True,
}
SECRET = "test-webhook-secret-0123456789abcdef"
WEBHOOK = {"type": "trigger.webhook", "config": {"method": "POST", "secret": SECRET}}


def _contract():
	return {
		"input_schema": {"type": "object"},
		"output_schema": {"type": "object"},
		"applies_when": [],
		"permission_envelope": {"read": [], "write": [], "http": "none", "code": "none"},
		"limits": LIMITS,
	}


def _code_graph(code, profile="Flow Scratch", inputs=None, timeout_s=None, on_error=None):
	config = {"code": code, "profile": profile, "inputs": inputs or {}}
	if timeout_s:
		config["timeout_s"] = timeout_s
	node = {"id": "code", "type": "code.run", "config": config, "next": "done"}
	if on_error:
		node["on_error"] = on_error
	nodes = [
		{"id": "start", "next": "code", **WEBHOOK},
		node,
		{"id": "done", "type": "output", "config": {"value": {"$from": "code"}}},
	]
	if on_error:
		nodes.append({"id": on_error, "type": "output", "config": {"value": "recovered"}})
	return {
		"schema_version": "1.0.0",
		"profile": "flow",
		"fingerprint": "0" * 64,
		"entry": "start",
		"nodes": nodes,
		"contract": _contract(),
	}


class CodeFlowBase(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._flows = []
		self._users = []
		self._roles = []
		self._conf_before = frappe.conf.get("huf_python_execution_enabled")
		self._setting_before = frappe.db.get_single_value("Agent Settings", "allow_code_in_flows")
		self._self_approval_before = frappe.db.get_single_value("Agent Settings", "allow_self_approval")
		frappe.conf.huf_python_execution_enabled = 1
		frappe.db.set_single_value("Agent Settings", "allow_code_in_flows", 1)
		frappe.db.set_single_value("Agent Settings", "allow_self_approval", 0)
		code_execution_profiles()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.commit()
		frappe.conf.huf_python_execution_enabled = self._conf_before
		frappe.db.set_single_value("Agent Settings", "allow_code_in_flows", self._setting_before or 0)
		frappe.db.set_single_value("Agent Settings", "allow_self_approval", self._self_approval_before or 0)
		for flow_id in self._flows:
			for run in frappe.get_all("Flow Run", filters={"flow_id": flow_id}, pluck="name"):
				for agent_run in frappe.get_all("Agent Run", filters={"flow_run": run}, pluck="name"):
					for call in frappe.get_all("Agent Tool Call", filters={"agent_run": agent_run}, pluck="name"):
						frappe.db.delete("Agent Execution Approval", {"agent_tool_call": call})
					frappe.db.delete("Agent Tool Call", {"agent_run": agent_run})
				frappe.db.delete("Agent Run", {"flow_run": run})
			frappe.db.delete("Flow Run", {"flow_id": flow_id})
			if frappe.db.exists("Flow Definition", flow_id):
				frappe.delete_doc("Flow Definition", flow_id, ignore_permissions=True, force=True)
		for email in self._users:
			frappe.db.delete("Huf User Role", {"user": email})
			if frappe.db.exists("User", email):
				frappe.delete_doc("User", email, ignore_permissions=True, force=True)
		for role in self._roles:
			if frappe.db.exists("Huf Role", role):
				frappe.delete_doc("Huf Role", role, ignore_permissions=True, force=True)
		frappe.db.commit()

	# -- helpers ----------------------------------------------------------------------------

	def _save(self, graph, active=True, user="Administrator"):
		flow_id = f"_test-wp19-{frappe.generate_hash(length=8)}"
		frappe.set_user(user)
		try:
			flow_api.save_flow_definition(flow_id, graph)
			self._flows.append(flow_id)
			if active:
				doc = frappe.get_doc("Flow Definition", flow_id)
				doc.status = "Active"
				doc.save(ignore_permissions=True)
		finally:
			frappe.set_user("Administrator")
		return flow_id

	def _run(self, flow_id, payload=None):
		run = flow_engine.create_flow_run(flow_id, payload or {}, "Manual")
		flow_engine.run_flow(run.name)
		return frappe.get_doc("Flow Run", run.name)

	def _outputs(self, run):
		ctx = json.loads(run.context_json or "{}")
		return ctx.get("__node_outputs__", {})

	def _calls(self, run):
		runs = frappe.get_all("Agent Run", filters={"flow_run": run.name}, pluck="name")
		return frappe.get_all(
			"Agent Tool Call", filters={"agent_run": ["in", runs]}, fields=["name", "status", "exit_status", "code_ref"]
		) if runs else []

	def _user(self, capabilities, frappe_role="Huf Manager"):
		email = f"wp19-{frappe.generate_hash(length=6)}@example.com"
		role_name = f"_wp19 role {frappe.generate_hash(length=5)}"
		frappe.get_doc(
			{"doctype": "Huf Role", "role_name": role_name, "permissions": [{"capability": c} for c in capabilities]}
		).insert(ignore_permissions=True)
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Wp19",
				"send_welcome_email": 0,
				"roles": [{"role": frappe_role}],
			}
		)
		user.flags.ignore_permissions = True
		user.insert()
		frappe.db.delete("Huf User Role", {"user": email})
		frappe.get_doc({"doctype": "Huf User Role", "user": email, "huf_role": role_name, "enabled": 1}).insert(
			ignore_permissions=True
		)
		frappe.cache().delete_value(f"huf_user_capabilities::{email}")
		self._users.append(email)
		self._roles.append(role_name)
		return email, role_name

	def _scratch_entries(self):
		base = os.path.join(code_execution.get_files_path(is_private=True), code_execution.SCRATCH_SUBDIR)
		return os.listdir(base) if os.path.isdir(base) else []


def code_execution_profiles():
	from huf.install import create_default_execution_profiles

	create_default_execution_profiles()


CAPS_EDITOR = ["flows.use", "flows.create", "flows.manage", "flows.publish_sensitive", "code_execution.run"]


class TestSwitchesAndPublishing(CodeFlowBase):
	def test_flow_scratch_profile_is_seeded(self):
		profile = frappe.get_doc("Execution Profile", "Flow Scratch")
		self.assertEqual(
			(profile.approval_mode, profile.filesystem_policy, profile.network_policy, profile.max_wall_time_s),
			("Auto Approve", "Scratch Only", None, 30),
		)
		self.assertEqual((profile.max_cpu_seconds, profile.max_memory_mb, profile.max_output_bytes), (30, 256, 262144))

	def test_setting_is_admin_only_and_off_by_default(self):
		field = frappe.get_meta("Agent Settings").get_field("allow_code_in_flows")
		self.assertEqual((field.permlevel, str(field.default)), (1, "0"))

	def test_both_switches_must_be_on_to_publish(self):
		graph = _code_graph("print(1)")
		flow_id = self._save(graph, active=False)
		for conf, setting, text in ((0, 1, "turned off on this server"), (1, 0, "Code in Flows is turned off")):
			frappe.conf.huf_python_execution_enabled = conf
			frappe.db.set_single_value("Agent Settings", "allow_code_in_flows", setting)
			with self.assertRaises(frappe.ValidationError) as ctx:
				flow_api.publish_flow(flow_id)
			self.assertIn(text, str(ctx.exception))
		frappe.conf.huf_python_execution_enabled = 1
		frappe.db.set_single_value("Agent Settings", "allow_code_in_flows", 1)
		self.assertEqual(flow_api.publish_flow(flow_id)["status"], "Active")

	def test_publisher_without_execute_code_is_denied(self):
		email, _role = self._user(CAPS_EDITOR)  # everything but flows.execute_code
		flow_id = self._save(_code_graph("print(1)"), active=False)
		frappe.set_user(email)
		try:
			with self.assertRaises(frappe.PermissionError) as ctx:
				flow_api.publish_flow(flow_id)
		finally:
			frappe.set_user("Administrator")
		self.assertIn("Execute code step", str(ctx.exception))
		self.assertEqual(frappe.db.get_value("Flow Definition", flow_id, "status"), "Draft")

	def test_user_without_execute_code_cannot_add_or_change_code_even_in_a_draft(self):
		email, _role = self._user(CAPS_EDITOR)
		with self.assertRaises(frappe.PermissionError):
			self._save(_code_graph("print(1)"), active=False, user=email)
		flow_id = self._save(_code_graph("print(1)"), active=False)
		frappe.set_user(email)
		try:
			with self.assertRaises(frappe.PermissionError):
				flow_api.save_flow_definition(flow_id, _code_graph("print(2)"))
			# an unrelated edit (the end value is not part of the step) is fine
			same = _code_graph("print(1)")
			same["nodes"][2]["config"]["value"] = "x"
			flow_api.save_flow_definition(flow_id, same)
		finally:
			frappe.set_user("Administrator")

	def test_user_with_execute_code_can_publish(self):
		email, _role = self._user(CAPS_EDITOR + ["flows.execute_code"])
		flow_id = self._save(_code_graph("print(1)"), active=False, user=email)
		frappe.set_user(email)
		try:
			self.assertEqual(flow_api.publish_flow(flow_id)["status"], "Active")
		finally:
			frappe.set_user("Administrator")

	def test_default_roles(self):
		from huf.permissions import DEFAULT_ROLE_CAPABILITIES, has_capability

		self.assertIn("flows.execute_code", DEFAULT_ROLE_CAPABILITIES["Huf Admin"])
		for role in ("Huf Manager", "Huf User", "Huf Viewer", "Huf Gateway User"):
			self.assertNotIn("flows.execute_code", DEFAULT_ROLE_CAPABILITIES[role])
		self.assertTrue(has_capability("Administrator", "flows.execute_code"))

	def test_unusable_profiles_and_bad_settings_block_publishing(self):
		for graph, text in (
			(_code_graph("print(1)", profile="Blocked"), "never allows code"),
			(_code_graph("print(1)", profile="No Such Profile"), "no longer exists"),
			(_code_graph("   "), "add the Python code"),
			(_code_graph("print(1)", timeout_s=999), "time limit is longer"),
			(_code_graph("x = 1\n" * 20000), "longer than 64 KB"),
		):
			flow_id = self._save(graph, active=False)
			with self.assertRaises(frappe.ValidationError) as ctx:
				flow_api.publish_flow(flow_id)
			self.assertIn(text, str(ctx.exception), text)

	def test_changed_code_needs_a_publisher_but_unchanged_does_not(self):
		a = code_node.fingerprint(_code_graph("print(1)")["nodes"][1])
		same_inputs_changed = _code_graph("print(1)", inputs={"x": 1})["nodes"][1]
		self.assertEqual(a, code_node.fingerprint(same_inputs_changed))  # inputs are data, not authority
		self.assertNotEqual(a, code_node.fingerprint(_code_graph("print(2)")["nodes"][1]))
		self.assertNotEqual(a, code_node.fingerprint(_code_graph("print(1)", profile="Trusted")["nodes"][1]))
		email, _ = self._user(CAPS_EDITOR)
		flow_id = self._save(_code_graph("print(1)"))  # Active, published by Administrator
		frappe.set_user(email)
		try:
			with self.assertRaises(frappe.PermissionError):
				flow_api.save_flow_definition(flow_id, _code_graph("print(99)"))
		finally:
			frappe.set_user("Administrator")

	def test_status_api(self):
		status = code_node.get_code_flow_status()
		self.assertTrue(status["enabled"] and status["available"] and status["can_manage"])
		self.assertEqual(status["default_profile"], "Flow Scratch")
		by_name = {p["name"]: p for p in status["profiles"]}
		self.assertTrue(by_name["Flow Scratch"]["usable"])
		self.assertFalse(by_name["Blocked"]["usable"])
		frappe.db.set_single_value("Agent Settings", "allow_code_in_flows", 0)
		off = code_node.get_code_flow_status()
		self.assertEqual((off["allowed"], off["server_switch"], off["enabled"], off["available"]), (False, True, False, False))


class TestRunning(CodeFlowBase):
	def test_runs_prints_and_returns_a_value_from_an_input(self):
		graph = _code_graph(
			"print('total', inputs['a'] + inputs['b'])\nresult = {'sum': inputs['a'] + inputs['b']}",
			inputs={"a": {"$from": "input.a"}, "b": 2},
		)
		run = self._run(self._save(graph), {"a": 40})
		self.assertEqual(run.status, "Success", run.last_error)
		out = self._outputs(run)["code"]
		self.assertEqual(
			out, {"stdout": "total 42\n", "result": {"sum": 42}, "exit_status": "Ok", "truncated": False}
		)
		self.assertEqual(len(self._calls(run)), 1)  # exactly one audit row
		self.assertEqual(code_node.runs_so_far(run.name), 1)
		self.assertNotIn("_code_run_count", json.loads(run.context_json))
		self.assertEqual(self._scratch_entries().count(code_execution._conversation_dir_key(run.name)), 0)

	def test_audit_row_has_profile_snapshot_and_code_hash_not_code(self):
		run = self._run(self._save(_code_graph("print('secret-code-marker')")))
		call = frappe.get_doc("Agent Tool Call", self._calls(run)[0].name)
		self.assertEqual(call.execution_profile, "Flow Scratch")
		self.assertEqual(call.code_ref, code_execution._sha256("print('secret-code-marker')"))
		snapshot = call.execution_profile_snapshot
		snapshot = json.loads(snapshot) if isinstance(snapshot, str) else snapshot
		self.assertEqual(snapshot["approval_mode"], "Auto Approve")
		self.assertNotIn("secret-code-marker", call.tool_args or "")
		agent_run = frappe.get_doc("Agent Run", call.agent_run)
		self.assertEqual((agent_run.flow_run, agent_run.flow_node_id), (run.name, "code"))

	def test_scratch_file_write_and_read_back(self):
		code = "f = open('note.txt', 'w')\nf.write('hello scratch')\nf.close()\nr = open('note.txt')\nresult = r.read()\nr.close()"
		run = self._run(self._save(_code_graph(code)))
		self.assertEqual(self._outputs(run)["code"]["result"], "hello scratch")
		self.assertEqual(self._scratch_entries().count(code_execution._conversation_dir_key(run.name)), 0)

	def test_path_outside_scratch_is_denied_readably(self):
		run = self._run(self._save(_code_graph("result = open('/etc/passwd').read()")))
		self.assertEqual(run.status, "Failed")
		self.assertIn("outside the sandbox workspace", run.last_error)
		self.assertNotIn("Traceback", run.last_error)
		self.assertEqual(self._scratch_entries().count(code_execution._conversation_dir_key(run.name)), 0)

	def test_failure_is_readable_and_on_error_routes(self):
		run = self._run(self._save(_code_graph("x = 1\ny = x / 0", on_error="recover")))
		self.assertEqual(run.status, "Success", run.last_error)
		out = self._outputs(run)
		self.assertIn("ZeroDivisionError", out["code"]["error"])
		self.assertIn("line 2", out["code"]["error"])
		self.assertEqual(out["recover"], "recovered")

	def test_network_is_denied(self):
		for code in ("import socket", "result = http.request(url='https://example.com')"):
			run = self._run(self._save(_code_graph(code)))
			self.assertEqual(run.status, "Failed", code)
		run = self._run(self._save(_code_graph("import socket")))
		self.assertIn("not permitted", run.last_error)

	def test_infinite_loop_is_killed_with_a_timeout_message(self):
		start = time.monotonic()
		run = self._run(self._save(_code_graph("while True:\n\tpass", timeout_s=2)))
		self.assertLess(time.monotonic() - start, 20)
		self.assertEqual(run.status, "Failed")
		self.assertIn("ran longer than 2 seconds", run.last_error)
		self.assertEqual(self._calls(run)[0].exit_status, "Timeout")
		self.assertEqual(self._scratch_entries().count(code_execution._conversation_dir_key(run.name)), 0)

	def test_memory_limit(self):
		run = self._run(self._save(_code_graph("x = 'a' * (1024 * 1024 * 600)\nresult = len(x)")))
		self.assertEqual(run.status, "Failed")
		self.assertIn("more memory", run.last_error)

	def test_output_over_the_cap_is_truncated(self):
		run = self._run(self._save(_code_graph("for i in range(60000):\n\tprint('0123456789abcdef')")))
		self.assertEqual(run.status, "Success", run.last_error)
		out = self._outputs(run)["code"]
		self.assertTrue(out["truncated"])
		self.assertLessEqual(len(out["stdout"].encode()), 262144)

	def test_inputs_cannot_change_code_or_profile(self):
		graph = _code_graph(
			"print(inputs['code'])\nresult = [inputs['profile'], inputs['code']]",
			inputs={"code": {"$from": "input.code"}, "profile": {"$from": "input.profile"}},
		)
		run = self._run(self._save(graph), {"code": "print('EVIL RAN')", "profile": "Trusted"})
		out = self._outputs(run)["code"]
		self.assertEqual(out["stdout"], "print('EVIL RAN')\n")  # printed as text, never executed
		self.assertEqual(self._calls(run)[0].code_ref, code_execution._sha256(graph["nodes"][1]["config"]["code"]))
		call = frappe.get_doc("Agent Tool Call", self._calls(run)[0].name)
		self.assertEqual(call.execution_profile, "Flow Scratch")

	def test_a_draft_flow_cannot_start_a_code_run(self):
		flow_id = self._save(_code_graph("print(1)"), active=False)
		with self.assertRaises(frappe.ValidationError) as ctx:
			flow_engine.create_flow_run(flow_id, {}, "Manual")
		self.assertIn("Publish this flow", str(ctx.exception))

	def test_switches_off_at_run_time_fail_closed(self):
		flow_id = self._save(_code_graph("print(1)"))
		for conf, setting, text in ((0, 1, "turned off on this server"), (1, 0, "Code in Flows is turned off")):
			frappe.conf.huf_python_execution_enabled = conf
			frappe.db.set_single_value("Agent Settings", "allow_code_in_flows", setting)
			run = self._run(flow_id)
			self.assertEqual(run.status, "Failed")
			self.assertIn(text, run.last_error)
			self.assertEqual(self._calls(run), [])

	def test_owner_who_lost_the_capability_fails_at_run_time(self):
		email, role = self._user(CAPS_EDITOR + ["flows.execute_code"])
		flow_id = self._save(_code_graph("print(1)"), user=email)
		self.assertEqual(frappe.db.get_value("Flow Definition", flow_id, "owner"), email)
		self.assertEqual(self._run(flow_id).status, "Success")
		frappe.db.delete("Huf Role Permission", {"parent": role, "capability": "flows.execute_code"})
		frappe.cache().delete_value(f"huf_user_capabilities::{email}")
		run = self._run(flow_id)
		self.assertEqual(run.status, "Failed")
		self.assertIn("no longer allowed to run code", run.last_error)
		self.assertEqual(self._calls(run), [])

	def test_per_run_cap(self):
		flow_id = self._save(_code_graph("print(1)"))
		with patch.object(code_node, "runs_so_far", return_value=code_node.MAX_CODE_RUNS_PER_FLOW_RUN):
			run = self._run(flow_id)
		self.assertEqual(run.status, "Failed")
		self.assertIn("most one run may start", run.last_error)

	def test_tool_call_naming_run_python_is_still_refused(self):
		from huf.ai.tools.invocation import invoke_tool

		result = asyncio.run(invoke_tool("run_python", {"code": "print(1)"}))
		self.assertFalse(result.success)
		self.assertTrue(result.denied)

	def test_code_step_in_a_loop_body_is_refused(self):
		out = flow_engine._run_sub_chain(
			frappe._dict(name="x"),
			flow_engine.FlowRunContext(
				{}, version=flow_engine.PinnedVersion.pin({"nodes": [{"id": "c", "type": "code.run", "config": {}}]})
			),
			["c"],
		)
		self.assertEqual(out["status"], "failed")
		self.assertIn("inside a loop", out["error"])


class TestApproval(CodeFlowBase):
	def _approver(self):
		email, _ = self._user([], frappe_role="System Manager")
		return email

	def _parked(self, code="print('approved run')\nresult = 7"):
		flow_id = self._save(_code_graph(code, profile="Restricted"))
		run = self._run(flow_id)
		self.assertEqual(run.status, "Waiting Code", run.last_error)
		waiting = json.loads(run.waiting)
		self.assertEqual((waiting["type"], waiting["node_id"]), ("code", "code"))
		self.assertTrue(waiting["approval"])
		return flow_id, run, waiting

	def test_parks_then_continues_on_approve(self):
		from huf.huf.doctype.agent_execution_approval.agent_execution_approval import approve_execution

		_flow_id, run, waiting = self._parked()
		self.assertEqual(frappe.db.get_value("Agent Execution Approval", waiting["approval"], "status"), "Pending")
		self.assertEqual(self._calls(run)[0].status, "Queued")
		frappe.set_user(self._approver())
		try:
			approve_execution(waiting["approval"])
		finally:
			frappe.set_user("Administrator")
		run.reload()
		self.assertEqual(run.status, "Success", run.last_error)
		self.assertEqual(self._outputs(run)["code"]["result"], 7)
		self.assertEqual(len(self._calls(run)), 1)

	def test_requester_cannot_approve_their_own_code(self):
		from huf.huf.doctype.agent_execution_approval.agent_execution_approval import approve_execution

		_flow_id, run, waiting = self._parked()
		with self.assertRaises(frappe.PermissionError):
			approve_execution(waiting["approval"])
		self.assertEqual(frappe.db.get_value("Flow Run", run.name, "status"), "Waiting Code")

	def test_reject_fails_the_step_with_a_readable_reason(self):
		from huf.huf.doctype.agent_execution_approval.agent_execution_approval import reject_execution

		_flow_id, run, waiting = self._parked()
		frappe.set_user(self._approver())
		try:
			reject_execution(waiting["approval"], "not now")
		finally:
			frappe.set_user("Administrator")
		run.reload()
		self.assertEqual(run.status, "Failed")
		self.assertIn("rejected", run.last_error)
		self.assertEqual(len(self._calls(run)), 1)
		self.assertEqual(self._calls(run)[0].status, "Failed")

	def test_expiry_fails_the_step(self):
		_flow_id, run, waiting = self._parked()
		frappe.db.set_value("Agent Execution Approval", waiting["approval"], "expires_on", "2020-01-01 00:00:00")
		frappe.db.set_value(
			"Flow Run", run.name, "waiting", json.dumps({**waiting, "timeout_at": "2020-01-01T00:00:00"})
		)
		self.assertIn(run.name, code_node.sweep_code_waits())
		run.reload()
		self.assertEqual(run.status, "Failed")
		self.assertIn("expired", run.last_error)

	def test_sweeper_gives_up_on_a_step_nobody_picked_up(self):
		flow_id = self._save(_code_graph("print(1)"))
		with patch.object(code_execution, "enqueue_execution"):  # the job never runs (no worker)
			run = self._run(flow_id)
		self.assertEqual(run.status, "Waiting Code")
		waiting = json.loads(run.waiting)
		frappe.db.set_value(
			"Flow Run", run.name, "waiting", json.dumps({**waiting, "timeout_at": "2020-01-01T00:00:00"})
		)
		code_node.sweep_code_waits()
		run.reload()
		self.assertEqual(run.status, "Failed")
		self.assertIn("did not start in time", run.last_error)


class TestChildProcess(IntegrationTestCase):
	def test_child_environment_has_no_credentials(self):
		from huf.ai.tools.execution_sandbox import _sanitize_child_env

		leaky = {
			"FRAPPE_DB_PASSWORD": "x",
			"DB_PASSWORD": "x",
			"MYSQL_PWD": "x",
			"REDIS_CACHE": "redis://:pw@host:6379",
			"REDIS_QUEUE": "redis://host:6379",
			"SITE_CONFIG": "{}",
			"AWS_SECRET_ACCESS_KEY": "x",
			"OPENAI_API_KEY": "x",
			"GITHUB_PERSONAL_ACCESS_TOKEN": "x",
			"ENCRYPTION_KEY": "x",
			"PATH": "/usr/bin",
			"LANG": "C.UTF-8",
		}
		with patch.dict(os.environ, leaky):
			env = _sanitize_child_env("/tmp/home-x")
		for name in leaky:
			if name not in ("PATH", "LANG"):
				self.assertNotIn(name, env)
		self.assertEqual((env["PATH"], env["LANG"], env["HOME"]), ("/usr/bin", "C.UTF-8", "/tmp/home-x"))

	def test_error_text_is_plain(self):
		self.assertIn("ran longer than 30 seconds", code_node.error_text("Timeout", "", {"max_wall_time_s": 30}))
		self.assertIn("256 MB", code_node.error_text("OOM", "", {"max_memory_mb": 256}))
		trace = 'Traceback (most recent call last):\n  File "<huf-exec>", line 3, in <module>\nKeyError: \'a\''
		self.assertEqual(
			code_node.error_text("Error", trace), "The code stopped with an error on line 3: KeyError: 'a'"
		)

	def test_purge_removes_old_scratch_folders_only(self):
		base = os.path.join(code_execution.get_files_path(is_private=True), code_execution.SCRATCH_SUBDIR)
		old, new = os.path.join(base, "wp19-old"), os.path.join(base, "wp19-new")
		os.makedirs(old, exist_ok=True)
		os.makedirs(new, exist_ok=True)
		try:
			ancient = time.time() - 3 * 24 * 3600
			os.utime(old, (ancient, ancient))
			removed = code_node.purge_scratch()
			self.assertIn("wp19-old", removed)
			self.assertFalse(os.path.exists(old))
			self.assertTrue(os.path.exists(new))
		finally:
			for path in (old, new):
				if os.path.exists(path):
					os.rmdir(path)
