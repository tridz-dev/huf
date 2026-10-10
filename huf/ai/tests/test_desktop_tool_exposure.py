# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Tests for Desktop Workspace tool exposure in huf.ai.sdk_tools.create_agent_tools().

Gate: tool attached to the agent (ordinary Agent Tool row) AND a live
desktop_ctx. Covers S27 (no ctx), S28 (ctx but not attached), S29 (_dx_*
overwrite), S30 (lease expired).

Run with:
	bench --site <site> run-tests --app huf --module huf.ai.tests.test_desktop_tool_exposure
"""

import asyncio
import json
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

import frappe

from huf.ai.sdk_tools import create_agent_tools
from huf.ai.tools._registry import DESKTOP_WORKSPACE_TOOL_NAMES, DESKTOP_WORKSPACE_TOOLS

EXECUTOR_ID = "exec-test-0001"
CTX = {"executor_id": EXECUTOR_ID, "fingerprint": "ctxfingerprint", "user": "Administrator"}
LIVE = {"executor_id": EXECUTOR_ID, "fingerprint": "abcdef0123456789", "user": "Administrator", "label": "ws"}

_PATCH_LIVE = (
	mock.patch("huf.ai.desktop_executor.is_lease_live", return_value=True),
	mock.patch("huf.ai.desktop_executor.resolve_desktop_ctx", return_value=LIVE),
)


class TestDesktopToolExposure(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")
		cls.provider = cls._ensure_provider()
		cls.model = cls._ensure_model(cls.provider)
		cls.tool_docs = cls._ensure_desktop_tool_rows()

	def setUp(self):
		frappe.set_user("Administrator")
		self._agents = []

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in self._agents:
			try:
				frappe.delete_doc("Agent", name, ignore_permissions=True, force=True)
			except Exception:
				pass
		frappe.db.commit()

	@staticmethod
	def _ensure_provider():
		existing = frappe.db.get_value("AI Provider", {}, "name")
		if existing:
			return existing
		doc = frappe.get_doc(
			{
				"doctype": "AI Provider",
				"provider_name": f"Desktop Exposure Test Provider {frappe.generate_hash(length=6)}",
				"api_key": "test-key-not-used",
				"provider_brand": "openai",
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	@staticmethod
	def _ensure_model(provider):
		existing = frappe.db.get_value("AI Model", {"provider": provider}, "name")
		if existing:
			return existing
		doc = frappe.get_doc(
			{
				"doctype": "AI Model",
				"model_name": f"desktop-exposure-test-model-{frappe.generate_hash(length=6)}",
				"provider": provider,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	@staticmethod
	def _ensure_desktop_tool_rows():
		"""Registry-synced Agent Tool Function rows; created here if the sync has not run."""
		if not frappe.db.exists("Agent Tool Type", "Desktop Workspace"):
			frappe.get_doc({"doctype": "Agent Tool Type", "name1": "Desktop Workspace"}).insert(
				ignore_permissions=True
			)
		docs = []
		for spec in DESKTOP_WORKSPACE_TOOLS:
			name = frappe.db.get_value("Agent Tool Function", {"tool_name": spec["tool_name"]}, "name")
			if not name:
				props = {
					p["fieldname"]: {"type": p["type"], "description": p.get("description", "")}
					for p in spec["parameters"]
				}
				doc = frappe.get_doc(
					{
						"doctype": "Agent Tool Function",
						"tool_name": spec["tool_name"],
						"description": spec["description"],
						"tool_type": "Desktop Workspace",
						"types": "App Provided",
						"function_path": spec["function_path"],
						"params": json.dumps({"type": "object", "properties": props}),
					}
				)
				doc.insert(ignore_permissions=True)
				name = doc.name
			docs.append(name)
		frappe.db.commit()
		return docs

	def _make_agent(self, tool_names):
		agent = frappe.get_doc(
			{
				"doctype": "Agent",
				"agent_name": f"desktop-exposure-agent-{frappe.generate_hash(length=8)}",
				"instructions": "Test desktop exposure agent instructions",
				"provider": self.provider,
				"model": self.model,
				"agent_tool": [{"tool": n} for n in tool_names],
			}
		)
		agent.insert(ignore_permissions=True)
		self._agents.append(agent.name)
		return agent

	@staticmethod
	def _desktop_tools(tools):
		return [t for t in tools if getattr(t, "name", "") in DESKTOP_WORKSPACE_TOOL_NAMES]

	def test_registry_has_ten_tools(self):
		self.assertEqual(len(DESKTOP_WORKSPACE_TOOL_NAMES), 10)

	# S27
	def test_s27_no_ctx_tools_absent(self):
		agent = self._make_agent(self.tool_docs)
		self.assertEqual(self._desktop_tools(create_agent_tools(agent)), [])
		self.assertEqual(self._desktop_tools(create_agent_tools(agent, desktop_ctx=None)), [])
		self.assertEqual(self._desktop_tools(create_agent_tools(agent, desktop_ctx={})), [])

	# S28
	def test_s28_ctx_but_not_attached_absent(self):
		agent = self._make_agent([])
		with _PATCH_LIVE[0], _PATCH_LIVE[1]:
			tools = create_agent_tools(agent, desktop_ctx=dict(CTX))
		self.assertEqual(self._desktop_tools(tools), [])

	# S30
	def test_s30_lease_expired_absent(self):
		agent = self._make_agent(self.tool_docs)
		with mock.patch("huf.ai.desktop_executor.is_lease_live", return_value=False), mock.patch(
			"huf.ai.desktop_executor.resolve_desktop_ctx", return_value=None
		):
			tools = create_agent_tools(agent, desktop_ctx=dict(CTX))
		self.assertEqual(self._desktop_tools(tools), [])

	def test_ctx_owned_by_other_user_absent(self):
		agent = self._make_agent(self.tool_docs)
		with mock.patch("huf.ai.desktop_executor.is_lease_live", return_value=True), mock.patch(
			"huf.ai.desktop_executor.resolve_desktop_ctx", return_value=None
		):
			tools = create_agent_tools(agent, desktop_ctx=dict(CTX, user="someone@example.com"))
		self.assertEqual(self._desktop_tools(tools), [])

	def test_attached_and_live_exposes_ten_with_pinned_extra_args(self):
		agent = self._make_agent(self.tool_docs)
		with _PATCH_LIVE[0], _PATCH_LIVE[1]:
			tools = create_agent_tools(agent, desktop_ctx=dict(CTX))
		desktop = self._desktop_tools(tools)
		self.assertEqual({t.name for t in desktop}, set(DESKTOP_WORKSPACE_TOOL_NAMES))
		self.assertEqual(len(desktop), 10)

	def test_partial_attachment_exposes_only_attached(self):
		agent = self._make_agent(self.tool_docs[:2])
		with _PATCH_LIVE[0], _PATCH_LIVE[1]:
			tools = create_agent_tools(agent, desktop_ctx=dict(CTX))
		self.assertEqual(len(self._desktop_tools(tools)), 2)

	# S29
	def test_s29_dx_args_overwrite_llm_values_and_run_blocking(self):
		captured = {}

		def fake_handler(**kwargs):
			captured.update(kwargs)
			return {"ok": True}

		agent = self._make_agent(self.tool_docs)
		with _PATCH_LIVE[0], _PATCH_LIVE[1], mock.patch(
			"huf.ai.tools.desktop_workspace.handle_list_files", fake_handler
		), mock.patch("huf.ai.sdk_tools.asyncio.to_thread", wraps=asyncio.to_thread) as to_thread:
			tools = create_agent_tools(agent, desktop_ctx=dict(CTX))
			tool = next(t for t in tools if t.name == "desktop_list_files")
			evil = {
				"path": ".",
				"_dx_executor_id": "attacker-exec",
				"_dx_fingerprint": "deadbeef",
				"_dx_user": "victim@example.com",
			}
			out = asyncio.run(tool.on_invoke_tool(None, json.dumps(evil)))

		self.assertEqual(json.loads(out), {"ok": True})
		self.assertEqual(captured["_dx_executor_id"], LIVE["executor_id"])
		# M3: the fingerprint is the one PINNED on the run at send time, not the live lease's.
		self.assertEqual(captured["_dx_fingerprint"], CTX["fingerprint"])
		self.assertNotEqual(captured["_dx_fingerprint"], LIVE["fingerprint"])
		self.assertEqual(captured["_dx_user"], LIVE["user"])
		self.assertTrue(to_thread.called)

	def test_pinned_fingerprint_falls_back_to_live_when_ctx_has_none(self):
		captured = {}

		def fake_handler(**kwargs):
			captured.update(kwargs)
			return {"ok": True}

		agent = self._make_agent(self.tool_docs)
		with _PATCH_LIVE[0], _PATCH_LIVE[1], mock.patch(
			"huf.ai.tools.desktop_workspace.handle_list_files", fake_handler
		):
			tools = create_agent_tools(agent, desktop_ctx={**CTX, "fingerprint": None})
			tool = next(t for t in tools if t.name == "desktop_list_files")
			asyncio.run(tool.on_invoke_tool(None, "{}"))
		self.assertEqual(captured["_dx_fingerprint"], LIVE["fingerprint"])

	# H1: identity is pinned server-side
	def _invoke_with_run_ctx(self, evil_args, run_ctx, tool_call_id="call_abc123", handler=None):
		captured = {}

		def fake_handler(**kwargs):
			captured.update(kwargs)
			return {"ok": True}

		agent = self._make_agent(self.tool_docs)
		with _PATCH_LIVE[0], _PATCH_LIVE[1], mock.patch(
			"huf.ai.tools.desktop_workspace.handle_list_files", handler or fake_handler
		):
			tools = create_agent_tools(agent, desktop_ctx=dict(CTX))
			tool = next(t for t in tools if t.name == "desktop_list_files")
			tool_ctx = SimpleNamespace(context=run_ctx, tool_call_id=tool_call_id)
			asyncio.run(tool.on_invoke_tool(tool_ctx, json.dumps(evil_args)))
		return captured

	def test_llm_supplied_run_identity_is_ignored(self):
		from huf.ai.desktop_executor import derive_call_id

		captured = self._invoke_with_run_ctx(
			{
				"path": ".",
				"agent_run_id": "AR-foreign-run",
				"conversation_id": "CONV-foreign",
				"call_id": "call-chosen-by-the-llm",
			},
			{"agent_run_id": "AR-real", "conversation_id": "CONV-real"},
		)
		self.assertEqual(captured["agent_run_id"], "AR-real")
		self.assertEqual(captured["conversation_id"], "CONV-real")
		# derived from the run + SDK tool_call_id plus a per-invocation nonce (N7)
		self.assertTrue(captured["call_id"].startswith(derive_call_id("AR-real", "call_abc123") + ".n"))
		self.assertNotIn("chosen", captured["call_id"])

	def test_each_invocation_gets_its_own_nonce_in_the_call_id(self):
		a = self._invoke_with_run_ctx({"path": "."}, {"agent_run_id": "AR-real"}, tool_call_id="0")
		b = self._invoke_with_run_ctx({"path": "."}, {"agent_run_id": "AR-real"}, tool_call_id="0")
		self.assertNotEqual(a["call_id"], b["call_id"])  # same run, same tool_call_id, two invocations
		self.assertEqual(a["call_id"].rsplit(".n", 1)[0], b["call_id"].rsplit(".n", 1)[0])

	def test_llm_run_identity_dropped_when_the_run_context_has_none(self):
		captured = self._invoke_with_run_ctx(
			{"path": ".", "agent_run_id": "AR-foreign-run", "call_id": "mine"}, {}
		)
		self.assertNotIn("agent_run_id", captured)
		self.assertNotIn("call_id", captured)

	def test_call_id_is_deterministic_per_run_and_tool_call(self):
		a = self._invoke_with_run_ctx({"path": "."}, {"agent_run_id": "AR-1"}, "call_x")
		b = self._invoke_with_run_ctx({"path": "."}, {"agent_run_id": "AR-1"}, "call_x")
		c = self._invoke_with_run_ctx({"path": "."}, {"agent_run_id": "AR-2"}, "call_x")
		d = self._invoke_with_run_ctx({"path": "."}, {"agent_run_id": "AR-1"}, "call_y")
		def base(x):  # the per-invocation nonce suffix is intentionally different (N7)
			return x["call_id"].rsplit(".n", 1)[0]

		self.assertEqual(base(a), base(b))
		self.assertEqual(len({base(a), base(c), base(d)}), 3)

	# N8: only the pinned-run path mints the token the handlers require
	def test_pin_token_is_minted_for_the_pinned_run_and_a_model_supplied_one_is_discarded(self):
		from huf.ai.tools.desktop_workspace import issue_pin_token

		captured = self._invoke_with_run_ctx(
			{"path": ".", "_dx_pin": "forged-by-the-model"},
			{"agent_run_id": "AR-real", "conversation_id": "CONV-real"},
		)
		self.assertNotEqual(captured["_dx_pin"], "forged-by-the-model")
		self.assertEqual(
			captured["_dx_pin"], issue_pin_token("AR-real", LIVE["executor_id"], LIVE["user"])
		)
		# bound to the run: the token of another run is different
		self.assertNotEqual(
			captured["_dx_pin"], issue_pin_token("AR-other", LIVE["executor_id"], LIVE["user"])
		)

	def test_pin_token_verification_rejects_anything_but_the_exact_binding(self):
		from huf.ai.tools import desktop_workspace as dw

		token = dw.issue_pin_token("AR-1", "exec-1", "u@example.com")
		self.assertTrue(dw._pin_token_valid(token, "AR-1", "exec-1", "u@example.com"))
		for args in (("AR-2", "exec-1", "u@example.com"), ("AR-1", "exec-2", "u@example.com"), ("AR-1", "exec-1", "v@example.com")):
			self.assertFalse(dw._pin_token_valid(token, *args))
		for bad in (None, "", 5, "x" * 64):
			self.assertFalse(dw._pin_token_valid(bad, "AR-1", "exec-1", "u@example.com"))

	def test_derive_call_id_is_bounded_and_wire_safe(self):
		from huf.ai.desktop_executor import derive_call_id

		self.assertEqual(derive_call_id("AR-1", "call_1"), "AR-1:call_1")
		long_id = derive_call_id("AR-1", "x" * 500)
		self.assertLessEqual(len(long_id), 200)
		self.assertEqual(long_id, derive_call_id("AR-1", "x" * 500))
		self.assertNotEqual(long_id, derive_call_id("AR-2", "x" * 500))
		self.assertLessEqual(len(derive_call_id("AR-1", "weird id/with spaces")), 200)

	# M5: DB work on the loop thread, only the wait in the worker thread
	def test_prepare_runs_on_the_loop_thread_and_only_execute_in_a_worker(self):
		seen = {}
		main = threading.get_ident()

		def handler(**kwargs):  # pragma: no cover - must not be used
			raise AssertionError("prepare/execute must be used instead")

		handler.prepare = lambda **kw: (seen.__setitem__("prepare", threading.get_ident()), {"p": kw})[1]
		handler.execute = lambda prepared: (seen.__setitem__("execute", threading.get_ident()), {"ok": True})[1]

		async def run():
			seen["loop"] = threading.get_ident()
			return await self._async_invoke(handler)

		out = asyncio.run(run())
		self.assertEqual(json.loads(out), {"ok": True})
		self.assertEqual(seen["prepare"], seen["loop"])
		self.assertNotEqual(seen["execute"], seen["loop"])
		self.assertEqual(main, seen["loop"])

	async def _async_invoke(self, handler):
		agent = self._make_agent(self.tool_docs)
		with _PATCH_LIVE[0], _PATCH_LIVE[1], mock.patch(
			"huf.ai.tools.desktop_workspace.handle_list_files", handler
		):
			tools = create_agent_tools(agent, desktop_ctx=dict(CTX))
			tool = next(t for t in tools if t.name == "desktop_list_files")
			return await tool.on_invoke_tool(None, "{}")

	def test_real_handlers_expose_prepare_and_execute(self):
		from huf.ai.tools import desktop_workspace as dw

		for name in (
			"handle_workspace_info", "handle_list_files", "handle_read_file", "handle_search_files",
			"handle_write_file", "handle_edit_file", "handle_make_directory", "handle_move_path",
			"handle_delete_path", "handle_run_command",
		):
			fn = getattr(dw, name)
			self.assertTrue(callable(fn.prepare), name)
			self.assertTrue(callable(fn.execute), name)
