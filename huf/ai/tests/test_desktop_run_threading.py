# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Tests for threading ``desktop_executor_id`` through run paths (H6).

Covers: runtime_context pin persisted and read back (queued worker), the
immediate and stream paths forwarding ``desktop_ctx``, foreign/invalid executor
ids ignored, and no behavior change when the param is absent.

Run with:
	bench --site <site> run-tests --app huf --module huf.ai.tests.test_desktop_run_threading
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from huf.ai import agent_chat
from huf.ai import agent_integration as ai
from huf.ai import desktop_executor as dx
from huf.ai import desktop_policy
from huf.ai.agent_stream_renderer import AgentStreamRenderer

CTX = {"executor_id": "exec-1", "fingerprint": "fp1", "user": "u@example.com", "label": "ws"}


def _agent_doc(**over):
	doc = MagicMock()
	doc.provider = "P"
	doc.model = "m"
	doc.allow_guest = 1
	doc.allowed_users = []
	doc.allowed_roles = []
	doc.persist_conversation = 1
	doc.prompt_mode = "Local"
	doc.run_immediately = 0
	for k, v in over.items():
		setattr(doc, k, v)
	return doc


class TestResolveDesktopRequest(unittest.TestCase):
	@patch("huf.ai.agent_integration.frappe")
	def test_absent_param_is_noop(self, _f):
		self.assertEqual(ai._resolve_desktop_request(None), (None, None))
		self.assertEqual(ai._resolve_desktop_request(""), (None, None))

	@patch("huf.ai.desktop_executor.origin_for", return_value="desktop")
	@patch("huf.ai.desktop_executor.resolve_desktop_ctx", return_value=CTX)
	@patch("huf.ai.agent_integration.frappe")
	def test_owned_lease_resolves(self, f, resolve, _origin):
		f.session.user = "u@example.com"
		ctx, status = ai._resolve_desktop_request("exec-1")
		self.assertEqual(ctx, {**CTX, "origin": "desktop", "agent_policy": desktop_policy.default_policy()})
		self.assertEqual(status, {"available": True, "reason": None})
		resolve.assert_called_once_with("exec-1", user="u@example.com")

	@patch("huf.ai.desktop_executor.lease_remote_control", return_value=True)
	@patch("huf.ai.desktop_executor.origin_for", return_value="remote")
	@patch("huf.ai.desktop_executor.resolve_desktop_ctx", return_value=CTX)
	@patch("huf.ai.agent_integration.frappe")
	def test_remote_origin_needs_the_agent_flag_and_the_desktop_switch(self, f, _resolve, _origin, _rc):
		f.session.user = "u@example.com"
		agent_off = {"allow_remote_desktop": 0}
		ctx, status = ai._resolve_desktop_request("exec-1", None, agent_off)
		self.assertIsNone(ctx)
		self.assertEqual(status, {"available": False, "reason": "remote_disabled"})
		ctx, status = ai._resolve_desktop_request("exec-1", None, {"allow_remote_desktop": 1})
		self.assertEqual(ctx["origin"], "remote")
		self.assertTrue(status["available"])

	@patch("huf.ai.desktop_executor.resolve_desktop_ctx", return_value=None)
	@patch("huf.ai.agent_integration.frappe")
	def test_foreign_user_executor_ignored_with_warning(self, f, _resolve):
		f.session.user = "other@example.com"
		ctx, status = ai._resolve_desktop_request("exec-1")
		self.assertIsNone(ctx)
		self.assertEqual(status["available"], False)
		self.assertTrue(status["reason"])
		f.logger.return_value.warning.assert_called()

	@patch("huf.ai.desktop_executor.resolve_desktop_ctx", side_effect=RuntimeError("boom"))
	@patch("huf.ai.agent_integration.frappe")
	def test_resolution_error_never_raises(self, f, _resolve):
		ctx, status = ai._resolve_desktop_request("exec-1")
		self.assertIsNone(ctx)
		self.assertFalse(status["available"])


