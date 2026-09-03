# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Unit tests for ST-R1.2: the v1 stream endpoint handler must acquire the
conversation-scoped execution lock before the SSE `Response` is constructed
(only when `stream_conversation_id` is set), raise `ConflictError` (409) on
a lock-acquisition failure, and release the lock exactly once via
`Response.call_on_close` -- even when the returned response's generator is
never iterated at all.

frappe.cache() is patched to a small hand-written fake implementing real
set(nx=)/expire/delete semantics (not a MagicMock, per this track's test
convention documented in huf.ai.tests.test_procedure_lock -- a MagicMock's
.set() is truthy by default regardless of nx, which would make the
"second acquire fails" assertion meaningless).

Run with:
  bench --site <site> run-tests --app huf --module huf.ai.tests.test_streaming_lock
"""

import unittest
from unittest.mock import MagicMock, patch

from huf.ai.agent_integration import _conversation_lock_key
from huf.api.v1.context import RequestContext
from huf.api.v1.endpoints import responses_stream
from huf.api.v1.errors import ConflictError


class FakeCache:
	"""Hand-written double with real set(nx=)/expire/delete semantics."""

	def __init__(self):
		self._store = {}
		self.set_calls = []
		self.delete_calls = []

	def set(self, key, value, ex=None, nx=False):
		self.set_calls.append((key, value, ex, nx))
		if nx and key in self._store:
			return False
		self._store[key] = value
		return True

	def expire(self, key, ttl):
		if key not in self._store:
			raise KeyError(key)

	def delete(self, key):
		self.delete_calls.append(key)
		self._store.pop(key, None)

	def get(self, key):
		return self._store.get(key)


def _make_context():
	ctx = MagicMock(spec=RequestContext)
	ctx.user = "test@example.com"
	ctx.request_id = "req-1"
	return ctx


def _make_agent_doc():
	doc = MagicMock()
	doc.run_immediately = 1
	return doc


class _FakeAsyncGen:
	def __init__(self, chunks):
		self._chunks = list(chunks)
		self._i = 0

	def __aiter__(self):
		return self

	async def __anext__(self):
		if self._i >= len(self._chunks):
			raise StopAsyncIteration
		chunk = self._chunks[self._i]
		self._i += 1
		return chunk

	async def aclose(self):
		return None


class TestStreamLockBase(unittest.TestCase):
	def setUp(self):
		self.cache = FakeCache()
		patchers = [
			patch.object(responses_stream, "require_scope", lambda *a, **k: None),
			patch.object(responses_stream, "require_agent_allowed", lambda *a, **k: None),
			patch.object(responses_stream, "assert_agent_access", lambda *a, **k: None),
			patch.object(responses_stream, "_has_queued_runs", lambda *a, **k: False),
			patch.object(responses_stream, "_get_owned_conversation", lambda *a, **k: MagicMock()),
			patch.object(responses_stream.frappe.db, "exists", lambda *a, **k: True, create=True),
			patch.object(responses_stream.frappe, "get_doc", lambda *a, **k: _make_agent_doc(), create=True),
			patch.object(responses_stream.frappe, "log_error", lambda *a, **k: None, create=True),
			patch.object(responses_stream.frappe, "logger", lambda *a, **k: MagicMock(), create=True),
			patch.object(responses_stream.frappe, "cache", lambda: self.cache, create=True),
			# Heartbeat runs a background thread; keep it inert for tests.
			patch.object(responses_stream, "_RunHeartbeat", lambda *a, **k: MagicMock()),
		]
		for p in patchers:
			p.start()
			self.addCleanup(p.stop)
		self.context = _make_context()


class TestLockAcquisition(TestStreamLockBase):
	def test_lock_key_uses_conversation_name_string(self):
		"""The lock key must be derived from _conversation_lock_key(name) --
		a string -- matching the direct-path lock in agent_integration.py,
		so the two paths actually contend."""
		fake_gen = _FakeAsyncGen([{"type": "complete", "full_response": "ok"}])
		with patch.object(responses_stream, "run_agent_stream", lambda **kwargs: fake_gen):
			resp = responses_stream.handle_stream_response(
				self.context, agent_id="agent-1", input_text="hi", conversation_id="conv-1"
			)
		expected_key = _conversation_lock_key("conv-1")
		self.assertTrue(self.cache.set_calls)
		key, value, ex, nx = self.cache.set_calls[0]
		self.assertEqual(key, expected_key)
		self.assertTrue(nx)
		self.assertIsNotNone(resp)

	def test_create_new_conversation_never_attempts_lock(self):
		"""A brand-new conversation (create_new=True) has nothing to
		contend with -- the lock must never be attempted."""
		fake_gen = _FakeAsyncGen([{"type": "complete", "full_response": "ok"}])
		with patch.object(responses_stream, "run_agent_stream", lambda **kwargs: fake_gen):
			responses_stream.handle_stream_response(
				self.context, agent_id="agent-1", input_text="hi", conversation_id=None
			)
		self.assertEqual(self.cache.set_calls, [])

	def test_conflict_error_raised_when_lock_set_fails(self):
		"""If cache().set(..., nx=True) returns False on every attempt, a
		ConflictError (409) must be raised before any SSE bytes are
		produced -- i.e. before Response() is even constructed."""
		lock_key = _conversation_lock_key("conv-1")
		# Pre-seed the lock so every nx=True attempt fails.
		self.cache._store[lock_key] = 1

		with patch.object(responses_stream, "time") as mock_time:
			with self.assertRaises(ConflictError) as ctx:
				responses_stream.handle_stream_response(
					self.context, agent_id="agent-1", input_text="hi", conversation_id="conv-1"
				)
		self.assertEqual(ctx.exception.status_code, 409)
		self.assertEqual(ctx.exception.code, "conflict")
		# Retried up to _DIRECT_LOCK_ATTEMPTS times with backoff between attempts.
		from huf.ai.agent_integration import _DIRECT_LOCK_ATTEMPTS

		self.assertEqual(len(self.cache.set_calls), _DIRECT_LOCK_ATTEMPTS)
		self.assertEqual(mock_time.sleep.call_count, _DIRECT_LOCK_ATTEMPTS - 1)

	def test_heartbeat_started_on_successful_acquisition(self):
		fake_gen = _FakeAsyncGen([{"type": "complete", "full_response": "ok"}])
		heartbeat_instances = []

		def _fake_heartbeat(*a, **k):
			hb = MagicMock()
			heartbeat_instances.append(hb)
			return hb

		with patch.object(responses_stream, "_RunHeartbeat", _fake_heartbeat), patch.object(
			responses_stream, "run_agent_stream", lambda **kwargs: fake_gen
		):
			responses_stream.handle_stream_response(
				self.context, agent_id="agent-1", input_text="hi", conversation_id="conv-1"
			)
		self.assertEqual(len(heartbeat_instances), 1)
		heartbeat_instances[0].start.assert_called_once()


class TestLockRelease(TestStreamLockBase):
	def test_lock_released_via_call_on_close_even_when_never_iterated(self):
		"""A not-yet-iterated generator's .close() never runs its finally
		body -- release must be wired to Response.call_on_close, not the
		generator's own finally, so a client that aborts before the first
		byte is read still frees the lock."""
		fake_gen = _FakeAsyncGen([{"type": "complete", "full_response": "ok"}])
		with patch.object(responses_stream, "run_agent_stream", lambda **kwargs: fake_gen):
			resp = responses_stream.handle_stream_response(
				self.context, agent_id="agent-1", input_text="hi", conversation_id="conv-1"
			)

		lock_key = _conversation_lock_key("conv-1")
		self.assertIn(lock_key, self.cache._store)

		# Never touch resp.response (the generator) -- simulate the abort by
		# invoking the werkzeug close hooks directly, as werkzeug itself
		# does when the response is closed without ever being iterated.
		for func in getattr(resp, "_on_close", []):
			func()

		self.assertNotIn(lock_key, self.cache._store)
		self.assertIn(lock_key, self.cache.delete_calls)

	def test_lock_released_exactly_once(self):
		"""Multiple close signals (e.g. werkzeug calling the hook, plus a
		defensive extra call) must not double-release or raise."""
		fake_gen = _FakeAsyncGen([{"type": "complete", "full_response": "ok"}])
		with patch.object(responses_stream, "run_agent_stream", lambda **kwargs: fake_gen):
			resp = responses_stream.handle_stream_response(
				self.context, agent_id="agent-1", input_text="hi", conversation_id="conv-1"
			)

		for func in getattr(resp, "_on_close", []):
			func()
			func()  # call twice -- must be idempotent (the `released` flag guard)

		self.assertEqual(self.cache.delete_calls.count(_conversation_lock_key("conv-1")), 1)

	def test_lock_released_after_normal_full_stream_completion(self):
		fake_gen = _FakeAsyncGen(
			[
				{"type": "delta", "content": "a", "full_response": "a"},
				{"type": "complete", "full_response": "a"},
			]
		)
		with patch.object(responses_stream, "run_agent_stream", lambda **kwargs: fake_gen):
			resp = responses_stream.handle_stream_response(
				self.context, agent_id="agent-1", input_text="hi", conversation_id="conv-1"
			)
		list(resp.response)  # drain the generator to completion

		for func in getattr(resp, "_on_close", []):
			func()

		lock_key = _conversation_lock_key("conv-1")
		self.assertNotIn(lock_key, self.cache._store)


if __name__ == "__main__":
	unittest.main()
