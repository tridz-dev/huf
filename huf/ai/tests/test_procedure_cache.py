# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Unit tests for huf.ai.graph.cache (T-33).

Standalone-first: frappe is faked with a hand-written double, never a bare MagicMock --
mirrors huf.ai.tests.test_graph_permissions._FrappeDouble / test_procedure_binding.py.
Covers:

  * Deterministic key normalisation -- equivalent inputs in different key order hit the
    same cache entry.
  * Different user / company / procedure_version never collide.
  * set_cached_result refuses (raises) when is_read_only is falsy -- the structural
    guard D7/I8 requires -- and never writes anything to the store in that case.
  * Request-scope semantics: the store is whatever dict frappe.local.cache is, so a
    fresh dict (a new "request") sees nothing from a previous one.

Run with:
  bench --site <site> run-tests --app huf --module huf.ai.tests.test_procedure_cache
"""

import sys
import types
import unittest
from unittest.mock import MagicMock, patch


def _install_standalone_frappe_stub():
	"""See huf.ai.tests.test_graph_permissions._install_standalone_frappe_stub -- same
	rationale: huf/__init__.py does `import frappe` unconditionally at package-import
	time, before conftest.py's stub would otherwise run.
	"""
	existing = sys.modules.get("frappe")
	if existing is not None and hasattr(existing, "__file__"):
		return

	fake = MagicMock(name="frappe")
	fake.PermissionError = PermissionError
	fake._ = lambda msg, *a, **k: msg
	fake.whitelist = lambda *a, **k: (lambda f: f)

	fake_utils = types.ModuleType("frappe.utils")
	fake_utils.now_datetime = lambda: None
	fake.utils = fake_utils

	sys.modules["frappe"] = fake
	sys.modules["frappe.utils"] = fake_utils


_install_standalone_frappe_stub()

from huf.ai.graph import cache as procedure_cache
from huf.ai.graph.cache import (
	MutatingProcedureCacheError,
	bust_procedure_cache,
	get_cached_result,
	set_cached_result,
)


class _Local:
	"""Plain stand-in for frappe.local: a request-scoped dict lives on .cache."""

	def __init__(self):
		self.cache = {}


class _FrappeDouble:
	"""Minimal stand-in for the ``frappe`` module as ``cache.py`` uses it."""

	def __init__(self):
		self.local = _Local()


class TestCacheKeyDeterminism(unittest.TestCase):
	def setUp(self):
		self.fake = _FrappeDouble()
		self.patcher = patch.object(procedure_cache, "frappe", self.fake)
		self.patcher.start()
		self.addCleanup(self.patcher.stop)

	def test_equivalent_inputs_in_different_order_hit_same_entry(self):
		set_cached_result(
			procedure_version="proc-v1",
			inputs={"a": 1, "b": 2},
			user="user@example.com",
			company="Acme",
			is_read_only=True,
			result={"ok": True},
		)

		hit = get_cached_result(
			procedure_version="proc-v1",
			inputs={"b": 2, "a": 1},  # same inputs, different key order
			user="user@example.com",
			company="Acme",
		)

		self.assertEqual(hit, {"ok": True})

	def test_nested_dict_key_order_also_normalises(self):
		set_cached_result(
			procedure_version="proc-v1",
			inputs={"filters": {"x": 1, "y": 2}},
			user="user@example.com",
			company=None,
			is_read_only=True,
			result="cached",
		)
		hit = get_cached_result(
			procedure_version="proc-v1",
			inputs={"filters": {"y": 2, "x": 1}},
			user="user@example.com",
			company=None,
		)
		self.assertEqual(hit, "cached")

	def test_different_user_is_a_different_entry(self):
		set_cached_result(
			procedure_version="proc-v1",
			inputs={"a": 1},
			user="user-a@example.com",
			company=None,
			is_read_only=True,
			result="result-a",
		)
		hit = get_cached_result(
			procedure_version="proc-v1",
			inputs={"a": 1},
			user="user-b@example.com",
			company=None,
		)
		self.assertIsNone(hit)

	def test_different_company_is_a_different_entry(self):
		set_cached_result(
			procedure_version="proc-v1",
			inputs={"a": 1},
			user="user@example.com",
			company="Acme",
			is_read_only=True,
			result="result-acme",
		)
		hit = get_cached_result(
			procedure_version="proc-v1",
			inputs={"a": 1},
			user="user@example.com",
			company="Beta",
		)
		self.assertIsNone(hit)

	def test_different_procedure_version_is_a_different_entry(self):
		set_cached_result(
			procedure_version="proc-v1",
			inputs={"a": 1},
			user="user@example.com",
			company=None,
			is_read_only=True,
			result="result-v1",
		)
		hit = get_cached_result(
			procedure_version="proc-v2",
			inputs={"a": 1},
			user="user@example.com",
			company=None,
		)
		self.assertIsNone(hit)

	def test_bust_removes_the_entry(self):
		set_cached_result(
			procedure_version="proc-v1",
			inputs={"a": 1},
			user="user@example.com",
			company=None,
			is_read_only=True,
			result="result",
		)
		bust_procedure_cache(procedure_version="proc-v1", inputs={"a": 1}, user="user@example.com", company=None)
		hit = get_cached_result(procedure_version="proc-v1", inputs={"a": 1}, user="user@example.com", company=None)
		self.assertIsNone(hit)


class TestMutatingProcedureNeverCached(unittest.TestCase):
	"""D7 / I8: caching a mutating procedure's result must be structurally impossible."""

	def setUp(self):
		self.fake = _FrappeDouble()
		self.patcher = patch.object(procedure_cache, "frappe", self.fake)
		self.patcher.start()
		self.addCleanup(self.patcher.stop)

	def test_set_cached_result_raises_when_not_read_only(self):
		with self.assertRaises(MutatingProcedureCacheError):
			set_cached_result(
				procedure_version="proc-write-v1",
				inputs={"a": 1},
				user="user@example.com",
				company=None,
				is_read_only=False,
				result={"wrote": "something"},
			)

	def test_nothing_is_stored_when_the_guard_rejects(self):
		with self.assertRaises(MutatingProcedureCacheError):
			set_cached_result(
				procedure_version="proc-write-v1",
				inputs={"a": 1},
				user="user@example.com",
				company=None,
				is_read_only=False,
				result={"wrote": "something"},
			)

		# The store backing the cache must be untouched -- not just "the getter
		# returns None," but literally nothing was written to frappe.local.cache.
		self.assertEqual(self.fake.local.cache, {})

		hit = get_cached_result(
			procedure_version="proc-write-v1", inputs={"a": 1}, user="user@example.com", company=None
		)
		self.assertIsNone(hit)


class TestRequestScope(unittest.TestCase):
	def test_fresh_request_dict_sees_nothing_from_a_previous_one(self):
		fake = _FrappeDouble()
		with patch.object(procedure_cache, "frappe", fake):
			set_cached_result(
				procedure_version="proc-v1",
				inputs={"a": 1},
				user="user@example.com",
				company=None,
				is_read_only=True,
				result="from-request-one",
			)

		# Simulate a new request: frappe resets frappe.local.cache to a fresh dict.
		fake.local = _Local()
		with patch.object(procedure_cache, "frappe", fake):
			hit = get_cached_result(
				procedure_version="proc-v1", inputs={"a": 1}, user="user@example.com", company=None
			)

		self.assertIsNone(hit)


if __name__ == "__main__":
	unittest.main()