class TestRuntimeContextRoundTrip(unittest.TestCase):
	def test_persisted_pin_has_no_secrets(self):
		noisy = {**CTX, "api_secret": "s3cret", "token": "t"}
		pin = ai._desktop_runtime_context(noisy)
		self.assertEqual(set(pin), {"executor_id", "fingerprint", "user", "label", "sig"})
		self.assertTrue(dx.verify_pin(pin))
		self.assertIsNone(ai._desktop_runtime_context(None))

	@patch("huf.ai.desktop_executor.resolve_desktop_ctx")
	def test_queued_worker_resolves_ctx_from_persisted_context(self, resolve):
		context = json.loads(json.dumps({"desktop": ai._desktop_runtime_context(CTX)}))
		resolve.return_value = {**CTX, "fingerprint": "fp-now"}
		run_doc = MagicMock(agent="A", conversation="C", prompt="hi", provider="P", model="m")
		run_doc.name = "AR-1"
		run_doc.owner = CTX["user"]
		kwargs = ai._build_execution_kwargs(run_doc, context)
		resolve.assert_called_once_with("exec-1", user="u@example.com")
		# Pinned fingerprint is kept so a workspace switch is still detectable.
		self.assertEqual(kwargs["desktop_ctx"]["executor_id"], "exec-1")
		self.assertEqual(kwargs["desktop_ctx"]["fingerprint"], "fp1")

	@patch("huf.ai.desktop_executor.resolve_desktop_ctx", return_value=None)
	def test_queued_worker_expired_lease_gives_no_ctx(self, _resolve):
		run_doc = MagicMock(agent="A", conversation="C", prompt="hi", provider="P", model="m")
		run_doc.owner = CTX["user"]
		kwargs = ai._build_execution_kwargs(run_doc, {"desktop": ai._desktop_runtime_context(CTX)})
		self.assertIsNone(kwargs["desktop_ctx"])

	@patch("huf.ai.desktop_executor.resolve_desktop_ctx")
	def test_absent_pin_unchanged(self, resolve):
		run_doc = MagicMock(agent="A", conversation="C", prompt="hi", provider="P", model="m")
		kwargs = ai._build_execution_kwargs(run_doc, {})
		self.assertIsNone(kwargs["desktop_ctx"])
		resolve.assert_not_called()


class TestWorkerPinVerification(unittest.TestCase):
	"""M1 / M2: the worker trusts the run owner, never the session user or the JSON alone."""

	def _run_doc(self, owner):
		run_doc = MagicMock(agent="A", conversation="C", prompt="hi", provider="P", model="m")
		run_doc.owner = owner
		return run_doc

	@patch("huf.ai.agent_integration._conversation_owner", return_value=None)
	@patch("huf.ai.desktop_executor.resolve_desktop_ctx", return_value=CTX)
	def test_owner_mismatch_drops_the_tools_without_resolving_the_lease(self, resolve, _conv):
		context = {"desktop": ai._desktop_runtime_context(CTX)}
		kwargs = ai._build_execution_kwargs(self._run_doc("attacker@example.com"), context)
		self.assertIsNone(kwargs["desktop_ctx"])
		resolve.assert_not_called()

	@patch("huf.ai.agent_integration._conversation_owner", return_value=None)
	@patch("huf.ai.desktop_executor.resolve_desktop_ctx")
	def test_missing_owner_drops_the_tools(self, resolve, _conv):
		context = {"desktop": ai._desktop_runtime_context(CTX)}
		self.assertIsNone(ai._build_execution_kwargs(self._run_doc(None), context)["desktop_ctx"])
		resolve.assert_not_called()

	@patch("huf.ai.agent_integration._conversation_owner", return_value="victim@example.com")
	@patch("huf.ai.desktop_executor.resolve_desktop_ctx", return_value=CTX)
	def test_conversation_owned_by_someone_else_drops_the_tools(self, resolve, _conv):
		context = {"desktop": ai._desktop_runtime_context(CTX)}
		kwargs = ai._build_execution_kwargs(self._run_doc(CTX["user"]), context)
		self.assertIsNone(kwargs["desktop_ctx"])
		resolve.assert_not_called()

	@patch("huf.ai.agent_integration._conversation_owner", return_value=CTX["user"])
	@patch("huf.ai.desktop_executor.resolve_desktop_ctx", return_value={**CTX, "user": "someone-else@example.com"})
	def test_lease_owned_by_another_user_drops_the_tools(self, resolve, _conv):
		context = {"desktop": ai._desktop_runtime_context(CTX)}
		self.assertIsNone(ai._build_execution_kwargs(self._run_doc(CTX["user"]), context)["desktop_ctx"])

	@patch("huf.ai.agent_integration._conversation_owner", return_value=CTX["user"])
	@patch("huf.ai.desktop_executor.resolve_desktop_ctx", return_value=CTX)
	def test_sweeper_drain_as_administrator_resolves_from_the_run_owner(self, resolve, _conv):
		"""Session user is Administrator (stale-run sweeper); the lease is resolved for the OWNER."""
		context = {"desktop": ai._desktop_runtime_context(CTX)}
		with patch.object(ai.frappe, "session", MagicMock(user="Administrator")):
			kwargs = ai._build_execution_kwargs(self._run_doc(CTX["user"]), context)
		resolve.assert_called_once_with("exec-1", user=CTX["user"])
		self.assertEqual(kwargs["desktop_ctx"]["user"], CTX["user"])
		self.assertEqual(kwargs["desktop_ctx"]["fingerprint"], "fp1")


