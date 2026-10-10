"""Unit tests for huf.ai.run_control (mocked; no DB)."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe

from huf.ai import run_control as rc


class TestRunControl(unittest.TestCase):
	def setUp(self):
		self.cache = MagicMock()
		self.store = {}
		self.cache.set_value.side_effect = lambda k, v, **kw: self.store.__setitem__(k, v)
		self.cache.get_value.side_effect = lambda k: self.store.get(k)
		self.cache.exists.side_effect = lambda k: 1 if k in self.store else 0
		self.patches = [
			patch.object(rc, "_cache", return_value=self.cache),
			patch.object(rc.frappe, "get_roles", return_value=["Desk User"]),
		]
		for p in self.patches:
			p.start()
		self.addCleanup(lambda: [p.stop() for p in self.patches])

	def _row(self, status="Started", owner="a@x.com"):
		return SimpleNamespace(owner=owner, conversation="C1", status=status)

	def _user(self, user):
		return patch.object(rc.frappe, "session", SimpleNamespace(user=user), create=True)

	def _db(self, row, conv_owner="a@x.com"):
		db = MagicMock()
		db.get_value.side_effect = lambda dt, *a, **k: row if dt == "Agent Run" else conv_owner
		return patch.object(rc.frappe, "db", db, create=True)

	def test_owner_sets_marker_and_idempotent(self):
		with self._user("a@x.com"), self._db(self._row()):
			r1 = rc.cancel_agent_run("R1")
			r2 = rc.cancel_agent_run("R1")
		self.assertTrue(r1["cancel_requested"])
		self.assertEqual(r1, r2)
		self.assertTrue(rc.is_run_cancelled("R1"))
		self.assertFalse(rc.is_run_cancelled("R2"))

	def test_other_user_denied(self):
		with self._user("b@x.com"), self._db(self._row()):
			with self.assertRaises(frappe.PermissionError):
				rc.cancel_agent_run("R1")
		self.assertFalse(rc.is_run_cancelled("R1"))

	def test_finished_run_not_marked(self):
		with self._user("a@x.com"), self._db(self._row("Success")):
			r = rc.cancel_agent_run("R1")
		self.assertFalse(r["cancel_requested"])
		self.assertFalse(rc.is_run_cancelled("R1"))

	def test_missing_run(self):
		with patch.object(rc.frappe, "db", MagicMock(**{"get_value.return_value": None}), create=True):
			with self.assertRaises(frappe.PermissionError):
				rc.cancel_agent_run("nope")

	def test_loop_observes_cancel(self):
		# The stream loop polls is_run_cancelled(run_name) per chunk.
		self.store[rc._key("R1")] = 1
		seen = []
		for i, _chunk in enumerate(["a", "b", "c"]):
			if rc.is_run_cancelled("R1"):
				break
			seen.append(i)
		self.assertEqual(seen, [])


class TestCancelFinalizesNotLiveRun(TestRunControl):
	"""Stop after the client tore down the stream: nothing polls the marker, so cancel finalizes."""

	def _db2(self, row, final_status="Failed"):
		db = MagicMock()

		def gv(dt, name, field=None, *a, **k):
			if dt == "Agent Run" and field == "status":
				return final_status
			return row if dt == "Agent Run" else "a@x.com"

		db.get_value.side_effect = gv
		return patch.object(rc.frappe, "db", db, create=True)

	def test_not_live_started_run_is_finalized(self):
		with self._user("a@x.com"), self._db2(self._row("Started")), patch(
			"huf.ai.agent_integration._guarded_fail_started_run"
		) as fail, patch.object(rc, "mark_cancelled_tool_calls") as mark:
			r = rc.cancel_agent_run("R1")
		fail.assert_called_once_with("R1", rc.CANCELLED_BY_USER)
		mark.assert_called_once()
		self.assertTrue(r["cancel_requested"])
		self.assertEqual(r["status"], "Failed")
		self.assertTrue(rc.is_run_cancelled("R1"))

	def test_immediate_finalize_error_is_logged_not_raised(self):
		logger = MagicMock()
		with self._user("a@x.com"), self._db2(self._row("Started")), patch(
			"huf.ai.agent_integration._guarded_fail_started_run", side_effect=RuntimeError("boom")
		), patch.object(rc, "mark_cancelled_tool_calls"), patch.object(rc.frappe, "logger", return_value=logger):
			r = rc.cancel_agent_run("R1")
		self.assertEqual(r["run_id"], "R1")
		messages = [c.args[0] for c in logger.warning.call_args_list]
		self.assertIn("cancel_agent_run finalize failed for R1: RuntimeError('boom')", messages)

	def test_live_run_only_sets_marker(self):
		rc.touch_run_alive("R1")
		with self._user("a@x.com"), self._db2(self._row("Started")), patch(
			"huf.ai.agent_integration._guarded_fail_started_run"
		) as fail, patch.object(rc, "mark_cancelled_tool_calls") as mark:
			r = rc.cancel_agent_run("R1")
		fail.assert_not_called()
		mark.assert_not_called()
		self.assertTrue(r["cancel_requested"])
		self.assertEqual(r["status"], "Started")
		self.assertTrue(rc.is_run_cancelled("R1"))

	def _aged_row(self, age_s):
		from frappe.utils import add_to_date, now_datetime

		row = self._row("Started")
		row.creation = add_to_date(now_datetime(), seconds=-age_s)
		return row

	def test_young_not_live_run_only_sets_marker(self):
		with self._user("a@x.com"), self._db2(self._aged_row(3), "Started"), patch(
			"huf.ai.agent_integration._guarded_fail_started_run"
		) as fail, patch.object(rc, "mark_cancelled_tool_calls") as mark:
			r = rc.cancel_agent_run("R1")
		fail.assert_not_called()
		mark.assert_not_called()
		self.assertEqual(r["status"], "Started")
		self.assertTrue(rc.is_run_cancelled("R1"))

	def test_old_not_live_run_is_finalized(self):
		with self._user("a@x.com"), self._db2(self._aged_row(120)), patch(
			"huf.ai.agent_integration._guarded_fail_started_run", return_value=True
		) as fail, patch.object(rc, "mark_cancelled_tool_calls") as mark:
			r = rc.cancel_agent_run("R1")
		fail.assert_called_once_with("R1", rc.CANCELLED_BY_USER)
		mark.assert_called_once()
		self.assertEqual(r["status"], "Failed")

	def test_lost_race_does_not_touch_tool_rows(self):
		with self._user("a@x.com"), self._db2(self._row("Started"), "Success"), patch(
			"huf.ai.agent_integration._guarded_fail_started_run", return_value=False
		), patch.object(rc, "mark_cancelled_tool_calls") as mark:
			r = rc.cancel_agent_run("R1")
		mark.assert_not_called()
		self.assertEqual(r["status"], "Success")

	def test_guarded_fail_returns_false_when_not_started(self):
		from huf.ai import agent_integration as ai

		db = MagicMock()
		db._cursor.rowcount = 0
		with patch.object(ai.frappe, "db", db, create=True), patch.object(ai, "now_datetime", return_value=0):
			self.assertFalse(ai._guarded_fail_started_run("R1", "x"))
		db._cursor.rowcount = 1
		with patch.object(ai.frappe, "db", db, create=True), patch.object(ai, "now_datetime", return_value=0):
			self.assertTrue(ai._guarded_fail_started_run("R1", "x"))

	def test_finished_run_is_noop(self):
		with self._user("a@x.com"), self._db2(self._row("Failed")), patch(
			"huf.ai.agent_integration._guarded_fail_started_run"
		) as fail:
			r = rc.cancel_agent_run("R1")
		fail.assert_not_called()
		self.assertFalse(r["cancel_requested"])


class TestCancelRedisDown(TestCancelFinalizesNotLiveRun):
	# Redis-down variants; inherited tests are overridden to the failing-cache expectations below.
	"""Marker write failure is best-effort; Stop still ends old runs."""

	def setUp(self):
		super().setUp()
		self.cache.set_value.side_effect = ConnectionError("redis down")
		self.cache.exists.side_effect = ConnectionError("redis down")
		self.cache.get_value.side_effect = ConnectionError("redis down")

	test_not_live_started_run_is_finalized = test_live_run_only_sets_marker = None
	test_young_not_live_run_only_sets_marker = test_old_not_live_run_is_finalized = None
	test_lost_race_does_not_touch_tool_rows = test_guarded_fail_returns_false_when_not_started = None
	test_finished_run_is_noop = test_owner_sets_marker_and_idempotent = test_other_user_denied = None
	test_finished_run_not_marked = test_missing_run = test_loop_observes_cancel = None

	def test_old_run_finalized_without_marker(self):
		with self._user("a@x.com"), self._db2(self._row("Started")), patch(
			"huf.ai.agent_integration._guarded_fail_started_run", return_value=True
		) as fail, patch.object(rc, "mark_cancelled_tool_calls") as mark:
			r = rc.cancel_agent_run("R1")
		fail.assert_called_once_with("R1", rc.CANCELLED_BY_USER)
		mark.assert_called_once()
		self.assertTrue(r["cancel_requested"])
		self.assertEqual(r["status"], "Failed")

	def test_young_run_not_finalized_and_not_requested(self):
		with self._user("a@x.com"), self._db2(self._aged_row(3), "Started"), patch(
			"huf.ai.agent_integration._guarded_fail_started_run"
		) as fail:
			r = rc.cancel_agent_run("R1")
		fail.assert_not_called()
		self.assertFalse(r["cancel_requested"])
		self.assertEqual(r["status"], "Started")

	def test_lost_finalize_race_not_requested(self):
		with self._user("a@x.com"), self._db2(self._row("Started"), "Started"), patch(
			"huf.ai.agent_integration._guarded_fail_started_run", return_value=False
		), patch.object(rc, "mark_cancelled_tool_calls") as mark:
			r = rc.cancel_agent_run("R1")
		mark.assert_not_called()
		self.assertFalse(r["cancel_requested"])


class TestCancelRelabelsFreshDisconnect(TestRunControl):
	"""Stop landing just after the stream finalizer wrote 'Client disconnected'."""

	def _db3(self, status, message, age_s):
		from frappe.utils import add_to_date, now_datetime

		extra = SimpleNamespace(
			error_message=message, modified=add_to_date(now_datetime(), seconds=-age_s)
		)
		db = MagicMock()

		def gv(dt, name, field=None, *a, **k):
			if dt == "Agent Run":
				return extra if isinstance(field, list) and "error_message" in field else self._row(status)
			return "a@x.com"

		db.get_value.side_effect = gv
		self.db = db
		return patch.object(rc.frappe, "db", db, create=True)

	def test_fresh_disconnect_is_relabelled(self):
		with self._user("a@x.com"), self._db3("Failed", rc.CLIENT_DISCONNECTED, 2):
			r = rc.cancel_agent_run("R1")
		self.db.sql.assert_called_once()
		self.assertEqual(
			self.db.sql.call_args[0][1], (rc.CANCELLED_BY_USER, "R1", rc.CLIENT_DISCONNECTED)
		)
		self.assertEqual(r, {"run_id": "R1", "status": "Failed", "cancel_requested": True})

	def test_old_disconnect_unchanged(self):
		with self._user("a@x.com"), self._db3("Failed", rc.CLIENT_DISCONNECTED, 120):
			r = rc.cancel_agent_run("R1")
		self.db.sql.assert_not_called()
		self.assertFalse(r["cancel_requested"])

	def test_disconnect_window_is_15s(self):
		self.assertEqual(rc._DISCONNECT_RELABEL_WINDOW_S, 15)
		with self._user("a@x.com"), self._db3("Failed", rc.CLIENT_DISCONNECTED, 30):
			r = rc.cancel_agent_run("R1")
		self.db.sql.assert_not_called()
		self.assertFalse(r["cancel_requested"])

	def test_other_failed_message_unchanged(self):
		with self._user("a@x.com"), self._db3("Failed", "Some other error", 2):
			r = rc.cancel_agent_run("R1")
		self.db.sql.assert_not_called()
		self.assertFalse(r["cancel_requested"])

	def test_success_run_unchanged(self):
		with self._user("a@x.com"), self._db3("Success", rc.CLIENT_DISCONNECTED, 2):
			r = rc.cancel_agent_run("R1")
		self.db.sql.assert_not_called()
		self.assertFalse(r["cancel_requested"])


class TestIterWithCancelPoll(unittest.TestCase):
	def _run(self, coro):
		import asyncio

		return asyncio.run(coro)

	def test_passes_chunks_through(self):
		async def gen():
			yield {"a": 1}
			yield {"a": 2}

		async def go():
			return [c async for c in rc.iter_with_cancel_poll(gen(), "R", slice_s=0.05, cancelled=lambda _r: False)]

		self.assertEqual(self._run(go()), [{"a": 1}, {"a": 2}])

	def test_cancel_before_first_provider_call(self):
		started = []

		async def gen():
			started.append(1)
			yield {"a": 1}

		async def go():
			return [c async for c in rc.iter_with_cancel_poll(gen(), "R", slice_s=0.05, cancelled=lambda _r: True)]

		self.assertEqual(self._run(go()), [rc.CANCELLED])
		self.assertEqual(started, [])

	def test_cancel_during_provider_silence(self):
		import asyncio
		import time

		state = {"cancel": False, "closed": False}

		async def silent():
			try:
				await asyncio.sleep(30)
				yield {"a": 1}
			finally:
				state["closed"] = True

		async def flip():
			await asyncio.sleep(0.12)
			state["cancel"] = True

		async def go():
			t = asyncio.ensure_future(flip())
			out = [c async for c in rc.iter_with_cancel_poll(silent(), "R", slice_s=0.05, cancelled=lambda _r: state["cancel"])]
			await t
			return out

		t0 = time.monotonic()
		self.assertEqual(self._run(go()), [rc.CANCELLED])
		self.assertLess(time.monotonic() - t0, 3)
		self.assertTrue(state["closed"])


class TestRunControlReviewLows(unittest.TestCase):
	def test_missing_run_same_permission_error(self):
		with patch.object(rc.frappe, "db", MagicMock(**{"get_value.return_value": None}), create=True):
			with self.assertRaises(frappe.PermissionError):
				rc._assert_can_cancel("nope")

	def test_constant(self):
		self.assertEqual(rc.CANCELLED_BY_USER, "Cancelled by user")

	def test_outer_cancellation_reraised(self):
		import asyncio

		async def slow():
			await asyncio.sleep(30)
			yield 1

		async def main():
			async def consume():
				async for _ in rc.iter_with_cancel_poll(slow(), "R", slice_s=0.05, cancelled=lambda r: False):
					pass
			t = asyncio.ensure_future(consume())
			await asyncio.sleep(0.2)
			t.cancel()
			with self.assertRaises(asyncio.CancelledError):
				await t

		asyncio.run(main())

	def test_mark_cancelled_tool_calls(self):
		row = SimpleNamespace(name="TC1", tool="t", call_id="c1")
		row.get = lambda k, d=None: getattr(row, k, d)
		db = MagicMock()
		with patch.object(rc.frappe, "get_all", return_value=[row]), \
			patch.object(rc.frappe, "db", db, create=True), \
			patch("huf.ai.providers.litellm._publish_stream_tool_outcome") as pub:
			n = rc.mark_cancelled_tool_calls("R1", {"conversation_id": "C1"})
		self.assertEqual(n, 1)
		db.set_value.assert_called_once()
		self.assertEqual(db.set_value.call_args[0][2]["error_message"], "Cancelled by user")
		self.assertEqual(pub.call_args[0][1], {"id": "c1"})


class TestMarkCancelledPassThrough(unittest.TestCase):
	def test_user_and_checkpoint_forwarded_to_publish(self):
		row = SimpleNamespace(name="TC1", tool="t", call_id="c1")
		row.get = lambda k, d=None: getattr(row, k, d)
		with patch.object(rc.frappe, "get_all", return_value=[row]), \
			patch.object(rc.frappe, "db", MagicMock(), create=True), \
			patch("huf.ai.providers.litellm._publish_stream_tool_outcome") as pub:
			rc.mark_cancelled_tool_calls("R1", {"conversation_id": "C1"}, user="owner@x.com", checkpoint=False)
		self.assertEqual(pub.call_args.kwargs, {"user": "owner@x.com", "checkpoint": False})


class TestStaleSweep(unittest.TestCase):
	def test_select_skips_live_runs_and_uses_cutoff(self):
		captured = {}

		def fake_get_all(doctype, **kw):
			captured.update(kw)
			return [{"name": n, "conversation": None, "agent_orchestration": None, "execution_mode": "stream",
				"modified": None} for n in ("A", "B", "C")]

		with patch.object(rc.frappe, "get_all", fake_get_all), patch.object(
			rc.frappe, "conf", {"huf_stale_run_minutes": 30}, create=True
		):
			out = rc.select_stale_runs(now=__import__("datetime").datetime(2026, 1, 1, 12, 0), alive=lambda r: r == "B")
		self.assertEqual(out, ["A", "C"])
		self.assertEqual(captured["filters"]["status"], "Started")
		self.assertEqual(captured["filters"]["modified"][0], "<")
		self.assertEqual(captured["filters"]["modified"][1], __import__("datetime").datetime(2026, 1, 1, 11, 30))

	def test_default_minutes_is_15(self):
		with patch.object(rc.frappe, "conf", {}, create=True):
			self.assertEqual(rc.get_stale_run_minutes(), 15)

	def test_sweep_marks_failed_stale_run_and_closes_tools(self):
		db = MagicMock()
		db._cursor.rowcount = 1
		cache = MagicMock()
		cache.lock.return_value.acquire.return_value = True
		with patch.object(rc.frappe, "db", db, create=True), patch.object(
			rc, "_cache", return_value=cache
		), patch.object(rc, "select_stale_runs", return_value=["R1"]), patch.object(
			rc, "mark_cancelled_tool_calls"
		) as mtc, patch("frappe.utils.now_datetime", return_value="t"):
			self.assertEqual(rc.sweep_stale_runs(), ["R1"])
		args = db.sql.call_args[0]
		self.assertIn("status='Started'", args[0])
		self.assertEqual(args[1][0], "Stale run")
		mtc.assert_called_once_with("R1", message="Stale run", user=db.get_value.return_value, checkpoint=False)
		db.get_value.assert_called_with("Agent Run", "R1", "owner")

	def test_sweep_skips_when_lock_held(self):
		cache = MagicMock()
		cache.lock.return_value.acquire.return_value = False
		with patch.object(rc, "_cache", return_value=cache), patch.object(rc, "select_stale_runs") as sel:
			self.assertEqual(rc.sweep_stale_runs(), [])
		sel.assert_not_called()

	def test_live_marker_roundtrip_same_cache(self):
		store = {}
		cache = MagicMock()
		cache.set_value.side_effect = lambda k, v, **kw: store.__setitem__(k, v)
		cache.exists.side_effect = lambda k: 1 if k in store else 0
		with patch.object(rc, "_cache", return_value=cache):
			self.assertFalse(rc.is_run_alive("R"))
			rc.touch_run_alive("R")
			self.assertTrue(rc.is_run_alive("R"))


class TestRendererFinalizesOnDisconnect(unittest.TestCase):
	def test_renderer_acloses_async_gen_after_terminal_error_chunk(self):
		import inspect

		from huf.ai import agent_stream_renderer as r

		src = inspect.getsource(r)
		self.assertIn("async_gen.aclose()", src)


class TestMarkerBypassesRequestLocalCache(unittest.TestCase):
	def test_marker_set_after_a_miss_is_seen(self):
		"""Regression: frappe.cache().get_value memoizes a miss in frappe.local.cache for the whole
		request, so a long SSE stream never saw the cancel marker another request set later."""
		redis_keys = set()
		local_cache = {}
		cache = MagicMock()
		cache.exists.side_effect = lambda k: 1 if ("site|" + k) in redis_keys else 0

		def get_value(k):
			k = "site|" + k
			if k not in local_cache:
				local_cache[k] = 1 if k in redis_keys else None
			return local_cache[k]

		cache.get_value.side_effect = get_value
		with patch.object(rc, "_cache", return_value=cache):
			self.assertFalse(rc.is_run_cancelled("R9"))  # first poll: miss
			redis_keys.add("site|huf:run_cancel:R9")  # another process (the cancel request) sets it
			self.assertTrue(rc.is_run_cancelled("R9"))


import datetime as _dt


def _row(name, mode="stream", modified=None, conv=None, orch=None):
	return {"name": name, "conversation": conv, "agent_orchestration": orch,
		"execution_mode": mode, "modified": modified}


class TestStaleSweepConservative(unittest.TestCase):
	NOW = _dt.datetime(2026, 1, 1, 12, 0)

	def _select(self, rows, children=False, orch_status=None, lock_ttl=0, recent_tool=False, conf=None):
		def exists(dt, filters=None):
			if dt == "Agent Run":
				return children
			return recent_tool

		db = MagicMock()
		db.exists.side_effect = exists
		db.get_value.return_value = orch_status
		cache = MagicMock()
		cache.ttl.return_value = lock_ttl
		with patch.object(rc.frappe, "get_all", return_value=rows), patch.object(
			rc.frappe, "db", db, create=True
		), patch.object(rc, "_cache", return_value=cache), patch.object(
			rc.frappe, "conf", conf or {}, create=True
		):
			return rc.select_stale_runs(now=self.NOW, alive=lambda r: False)

	def test_plain_stale_stream_run_selected(self):
		self.assertEqual(self._select([_row("A")]), ["A"])

	def test_skips_unfinished_children(self):
		self.assertEqual(self._select([_row("P")], children=True), [])

	def test_skips_orchestration_parent_while_orchestration_running(self):
		self.assertEqual(self._select([_row("P", orch="O1")], orch_status="Running"), [])
		self.assertEqual(self._select([_row("P", orch="O1")], orch_status="Completed"), ["P"])

	def test_skips_live_conversation_lock(self):
		self.assertEqual(self._select([_row("A", conv="C1")], lock_ttl=100), [])

	def test_skips_recent_tool_call(self):
		self.assertEqual(self._select([_row("A")], recent_tool=True), [])

	def test_non_stream_run_uses_background_threshold(self):
		young = self.NOW - _dt.timedelta(minutes=30)
		old = self.NOW - _dt.timedelta(minutes=90)
		self.assertEqual(self._select([_row("S", mode="sync", modified=young)]), [])
		self.assertEqual(self._select([_row("S", mode="sync", modified=old)]), ["S"])

	def test_explain_run_reports_protecting_rule(self):
		old = self.NOW - _dt.timedelta(minutes=20)
		def explain(mode):
			db = MagicMock()
			db.get_value.return_value = SimpleNamespace(
				name="R", status="Started", conversation=None, agent_orchestration=None,
				execution_mode=mode, modified=old)
			db.exists.return_value = False
			with patch.object(rc.frappe, "db", db, create=True), patch.object(
				rc.frappe, "conf", {}, create=True), patch.object(rc, "_cache", return_value=MagicMock()):
				return rc.explain_run("R", now=self.NOW, alive=lambda r: False)
		self.assertIn("non-stream run", explain(""))
		self.assertEqual(explain("stream"), "stale: will be swept")

	def test_sweep_stale_tool_calls_skips_started_runs(self):
		rows = [SimpleNamespace(name="T1", agent_run="RS"), SimpleNamespace(name="T2", agent_run="RD")]
		db = MagicMock()
		db.get_value.side_effect = lambda dt, name, f: "Started" if name == "RS" else "Success"
		with patch.object(rc.frappe, "get_all", return_value=rows), patch.object(
			rc.frappe, "db", db, create=True), patch.object(rc.frappe, "conf", {}, create=True):
			n = rc.sweep_stale_tool_calls(now=self.NOW)
		self.assertEqual(n, 1)
		self.assertEqual(db.set_value.call_args[0][1], "T2")

	def test_background_minutes_default_and_floor(self):
		with patch.object(rc.frappe, "conf", {}, create=True):
			self.assertEqual(rc.get_stale_run_minutes(background=True), 60)
		with patch.object(rc.frappe, "conf", {"huf_stale_run_minutes_background": 5}, create=True):
			self.assertEqual(rc.get_stale_run_minutes(background=True), 15)

	def _sweep(self, rowcount):
		db = MagicMock()
		db._cursor.rowcount = rowcount
		cache = MagicMock()
		cache.lock.return_value.acquire.return_value = True
		with patch.object(rc.frappe, "db", db, create=True), patch.object(
			rc, "_cache", return_value=cache
		), patch.object(rc, "select_stale_runs", return_value=["R1"]), patch.object(
			rc, "mark_cancelled_tool_calls"
		) as mtc, patch("frappe.utils.now_datetime", return_value="t"):
			return rc.sweep_stale_runs(), mtc

	def test_rowcount_zero_does_not_touch_tools_or_count(self):
		cleaned, mtc = self._sweep(0)
		self.assertEqual(cleaned, [])
		mtc.assert_not_called()

	def test_rowcount_one_cleans(self):
		cleaned, mtc = self._sweep(1)
		self.assertEqual(cleaned, ["R1"])
		mtc.assert_called_once()

	def test_marker_set_fails_open_and_logs_rate_limited(self):
		cache = MagicMock()
		cache.exists.side_effect = ConnectionError("down")
		logger = MagicMock()
		rc._last_marker_warn = -1e9
		with patch.object(rc, "_cache", return_value=cache), patch.object(
			rc.frappe, "logger", return_value=logger
		):
			self.assertFalse(rc._marker_set("k"))
			self.assertFalse(rc._marker_set("k"))
		self.assertEqual(logger.warning.call_count, 1)


class TestGuardedFinishStartedRun(unittest.TestCase):
	"""_guarded_finish_started_run must only finalize runs still 'Started'."""

	def _run(self, status, rowcount):
		from huf.ai import agent_integration as ai

		db = MagicMock()
		db._cursor.rowcount = rowcount
		with patch.object(ai.frappe, "db", db, create=True), patch.object(ai, "now_datetime", return_value="t"):
			result = ai._guarded_finish_started_run("R1", status, response="hi", end_time="t")
		return result, db

	def test_success_writes_with_started_guard(self):
		result, db = self._run("Success", 1)
		self.assertTrue(result)
		sql, params = db.sql.call_args[0]
		self.assertIn("status='Started'", sql)
		self.assertIn("`response`=%s", sql)
		self.assertEqual(params[0], "Success")
		self.assertEqual(params[-1], "R1")

	def test_success_does_not_overwrite_already_failed(self):
		result, db = self._run("Success", 0)
		self.assertFalse(result)  # no raise; update matched 0 rows (run already Failed)
		self.assertIn("status='Started'", db.sql.call_args[0][0])

	def test_failure_path_guarded_and_noop_when_finalized(self):
		ok, db = self._run("Failed", 1)
		self.assertTrue(ok)
		self.assertEqual(db.sql.call_args[0][1][0], "Failed")
		noop, _db = self._run("Failed", 0)
		self.assertFalse(noop)


class TestSyncPathFinalWritesGuarded(unittest.TestCase):
	"""Source-level guard: the sync run path's final Success/Failed writes must use the guard."""

	def test_sync_final_writes_use_guard(self):
		import inspect

		from huf.ai import agent_integration as ai

		src = inspect.getsource(ai._execute_agent_run)
		self.assertIn('_guarded_finish_started_run(\n            run_doc.name, "Success"', src)
		self.assertEqual(src.count('_guarded_finish_started_run(run_doc.name, "Failed", error_message=error_msg)'), 3)
		self.assertNotIn('run_doc.db_set("status", "Failed"', src)
		self.assertNotIn('"Agent Run", run_doc.name, run_update', src)

	def test_late_success_cannot_overwrite_failed_and_keeps_fields(self):
		from huf.ai import agent_integration as ai

		db = MagicMock()
		db._cursor.rowcount = 0
		fields = {"response": "r", "prompt": "p", "model": "m", "provider": "x", "end_time": "t", "reasoning_snapshot": "{}"}
		with patch.object(ai.frappe, "db", db, create=True), patch.object(ai, "now_datetime", return_value="t"):
			self.assertFalse(ai._guarded_finish_started_run("R1", "Success", **fields))
		sql, params = db.sql.call_args[0]
		self.assertIn("status='Started'", sql)
		for k in fields:
			self.assertIn(f"`{k}`=%s", sql)


