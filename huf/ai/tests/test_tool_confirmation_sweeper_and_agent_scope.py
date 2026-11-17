"""FIX-B tests. Run: bench run-tests --module huf.ai.tests.test_tool_confirmation_sweeper_and_agent_scope"""

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime

from huf.ai import tool_confirmation as tc
from huf.ai.gateways import tool_policy
from huf.ai.tools.invocation import ToolResult, invoke_tool_sync

ARGS = {"recipients": ["+911"], "template": "promo", "message": "Hi", "channel": "whatsapp"}


class SweeperScopeCase(IntegrationTestCase):
	"""Shared fixture/helpers; no test_ methods so subclasses do not rerun each other."""

	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def _park(self):
		return json.loads(tool_policy.check_tool_call("send_campaign", dict(ARGS), None, True))

class TestSweeperAndAgentScope(SweeperScopeCase):
	def test_failed_execution_in_job_is_recorded_and_args_cleared(self):
		req = self._park()
		with patch.object(tc, "assert_user_may_run"), patch.object(frappe, "enqueue"):
			tc.decide(req["id"], True)
		with patch.object(tc, "_execute", side_effect=RuntimeError("boom")):
			tc.run_approved(req["id"], "Administrator")
		row = frappe.get_doc(tc.DOCTYPE, req["id"])
		self.assertEqual(row.state, "failed")
		self.assertFalse(row.raw_args)
		self.assertEqual(frappe.session.user, "Administrator")

	def test_sweeper_fails_stale_approved(self):
		req = self._park()
		frappe.db.set_value(tc.DOCTYPE, req["id"], {"state": "approved", "modified": add_to_date(now_datetime(), minutes=-46)}, update_modified=False)
		tc.sweep_expired()
		row = frappe.get_doc(tc.DOCTYPE, req["id"])
		self.assertEqual((row.state, row.error), ("failed", "execution_timeout_unknown"))
		self.assertFalse(row.raw_args)

	def test_sweeper_expires_and_clears(self):
		req = self._park()
		frappe.db.set_value(tc.DOCTYPE, req["id"], "expires_at", add_to_date(now_datetime(), minutes=-1))
		req2 = self._park()
		frappe.db.set_value(tc.DOCTYPE, req2["id"], "state", "executed")  # terminal still holding raw_args
		out = tc.sweep_expired()
		self.assertGreaterEqual(out["expired"], 1)
		self.assertEqual(frappe.db.get_value(tc.DOCTYPE, req["id"], "state"), "expired")
		self.assertFalse(frappe.db.get_value(tc.DOCTYPE, req["id"], "raw_args"))
		self.assertFalse(frappe.db.get_value(tc.DOCTYPE, req2["id"], "raw_args"))

	def test_agent_scope_denied_when_tool_removed(self):
		doc = frappe._dict(agent="Nonexistent Agent", tool="send_campaign")
		with self.assertRaises(tc.RoleDenied):
			tc.assert_agent_scope(doc, "Administrator")

	def test_agent_scope_noop_without_agent(self):
		tc.assert_agent_scope(frappe._dict(agent="", tool="x"), "Administrator")

	def test_invoke_tool_denies_user_without_role(self):
		tool_doc = {"name": "T1", "tool_name": "t1", "types": "Custom Function"}
		with (
			patch("huf.ai.tools.invocation.resolve_tool_doc", return_value=tool_doc),
			patch("huf.ai.tools.registry.assert_tool_role", side_effect=frappe.PermissionError("no role")),
			patch("frappe.get_cached_doc"),
		):
			res = invoke_tool_sync("t1", {})
		self.assertFalse(res.success)
		self.assertTrue(res.denied)

	def test_invoke_tool_skip_flag_bypasses_role_check(self):
		tool_doc = {"name": "T1", "tool_name": "t1", "types": "Code Execution"}
		with (
			patch("huf.ai.tools.invocation.resolve_tool_doc", return_value=tool_doc),
			patch("huf.ai.tools.registry.assert_tool_role", side_effect=frappe.PermissionError("no role")) as chk,
		):
			res = invoke_tool_sync("t1", {}, _skip_role_check=True)
		chk.assert_not_called()
		self.assertIn("Code Execution", res.error)

	def test_gateway_run_without_conversation_passes_none(self):
		with patch.object(tool_policy, "_park", return_value="{}") as p, patch.object(
			tool_policy, "resolve_gateway_context", return_value={"gateway": "g", "channel": "C1"}
		), patch.object(tool_policy, "is_tool_allowed", return_value=True):
			tool_policy.check_tool_call("send_campaign", dict(ARGS), "run1", True, conversation_id=None)
		self.assertIsNone(p.call_args.args[4])


class TestFixSweeperAndRun(SweeperScopeCase):
	def _approve(self):
		req = self._park()
		with patch.object(tc, "assert_user_may_run"), patch.object(frappe, "enqueue"):
			tc.decide(req["id"], True)
		return req["id"]

	def test_followup_failure_keeps_executed(self):
		rid = self._approve()
		with (
			patch.object(tc, "_execute", return_value={"ok": 1}),
			patch.object(tc, "_append_followup", side_effect=RuntimeError("x")),
		):
			tc.run_approved(rid, "Administrator")
		row = frappe.get_doc(tc.DOCTYPE, rid)
		self.assertEqual(row.state, "executed")
		self.assertFalse(row.raw_args)

	def test_stale_threshold_and_null_result(self):
		self.assertGreater(tc.APPROVED_STALE_MINUTES, 30)
		rid = self._approve()
		frappe.db.sql(f"update `tab{tc.DOCTYPE}` set result=NULL where name=%s", rid)
		frappe.db.set_value(tc.DOCTYPE, rid, "modified", add_to_date(now_datetime(), minutes=-30), update_modified=False)
		tc.sweep_expired()
		self.assertEqual(frappe.db.get_value(tc.DOCTYPE, rid, "state"), "approved")
		frappe.db.set_value(tc.DOCTYPE, rid, "modified", add_to_date(now_datetime(), minutes=-46), update_modified=False)
		tc.sweep_expired()
		self.assertEqual(frappe.db.get_value(tc.DOCTYPE, rid, "state"), "failed")

	def test_sweeper_failed_row_but_tool_ran_ends_executed(self):
		rid = self._approve()

		def _exec(doc, args):
			frappe.db.set_value(tc.DOCTYPE, rid, {"state": "failed", "error": "execution_timeout_unknown"}, update_modified=False)
			return {"ok": 1}

		with patch.object(tc, "_execute", side_effect=_exec):
			tc.run_approved(rid, "Administrator")
		row = frappe.get_doc(tc.DOCTYPE, rid)
		self.assertEqual(row.state, "executed")
		self.assertTrue(row.error)

	def test_sweep_isolated_and_followup_called(self):
		r1, r2 = self._park()["id"], self._park()["id"]
		for r in (r1, r2):
			frappe.db.set_value(tc.DOCTYPE, r, "expires_at", add_to_date(now_datetime(), minutes=-1))
		calls = []

		def _fu(doc, state, result):
			calls.append((doc.name, state))
			if doc.name == r1:
				raise RuntimeError("bad row")

		with patch.object(tc, "_append_followup", side_effect=_fu):
			tc.sweep_expired()
		self.assertIn((r2, "expired"), calls)
		self.assertEqual(frappe.db.get_value(tc.DOCTYPE, r2, "state"), "expired")