class TestAgentManagerPassesCtx(unittest.TestCase):
	def test_setup_tools_passes_desktop_ctx(self):
		mgr = ai.AgentManager.__new__(ai.AgentManager)
		mgr.agent_doc = MagicMock()
		mgr.agent_doc.name = "A"
		mgr.effective_model = "m"
		mgr.conversation_id = "C"
		mgr.desktop_ctx = CTX
		mgr.tool_setup_warnings = []
		with patch("huf.ai.sdk_tools.create_agent_tools", return_value=[]) as cat, \
				patch("huf.ai.mcp_client.create_mcp_tools", return_value=[]):
			try:
				mgr._setup_tools()
			except Exception:
				pass  # later setup stages are irrelevant here
		self.assertEqual(cat.call_args.kwargs["desktop_ctx"], CTX)


class TestRunAgentSyncThreading(unittest.TestCase):
	def setUp(self):
		self.conversation = MagicMock()
		self.conversation.name = "CONV-1"
		self.run_doc = MagicMock()
		self.run_doc.name = "AR-1"
		self.run_doc.conversation = "CONV-1"
		self.run_doc.agent = "A"
		self.run_doc.prompt = "hi"
		self.run_doc.creation = "2026-09-30 10:00:00.000000"
		self.conv_manager = MagicMock()
		self.conv_manager.session_id = "s"
		self.conv_manager.get_or_create_conversation.return_value = self.conversation
		self.conv_manager.create_new_conversation.return_value = self.conversation

	def _get_doc(self, agent_doc):
		def _g(first, *a, **k):
			if first == "Agent":
				return agent_doc
			if first == "Agent Conversation":
				return self.conversation
			return self.run_doc
		return _g

	def _run(self, mock_frappe, mock_cm_cls, **kw):
		mock_frappe.session.user = "u@example.com"
		mock_frappe.get_doc.side_effect = self._get_doc(_agent_doc(run_immediately=kw.pop("immediate", 0)))
		mock_frappe.db.get_value.return_value = None
		mock_frappe.db.exists.return_value = False
		mock_frappe.cache.return_value.set.return_value = True
		mock_frappe.as_json.side_effect = json.dumps
		mock_cm_cls.return_value = self.conv_manager
		return ai.run_agent_sync(agent_name="A", prompt="hi", **kw)

	def _signed_pin(self, mock_frappe):
		"""The pin as stored after the insert: signed, bound to the run that now exists."""
		for c in mock_frappe.db.set_value.call_args_list:
			if c.args[:3] == ("Agent Run", "AR-1", "runtime_context"):
				return json.loads(c.args[3])["desktop"]
		self.fail("the run pin was never signed after the insert")

	def _persisted_context(self, mock_frappe):
		data = mock_frappe.get_doc.call_args_list
		for c in data:
			if c.args and isinstance(c.args[0], dict) and c.args[0].get("doctype") == "Agent Run":
				return json.loads(c.args[0]["runtime_context"])
		self.fail("Agent Run doc not created")

	@patch("huf.ai.agent_integration._execute_agent_run")
	@patch("huf.ai.agent_integration.ConversationManager")
	@patch("huf.ai.desktop_executor.origin_for", return_value="desktop")
	@patch("huf.ai.desktop_executor.resolve_desktop_ctx", return_value=CTX)
	@patch("huf.ai.agent_integration.frappe")
	def test_immediate_path_passes_ctx_and_status(self, f, _resolve, _origin, cm, execute):
		execute.return_value = {"success": True}
		result = self._run(f, cm, immediate=1, desktop_executor_id="exec-1")
		passed = execute.call_args.kwargs["desktop_ctx"]
		self.assertEqual({k: passed[k] for k in CTX}, CTX)
		self.assertEqual(passed["origin"], "desktop")
		self.assertEqual(result["desktop_tools"], {"available": True, "reason": None})
		self.assertEqual(self._persisted_context(f)["desktop"]["executor_id"], "exec-1")

	@patch("huf.ai.agent_integration._execute_agent_run")
	@patch("huf.ai.agent_integration.ConversationManager")
	@patch("huf.ai.desktop_executor.origin_for", return_value="desktop")
	@patch("huf.ai.desktop_executor.resolve_desktop_ctx", return_value=CTX)
	@patch("huf.ai.agent_integration.frappe")
	def test_queued_path_persists_pin_and_status(self, f, _resolve, _origin, cm, execute):
		result = self._run(f, cm, desktop_executor_id="exec-1")
		self.assertTrue(result["queued"])
		execute.assert_not_called()
		# written unsigned by the insert (the run has no name yet) ...
		self.assertNotIn("sig", self._persisted_context(f)["desktop"])
		# ... and signed right after it, for THIS conversation and THIS run
		pin = self._signed_pin(f)
		self.assertEqual({k: pin[k] for k in CTX}, CTX)
		self.assertEqual(pin["origin"], "desktop")
		self.assertTrue(dx.verify_pin(pin, "CONV-1", self.run_doc))
		self.assertFalse(dx.verify_pin(pin, "CONV-1", MagicMock(name="another run")))
		self.assertTrue(result["desktop_tools"]["available"])

	@patch("huf.ai.agent_integration._execute_agent_run")
	@patch("huf.ai.agent_integration.ConversationManager")
	@patch("huf.ai.desktop_executor.resolve_desktop_ctx", return_value=None)
	@patch("huf.ai.agent_integration.frappe")
	def test_foreign_executor_ignored_run_proceeds(self, f, _resolve, cm, execute):
		execute.return_value = {"success": True}
		result = self._run(f, cm, immediate=1, desktop_executor_id="someone-elses")
		self.assertIsNone(execute.call_args.kwargs["desktop_ctx"])
		self.assertNotIn("desktop", self._persisted_context(f))
		self.assertFalse(result["desktop_tools"]["available"])

	@patch("huf.ai.agent_integration._execute_agent_run")
	@patch("huf.ai.agent_integration.ConversationManager")
	@patch("huf.ai.desktop_executor.resolve_desktop_ctx")
	@patch("huf.ai.agent_integration.frappe")
	def test_absent_param_unchanged(self, f, resolve, cm, execute):
		sentinel = {"success": True}
		execute.return_value = sentinel
		result = self._run(f, cm, immediate=1)
		self.assertIs(result, sentinel)
		self.assertNotIn("desktop_tools", result)
		self.assertNotIn("desktop", self._persisted_context(f))
		self.assertIsNone(execute.call_args.kwargs["desktop_ctx"])
		resolve.assert_not_called()


