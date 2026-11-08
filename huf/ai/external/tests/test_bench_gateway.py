"""Bench-run integration tests for the external-intelligence gateway on the real database.

Run with ``bench --site <site> run-tests --module huf.ai.external.tests.test_bench_gateway``.
Under plain pytest the repo conftest installs a mock ``frappe``; the whole module then skips.
"""

import unittest
from unittest.mock import MagicMock

import frappe

try:
	from frappe.tests import IntegrationTestCase as _Base
except Exception:  # noqa: BLE001 - mocked frappe or an older Frappe without IntegrationTestCase
	_Base = unittest.TestCase

if isinstance(_Base, MagicMock) or not isinstance(_Base, type):
	_Base = unittest.TestCase


def _frappe_is_real() -> bool:
	if isinstance(frappe, MagicMock):
		return False
	db = getattr(frappe, "db", None)
	return db is not None and not isinstance(db, MagicMock)


USER = "bench-gateway@example.com"
AGENT = "bench-gateway-agent"
PROVIDER = "bench-gateway-provider"
READ_TOOL = "bench_gw_list_todos"
WRITE_TOOL = "bench_gw_make_todo"


class TestBenchGateway(_Base):
	@classmethod
	def setUpClass(cls):
		if not _frappe_is_real():
			raise unittest.SkipTest("needs a real Frappe site (bench run-tests)")
		super().setUpClass()
		frappe.set_user("Administrator")
		cls._build_fixtures()

	@classmethod
	def tearDownClass(cls):
		if _frappe_is_real():
			frappe.set_user("Administrator")
			frappe.db.rollback()
		super().tearDownClass()

	@classmethod
	def _build_fixtures(cls):
		def make(doctype, **fields):
			return frappe.get_doc({"doctype": doctype, **fields}).insert(ignore_permissions=True)

		make("AI Provider", provider_name=PROVIDER, provider_brand="openai", api_key="sk-bench")
		model = make("AI Model", provider=PROVIDER, model_name="bench-model")
		for tool_name, tool_type in ((READ_TOOL, "Get List"), (WRITE_TOOL, "Create Document")):
			make(
				"Agent Tool Function",
				tool_name=tool_name,
				description=tool_name,
				types=tool_type,
				reference_doctype="ToDo",
				tool_type="Data Operations",
			)
		agent = make(
			"Agent",
			agent_name=AGENT,
			agent_modality="Text",
			provider=PROVIDER,
			model=model.name,
			instructions="bench",
			execution_mode="Connected External",
		)
		for tool_name in (READ_TOOL, WRITE_TOOL):
			agent.append("agent_tool", {"tool": frappe.db.get_value("Agent Tool Function", {"tool_name": tool_name})})
		agent.save(ignore_permissions=True)

		make(
			"User",
			email=USER,
			first_name="Bench",
			send_welcome_email=0,
			roles=[{"role": "System Manager"}],
		)
		cls.connection = make(
			"External Agent Connection",
			user=USER,
			agent=AGENT,
			read_policy="Allow",
			write_policy="Requires Approval",
		).name

	def setUp(self):
		frappe.set_user(USER)
		from huf.ai.external import sessions

		created = sessions.create_session(self.connection)
		self.session_name = created["session"]
		self.session = frappe.get_doc("External Agent Session", self.session_name)

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_create_session_links_conversation_and_run(self):
		self.assertEqual(self.session.state, "Active")
		self.assertEqual(self.session.user, USER)
		self.assertTrue(frappe.db.exists("Agent Conversation", self.session.conversation))
		self.assertTrue(frappe.db.exists("Agent Run", self.session.agent_run))

	def test_mailbox_post_fetch_ack(self):
		from huf.ai.external import mailbox

		first = mailbox.post_event(self.session_name, "to_agent", "user_message", {"text": "hi"})
		second = mailbox.post_event(self.session_name, "to_agent", "user_message", {"text": "again"})
		self.assertEqual((first["seq"], second["seq"]), (1, 2))

		keyed = mailbox.post_event(self.session_name, "to_agent", "note", {}, idempotency_key="k1")
		again = mailbox.post_event(self.session_name, "to_agent", "note", {}, idempotency_key="k1")
		self.assertEqual(keyed["name"], again["name"])

		events = mailbox.fetch_pending(self.session_name)
		self.assertEqual([e["seq"] for e in events], [1, 2, 3])
		self.assertTrue(all(e["status"] == "Delivered" for e in events))

		self.assertEqual(mailbox.ack(self.session_name, 2), 2)
		self.assertEqual(mailbox.ack(self.session_name, 1), 2)
		self.assertEqual([e["seq"] for e in mailbox.fetch_pending(self.session_name)], [3])

	def test_approval_request_decide_consume(self):
		from huf.ai.external import approvals

		args = {"description": "approve me"}
		self.assertFalse(approvals.consume_approval(self.session_name, WRITE_TOOL, args))
		pending = approvals.request_approval(self.session_name, WRITE_TOOL, "write", args)
		self.assertEqual(pending["status"], "Pending")
		self.assertEqual(
			approvals.request_approval(self.session_name, WRITE_TOOL, "write", args)["approval"],
			pending["approval"],
		)
		self.assertEqual(frappe.db.get_value("External Agent Session", self.session_name, "state"), "Waiting for Approval")

		decided = approvals.decide_approval(pending["approval"], True)
		self.assertEqual(decided["status"], "Approved")
		self.assertEqual(frappe.db.get_value("External Agent Session", self.session_name, "state"), "Active")

		self.assertFalse(approvals.consume_approval(self.session_name, WRITE_TOOL, {"description": "other"}))
		self.assertTrue(approvals.consume_approval(self.session_name, WRITE_TOOL, args))
		self.assertFalse(approvals.consume_approval(self.session_name, WRITE_TOOL, args))

	def test_invoke_read_tool_returns_rows(self):
		from huf.ai.external.invoke import external_invoke

		todo = frappe.get_doc({"doctype": "ToDo", "description": "bench read row", "allocated_to": USER}).insert(
			ignore_permissions=True
		)
		result = external_invoke(self.session, READ_TOOL, {"fields": ["name", "description"], "limit": 100})
		self.assertEqual(result["status"], "ok")
		self.assertEqual(result["action_class"], "read")
		names = [row["name"] for row in result["result"]["result"]]
		self.assertIn(todo.name, names)

	def test_invoke_write_needs_approval_then_runs_once(self):
		from huf.ai.external import approvals
		from huf.ai.external.invoke import external_invoke

		args = {"description": "bench write row"}
		first = external_invoke(self.session, WRITE_TOOL, args, "call-1")
		self.assertEqual(first["status"], "approval_required")
		self.assertFalse(frappe.db.exists("ToDo", {"description": "bench write row"}))

		approvals.decide_approval(first["approval"], True)
		done = external_invoke(self.session, WRITE_TOOL, args, "call-1")
		self.assertEqual(done["status"], "ok")
		self.assertNotIn("replayed", done)
		self.assertEqual(frappe.db.count("ToDo", {"description": "bench write row"}), 1)

		replay = external_invoke(self.session, WRITE_TOOL, args, "call-1")
		self.assertTrue(replay["replayed"])
		self.assertEqual(frappe.db.count("ToDo", {"description": "bench write row"}), 1)


	def test_dispatch_tools_list_and_discover(self):
		from huf.ai.external import dispatch

		listed = dispatch.handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, self.session)
		self.assertEqual(len(listed["result"]["tools"]), 7)

		call = {"name": "huf_discover", "arguments": {}}
		found = dispatch.handle_rpc(
			{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": call}, self.session
		)
		self.assertFalse(found["result"]["isError"])
		import json

		tools = json.loads(found["result"]["content"][0]["text"])["tools"]
		decisions = {tool["name"]: tool["decision"] for tool in tools}
		self.assertEqual(decisions, {READ_TOOL: "allow", WRITE_TOOL: "approve"})
