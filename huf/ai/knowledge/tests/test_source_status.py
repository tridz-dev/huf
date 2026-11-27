"""Source status recompute after input delete / reprocess (frappe mocked)."""

import types
import unittest
from unittest.mock import patch

import huf.ai.knowledge.hooks as mod


class FakeDB:
	def __init__(self, status):
		self.status = status
		self.set = None

	def get_value(self, *a, **k):
		return self.status

	def set_value(self, doctype, name, values):
		self.set = values


def _run(status, errors, exclude=None):
	db = FakeDB(status)

	def get_all(doctype, filters=None, **k):
		skip = (filters.get("name") or [None, None])[1]
		return [types.SimpleNamespace(error_message=m) for n, m in errors if n != skip][:1]

	with (
		patch.object(mod.frappe, "db", db, create=True),
		patch.object(mod.frappe, "get_all", get_all, create=True),
	):
		mod.recompute_source_status("S", exclude_input=exclude)
	return db.set


class TestSourceStatus(unittest.TestCase):
	def test_delete_only_failed_returns_ready(self):
		self.assertEqual(
			(_run("Error", [("A", "boom")], exclude="A")), ({"status": "Ready", "error_message": None})
		)

	def test_second_failed_keeps_error(self):
		self.assertEqual(
			(_run("Error", [("A", "boom"), ("B", "bad")], exclude="A")),
			(
				{
					"status": "Error",
					"error_message": "bad",
				}
			),
		)

	def test_busy_states_untouched(self):
		self.assertIsNone(_run("Rebuilding", [("A", "x")], exclude="A"))
		self.assertIsNone(_run("Indexing", [], None))

	def test_reprocess_success_recomputes(self):
		self.assertEqual((_run("Ready", [], None)), ({"status": "Ready", "error_message": None}))