class TestChatEndpointsForward(unittest.TestCase):
	@patch("huf.ai.agent_chat.run_agent_sync", return_value={"conversation_id": "C", "desktop_tools": {"available": False, "reason": "executor_unavailable"}})
	@patch("huf.ai.agent_chat.frappe")
	def test_send_message_forwards_param_and_returns_status(self, f, run):
		conv = MagicMock(is_active=1, agent="A", model="m", channel="Chat")
		conv.name = "C"
		f.get_doc.return_value = conv
		f.db.get_value.return_value = "P"
		result = agent_chat.send_message_to_conversation("C", "hi", desktop_executor_id="exec-1")
		self.assertEqual(run.call_args.kwargs["desktop_executor_id"], "exec-1")
		self.assertFalse(result["desktop_tools"]["available"])

	@patch("huf.ai.agent_chat.run_agent_sync", return_value={"conversation_id": "C"})
	@patch("huf.ai.agent_chat.frappe")
	def test_send_message_without_param_unchanged(self, f, run):
		conv = MagicMock(is_active=1, agent="A", model="m", channel="Chat")
		conv.name = "C"
		f.get_doc.return_value = conv
		f.db.get_value.return_value = "P"
		result = agent_chat.send_message_to_conversation("C", "hi")
		self.assertIsNone(run.call_args.kwargs["desktop_executor_id"])
		self.assertNotIn("desktop_tools", result)

	@patch("huf.ai.agent_chat.run_agent_sync", return_value={"conversation_id": "C", "desktop_tools": {"available": True, "reason": None}})
	@patch("huf.ai.agent_chat.ConversationManager")
	@patch("huf.ai.agent_chat.frappe")
	def test_new_conversation_forwards_and_surfaces_status(self, f, cm, run):
		cm.return_value.create_new_conversation.return_value = MagicMock(name="C")
		f.db.get_value.return_value = "x"
		result = agent_chat.new_conversation("A", "hi", desktop_executor_id="exec-1")
		self.assertEqual(run.call_args.kwargs["desktop_executor_id"], "exec-1")
		self.assertTrue(result["desktop_tools"]["available"])


