# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Unit tests for ST-R5.3: Get List tool limit clamping in huf.ai.handlers.crud.

``handle_get_list`` previously passed the caller-supplied ``limit`` straight
through to ``frappe.get_list(limit_page_length=...)`` with no upper bound
(only a lower-bound guard against 0/negative values), letting a single tool
call request an unbounded result set. These tests exercise the clamping
formula directly against a mocked ``frappe.get_list`` so they can run
without a live site.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.tests.test_crud_get_list_limit_clamp
"""
import unittest
from unittest.mock import MagicMock, patch

import frappe

from huf.ai.handlers.crud import default_limit, hard_cap, handle_get_list


class TestGetListLimitClamp(unittest.TestCase):
    def setUp(self):
        self.doctype = "Agent"

        self._get_meta_patcher = patch("huf.ai.handlers.crud.frappe.get_meta")
        mock_get_meta = self._get_meta_patcher.start()
        meta = MagicMock()
        meta.fields = []
        mock_get_meta.return_value = meta

        self._exists_patcher = patch(
            "huf.ai.handlers.crud.frappe.db.exists", return_value=True
        )
        self._exists_patcher.start()

        self._flags_patcher = patch.object(frappe, "flags", {"current_function_doctype": None})
        self._flags_patcher.start()

    def tearDown(self):
        self._get_meta_patcher.stop()
        self._exists_patcher.stop()
        self._flags_patcher.stop()

    def _call_and_capture_limit(self, limit):
        with patch("huf.ai.handlers.crud.frappe.get_list", return_value=[]) as mock_get_list:
            handle_get_list(reference_doctype=self.doctype, limit=limit)
            self.assertTrue(mock_get_list.called)
            _, kwargs = mock_get_list.call_args
            return kwargs["limit_page_length"]

    def test_limit_zero_defaults_to_default_limit(self):
        self.assertEqual(self._call_and_capture_limit(0), default_limit)

    def test_limit_none_defaults_to_default_limit(self):
        self.assertEqual(self._call_and_capture_limit(None), default_limit)

    def test_huge_limit_is_clamped_to_hard_cap(self):
        self.assertEqual(self._call_and_capture_limit(99999), hard_cap)

    def test_reasonable_limit_passes_through_unchanged(self):
        self.assertEqual(self._call_and_capture_limit(50), 50)

    def test_hard_cap_boundary_is_not_exceeded(self):
        self.assertEqual(self._call_and_capture_limit(hard_cap), hard_cap)
        self.assertEqual(self._call_and_capture_limit(hard_cap + 1), hard_cap)


if __name__ == "__main__":
    unittest.main()