import asyncio as _asyncio


class TestKeepRunAlive(unittest.TestCase):
	def test_touches_periodically_and_cancels_on_exit(self):
		touches = []

		async def body():
			with patch.object(rc, "touch_run_alive", side_effect=lambda r: touches.append(r)):
				async with rc.keep_run_alive("R", interval=0.05) as k:
					await _asyncio.sleep(0.22)
					task = k._task
				self.assertTrue(task.done())
				n = len(touches)
				await _asyncio.sleep(0.15)
				self.assertEqual(len(touches), n)  # no leak after exit
				self.assertTrue(k._stop.is_set())
			return n

		self.assertGreaterEqual(_asyncio.run(body()), 4)  # enter + >=2 ticks (task and/or thread) + exit

	def test_cancels_cleanly_when_body_raises(self):
		holder = {}

		async def body():
			with patch.object(rc, "touch_run_alive"):
				try:
					async with rc.keep_run_alive("R", interval=0.05) as k:
						holder["k"] = k
						raise ValueError("boom")
				except ValueError:
					pass
			return holder["k"]

		k = _asyncio.run(body())
		self.assertTrue(k._task.done())
		self.assertTrue(k._stop.is_set())


class TestKeepRunAliveThread(unittest.TestCase):
	def _thread(self, loop, deadline_s=None):
		k = rc.keep_run_alive("R", interval=0.01)
		import threading
		k._stop = threading.Event()
		return k

	def test_thread_exits_when_loop_closed(self):
		k = self._thread(None)
		loop = MagicMock()
		loop.is_closed.return_value = True
		with patch.object(rc, "touch_run_alive") as t:
			k._thread_loop(loop)  # returns instead of looping forever
		t.assert_not_called()

	def test_thread_exits_after_max_lifetime(self):
		k = self._thread(None)
		with patch.object(rc, "_KEEP_ALIVE_MAX_S", 0), patch.object(rc, "touch_run_alive") as t:
			k._thread_loop(None)
		t.assert_not_called()

	def test_init_failure_logs_once_and_exits_task_keeps_marker(self):
		logger = MagicMock()

		async def body():
			with patch.object(rc, "touch_run_alive"), patch.object(
				rc.frappe.local, "site", "s.local", create=True
			), patch.object(rc.frappe, "init", side_effect=RuntimeError("x")), patch.object(
				rc.frappe, "logger", return_value=logger
			), patch.object(rc.frappe, "destroy") as destroy:
				async with rc.keep_run_alive("R", interval=0.05) as k:
					k._thread.join(2)
					self.assertFalse(k._thread.is_alive())
					self.assertFalse(k._task.done())
				return destroy

		destroy = _asyncio.run(body())
		logger.warning.assert_called_once()
		destroy.assert_not_called()

	def test_destroy_called_in_finally_after_init(self):
		async def body():
			with patch.object(rc, "touch_run_alive"), patch.object(
				rc.frappe.local, "site", "s.local", create=True
			), patch.object(rc.frappe, "init"), patch.object(rc.frappe, "destroy") as destroy:
				async with rc.keep_run_alive("R", interval=0.05) as k:
					pass
				k._thread.join(2)
				return destroy

		_asyncio.run(body()).assert_called_once()