class TestStreamPathThreading(unittest.TestCase):
	def _render(self, params):
		renderer = AgentStreamRenderer.__new__(AgentStreamRenderer)
		renderer.path = "huf/stream/a"
		renderer.http_status_code = 200
		agent_doc = _agent_doc(run_immediately=1)
		captured = {}

		async def fake_stream(**kwargs):
			captured.update(kwargs)
			yield {"type": "complete"}

		with patch("huf.ai.agent_stream_renderer.frappe.form_dict", {"agent_name": "a", **params}), \
				patch("huf.ai.agent_stream_renderer.frappe.request", new=MagicMock(method="GET")), \
				patch("huf.ai.agent_stream_renderer.frappe.get_doc", return_value=agent_doc), \
				patch("huf.ai.agent_stream_renderer.frappe.has_permission", return_value=True), \
				patch("huf.ai.agent_stream_renderer.run_agent_stream", fake_stream):
			response = renderer._render_agent_stream("a")
			list(response.response)
		return captured

	def test_stream_route_forwards_param(self):
		captured = self._render({"prompt": "hi", "desktop_executor_id": "exec-1"})
		self.assertEqual(captured["desktop_executor_id"], "exec-1")

	def test_stream_route_absent_param_is_none(self):
		captured = self._render({"prompt": "hi"})
		self.assertIsNone(captured["desktop_executor_id"])

	def test_stream_emits_keep_alive_comments_while_a_desktop_call_is_pending(self):
		"""N5: a pending desktop call produces no chunks for a long time; the SSE stream must
		still write bytes (an SSE comment) so a proxy read timeout does not cut it."""
		import asyncio

		renderer = AgentStreamRenderer.__new__(AgentStreamRenderer)
		renderer.path = "huf/stream/a"
		renderer.http_status_code = 200

		async def slow_stream(**kwargs):
			yield {"type": "run_started", "agent_run_id": "R"}
			await asyncio.sleep(0.35)  # a tool call waiting for the user's approval on the desktop
			yield {"type": "delta", "content": "hi"}
			yield {"type": "complete"}

		with patch("huf.ai.agent_stream_renderer.SSE_KEEPALIVE_S", 0.1), \
				patch("huf.ai.agent_stream_renderer.frappe.form_dict", {"agent_name": "a", "prompt": "hi"}), \
				patch("huf.ai.agent_stream_renderer.frappe.request", new=MagicMock(method="GET")), \
				patch("huf.ai.agent_stream_renderer.frappe.get_doc", return_value=_agent_doc(run_immediately=1)), \
				patch("huf.ai.agent_stream_renderer.frappe.has_permission", return_value=True), \
				patch("huf.ai.agent_stream_renderer.run_agent_stream", slow_stream):
			response = renderer._render_agent_stream("a")
			body = "".join(c if isinstance(c, str) else c.decode() for c in response.response)
		data_lines = [ln for ln in body.split("\n\n") if ln.startswith("data: ")]
		types = [json.loads(ln[6:])["type"] for ln in data_lines]
		self.assertGreaterEqual(types.count("heartbeat"), 2)
		self.assertEqual([t for t in types if t != "heartbeat"], ["run_started", "delta", "complete"])
