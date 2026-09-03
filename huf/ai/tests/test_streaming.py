# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Unit tests for ST-R1.1: `stream_generator()`'s finally block in
`huf.api.v1.endpoints.responses_stream` must call `async_gen.aclose()`
unconditionally (when the generator was actually created), regardless of
whether this call created the asyncio event loop.

Run with:
  bench --site <site> run-tests --app huf --module huf.ai.tests.test_streaming
"""

import asyncio
import unittest
from unittest.mock import MagicMock, patch

from huf.api.v1.context import RequestContext
from huf.api.v1.endpoints import responses_stream


class _FakeAsyncGen:
	"""Stand-in for the async generator returned by `run_agent_stream`.

	Tracks whether `aclose()` was invoked so tests can assert the finally
	block actually drives cleanup (which, in production, is what makes the
	salvage `finally` in `agent_integration.run_agent_stream` reachable --
	see ST-R1.4).
	"""

	def __init__(self, chunks):
		self._chunks = list(chunks)
		self._i = 0
		self.aclose_called = False
		self.aclose_call_count = 0

	def __aiter__(self):
		return self

	async def __anext__(self):
		if self._i >= len(self._chunks):
			raise StopAsyncIteration
		chunk = self._chunks[self._i]
		self._i += 1
		return chunk

	async def aclose(self):
		self.aclose_called = True
		self.aclose_call_count += 1


def _make_context():
	ctx = MagicMock(spec=RequestContext)
	ctx.user = "test@example.com"
	ctx.request_id = "req-1"
	return ctx


def _make_agent_doc():
	doc = MagicMock()
	doc.run_immediately = 1
	return doc


class TestStreamGeneratorAclose(unittest.TestCase):
	"""ST-R1.1: aclose() must be called on disconnect, before the
	created_loop-gated cleanup, and must never be skipped just because this
	call didn't create the loop."""

	def setUp(self):
		# require_scope / require_agent_allowed / frappe.db.exists /
		# frappe.get_doc / assert_agent_access / _has_queued_runs / the
		# conversation lock are all irrelevant to this ST -- stub them so a
		# stream can be constructed without touching real Frappe state.
		patchers = [
			patch.object(responses_stream, "require_scope", lambda *a, **k: None),
			patch.object(responses_stream, "require_agent_allowed", lambda *a, **k: None),
			patch.object(responses_stream, "assert_agent_access", lambda *a, **k: None),
			patch.object(responses_stream, "_has_queued_runs", lambda *a, **k: False),
			patch.object(responses_stream, "_get_owned_conversation", lambda *a, **k: MagicMock()),
			patch.object(responses_stream.frappe.db, "exists", lambda *a, **k: True, create=True),
			patch.object(responses_stream.frappe, "get_doc", lambda *a, **k: _make_agent_doc(), create=True),
			patch.object(responses_stream.frappe, "log_error", lambda *a, **k: None, create=True),
		]
		for p in patchers:
			p.start()
			self.addCleanup(p.stop)

		# No conversation_id => create_new=True => stream_conversation_id is
		# None => the ST-R1.2 lock path is skipped entirely, keeping this
		# test focused on ST-R1.1's aclose() behavior only.
		self.context = _make_context()

	def _build_response(self, fake_gen):
		with patch.object(responses_stream, "run_agent_stream", lambda **kwargs: fake_gen):
			return responses_stream.handle_stream_response(
				self.context, agent_id="agent-1", input_text="hi", conversation_id=None
			)

	def test_aclose_called_on_disconnect_mid_stream(self):
		"""Simulate a client disconnect (GeneratorExit) after the first
		chunk: aclose() on the async generator must have been called by the
		time the sync generator's close() returns."""
		fake_gen = _FakeAsyncGen(
			[
				{"type": "delta", "content": "a", "full_response": "a"},
				{"type": "delta", "content": "b", "full_response": "ab"},
				{"type": "complete", "full_response": "ab"},
			]
		)
		resp = self._build_response(fake_gen)
		gen = resp.response  # the underlying Python generator wrapped by werkzeug's Response

		# Consume the "response.created" line and one delta, then simulate a
		# disconnect by closing the generator early (GeneratorExit at the
		# next yield point inside stream_generator's while loop).
		next(gen)  # response.created
		next(gen)  # first delta
		gen.close()

		self.assertTrue(fake_gen.aclose_called)
		self.assertEqual(fake_gen.aclose_call_count, 1)

	def test_aclose_not_called_when_generator_never_created(self):
		"""If stream setup fails before `run_agent_stream()` is ever called,
		`async_gen` stays None and aclose() must not be attempted (would
		raise AttributeError on None otherwise)."""

		def _raise_setup_error(**kwargs):
			raise RuntimeError("boom")

		with patch.object(responses_stream, "run_agent_stream", _raise_setup_error):
			resp = responses_stream.handle_stream_response(
				self.context, agent_id="agent-1", input_text="hi", conversation_id=None
			)
		gen = resp.response
		# Fully drain -- the setup error path yields a single
		# response.failed frame and returns; the finally block must not
		# blow up despite async_gen being None throughout.
		lines = list(gen)
		self.assertTrue(any("response.failed" in line for line in lines))


class TestStreamGeneratorPreExistingLoop(unittest.TestCase):
	"""ST-R1.1: when `asyncio.get_event_loop()` returns a pre-existing,
	non-closed loop (`created_loop` stays False), the cancel-pending-tasks /
	gather / close sequence must never run -- only `aclose()` on this
	request's own async generator is safe to call unconditionally."""

	def setUp(self):
		patchers = [
			patch.object(responses_stream, "require_scope", lambda *a, **k: None),
			patch.object(responses_stream, "require_agent_allowed", lambda *a, **k: None),
			patch.object(responses_stream, "assert_agent_access", lambda *a, **k: None),
			patch.object(responses_stream, "_has_queued_runs", lambda *a, **k: False),
			patch.object(responses_stream.frappe.db, "exists", lambda *a, **k: True, create=True),
			patch.object(responses_stream.frappe, "get_doc", lambda *a, **k: _make_agent_doc(), create=True),
			patch.object(responses_stream.frappe, "log_error", lambda *a, **k: None, create=True),
		]
		for p in patchers:
			p.start()
			self.addCleanup(p.stop)
		self.context = _make_context()

		# A real, live event loop standing in for "a pre-existing loop
		# owned by someone else" -- run_until_complete must actually work
		# against it for the test to exercise the real code path.
		self.shared_loop = asyncio.new_event_loop()
		self.addCleanup(self.shared_loop.close)

	def test_shared_loop_tasks_never_cancelled_on_disconnect(self):
		fake_gen = _FakeAsyncGen(
			[
				{"type": "delta", "content": "a", "full_response": "a"},
				{"type": "complete", "full_response": "a"},
			]
		)

		with patch.object(responses_stream, "run_agent_stream", lambda **kwargs: fake_gen), patch(
			"asyncio.get_event_loop", return_value=self.shared_loop
		), patch("asyncio.all_tasks") as mock_all_tasks:
			resp = responses_stream.handle_stream_response(
				self.context, agent_id="agent-1", input_text="hi", conversation_id=None
			)
			gen = resp.response
			next(gen)  # response.created
			next(gen)  # first delta
			gen.close()  # disconnect mid-stream

			self.assertTrue(fake_gen.aclose_called)
			# created_loop stayed False (get_event_loop returned our
			# already-open shared loop), so the cancel-pending-tasks branch
			# must never touch this loop's other tasks.
			mock_all_tasks.assert_not_called()


if __name__ == "__main__":
	unittest.main()