class TestSweepToolCallsRunStatus(unittest.TestCase):
	def _sweep(self, run_status):
		db = MagicMock()
		db.get_value.return_value = run_status
		with patch.object(rc.frappe, "get_all", return_value=[SimpleNamespace(name="T", agent_run="R")]), \
				patch.object(rc.frappe, "db", db, create=True):
			n = rc.sweep_stale_tool_calls(now=_dt.datetime(2026, 1, 1, 12, 0))
		return n, db.set_value.called

	def test_ignores_started_and_queued_runs(self):
		self.assertEqual(self._sweep("Started"), (0, False))
		self.assertEqual(self._sweep("Queued"), (0, False))

	def test_fails_calls_of_terminal_or_missing_runs(self):
		for st in ("Success", "Failed", None):
			self.assertEqual(self._sweep(st), (1, True))


class TestStaleSelectLiveMarkerOldToolCall(unittest.TestCase):
	def test_live_marker_with_old_queued_tool_call_is_skipped(self):
		db = MagicMock()
		db.exists.return_value = False  # no recent tool call: only an old Queued one
		with patch.object(rc.frappe, "get_all", return_value=[_row("A")]), patch.object(
			rc.frappe, "db", db, create=True
		), patch.object(rc, "_cache", return_value=MagicMock()), patch.object(rc.frappe, "conf", {}, create=True):
			now = _dt.datetime(2026, 1, 1, 12, 0)
			self.assertEqual(rc.select_stale_runs(now=now, alive=lambda r: True), [])
			self.assertEqual(rc.select_stale_runs(now=now, alive=lambda r: False), ["A"])


