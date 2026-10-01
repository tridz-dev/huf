# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""REAL round-trip tests for desktop workspace tools (no mocked cache, no mocked get_doc).

A real (non-admin) user registers a lease through the whitelisted endpoints, a real
Agent Run stores ``runtime_context`` as a JSON string, a real tool handler is called,
and a background thread plays the desktop (polls ``list_pending_desktop_tool_calls``
and answers via ``submit_desktop_tool_event``) against the live Redis cache. Some
cases deliberately wait longer than the 5 s redis-cache socket timeout.

Run with:
	bench --site <site> run-tests --app huf --module huf.ai.tests.test_desktop_roundtrip
"""

import contextvars
import threading
import time
import unittest
from unittest import mock

import frappe

from huf.ai import agent_integration as ai
from huf.ai import desktop_executor as dx
from huf.ai.tests import desktop_test_helpers as h
from huf.ai.tools import desktop_workspace as dw

CAPS = ["fs.read", "fs.write", "fs.trash", "exec"]


class TestDesktopRoundTrip(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")
		cls.user = h.make_user("dxrt")
		cls.other = h.make_user("dxrt2")
		cls._docs = []

	@classmethod
	def tearDownClass(cls):
		h.delete_docs(cls._docs + [("User", cls.user), ("User", cls.other)])

	def setUp(self):
		frappe.set_user(self.user)
		self.exec_id = f"exec-rt-{frappe.generate_hash(length=10)}"
		self.call_id = f"call-rt-{frappe.generate_hash(length=10)}"
		self.register()
		self.run_name = h.make_run(self.user, h.desktop_pin(self.exec_id, self.user))
		self._docs.append(("Agent Run", self.run_name))
		frappe.set_user(self.user)

	def tearDown(self):
		frappe.set_user(self.user)
		try:
			h.unregister_desktop_executor(executor_id=self.exec_id)
		except Exception:
			pass
		frappe.set_user("Administrator")

	# helpers
	def register(self, fingerprint=h.FP):
		frappe.set_user(self.user)
		return h.register_desktop_executor(
			executor_id=self.exec_id,
			protocol_version=1,
			app_version="0.1",
			platform="darwin",
			workspace=h.workspace(fingerprint),
			capabilities=CAPS,
		)

	def read_file(self, **over):
		kwargs = dict(
			path="a.txt",
			_dx_executor_id=self.exec_id,
			_dx_fingerprint=h.FP,
			_dx_user=self.user,
			agent_run_id=self.run_name,
			call_id=self.call_id,
		)
		kwargs.update(over)
		kwargs.setdefault("_dx_pin", self.pin(kwargs))
		return dw.handle_read_file(**kwargs)

	def pin(self, kwargs=None, **over):
		"""The pin token sdk_tools mints for a pinned run (bound to run, executor, user)."""
		kwargs = dict(kwargs or {}, **over)
		return dw.issue_pin_token(
			kwargs.get("agent_run_id", self.run_name),
			kwargs.get("_dx_executor_id", self.exec_id),
			kwargs.get("_dx_user", self.user),
		)

	def play_desktop(self, script, poll_for_s=15):
		"""Background desktop: wait for our call to show up in list_pending, then run
		``script`` = [(sleep_s, kind, payload), ...] through submit_desktop_tool_event."""
		results = []

		def play():
			deadline = time.monotonic() + poll_for_s
			seen = None
			while time.monotonic() < deadline and seen is None:
				for req in h.list_pending_desktop_tool_calls(executor_id=self.exec_id):
					if req["call_id"] == self.call_id:
						seen = req
				if seen is None:
					time.sleep(0.1)
			if seen is None:
				raise AssertionError("desktop never saw the call in list_pending")
			results.append(("request", seen))
			for delay, kind, payload in script:
				time.sleep(delay)
				results.append(
					(
						kind,
						h.submit_desktop_tool_event(
							call_id=self.call_id, executor_id=self.exec_id, kind=kind, payload=payload
						),
					)
				)

		thread, errors = h.run_in_thread(play)
		return thread, errors, results

	def finish(self, thread, errors, timeout=30):
		thread.join(timeout)
		self.assertFalse(thread.is_alive(), "desktop thread did not finish")
		self.assertEqual(errors, [])

	# tests
	def test_fast_round_trip_through_a_real_handler(self):
		thread, errors, results = self.play_desktop(
			[
				(0.2, "ack", {}),
				(0.2, "result", {"ok": True, "data": {"content": "hello"}, "duration_ms": 5}),
			]
		)
		out = self.read_file()
		self.finish(thread, errors)
		self.assertEqual(out["data"]["content"], "hello")
		self.assertTrue(out["ok"])
		self.assertTrue(out["untrusted_content"])
		req = results[0][1]
		self.assertEqual(req["executor_id"], self.exec_id)
		self.assertEqual(req["fingerprint"], h.FP)
		self.assertEqual(req["agent_run_id"], self.run_name)
		self.assertEqual(req["op"], "fs.read")
		self.assertEqual([r[1]["status"] for r in results[1:]], ["recorded", "recorded"])

	def test_redis_state_is_cleaned_up_after_the_call(self):
		thread, errors, _ = self.play_desktop(
			[(0.1, "ack", {}), (0.1, "result", {"ok": True, "data": {"content": "x"}})]
		)
		self.read_file()
		self.finish(thread, errors)
		r = dx._raw_client()
		self.assertEqual(r.exists(dx._k(dx._result_key(self.call_id))), 0)
		self.assertEqual(r.exists(dx._result_key(self.call_id)), 0)  # never used unprefixed
		self.assertEqual(r.exists(dx._k(dx._request_key(self.call_id))), 0)
		self.assertGreater(r.ttl(dx._k(dx._done_key(self.call_id))), 0)
		self.assertGreater(r.ttl(dx._k(dx._final_key(self.user, self.run_name, self.call_id))), 0)

	def test_event_list_is_written_with_the_site_prefix_and_a_ttl(self):
		"""Producer side: the list a desktop event lands in is exactly the key the waiter
		reads (prefixed), and always has an expiry."""
		dx._setex(
			dx._request_key(self.call_id),
			{"user": self.user, "executor_id": self.exec_id, "request": {"call_id": self.call_id}},
			60,
		)
		out = h.submit_desktop_tool_event(
			call_id=self.call_id, executor_id=self.exec_id, kind="ack", payload={}
		)
		self.assertEqual(out["status"], "recorded")
		r = dx._raw_client()
		key = dx._k(dx._result_key(self.call_id))
		try:
			self.assertEqual(r.llen(key), 1)
			self.assertGreater(r.ttl(key), 0)
			self.assertEqual(r.exists(dx._result_key(self.call_id)), 0)
		finally:
			dx._delete(dx._request_key(self.call_id), dx._result_key(self.call_id))

	def test_approval_flow_longer_than_the_5s_redis_socket_timeout(self):
		"""ack, approval_pending, then the user takes ~7 s: would raise TimeoutError (mapped to
		cache_unavailable) with a single long BLPOP on the 5 s cache connection."""
		thread, errors, _ = self.play_desktop(
			[
				(0.3, "ack", {}),
				(0.3, "approval_pending", {}),
				(7.0, "result", {"ok": True, "data": {"content": "approved"}}),
			]
		)
		started = time.monotonic()
		out = self.read_file()
		elapsed = time.monotonic() - started
		self.finish(thread, errors)
		self.assertEqual(out["data"]["content"], "approved", out)
		self.assertGreater(elapsed, 6.5)

	def test_slow_ack_longer_than_the_5s_redis_socket_timeout(self):
		thread, errors, _ = self.play_desktop(
			[(6.5, "ack", {}), (0.3, "result", {"ok": True, "data": {"content": "late"}})]
		)
		out = self.read_file()
		self.finish(thread, errors)
		self.assertEqual(out["data"]["content"], "late", out)

	def test_desktop_reported_error_reaches_the_model(self):
		thread, errors, _ = self.play_desktop(
			[(0.1, "ack", {}), (0.1, "error", {"code": "denied_by_user", "message": "User said no"})]
		)
		out = self.read_file()
		self.finish(thread, errors)
		self.assertEqual(out["error"]["message"], "User said no")
		self.assertEqual(out["error"]["code"], "denied_by_user")

	def test_offline_lease_fails_fast_without_waiting(self):
		h.unregister_desktop_executor(executor_id=self.exec_id)
		started = time.monotonic()
		out = self.read_file()
		self.assertLess(time.monotonic() - started, 2)
		self.assertEqual(out["error"]["code"], "desktop_offline")
		self.assertIn("not connected", out["error"]["message"])
		self.assertEqual(h.list_pending_desktop_tool_calls(executor_id=self.exec_id), [])

	def test_run_phase_timeout_when_desktop_acks_then_goes_silent(self):
		thread, errors, _ = self.play_desktop([(0.1, "ack", {})])
		ctx = dw._validate_executor_context(self.exec_id, h.FP, self.user, self.run_name, self.pin())
		started = time.monotonic()
		res = dx.dispatch("fs.read", {"path": "a.txt"}, ctx, call_id=self.call_id, timeout_ms=1500)
		elapsed = time.monotonic() - started
		self.finish(thread, errors)
		self.assertEqual(res["error"]["code"], "timeout")
		self.assertGreater(elapsed, 1.4)
		self.assertLess(elapsed, 6)

	def test_lease_removed_mid_request_is_seen_by_the_next_call(self):
		"""Lease reads must not be served from the per-request frappe.local.cache."""
		thread, errors, _ = self.play_desktop(
			[(0.1, "ack", {}), (0.1, "result", {"ok": True, "data": {"content": "one"}})]
		)
		self.assertEqual(self.read_file()["data"]["content"], "one")
		self.finish(thread, errors)
		self.assertTrue(dx.is_lease_live(self.exec_id))  # warm any local caching
		self.assertIsNotNone(dx.resolve_desktop_ctx(self.exec_id, user=self.user))

		dx._delete(dx._lease_key(self.exec_id))  # expiry / unregister from another process
		self.assertFalse(dx.is_lease_live(self.exec_id))
		self.assertIsNone(dx.resolve_desktop_ctx(self.exec_id, user=self.user))
		out = self.read_file(call_id=f"{self.call_id}-2")
		self.assertEqual(out["error"]["code"], "desktop_offline")

	def test_pinned_fingerprint_is_compared_with_the_live_workspace(self):
		self.register(fingerprint="ffffffffffffffff")  # user switched workspace after the send
		started = time.monotonic()
		out = self.read_file()
		self.assertLess(time.monotonic() - started, 2)
		self.assertEqual(out["error"]["code"], "workspace_changed")

	def test_other_users_lease_is_not_reachable(self):
		frappe.set_user(self.other)
		with self.assertRaises(frappe.PermissionError):
			h.list_pending_desktop_tool_calls(executor_id=self.exec_id)
		with self.assertRaises(frappe.PermissionError):
			self.read_file(_dx_user=self.other)

	# H1: a call id cached for one run is never served to another run of the same user
	def test_foreign_run_cannot_read_another_runs_cached_result(self):
		thread, errors, _ = self.play_desktop(
			[(0.1, "ack", {}), (0.1, "result", {"ok": True, "data": {"content": "run-A-secret"}})]
		)
		self.assertEqual(self.read_file()["data"]["content"], "run-A-secret")
		self.finish(thread, errors)
		run_b = h.make_run(self.user, h.desktop_pin(self.exec_id, self.user))
		self._docs.append(("Agent Run", run_b))
		frappe.set_user(self.user)
		with mock.patch.object(dx, "ACK_TIMEOUT_S", 1):
			out = self.read_file(agent_run_id=run_b)  # same call id, other run
		self.assertFalse(out["ok"])
		self.assertEqual(out["error"]["code"], "desktop_unreachable")  # it really ran (and nobody answered)
		# the original run still dedupes
		self.assertEqual(self.read_file()["data"]["content"], "run-A-secret")

	# M1: worker-side pin verification against a REAL run row
	def test_pin_naming_another_users_live_lease_is_dropped_for_a_run_owned_by_someone_else(self):
		victim_exec = f"exec-victim-{frappe.generate_hash(length=8)}"
		frappe.set_user(self.other)
		h.register_desktop_executor(
			executor_id=victim_exec, protocol_version=1, workspace=h.workspace(), capabilities=CAPS
		)
		try:
			# attacker (self.user) owns a run whose forged runtime_context pins the victim's live lease
			forged = h.make_run(self.user, h.desktop_pin(victim_exec, self.other))
			self._docs.append(("Agent Run", forged))
			run_doc = frappe.get_doc("Agent Run", forged)
			kwargs = ai._build_execution_kwargs(run_doc, frappe.parse_json(run_doc.runtime_context))
			self.assertIsNone(kwargs["desktop_ctx"])
			# a pin naming the owner's OWN executor but another user as `user` is dropped too
			forged2 = h.make_run(self.user, h.desktop_pin(self.exec_id, self.other))
			self._docs.append(("Agent Run", forged2))
			run_doc2 = frappe.get_doc("Agent Run", forged2)
			self.assertIsNone(
				ai._build_execution_kwargs(run_doc2, frappe.parse_json(run_doc2.runtime_context))["desktop_ctx"]
			)
		finally:
			frappe.set_user(self.other)
			h.unregister_desktop_executor(executor_id=victim_exec)
			frappe.set_user(self.user)

	def test_honest_pin_is_kept_for_the_run_owner(self):
		run_doc = frappe.get_doc("Agent Run", self.run_name)
		kwargs = ai._build_execution_kwargs(run_doc, frappe.parse_json(run_doc.runtime_context))
		self.assertEqual(kwargs["desktop_ctx"]["executor_id"], self.exec_id)
		self.assertEqual(kwargs["desktop_ctx"]["user"], self.user)
		self.assertEqual(kwargs["desktop_ctx"]["fingerprint"], h.FP)

	# M2 (decision: resolve from the run OWNER, keep the tools) - queued drain as Administrator
	def test_queued_run_drained_as_administrator_resolves_from_the_owner_and_can_call(self):
		run_doc = frappe.get_doc("Agent Run", self.run_name)
		context = frappe.parse_json(run_doc.runtime_context)
		frappe.set_user("Administrator")  # what the stale-run sweeper's drain job runs as
		kwargs = ai._build_execution_kwargs(run_doc, context)
		self.assertEqual(kwargs["desktop_ctx"]["user"], self.user)
		# the handler accepts the run (owner == pinned user) even though the session user differs
		prepared = dw.handle_read_file.prepare(
			path="a.txt",
			_dx_executor_id=self.exec_id,
			_dx_fingerprint=h.FP,
			_dx_user=self.user,
			_dx_pin=self.pin(),
			agent_run_id=self.run_name,
			call_id=self.call_id,
		)
		self.assertEqual(prepared["ctx"]["user"], self.user)
		with mock.patch.object(dx, "ACK_TIMEOUT_S", 1):
			out = dw.handle_read_file.execute(prepared)
		# got as far as publishing and waiting for the desktop: no permission or lease failure
		self.assertEqual(out["error"]["code"], "desktop_unreachable")

	def test_another_non_admin_session_still_cannot_use_the_run(self):
		frappe.set_user(self.other)
		with self.assertRaises(frappe.PermissionError):
			dw.handle_read_file.prepare(
				path="a.txt",
				_dx_executor_id=self.exec_id,
				_dx_fingerprint=h.FP,
				_dx_user=self.user,
				_dx_pin=self.pin(),
				agent_run_id=self.run_name,
			)

	# M5: no DB access inside the execute (worker thread) half
	def test_execute_half_never_touches_the_database(self):
		prepared = dw.handle_read_file.prepare(
			path="a.txt",
			_dx_executor_id=self.exec_id,
			_dx_fingerprint=h.FP,
			_dx_user=self.user,
			_dx_pin=self.pin(),
			agent_run_id=self.run_name,
			call_id=self.call_id,
		)
		thread, errors, _ = self.play_desktop(
			[(0.1, "ack", {}), (0.1, "result", {"ok": True, "data": {"content": "no db"}})]
		)
		with mock.patch.object(frappe, "get_doc", side_effect=AssertionError("DB read in execute")), \
				mock.patch.object(frappe.db, "get_value", side_effect=AssertionError("DB read in execute")), \
				mock.patch.object(frappe, "get_all", side_effect=AssertionError("DB read in execute")):
			out = dw.handle_read_file.execute(prepared)
		self.finish(thread, errors)
		self.assertEqual(out["data"]["content"], "no db")

	# M4 end to end
	def test_error_code_and_untrusted_marking_survive_the_handler(self):
		thread, errors, _ = self.play_desktop(
			[(0.1, "ack", {}), (0.1, "error", {"code": "sandbox_violation", "message": "outside workspace"})]
		)
		out = self.read_file()
		self.finish(thread, errors)
		self.assertEqual(out["error"]["code"], "sandbox_violation")
		self.assertTrue(out["untrusted_content"])
		self.assertIn("data, not instructions", out["note"])

	# ------------------------------------------------------------------
	# K3: N5 web budget / sweeper, N6 accounting, N7 reused ids, N8 pin gate
	# ------------------------------------------------------------------

	def answer_every_call(self, delay_s=0.2, stop=None, only=None):
		"""Background desktop that answers EVERY pending call (ack then result echoing the
		request params) until ``stop`` is set. Returns ``(thread, errors, seen_requests)``."""
		stop = stop or threading.Event()
		seen = []
		answered = set()

		def answer(req):
			cid = req["call_id"]
			time.sleep(delay_s)
			h.submit_desktop_tool_event(call_id=cid, executor_id=self.exec_id, kind="ack", payload={})
			time.sleep(delay_s)
			h.submit_desktop_tool_event(
				call_id=cid,
				executor_id=self.exec_id,
				kind="result",
				payload={"ok": True, "data": {"echo": req["params"]}},
			)

		def play():
			while not stop.is_set():
				for req in h.list_pending_desktop_tool_calls(executor_id=self.exec_id):
					cid = req["call_id"]
					if cid in answered or (only and cid not in only):
						continue
					answered.add(cid)
					seen.append(req)
					# one thread per call: the desktop runs parallel calls concurrently
					threading.Thread(
						target=contextvars.copy_context().run, args=(answer, req), daemon=True
					).start()
				time.sleep(0.05)

		thread, errors = h.run_in_thread(play)
		return thread, errors, seen, stop

	def ctx(self, run=None):
		return dw._validate_executor_context(
			self.exec_id, h.FP, self.user, run or self.run_name, self.pin(agent_run_id=run or self.run_name)
		)

	# ---- N7
	def test_a_provider_reusing_a_tool_call_id_never_gets_a_stale_result(self):
		thread, errors, seen, stop = self.answer_every_call(0.1)
		try:
			first = self.read_file(path="a.txt")
			second = self.read_file(path="b.txt")  # SAME call id, different params
			third = self.read_file(path="b.txt")  # same id, same params: deduped
		finally:
			stop.set()
			thread.join(10)
		self.assertEqual(errors, [])
		self.assertEqual(first["data"], {"echo": {"path": "a.txt", "offset": 0, "limit": 2000}})
		self.assertEqual(second["data"]["echo"]["path"], "b.txt")  # not turn 1's a.txt
		self.assertEqual(third, second)
		self.assertEqual([r["params"]["path"] for r in seen], ["a.txt", "b.txt"])  # third never sent
		self.assertEqual(seen[0]["call_id"], self.call_id)
		self.assertNotEqual(seen[1]["call_id"], self.call_id)  # the desktop cannot serve a stale one either
		self.assertTrue(seen[1]["call_id"].startswith(self.call_id + "."))

	def test_identical_params_under_a_reused_id_execute_per_invocation_but_a_redelivery_dedupes(self):
		"""N7: a provider reusing tool_call_id "0" with IDENTICAL params in two invocations must run
		both (no stale result); redelivering the SAME invocation (same nonce) must not run again."""
		self.addCleanup(dx._delete, dx._ledger_key(self.run_name))
		inv1 = dx.derive_call_id(self.run_name, "0", dx.mint_invocation_nonce())
		inv2 = dx.derive_call_id(self.run_name, "0", dx.mint_invocation_nonce())
		self.assertNotEqual(inv1, inv2)
		thread, errors, seen, stop = self.answer_every_call(0.1)
		try:
			# each call is issued with a distinct nonce, like sdk_tools does per invocation
			first = self.read_file(path="a.txt", call_id=inv1)
			second = self.read_file(path="a.txt", call_id=inv2)
			redelivered = self.read_file(path="a.txt", call_id=inv2)
		finally:
			stop.set()
			thread.join(10)
		self.assertEqual(errors, [])
		self.assertTrue(first["ok"] and second["ok"])
		self.assertEqual([r["call_id"] for r in seen], [inv1, inv2])  # two dispatches published
		self.assertEqual(redelivered, second)  # same invocation: served from its own result, not sent

	def test_sdk_invocations_with_the_same_tool_call_id_get_distinct_wire_ids(self):
		import json as _json

		from huf.ai import sdk_tools

		ids = []
		for _i in range(2):
			args = {"path": "a.txt"}
			sdk_tools._pin_run_identity(
				args,
				mock.Mock(context={"agent_run_id": self.run_name}, tool_call_id="0"),
				dx.mint_invocation_nonce(),
			)
			ids.append(args.get("call_id"))
		self.assertIsNotNone(ids[0])
		self.assertNotEqual(ids[0], ids[1])
		self.assertTrue(all(i.startswith(dx.derive_call_id(self.run_name, "0")) for i in ids))
		_json.dumps(ids)

	# ---- N8
	def test_handlers_refuse_a_call_that_was_not_pinned_by_the_run(self):
		with self.assertRaises(frappe.PermissionError):
			dw.handle_read_file(
				path="a.txt",
				_dx_executor_id=self.exec_id,
				_dx_fingerprint=h.FP,
				_dx_user=self.user,
				agent_run_id=self.run_name,
				call_id=self.call_id,
			)  # self-chosen ids, no pin (what a flow / procedure / API caller can do)
		self.assertEqual(h.list_pending_desktop_tool_calls(executor_id=self.exec_id), [])

	def test_handlers_refuse_a_forged_or_borrowed_pin(self):
		for bad in ("", "0" * 64, "not-a-token", None, 12345):
			with self.assertRaises(frappe.PermissionError, msg=repr(bad)):
				self.read_file(_dx_pin=bad)
		other_run = h.make_run(self.user, h.desktop_pin(self.exec_id, self.user))
		self._docs.append(("Agent Run", other_run))
		frappe.set_user(self.user)
		# a token minted for another run of the same user does not work for this one
		with self.assertRaises(frappe.PermissionError):
			self.read_file(_dx_pin=dw.issue_pin_token(other_run, self.exec_id, self.user))
		# nor one minted for another executor
		with self.assertRaises(frappe.PermissionError):
			self.read_file(_dx_pin=dw.issue_pin_token(self.run_name, "exec-other-0001", self.user))

	def test_a_pinned_run_call_is_accepted(self):
		thread, errors, results = self.play_desktop([(0.1, "ack", {}), (0.1, "result", {"ok": True, "data": {"content": "ok"}})])
		out = self.read_file()
		self.finish(thread, errors)
		self.assertEqual(out["data"]["content"], "ok")

	def test_a_flow_or_procedure_cannot_reach_the_handlers_through_invoke_tool(self):
		import asyncio

		from huf.ai.tool_invocation import invoke_tool

		frappe.set_user("Administrator")
		row = frappe.db.get_value(
			"Agent Tool Function", {"function_path": "huf.ai.tools.desktop_workspace.handle_read_file"}, "tool_name"
		)
		if not row:
			self.skipTest("Desktop Workspace tool rows are not synced on this site")
		frappe.set_user(self.user)
		result = asyncio.run(
			invoke_tool(
				row,
				{
					"path": "a.txt",
					"_dx_executor_id": self.exec_id,
					"_dx_fingerprint": h.FP,
					"_dx_user": self.user,
					"agent_run_id": self.run_name,
					"call_id": "self-chosen-by-a-flow",
				},
			)
		)
		self.assertFalse(result.success)
		self.assertTrue(result.denied)
		self.assertEqual(h.list_pending_desktop_tool_calls(executor_id=self.exec_id), [])

	# ---- N5 web budget
	def test_web_request_with_a_used_up_budget_gets_a_structured_error_without_waiting(self):
		dx._budget_charge(self.run_name, dx.web_wait_budget_s() - 1)
		self.addCleanup(dx._delete, dx._budget_key(self.run_name))
		started = time.monotonic()
		with mock.patch.object(dw, "_in_web_request", return_value=True):
			out = self.read_file()
		self.assertLess(time.monotonic() - started, 2)
		self.assertEqual(out["error"]["code"], "web_budget_exhausted")
		self.assertEqual(h.list_pending_desktop_tool_calls(executor_id=self.exec_id), [])
		# the very same state is fine for a queued (RQ) run
		thread, errors, _ = self.play_desktop([(0.1, "ack", {}), (0.1, "result", {"ok": True, "data": {"content": "q"}})])
		with mock.patch.object(dw, "_in_web_request", return_value=False):
			queued = self.read_file(call_id=self.call_id)
		self.finish(thread, errors)
		self.assertEqual(queued["data"]["content"], "q")

	def test_web_call_that_outlives_the_web_budget_is_cancelled_and_reported(self):
		self.addCleanup(dx._delete, dx._budget_key(self.run_name))
		cancels = []
		real_cancel = dx._publish_cancel
		with mock.patch.dict(frappe.conf, {"huf_desktop_web_budget_s": 10}), \
				mock.patch.object(dw, "_in_web_request", return_value=True), \
				mock.patch.object(dx, "_publish_cancel", side_effect=lambda *a: (cancels.append(a), real_cancel(*a))):
			thread, errors, _ = self.play_desktop([(0.1, "ack", {})])  # acks, then the user never answers
			started = time.monotonic()
			out = self.read_file()
			elapsed = time.monotonic() - started
		self.finish(thread, errors)
		self.assertEqual(out["error"]["code"], "web_budget_exhausted", out)
		self.assertIn("cancelled", out["error"]["message"])
		self.assertLess(elapsed, 16)  # ~10 s budget, not the 20 s call timeout
		self.assertEqual([c[1] for c in cancels], [self.call_id])

	# ---- N5 sweeper
	def _backdate(self, run_name):
		frappe.db.set_value("Agent Run", run_name, "modified", "2000-01-01 00:00:00", update_modified=False)
		frappe.db.commit()

	def test_sweeper_fails_a_stale_run_that_already_changed_the_workspace_instead_of_requeueing_it(self):
		mutated = h.make_run(self.user, h.desktop_pin(self.exec_id, self.user))
		readonly = h.make_run(self.user, h.desktop_pin(self.exec_id, self.user))
		self._docs.extend([("Agent Run", mutated), ("Agent Run", readonly)])
		frappe.set_user(self.user)
		self.addCleanup(dx._delete, dx._ledger_key(mutated), dx._ledger_key(readonly))
		thread, errors, seen, stop = self.answer_every_call(0.1)
		try:
			ctx_m, ctx_r = self.ctx(mutated), self.ctx(readonly)
			self.assertTrue(dx.dispatch("fs.write", {"path": "a", "content": "x"}, ctx_m, call_id="m-1", agent_run_id=mutated)["ok"])
			self.assertTrue(dx.dispatch("fs.read", {"path": "a"}, ctx_r, call_id="r-1", agent_run_id=readonly)["ok"])
		finally:
			stop.set()
			thread.join(10)
		self.assertTrue(dx.run_executed_mutations(mutated))
		self.assertFalse(dx.run_executed_mutations(readonly))
		frappe.set_user("Administrator")
		for name in (mutated, readonly):
			self._backdate(name)
		with mock.patch.object(ai, "_enqueue_drain") as drain:
			ai.recover_stalled_agent_runs()
		frappe.db.commit()
		mutated_doc = frappe.db.get_value("Agent Run", mutated, ["status", "error_message"], as_dict=True)
		readonly_status = frappe.db.get_value("Agent Run", readonly, "status")
		self.assertEqual(mutated_doc.status, "Failed")  # NOT re-run: its write would repeat
		self.assertIn("already changed the desktop workspace", mutated_doc.error_message)
		self.assertEqual(readonly_status, "Queued")  # nothing was changed: safe to run again
		self.assertTrue(drain.called)

	def test_drain_of_a_rerun_takes_a_replay_snapshot_of_the_earlier_attempt(self):
		self.addCleanup(dx._delete, dx._ledger_key(self.run_name), dx._replay_key(self.run_name))
		thread, errors, seen, stop = self.answer_every_call(0.1)
		try:
			first = dx.dispatch("fs.write", {"path": "a", "content": "x"}, self.ctx(), call_id="w-1", agent_run_id=self.run_name)
			self.assertTrue(first["ok"])
			run_doc = frappe.get_doc("Agent Run", self.run_name)
			with mock.patch.object(ai, "_execute_agent_run", return_value={"ok": True}), \
					mock.patch.object(ai, "_build_execution_kwargs", return_value={"prompt": None}), \
					mock.patch.object(ai, "_link_preexisting_user_message"), \
					mock.patch.object(ai, "safe_commit"):
				ai._drain_run(run_doc, "test-lock")
			# the model of the re-run repeats the write under a new tool_call id: not executed again
			again = dx.dispatch("fs.write", {"path": "a", "content": "x"}, self.ctx(), call_id="w-NEW", agent_run_id=self.run_name)
		finally:
			stop.set()
			thread.join(10)
		self.assertEqual(errors, [])
		self.assertEqual(again, first)
		self.assertEqual(len(seen), 1)

	def test_sweeper_fails_closed_when_the_ledger_cannot_be_read_for_a_desktop_run(self):
		desktop_run = h.make_run(self.user, h.desktop_pin(self.exec_id, self.user))
		plain_run = h.make_run(self.user, {})
		self._docs.extend([("Agent Run", desktop_run), ("Agent Run", plain_run)])
		frappe.set_user("Administrator")
		for name in (desktop_run, plain_run):
			self._backdate(name)
		with mock.patch.object(dx, "_raw_client", side_effect=RuntimeError("redis down")), \
				mock.patch.object(ai, "_enqueue_drain"):
			ai.recover_stalled_agent_runs()
		frappe.db.commit()
		doc = frappe.db.get_value("Agent Run", desktop_run, ["status", "error_message"], as_dict=True)
		self.assertEqual(doc.status, "Failed")  # NOT re-queued
		self.assertIn("could not be read", doc.error_message)
		# a run that is not pinned to a desktop is unaffected by the desktop ledger
		self.assertEqual(frappe.db.get_value("Agent Run", plain_run, "status"), "Queued")

	def test_rerun_refuses_a_different_mutating_call_while_recorded_ones_are_unreplayed(self):
		self.addCleanup(dx._delete, dx._ledger_key(self.run_name), dx._replay_key(self.run_name))
		thread, errors, seen, stop = self.answer_every_call(0.1)
		try:
			first = dx.dispatch("fs.write", {"path": "a", "content": "x"}, self.ctx(), call_id=f"w-1-{self.call_id}", agent_run_id=self.run_name)
			self.assertTrue(first["ok"], first)
			self.assertEqual(dx.begin_run_attempt(self.run_name), 1)
			# the re-run's model rephrases: different params, and the first write was already sent
			diverged = dx.dispatch("fs.write", {"path": "a", "content": "y"}, self.ctx(), call_id=f"w-2-{self.call_id}", agent_run_id=self.run_name)
			read = dx.dispatch("fs.read", {"path": "a"}, self.ctx(), call_id=f"r-1-{self.call_id}", agent_run_id=self.run_name)
			replay = dx.dispatch("fs.write", {"path": "a", "content": "x"}, self.ctx(), call_id=f"w-3-{self.call_id}", agent_run_id=self.run_name)
			after = dx.dispatch("fs.write", {"path": "b", "content": "z"}, self.ctx(), call_id=f"w-4-{self.call_id}", agent_run_id=self.run_name)
		finally:
			stop.set()
			thread.join(10)
		self.assertEqual(errors, [])
		self.assertFalse(diverged["ok"])
		self.assertEqual(diverged["error"]["code"], "already_dispatched")
		self.assertIn("unknown", diverged["error"]["message"])
		self.assertTrue(read["ok"])  # reads are never refused
		self.assertEqual(replay, first)  # the identical call is answered from the record
		self.assertTrue(after["ok"])  # caught up with the record: new work may proceed
		self.assertEqual([r["op"] for r in seen], ["fs.write", "fs.read", "fs.write"])

	# ---- N6
	def test_parallel_calls_are_charged_by_wall_clock_once(self):
		self.addCleanup(dx._delete, dx._budget_key(self.run_name))
		thread, errors, seen, stop = self.answer_every_call(1.0)  # each call takes ~2 s on the desktop
		results = []
		try:
			ctx = self.ctx()

			def one(i):
				results.append(dx.dispatch("fs.read", {"path": f"f{i}"}, ctx, call_id=f"par-{i}", agent_run_id=self.run_name))

			workers = [h.run_in_thread(lambda i=i: one(i)) for i in range(3)]
			for t, errs in workers:
				t.join(30)
				self.assertEqual(errs, [])
		finally:
			stop.set()
			thread.join(10)
		self.assertEqual(len(results), 3)
		self.assertTrue(all(r["ok"] for r in results), results)
		used = dx._budget_used_s(self.run_name)
		self.assertGreater(used, 1.5)
		self.assertLess(used, 5.5)  # per-call charging would have booked ~6 s or more
		r = dx._raw_client()
		self.assertEqual(r.zcard(dx._k(dx._inflight_executor_key(self.exec_id))), 0)
		self.assertEqual(r.zcard(dx._k(dx._inflight_user_key(self.user))), 0)

	def test_slots_leaked_by_a_dead_worker_self_heal(self):
		r = dx._raw_client()
		xkey = dx._k(dx._inflight_executor_key(self.exec_id))
		self.addCleanup(r.delete, xkey)
		now = dx._now_ms()
		r.zadd(xkey, {f"dead-{i}": now - 1000 for i in range(dx.MAX_INFLIGHT_PER_EXECUTOR)})  # leases lapsed
		thread, errors, _ = self.play_desktop([(0.1, "ack", {}), (0.1, "result", {"ok": True, "data": {"content": "healed"}})])
		out = self.read_file()
		self.finish(thread, errors)
		self.assertEqual(out["data"]["content"], "healed")
		self.assertEqual(r.zcard(xkey), 0)
		# holders whose lease is alive still count
		r.zadd(xkey, {f"live-{i}": now + 60_000 for i in range(dx.MAX_INFLIGHT_PER_EXECUTOR)})
		busy = self.read_file(call_id=f"{self.call_id}-busy")
		self.assertEqual(busy["error"]["code"], "busy")
		self.assertEqual(h.list_pending_desktop_tool_calls(executor_id=self.exec_id), [])

	def test_a_queue_job_shares_one_wait_budget_across_the_runs_it_drains(self):
		conversation = f"CONV-K3-{frappe.generate_hash(length=6)}"
		seen = {}

		def fake_next(conv):
			seen["job"] = dx._current_job_id(conv)
			return None  # nothing to drain

		with mock.patch.object(ai, "_next_queued_run", side_effect=fake_next), \
				mock.patch.object(ai, "_has_queued_runs", return_value=False):
			ai._run_queued_agent(conversation_id=conversation)
		self.assertTrue(seen["job"])  # a job budget id existed while the job drained
		self.assertIsNone(dx._current_job_id(conversation))  # and is gone when the job ends
