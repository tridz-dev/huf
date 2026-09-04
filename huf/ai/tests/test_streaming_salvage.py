# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Regression test for ST-R1.4: the salvage `finally` block in
`huf.ai.agent_integration.run_agent_stream` (~lines 3637-3672 on
origin/develop) already writes `status="Success"` with partial text when
`full_response` is non-empty, and `status="Failed"` with "Stream
disconnected before response was generated" when it is empty -- but that
block was unreachable before ST-R1.1, because nothing ever called
`aclose()` on the async generator when a client disconnected mid-stream.

This test proves the block is now reachable and behaves as documented: it
drives `run_agent_stream` directly (not through the HTTP layer), consumes
three of five mocked provider deltas, then calls `aclose()` on the async
generator exactly as ST-R1.1's `stream_generator()` finally block now does,
and asserts the resulting `Agent Run` write.

Every collaborator of `run_agent_stream` outside the provider streaming
loop itself (`RunProvider.run_stream`) is mocked -- this test is scoped to
the salvage `finally` block's behavior, not the full agent-turn pipeline
(covered elsewhere, e.g. huf.ai.tests.test_queue_first_runs).

Run with:
  bench --site <site> run-tests --app huf --module huf.ai.tests.test_streaming_salvage
"""

import asyncio
import unittest
from unittest.mock import MagicMock, patch

from huf.ai import agent_integration


class _FakeProviderStream:
	"""Stand-in for `RunProvider.run_stream(...)`: yields 5 delta chunks
	with a monotonically growing `full_response`.

	`gate`, if given, is awaited before producing the *first* chunk. This
	gives a test a genuine suspension point inside `run_agent_stream`'s
	`async for chunk in stream:` loop -- needed to simulate "client
	disconnected before any chunk arrived, but after the Agent Run was
	already created". An async generator's `aclose()` is a complete no-op
	if the generator was never started (no `__anext__()` call ever made):
	none of its code -- including `finally` -- runs. So a driver that
	wants to close *after* setup but *before* the first delta must first
	start the generator and let it suspend somewhere, then close it from
	there; it cannot simply skip calling `__anext__()` altogether.
	"""

	def __init__(self, chunk_texts, gate: asyncio.Event = None):
		self._texts = list(chunk_texts)
		self._i = 0
		self._acc = ""
		self._gate = gate

	def __aiter__(self):
		return self

	async def __anext__(self):
		if self._gate is not None and self._i == 0:
			await self._gate.wait()
		if self._i >= len(self._texts):
			raise StopAsyncIteration
		text = self._texts[self._i]
		self._i += 1
		self._acc += text
		return {"type": "delta", "content": text, "full_response": self._acc}


class TestStreamSalvageOnDisconnect(unittest.TestCase):
	def setUp(self):
		self.agent_doc = MagicMock()
		self.agent_doc.allow_guest = 1
		self.agent_doc.disabled = 0
		self.agent_doc.allow_chat = 1
		self.agent_doc.persist_conversation = 1
		self.agent_doc.get = lambda key, default=None: {"prompt_mode": "Local"}.get(key, default)
		self.agent_doc.context_strategy = "FIFO"
		self.agent_doc.history_limit = 20
		self.agent_doc.max_knowledge_tokens = 4000
		self.agent_doc.enable_conversation_data = 0

		self.run_doc = MagicMock()
		self.run_doc.name = "Agent Run 1"
		self.run_doc.insert = MagicMock()
		self.run_doc.db_set = MagicMock()

		self.conversation = MagicMock()
		self.conversation.name = "Conv 1"
		self.conversation.conversation_data = None

		self.conv_manager = MagicMock()
		self.conv_manager.create_new_conversation.return_value = self.conversation
		self.conv_manager.get_or_create_conversation.return_value = self.conversation
		self.conv_manager.get_conversation_history.return_value = []
		self.conv_manager.get_stored_summary.return_value = None
		self.conv_manager.add_message.return_value = MagicMock(name="Agent Message 1")

		self.manager = MagicMock()
		self.manager.tool_sources = {}
		self.manager.agent_doc = self.agent_doc
		self.manager.create_agent.return_value = MagicMock(tools=[], instructions="you are helpful")

		# Records every frappe.db.set_value("Agent Run", ...) call so the
		# test can assert the final salvage write without depending on a
		# real database.
		self.set_value_calls = []

		def _fake_set_value(doctype, name, fieldname, value=None, **kwargs):
			# Real `frappe.db.set_value` supports two calling conventions:
			# `set_value(doctype, name, {field: value, ...})` (dict form,
			# `value` unused) and `set_value(doctype, name, fieldname,
			# value)` (single-field shorthand, used e.g. for "Agent
			# Conversation" model persistence in `run_agent_stream`). Only
			# the dict form was previously handled here, so any shorthand
			# call -- even one against an unrelated doctype -- raised a
			# TypeError that `run_agent_stream`'s broad exception handling
			# swallowed into a single error chunk, ending the stream after
			# one item and starving these tests of ever reaching the
			# provider streaming loop. Accept both forms, exactly like the
			# real API.
			if isinstance(fieldname, dict):
				values = fieldname
			else:
				values = {fieldname: value}
			if doctype == "Agent Run":
				self.set_value_calls.append((name, dict(values)))
			return None

		self._agent_run_status = "Started"

		def _fake_get_value(doctype, name=None, fieldname=None, **kwargs):
			if doctype == "Agent Run" and fieldname == "status":
				return self._agent_run_status
			if doctype == "Agent":
				return 0
			return None

		# `frappe.get_doc` is patched globally (it's the same module object
		# `frappe` that Frappe's own internals import), so any *other* real
		# Frappe code that runs incidentally during the test -- e.g.
		# `now_datetime()` -> `get_system_timezone()` ->
		# `frappe.get_system_settings()` -> `frappe.get_cached_doc("System
		# Settings")` -- goes through this fake too. Returning a bare
		# `MagicMock()` for such doctypes is unsafe: `get_cached_doc()`
		# then tries to cache that MagicMock via the real Redis-backed
		# cache, which pickles it -- and a dynamically-created MagicMock
		# class/instance is not reliably picklable, so this blew up
		# non-deterministically (depending on whether "System Settings"
		# happened to already be cached from an earlier test). Delegate to
		# the real `frappe.get_doc` for anything that isn't one of this
		# test's own mocked doctypes, so real framework docs stay real.
		_real_get_doc = agent_integration.frappe.get_doc

		def _fake_get_doc(*args, **kwargs):
			if args and args[0] == "Agent":
				return self.agent_doc
			if args and isinstance(args[0], dict) and args[0].get("doctype") == "Agent Run":
				return self.run_doc
			return _real_get_doc(*args, **kwargs)

		self.patchers = [
			patch.object(agent_integration.frappe, "get_doc", _fake_get_doc, create=True),
			patch.object(agent_integration.frappe, "session", MagicMock(user="test@example.com"), create=True),
			patch.object(agent_integration.frappe, "has_permission", lambda *a, **k: True, create=True),
			patch.object(agent_integration.frappe.db, "set_value", _fake_set_value, create=True),
			patch.object(agent_integration.frappe.db, "get_value", _fake_get_value, create=True),
			patch.object(agent_integration.frappe.db, "count", lambda *a, **k: 0, create=True),
			patch.object(agent_integration.frappe, "log_error", lambda *a, **k: None, create=True),
			patch.object(agent_integration.frappe, "logger", lambda *a, **k: MagicMock(), create=True),
			patch.object(agent_integration, "assert_agent_access", lambda *a, **k: None),
			patch.object(agent_integration, "has_capability", lambda *a, **k: True),
			patch.object(agent_integration, "safe_commit", lambda *a, **k: None),
			patch.object(agent_integration, "transaction_checkpoint", lambda *a, **k: None),
			patch.object(agent_integration, "serialize_tools", lambda *a, **k: []),
			patch.object(agent_integration, "ConversationManager", lambda **kwargs: self.conv_manager),
			patch.object(agent_integration, "AgentManager", lambda *a, **k: self.manager),
			patch.object(
				agent_integration,
				"_resolve_effective_model",
				lambda *a, **k: ("test-provider", "test-model", "test-model"),
			),
			patch.object(agent_integration, "_resolve_prompt_cache_options", lambda *a, **k: {}),
			patch.object(agent_integration, "build_knowledge_context", lambda *a, **k: None),
			# Local imports inside run_agent_stream resolve these attributes
			# on the real modules at call time -- patch them there.
			patch(
				"huf.ai.context_segments.compute_segment_tokens",
				lambda *a, **k: {},
			),
			patch(
				"huf.ai.context_segments.compute_prefix_breakpoints",
				lambda *a, **k: {},
			),
			patch(
				"huf.ai.context_segments.compute_tools_breakdown",
				lambda *a, **k: {},
			),
			patch(
				"huf.ai.context_segments.reconcile_composition",
				lambda *a, **k: None,
			),
			patch(
				"huf.ai.system_prompt_retention.maybe_snapshot_system_prompt",
				lambda *a, **k: None,
			),
		]
		for p in self.patchers:
			p.start()
			self.addCleanup(p.stop)

	def _drive_partial_stream(self, chunk_texts, take):
		"""Start `run_agent_stream`, pull `take` chunks, then `aclose()` it
		-- exactly the sequence ST-R1.1's `stream_generator()` finally
		block performs on disconnect.

		`take == 0` needs special handling: an async generator's
		`aclose()` is a no-op if `__anext__()` was never called on it
		first (the function body -- including the Agent Run insert --
		never runs). To exercise "disconnected before any chunk, but
		after the Agent Run was created", the fake provider stream is
		given a `gate` that it awaits before producing its first chunk, so
		the generator has a genuine suspension point to hang at: start
		`__anext__()` as a task, pump the loop once to let it run up to
		(and suspend at) the gate, cancel that task, then `aclose()`.
		"""
		gate = asyncio.Event() if take == 0 else None
		fake_stream = _FakeProviderStream(chunk_texts, gate=gate)
		with patch.object(agent_integration.RunProvider, "run_stream", lambda *a, **k: fake_stream):
			gen = agent_integration.run_agent_stream(
				agent_name="test-agent",
				prompt="hello",
				channel_id="test",
				external_id="test@example.com",
				conversation_id=None,
				create_new=True,
			)

			loop = asyncio.new_event_loop()
			try:
				if take == 0:
					task = loop.create_task(gen.__anext__())
					# Never set `gate` -- just pump the loop long enough for
					# all the synchronous setup (Agent Run insert, etc.) to
					# run and for the task to reach and suspend on
					# `gate.wait()`.
					loop.run_until_complete(asyncio.sleep(0.05))
					self.assertFalse(task.done(), "fake provider stream should still be gated open")
					task.cancel()
					try:
						loop.run_until_complete(task)
					except (asyncio.CancelledError, StopAsyncIteration):
						pass
				else:
					for _ in range(take):
						loop.run_until_complete(gen.__anext__())
				loop.run_until_complete(gen.aclose())
			finally:
				loop.close()

	def test_partial_disconnect_salvages_success_with_partial_text(self):
		"""5 chunks total, close after 3: salvage finally must write
		status=Success with the partial accumulated text."""
		self._drive_partial_stream(["a", "b", "c", "d", "e"], take=3)

		self.assertTrue(self.set_value_calls, "expected the salvage finally to write Agent Run")
		name, values = self.set_value_calls[-1]
		self.assertEqual(name, self.run_doc.name)
		self.assertEqual(values.get("status"), "Success")
		self.assertEqual(values.get("response"), "abc")

	def test_disconnect_before_any_chunk_salvages_failed(self):
		"""Close before any chunk is yielded: full_response is empty, so
		the salvage finally must write status=Failed with the documented
		error message."""
		self._drive_partial_stream(["a", "b", "c", "d", "e"], take=0)

		self.assertTrue(self.set_value_calls, "expected the salvage finally to write Agent Run")
		name, values = self.set_value_calls[-1]
		self.assertEqual(name, self.run_doc.name)
		self.assertEqual(values.get("status"), "Failed")
		self.assertEqual(values.get("error_message"), "Stream disconnected before response was generated")

	def test_no_salvage_write_when_run_already_terminal(self):
		"""If the run's status is no longer 'Started' (already resolved by
		some other path) by the time the finally block runs, the salvage
		block must not overwrite it."""
		self._agent_run_status = "Success"
		self._drive_partial_stream(["a", "b", "c", "d", "e"], take=3)
		self.assertEqual(self.set_value_calls, [])


if __name__ == "__main__":
	unittest.main()