class TestDeadQueuedSweep(unittest.TestCase):
	NOW = _dt.datetime(2026, 1, 2, 12, 0)

	def test_select_uses_cutoff_and_skips_live_lock(self):
		captured = {}

		def fake_get_all(doctype, **kw):
			captured.update(kw)
			return [SimpleNamespace(name="A", conversation="c1"), SimpleNamespace(name="B", conversation="c2")]

		with patch.object(rc.frappe, "get_all", fake_get_all), patch.object(
			rc.frappe, "conf", {}, create=True
		), patch.object(rc, "_conversation_lock_live", side_effect=lambda c: c == "c2"):
			out = rc.select_dead_queued_runs(now=self.NOW)
		self.assertEqual(out, ["A"])
		self.assertEqual(captured["filters"]["status"], "Queued")
		self.assertEqual(captured["filters"]["modified"], ["<", _dt.datetime(2026, 1, 1, 12, 0)])

	def test_config_hours(self):
		with patch.object(rc.frappe, "conf", {"huf_stale_queued_hours": 6}, create=True):
			self.assertEqual(rc.get_stale_queued_hours(), 6)
		with patch.object(rc.frappe, "conf", {}, create=True):
			self.assertEqual(rc.get_stale_queued_hours(), 24)

	def _run(self, rowcount, select=("R1",)):
		db = MagicMock()
		db._cursor.rowcount = rowcount
		cache = MagicMock()
		cache.lock.return_value.acquire.return_value = True
		with patch.object(rc.frappe, "db", db, create=True), patch.object(
			rc, "_cache", return_value=cache
		), patch.object(rc, "select_dead_queued_runs", return_value=list(select)), patch.object(
			rc, "mark_cancelled_tool_calls"
		) as mtc, patch("frappe.utils.now_datetime", return_value="t"):
			return rc.sweep_dead_queued_runs(), db, mtc

	def test_sweep_fails_run_with_guard_and_closes_tools(self):
		out, db, mtc = self._run(1)
		self.assertEqual(out, ["R1"])
		args = db.sql.call_args[0]
		self.assertIn("status='Queued'", args[0])
		self.assertEqual(args[1][0], "Stale queued run")
		mtc.assert_called_once_with("R1", message="Stale queued run", user=db.get_value.return_value, checkpoint=False)

	def test_guarded_update_zero_rows_is_skipped(self):
		out, db, mtc = self._run(0)
		self.assertEqual(out, [])
		mtc.assert_not_called()

	def test_sweep_skips_when_lock_held(self):
		cache = MagicMock()
		cache.lock.return_value.acquire.return_value = False
		with patch.object(rc, "_cache", return_value=cache), patch.object(rc, "select_dead_queued_runs") as sel:
			self.assertEqual(rc.sweep_dead_queued_runs(), [])
		sel.assert_not_called()
