"""Q11: a route to a flow that is not Active warns at save and never refuses."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

from huf.ai.flow.gateways import route_warning as rw


class TestRouteWarning(unittest.TestCase):
	def setUp(self):
		for p in (mock.patch.object(rw, "_", lambda s: s), mock.patch.object(rw.frappe, "flags", SimpleNamespace())):
			p.start()
			self.addCleanup(p.stop)

	def test_active_and_blank_are_silent(self):
		with mock.patch.object(rw.frappe.db, "get_value", return_value="Active"), mock.patch.object(rw.frappe, "msgprint") as note:
			self.assertIsNone(rw.warn_if_flow_not_live("f1"))
			self.assertIsNone(rw.warn_if_flow_not_live(""))
		note.assert_not_called()

	def test_draft_warns_but_does_not_raise(self):
		with mock.patch.object(rw.frappe.db, "get_value", return_value="Draft"), mock.patch.object(rw.frappe, "msgprint") as note:
			message = rw.warn_if_flow_not_live("f1")
		self.assertIn("not published", message)
		self.assertEqual(note.call_args.kwargs["indicator"], "orange")

	def test_missing_flow_warns(self):
		with mock.patch.object(rw.frappe.db, "get_value", return_value=None), mock.patch.object(rw.frappe, "msgprint"):
			self.assertIn("was not found", rw.warn_if_flow_not_live("gone"))

	def test_lookup_failure_never_blocks(self):
		with mock.patch.object(rw.frappe.db, "get_value", side_effect=RuntimeError("db down")):
			self.assertIsNone(rw.warn_if_flow_not_live("f1"))


if __name__ == "__main__":
	unittest.main()
