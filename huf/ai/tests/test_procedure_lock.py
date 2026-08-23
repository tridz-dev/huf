# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Unit tests for huf.ai.procedure_lock (T-21, GT-08).

Runs standalone (frappe-free stub, per this package's convention -- see
huf.ai.tests.test_graph_permissions for the documented reason the stub must be
installed before ``huf`` is first imported) and unmodified on a real bench.

frappe.cache() is patched to a small hand-written fake implementing real set/expire/
delete/nx semantics (not a MagicMock, per this track's test convention: a MagicMock's
``.set()`` is truthy by default regardless of ``nx``, which would make the "second
acquire fails" assertion meaningless).

Run with:
  pytest huf/ai/tests/test_procedure_lock.py
  bench --site <site> run-tests --app huf --module huf.ai.tests.test_procedure_lock
"""

import sys
import types
import unittest
from unittest.mock import patch


def _install_standalone_frappe_stub():
	existing = sys.modules.get("frappe")
	if existing is not None and hasattr(existing, "__file__"):
		return

	fake = types.ModuleType("frappe")
	fake._ = lambda msg, *a, **k: msg
	fake.whitelist = lambda *a, **k: lambda f: f
	sys.modules["frappe"] = fake


_install_standalone_frappe_stub()

import frappe

from huf.ai import procedure_lock


class FakeCache:
	"""Hand-written double with real set(nx=)/expire/delete semantics -- no MagicMock."""

	def __init__(self):
		self._store = {}

	def set(self, key, value, ex=None, nx=False):
		if nx and key in self._store:
			return False
		self._store[key] = value
		return True

	def expire(self, key, ttl):
		if key not in self._store:
			raise KeyError(key)

	def delete(self, key):
		self._store.pop(key, None)

	def get(self, key):
		return self._store.get(key)


class TestProcedureRunLock(unittest.TestCase):
	def setUp(self):
		self.cache = FakeCache()
		self.patcher = patch.object(frappe, "cache", lambda: self.cache, create=True)
		self.patcher.start()
		self.addCleanup(self.patcher.stop)
		# frappe.logger is used only on exception paths; give it a no-op double.
		self.logger_patcher = patch.object(
			frappe, "logger", lambda *a, **k: types.SimpleNamespace(debug=lambda *a, **k: None), create=True
		)
		self.logger_patcher.start()
		self.addCleanup(self.logger_patcher.stop)

	def test_acquire_succeeds_when_unheld(self):
		self.assertTrue(procedure_lock.acquire_run_lock("run-1"))

	def test_second_acquire_fails_while_first_holds(self):
		self.assertTrue(procedure_lock.acquire_run_lock("run-1"))
		self.assertFalse(procedure_lock.acquire_run_lock("run-1"))

	def test_different_runs_do_not_contend(self):
		self.assertTrue(procedure_lock.acquire_run_lock("run-1"))
		self.assertTrue(procedure_lock.acquire_run_lock("run-2"))

	def test_release_then_reacquire_succeeds(self):
		self.assertTrue(procedure_lock.acquire_run_lock("run-1"))
		procedure_lock.release_run_lock("run-1")
		self.assertTrue(procedure_lock.acquire_run_lock("run-1"))

	def test_context_manager_releases_on_exit(self):
		with procedure_lock.ProcedureRunLock("run-1") as lock:
			self.assertTrue(lock.acquired)
			self.assertFalse(procedure_lock.acquire_run_lock("run-1"))
		self.assertTrue(procedure_lock.acquire_run_lock("run-1"))

	def test_context_manager_reports_not_acquired_when_contended(self):
		procedure_lock.acquire_run_lock("run-1")
		with procedure_lock.ProcedureRunLock("run-1") as lock:
			self.assertFalse(lock.acquired)
		# A non-acquiring context manager must not release the other holder's lock.
		self.assertFalse(procedure_lock.acquire_run_lock("run-1"))

	def test_context_manager_releases_even_on_exception(self):
		with self.assertRaises(ValueError):
			with procedure_lock.ProcedureRunLock("run-1") as lock:
				self.assertTrue(lock.acquired)
				raise ValueError("boom")
		self.assertTrue(procedure_lock.acquire_run_lock("run-1"))

	def test_extend_does_not_raise_when_lock_missing(self):
		# extend_run_lock must be safe to call defensively; it must never raise into
		# the caller's execution loop even if the key already expired.
		procedure_lock.extend_run_lock("no-such-run")

	def test_lock_key_is_scoped_per_run_not_per_procedure(self):
		self.assertNotEqual(
			procedure_lock._run_lock_key("run-1"),
			procedure_lock._run_lock_key("run-2"),
		)


if __name__ == "__main__":
	unittest.main()
