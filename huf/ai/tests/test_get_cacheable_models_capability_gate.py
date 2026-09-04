"""Unit tests for huf.huf.doctype.agent.agent.get_cacheable_models's
capability gate (ST-R5.11).

The function is whitelisted config-UI plumbing consumed only by the
edit-only Agent config UI, so it must be gated on the "agent.edit"
capability -- and ONLY that capability, not "agent.view_all" and not the
underlying DocPerm read permission on "AI Provider"/"AI Model". These tests
prove the gate is capability-based, not DocPerm-based, per the plan's
acceptance criteria.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.tests.test_get_cacheable_models_capability_gate
"""
import unittest
from unittest.mock import patch

import frappe

from huf.huf.doctype.agent.agent import get_cacheable_models


class TestGetCacheableModelsCapabilityGate(unittest.TestCase):
    def setUp(self):
        self._orig_user = frappe.session.user
        frappe.session.user = "someone@example.com"

    def tearDown(self):
        frappe.session.user = self._orig_user

    def test_denied_without_agent_edit_capability_returns_empty_list(self):
        with patch(
            "huf.permissions.has_capability", return_value=False
        ) as mock_has_capability:
            result = get_cacheable_models(provider="Some Provider", model="some-model")

        self.assertEqual(result, [])
        mock_has_capability.assert_called_once_with("someone@example.com", "agent.edit")

    def test_allowed_with_agent_edit_capability_even_without_docperm_read(self):
        """A user WITH agent.edit but explicitly denied DocPerm read on
        AI Provider must still get the full result -- proving the gate is
        capability-based, not DocPerm-based.
        """
        with patch("huf.permissions.has_capability", return_value=True), patch(
            "huf.huf.doctype.agent.agent.frappe.has_permission", return_value=False
        ), patch(
            "huf.huf.doctype.agent.agent.frappe.db.get_value",
            side_effect=lambda doctype, name, field: {
                ("AI Model", "some-model", "model_name"): "some-model",
                ("AI Provider", "Some Provider", "provider_name"): "Some Provider",
            }.get((doctype, name, field)),
        ), patch(
            "huf.huf.doctype.agent.agent._check_model_supports_caching",
            return_value=True,
        ), patch(
            "huf.huf.doctype.agent.agent._get_cacheable_models_for_provider",
            return_value=["alt-model-1", "alt-model-2"],
        ):
            result = get_cacheable_models(provider="Some Provider", model="some-model")

        # frappe.has_permission (DocPerm) is never even consulted by this
        # function -- the assertion above just documents that a denial there
        # would not matter. The real proof is that we get the full payload.
        self.assertEqual(
            result, {"supported": True, "alternatives": ["alt-model-1", "alt-model-2"]}
        )

    def test_no_provider_still_requires_capability_first(self):
        with patch(
            "huf.permissions.has_capability", return_value=False
        ) as mock_has_capability:
            result = get_cacheable_models(provider=None)

        self.assertEqual(result, [])
        mock_has_capability.assert_called_once()


if __name__ == "__main__":
    unittest.main()
