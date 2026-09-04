"""Layer A (mocked-frappe, no bench) unit tests for the doctype guard module.

These tests verify the doctype gate is applied before any DB call.
Run standalone from repo root:
    PYTHONPATH=. python3 huf/ai/tests/test_tool_doctype_guard.py -v
"""

import json
import sys
import unittest
from unittest.mock import MagicMock, patch

try:
    import frappe  # noqa: F401
except ImportError:
    frappe_mock = MagicMock()
    frappe_mock.utils = MagicMock()
    frappe_mock._ = lambda x: x
    frappe_mock.logger = lambda *a, **k: MagicMock()
    frappe_mock.db = MagicMock()
    frappe_mock.session = MagicMock(user="test_user")
    frappe_mock.flags = MagicMock()
    frappe_mock.flags.get = lambda x, default=None: default
    sys.modules["frappe"] = frappe_mock
    sys.modules["frappe.utils"] = frappe_mock.utils
    sys.modules["frappe.utils.file_manager"] = MagicMock()
    sys.modules["frappe.utils.background_jobs"] = MagicMock()
    sys.modules["frappe.client"] = MagicMock()
    sys.modules["frappe.model"] = MagicMock()
    sys.modules["frappe.model.document"] = MagicMock()

import frappe  # noqa: E402

from huf.ai.tool_doctype_guard import _check_doctype_allowed  # noqa: E402
from huf.ai.handlers import crud as crud_module  # noqa: E402
from huf.ai import tool_functions  # noqa: E402


class TestDoctypeGuard(unittest.TestCase):
    """Test the core _check_doctype_allowed function."""

    def setUp(self):
        frappe.db.exists = MagicMock(return_value=True)
        frappe.get_meta = MagicMock()

    def test_deny_user_doctype(self):
        """User doctype is denied."""
        meta, err = _check_doctype_allowed("User")
        self.assertIsNone(meta)
        self.assertIsNotNone(err)
        self.assertIn("not permitted", err)

    def test_deny_oauth_prefix(self):
        """OAuth prefix is denied."""
        meta, err = _check_doctype_allowed("OAuth Client")
        self.assertIsNone(meta)
        self.assertIsNotNone(err)

    def test_allow_valid_doctype(self):
        """Valid doctype is allowed."""
        mock_meta = MagicMock()
        mock_meta.issingle = False
        frappe.get_meta = MagicMock(return_value=mock_meta)
        meta, err = _check_doctype_allowed("Customer")
        self.assertIsNotNone(meta)
        self.assertIsNone(err)


class TestCrudHandlerGates(unittest.TestCase):
    """Test that crud.py handlers gate on doctype."""

    def setUp(self):
        frappe.db = MagicMock()
        frappe.db.exists = MagicMock(return_value=True)
        frappe.get_meta = MagicMock()
        frappe.get_doc = MagicMock()
        frappe.has_permission = MagicMock(return_value=True)
        frappe.session = MagicMock(user="test_user")
        frappe.flags = MagicMock()
        frappe.flags.get = lambda x, default=None: default

    def test_handle_create_document_denies_user(self):
        """handle_create_document denies User before DB call."""
        result = crud_module.handle_create_document(reference_doctype="User")
        self.assertFalse(result.get("success", False))
        frappe.db.exists.assert_not_called()

    def test_handle_delete_document_denies_user(self):
        """handle_delete_document denies User before DB call (mutator)."""
        result = crud_module.handle_delete_document(
            reference_doctype="User",
            document_id="test"
        )
        self.assertFalse(result.get("success", False))

    def test_handle_update_document_denies_user(self):
        """handle_update_document denies User before DB call (mutator)."""
        result = crud_module.handle_update_document(
            reference_doctype="User",
            document_id="test"
        )
        self.assertFalse(result.get("success", False))

    def test_handle_get_value_denies_user(self):
        """handle_get_value denies User before DB call."""
        result = crud_module.handle_get_value(
            doctype="User",
            filters={"name": "test"},
            fieldname="name"
        )
        self.assertFalse(result.get("success", False))

    def test_handle_set_value_denies_user(self):
        """handle_set_value denies User before DB call (mutator)."""
        result = crud_module.handle_set_value(
            doctype="User",
            filters={"name": "test"},
            fieldname="email"
        )
        self.assertFalse(result.get("success", False))

    def test_handle_get_list_denies_user(self):
        result = crud_module.handle_get_list(reference_doctype="User")
        self.assertFalse(result.get("success", False))
        frappe.db.exists.assert_not_called()

    def test_handle_get_document_denies_user(self):
        result = crud_module.handle_get_document(reference_doctype="User", document_id="test")
        self.assertFalse(result.get("success", False))
        frappe.db.exists.assert_not_called()

    def test_handle_get_documents_denies_user(self):
        result = crud_module.handle_get_documents(reference_doctype="User", document_ids=["test"])
        self.assertFalse(result.get("success", False))

    def test_handle_create_documents_denies_user(self):
        result = crud_module.handle_create_documents(reference_doctype="User", documents=[{"a": 1}])
        self.assertFalse(result.get("success", False))

    def test_handle_update_documents_denies_user(self):
        result = crud_module.handle_update_documents(
            reference_doctype="User", documents=[{"document_id": "x", "a": 1}]
        )
        self.assertFalse(result.get("success", False))

    def test_handle_delete_documents_denies_user(self):
        """handle_delete_documents denies User before DB call (mutator)."""
        result = crud_module.handle_delete_documents(reference_doctype="User", document_ids=["test"])
        self.assertFalse(result.get("success", False))

    def test_handle_submit_document_denies_user(self):
        """handle_submit_document denies User before DB call (mutator)."""
        result = crud_module.handle_submit_document(reference_doctype="User", document_id="test")
        self.assertFalse(result.get("success", False))

    def test_handle_cancel_document_denies_user(self):
        """handle_cancel_document denies User before DB call (mutator)."""
        result = crud_module.handle_cancel_document(reference_doctype="User", document_id="test")
        self.assertFalse(result.get("success", False))

    def test_handle_get_report_result_denies_when_report_denylisted(self):
        with patch("huf.ai.tool_doctype_guard._DENYLISTED_DOCTYPES", {"report"}):
            result = crud_module.handle_get_report_result(report_name="Some Report")
        self.assertFalse(result.get("success", False))

    def test_handle_attach_file_to_document_denies_user(self):
        result = crud_module.handle_attach_file_to_document(
            reference_doctype="User", document_id="test"
        )
        self.assertFalse(result.get("success", False))


