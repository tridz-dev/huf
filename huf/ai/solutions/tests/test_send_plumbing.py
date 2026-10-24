"""R2: the real send paths pass the run's solution to the policy/usage plumbing."""

import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.gateway_adapters import whatsapp as wa_adapter
from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.solutions.tests._fixtures import make_agent, make_binding, make_gateway, make_solution, uid
from huf.ai.solutions.tests.test_stamping import make_run
from huf.ai.tools import whatsapp as tool
from huf.ai.whatsapp import outbound_policy as policy
from huf.ai.whatsapp import send_scope as scope

CONTACT = "15550001111"


def _ok():
	return json.dumps({"success": True, "data": {"message_id": "wamid." + uid(), "recipient": CONTACT, "status": "sent"}})


class _Base(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.agent = make_agent()
		self.gw = make_gateway().name
		self.sol = make_solution()
		self.run = make_run(self.agent, self.sol.name)
		self.plain_run = make_run(self.agent, None)
		self.current = self.run
		p = patch.object(frappe.db, "commit")
		p.start()
		self.addCleanup(p.stop)
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(patch.stopall)
		patch.object(tool, "_effective_run_id", side_effect=lambda: self.current).start()
		patch.object(scope, "current_contact", return_value=CONTACT).start()
		self.dispatch = patch.object(tool, "_dispatch", side_effect=lambda action, kw: _ok()).start()

	def send(self, text="hi", run=None):
		self.current = run or self.run
		return json.loads(
			tool._idempotent_send("send_message", {"to": CONTACT, "text": text, "gateway_name": self.gw}, self.gw)
		)


class TestToolPlumbing(_Base):
	def test_send_key_stamped_through_tool(self):
		self.assertTrue(self.send()["success"])
		sols = frappe.get_all("WhatsApp Send Key", filters={"gateway": self.gw}, pluck="solution")
		self.assertEqual(sols, [self.sol.name])

	def test_check_caps_receives_solution(self):
		with patch.object(scope, "check_caps", wraps=scope.check_caps) as cc:
			self.send()
		self.assertEqual(cc.call_args.kwargs.get("solution"), self.sol.name)

	def test_check_caps_unchanged_without_solution(self):
		with patch.object(scope, "check_caps", wraps=scope.check_caps) as cc:
			self.send(run=self.plain_run)
		self.assertNotIn("solution", cc.call_args.kwargs)
		self.assertEqual(cc.call_args.args, (self.gw, self.plain_run))

	def test_check_recipient_receives_solution(self):
		self.current = self.run
		with patch.object(scope, "check_recipient", wraps=scope.check_recipient) as cr:
			self.assertIsNone(tool._scope_refusal({"to": CONTACT}, self.gw))
		self.assertEqual(cr.call_args.kwargs.get("solution"), self.sol.name)
		self.current = self.plain_run
		with patch.object(scope, "check_recipient", wraps=scope.check_recipient) as cr:
			tool._scope_refusal({"to": CONTACT}, self.gw)
		self.assertNotIn("solution", cr.call_args.kwargs)

	def test_per_solution_cap_refuses_only_that_solution(self):
		make_binding(self.gw, self.agent, match_type="Keyword", match_value="x", solution=self.sol.name, cap_per_day=1)
		other = make_solution()
		other_run = make_run(self.agent, other.name)
		self.assertTrue(self.send("one")["success"])
		second = self.send("two")
		self.assertFalse(second["success"])
		self.assertEqual((second["error"], second["cap"]), ("send_cap_exceeded", "solution_day"))
		self.assertTrue(self.send("three", run=other_run)["success"])
		self.assertTrue(self.send("four", run=self.plain_run)["success"])


class TestSendTemplatePlumbing(_Base):
	def test_tool_passes_run_id_to_bridge(self):
		self.current = self.run
		with patch.object(tool, "_resolve_bridge_account", return_value={"name": "acct-r2"}), \
			patch.object(tool, "_is_opted_out", return_value=False), \
			patch.object(bridge, "send_template", return_value={"message_id": "w1", "name": "n"}) as st:
			out = json.loads(
				tool._send_template({"to": CONTACT, "template_name": "hello", "gateway_name": self.gw, "parameters": []})
			)
		self.assertTrue(out["success"], out)
		self.assertEqual(st.call_args.kwargs.get("run_id"), self.run)

	def test_adapter_passes_run_and_solution(self):
		adapter = wa_adapter.WhatsAppGatewayAdapter(
			{"phone_number_id": "1", "access_token": "t", "webhook_verify_token": "v"},
			gateway_context={"gateway_name": self.gw, "whatsapp_account": "acct-r2"},
		)
		with patch.object(adapter, "_bridge_mode", return_value=True), patch.object(adapter, "_guard"), \
			patch.object(bridge, "send_template", return_value={"message_id": "w2"}) as st:
			adapter.send_template(CONTACT, "hello", "en", [], run_id=self.run, solution=self.sol.name)
			self.assertEqual(st.call_args.kwargs.get("run_id"), self.run)
			self.assertEqual(st.call_args.kwargs.get("solution"), self.sol.name)
			adapter.send_template(CONTACT, "hello", "en", [])
			self.assertNotIn("run_id", st.call_args.kwargs)
			self.assertNotIn("solution", st.call_args.kwargs)

	def test_observed_template_usage_end_to_end(self):
		"""bridge.send_template(run_id=...) -> note_template_sent -> Template Usage (Observed)."""
		acct = "acct-r2-" + uid()
		with patch.object(bridge, "_account_or_error", return_value={"name": acct}), \
			patch.object(bridge, "_refuse_if_disconnected"), \
			patch.object(bridge, "_template_docname", return_value="doc"), \
			patch.object(bridge, "_template_row", return_value=None), \
			patch.object(bridge, "_may_bypass", return_value=True), \
			patch.object(policy, "enforce_template"), \
			patch.object(bridge, "_graph_post_message", return_value="wamid.x"), \
			patch.object(bridge, "_mirror_template_send", return_value={"message_id": "wamid.x"}):
			bridge.send_template(acct, CONTACT, "tpl_r2", [], header_params="H", language_code="en", run_id=self.run)
		rows = frappe.get_all(
			"Template Usage", filters={"whatsapp_account": acct, "template": "tpl_r2"}, fields=["solution", "source"]
		)
		self.assertEqual([(r.solution, r.source) for r in rows], [(self.sol.name, "Observed")])
