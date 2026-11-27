# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Pre-send guard chain (H-W2-01): ordered, fail-closed, no request data in the result or the log."""

import threading
import time
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.channels import guard

RECIPIENT = "+15550001234"


def allow(request):
	return {"allow": True}


class TestGuardChain(IntegrationTestCase):
	def setUp(self):
		# app-hook behaviour only; the built-in steps are covered by test_guard_steps
		patcher = patch.object(guard, "BUILTIN_STEPS", [])
		patcher.start()
		self.addCleanup(patcher.stop)

	def run_chain(self, *steps, request=None, **kwargs):
		"""Evaluate with ``steps`` registered as app hooks."""
		registry = {f"app.step{i}": step for i, step in enumerate(steps)}
		with (
			patch.object(guard, "_hook_paths", return_value=list(registry)),
			patch.object(frappe, "get_attr", side_effect=registry.__getitem__),
		):
			return guard.evaluate({"to": RECIPIENT} if request is None else request, **kwargs)

	def assertBlocked(self, result, reason, step="app.step0"):
		self.assertEqual(result, guard.GuardResult(False, reason, step))

	def test_no_steps_allows(self):
		self.assertEqual(self.run_chain(), guard.GuardResult(True))

	def test_builtins_run_first_and_hooks_in_order_with_their_own_copy(self):
		seen = []

		def step(label):
			def run(request):
				seen.append((label, request["vars"][:]))
				request["vars"].append(label)
				return {"allow": True}

			return run

		request = {"vars": []}
		with patch.object(guard, "BUILTIN_STEPS", [("builtin", step("builtin"))]):
			result = self.run_chain(step("a"), step("b"), request=request)
		self.assertTrue(result.allowed)
		self.assertEqual(seen, [("builtin", []), ("a", []), ("b", [])])
		self.assertEqual(request, {"vars": []})

	def test_first_block_short_circuits(self):
		later = []
		result = self.run_chain(
			lambda r: {"allow": False, "reason": "freq_cap"}, lambda r: later.append(1) or allow(r)
		)
		self.assertBlocked(result, "freq_cap")
		self.assertEqual(later, [])

	def test_unregistered_reason_is_stored_as_unknown(self):
		result = self.run_chain(lambda r: {"allow": False, "reason": f"no consent for {r['to']}"})
		self.assertBlocked(result, "unknown")

	def test_anything_but_an_explicit_verdict_blocks(self):
		bad = (None, True, False, "", {}, {"allow": 1}, {"allow": "True"}, {"allow": True, "x": 1})
		for verdict in bad:
			with self.subTest(verdict=verdict):
				self.assertBlocked(self.run_chain(lambda r, v=verdict: v), "hook_error")

	def test_raising_step_blocks_without_leaking(self):
		def boom(request):
			raise ValueError(request["to"])

		with patch.object(frappe, "logger") as logger:
			result = self.run_chain(boom)
		self.assertBlocked(result, "hook_error")
		self.assertNotIn(RECIPIENT, repr(result) + repr(logger.mock_calls))

	def test_base_exception_blocks(self):
		def leave(request):
			raise SystemExit

		self.assertBlocked(self.run_chain(leave), "hook_error")

	def test_bad_path_and_failing_lookup_block(self):
		with patch.object(guard, "_hook_paths", return_value=["huf.no_such.step"]):
			self.assertBlocked(guard.evaluate({}), "hook_error", "huf.no_such.step")
		with patch.object(guard, "_hook_paths", side_effect=RuntimeError):
			self.assertEqual(guard.evaluate({}), guard.GuardResult(False, "hook_error"))

	def test_hooks_are_read_from_the_named_hook(self):
		with patch.object(frappe, "get_hooks", return_value=["a.b"]) as get_hooks:
			self.assertEqual(guard._hook_paths(), ["a.b"])
		get_hooks.assert_called_once_with("huf_pre_send_hooks")

	def test_timeout_blocks_and_the_abandoned_step_loses_the_database(self):
		release, done, errors, later = threading.Event(), threading.Event(), [], []

		def slow(request):
			release.wait(5)
			try:
				frappe.db.sql("select 1")
			except RuntimeError as error:
				errors.append(error)
			done.set()
			return {"allow": True}

		result = self.run_chain(slow, lambda r: later.append(1) or allow(r), timeout=0.05)
		release.set()
		self.assertBlocked(result, "hook_timeout")
		self.assertTrue(done.wait(5))
		self.assertEqual(len(errors), 1)
		self.assertEqual(later, [])
		self.assertEqual(frappe.db.sql("select 1")[0][0], 1)

	def test_timeout_waits_for_a_query_already_in_flight(self):
		finished = []

		def slow_query(request):
			frappe.db.sql("select sleep(0.3)")
			finished.append(1)
			return {"allow": True}

		started = time.monotonic()
		self.assertBlocked(self.run_chain(slow_query, timeout=0.05), "hook_timeout")
		self.assertGreaterEqual(time.monotonic() - started, 0.25)
		self.assertEqual(frappe.db.sql("select 1")[0][0], 1)

	def test_step_sees_the_site_and_the_callers_transaction(self):
		def read(request):
			rows = frappe.db.sql("select @huf_guard_probe")
			return {"allow": frappe.local.site == request["site"] and rows[0][0] == 7}

		frappe.db.sql("set @huf_guard_probe = 7")
		self.assertTrue(self.run_chain(read, request={"site": frappe.local.site}).allowed)

	def test_timeout_is_configurable_and_bad_values_use_the_default(self):
		with patch.dict(frappe.conf, {guard.TIMEOUT_CONF: 0.5}):
			self.assertEqual(guard._timeout(None), 0.5)
		for bad in (None, "x", 0, -1, float("nan"), float("inf")):
			with self.subTest(bad=bad), patch.dict(frappe.conf, {guard.TIMEOUT_CONF: bad}):
				self.assertEqual(guard._timeout(None), 2.0)

	def test_result_is_immutable(self):
		with self.assertRaises(AttributeError):
			guard.GuardResult(True).allowed = False