class TestToolFunctionsGates(unittest.TestCase):
    """Test that tool_functions.py handlers gate on doctype."""

    def setUp(self):
        frappe.db = MagicMock()
        frappe.db.exists = MagicMock(return_value=True)
        frappe.get_meta = MagicMock()
        frappe.get_doc = MagicMock()
        frappe.has_permission = MagicMock(return_value=True)
        frappe.session = MagicMock(user="test_user")
        frappe.flags = MagicMock()
        frappe.flags.get = lambda x, default=None: default

    def test_get_document_denies_user(self):
        result = tool_functions.get_document("User", "test")
        self.assertFalse(result.get("success", False))
        frappe.db.exists.assert_not_called()

    def test_get_documents_denies_user(self):
        result = tool_functions.get_documents("User", ["test"])
        self.assertFalse(result.get("success", False))

    def test_create_document_denies_user(self):
        result = tool_functions.create_document("User", {"a": 1})
        self.assertFalse(result.get("success", False))
        frappe.db.exists.assert_not_called()

    def test_create_documents_denies_user(self):
        result = tool_functions.create_documents("User", [{"a": 1}])
        self.assertFalse(result.get("success", False))

    def test_update_document_denies_user(self):
        result = tool_functions.update_document("User", "test", {"a": 1})
        self.assertFalse(result.get("success", False))
        frappe.db.exists.assert_not_called()

    def test_update_documents_denies_user(self):
        result = tool_functions.update_documents("User", [{"document_id": "x", "a": 1}])
        self.assertFalse(result.get("success", False))

    def test_delete_document_denies_user(self):
        """delete_document denies User before DB call (mutator)."""
        result = tool_functions.delete_document("User", "test")
        self.assertFalse(result.get("success", False))
        frappe.db.exists.assert_not_called()

    def test_delete_documents_denies_user(self):
        """delete_documents denies User before DB call (mutator)."""
        result = tool_functions.delete_documents("User", ["test"])
        self.assertFalse(result.get("success", False))

    def test_submit_document_denies_user(self):
        """submit_document denies User before DB call (mutator)."""
        result = tool_functions.submit_document("User", "test")
        self.assertFalse(result.get("success", False))
        frappe.get_doc.assert_not_called()

    def test_cancel_document_denies_user(self):
        """cancel_document denies User before DB call (mutator)."""
        result = tool_functions.cancel_document("User", "test")
        self.assertFalse(result.get("success", False))
        frappe.get_doc.assert_not_called()

    def test_get_amended_document_denies_user(self):
        result = tool_functions.get_amended_document("User", "test")
        self.assertFalse(result.get("success", False))
        frappe.db.exists.assert_not_called()

    def test_get_list_denies_user(self):
        result = tool_functions.get_list("User")
        self.assertFalse(result.get("success", False))

    def test_get_value_denies_user(self):
        result = tool_functions.get_value("User", filters={"name": "test"}, fieldname="name")
        self.assertFalse(result.get("success", False))
        frappe.get_meta.assert_not_called()

    def test_set_value_denies_user(self):
        """set_value denies User before DB call (mutator)."""
        result = tool_functions.set_value("User", "test", "email", "a@b.com")
        self.assertFalse(result.get("success", False))

    def test_get_report_result_denies_when_report_denylisted(self):
        with patch("huf.ai.tool_doctype_guard._DENYLISTED_DOCTYPES", {"report"}):
            result = tool_functions.get_report_result("Some Report")
        self.assertFalse(result.get("success", False))
        frappe.get_doc.assert_not_called()

    def test_attach_file_to_document_denies_user(self):
        result = tool_functions.attach_file_to_document("User", "test")
        self.assertFalse(result.get("success", False))
        frappe.db.exists.assert_not_called()


if __name__ == "__main__":
    unittest.main()
