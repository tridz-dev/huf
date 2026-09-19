# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Coverage for the dual-control / anti-self-approval guard added to
``_can_decide`` (huf.huf.doctype.agent_execution_approval.agent_execution_approval).

ST-R5.15: a new persisted ``requested_by`` field records who triggered a
code/SSH execution approval. ``_can_decide`` now short-circuits before its
existing capability/role/user checks: if ``requested_by`` is set and matches
the acting user, the decision is gated on the ``Agent Settings.allow_self_approval``
escape hatch (default off, fail-closed) rather than falling through to the
normal approver checks (which would otherwise let a requester who also holds
the approval capability rubber-stamp their own request).

Pre-migration rows with an empty/None ``requested_by`` must be entirely
unaffected -- the guard is skipped and the pre-existing (a)/(b)/(c) logic in
``_can_decide`` decides the outcome, same as before this change.
"""

import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _stub_env  # noqa: E402

_stub_env.install()

# ``agent_execution_approval.py`` additionally does
# ``from frappe.model.document import Document`` and
# ``from frappe.utils import get_datetime, now_datetime`` -- _stub_env wires
# ``frappe.utils`` already; add the ``frappe.model.document`` submodule here
# since no other test in this suite needs it yet.
if "frappe.model.document" not in sys.modules:
    frappe_model = sys.modules.get("frappe.model") or types.ModuleType("frappe.model")
    sys.modules.setdefault("frappe.model", frappe_model)
    frappe_model_document = types.ModuleType("frappe.model.document")

    class _StubDocument:
        pass

    frappe_model_document.Document = _StubDocument
    sys.modules["frappe.model.document"] = frappe_model_document
    frappe_model.document = frappe_model_document

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

import frappe  # noqa: E402

from huf.huf.doctype.agent_execution_approval.agent_execution_approval import (  # noqa: E402
    _can_decide,
)


class _FakeApproval:
    """Minimal stand-in for an ``Agent Execution Approval`` Document."""

    def __init__(self, requested_by=None, approver_role=None, approver_users=None):
        self.requested_by = requested_by
        self.approver_role = approver_role
        self.approver_users = approver_users or []
        self.execution_kind = "code_execution"


class TestSelfApprovalGuard(unittest.TestCase):
    def setUp(self):
        # Reset frappe stub attributes touched by _can_decide / its helpers
        # between tests so mock call history doesn't leak across cases.
        frappe.get_roles = MagicMock(return_value=[])
        frappe.db = MagicMock()
        frappe.db.get_single_value = MagicMock(return_value=0)

    def test_self_approval_denied_by_default(self):
        """(a) requested_by == user, allow_self_approval unset/0 -> False."""
        doc = _FakeApproval(requested_by="user_A")
        frappe.db.get_single_value.return_value = 0

        with patch(
            "huf.huf.doctype.agent_execution_approval.agent_execution_approval."
            "_has_approval_capability",
            return_value=True,  # would otherwise grant via path (a); must not be reached
        ) as has_cap:
            result = _can_decide(doc, "user_A")

        self.assertFalse(result)
        # The self-approval branch must short-circuit before falling through
        # to the capability check for the matching requester.
        has_cap.assert_not_called()

    def test_self_approval_allowed_with_escape_hatch(self):
        """(b) requested_by == user, allow_self_approval=1 -> True."""
        doc = _FakeApproval(requested_by="user_A")
        frappe.db.get_single_value.return_value = 1

        result = _can_decide(doc, "user_A")

        self.assertTrue(result)
        frappe.db.get_single_value.assert_called_with("Agent Settings", "allow_self_approval")

    def test_empty_requested_by_skips_guard_entirely(self):
        """(c) requested_by empty/None -> guard skipped, _self_approval_permitted not called."""
        for empty_value in (None, ""):
            doc = _FakeApproval(requested_by=empty_value)

            with patch(
                "huf.huf.doctype.agent_execution_approval.agent_execution_approval."
                "_self_approval_permitted"
            ) as self_approval_permitted:
                with patch(
                    "huf.huf.doctype.agent_execution_approval.agent_execution_approval."
                    "_has_approval_capability",
                    return_value=False,
                ):
                    # Any user, any outcome from (a)/(b)/(c) is fine -- the
                    # only thing under test is that the new guard is a no-op.
                    _can_decide(doc, "anyone")

            self_approval_permitted.assert_not_called()

    def test_different_requester_does_not_block(self):
        """(d) requested_by set to a DIFFERENT user -> guard doesn't block; normal checks apply."""
        doc = _FakeApproval(requested_by="user_A")

        with patch(
            "huf.huf.doctype.agent_execution_approval.agent_execution_approval."
            "_self_approval_permitted"
        ) as self_approval_permitted:
            with patch(
                "huf.huf.doctype.agent_execution_approval.agent_execution_approval."
                "_has_approval_capability",
                return_value=True,
            ):
                result = _can_decide(doc, "user_B")

        self.assertTrue(result)
        self_approval_permitted.assert_not_called()


if __name__ == "__main__":
    unittest.main()
