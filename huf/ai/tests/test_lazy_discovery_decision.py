"""Tests for Tool Selection decision integration in lazy discovery (T4.02, PLAN.md §3.6).

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.tests.test_lazy_discovery_decision
"""

import json
import unittest
from types import SimpleNamespace
from unittest import mock

import frappe

from huf.ai.tools.lazy_discovery import (
    handle_list_tool_groups,
    handle_search_tools,
)
from huf.ai.decision.types import (
    DecisionOrigin,
    DecisionResponse,
    DecisionStatus,
    DecisionAnswer,
    Option,
    QuestionKind,
    ServiceResult,
    CandidateSource,
)


class TestToolSelectionDecision(unittest.TestCase):
    """Test Tool Selection decision integration in lazy discovery handlers."""

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")

    def setUp(self):
        frappe.set_user("Administrator")
        self.agent_name = "Test Agent Decision"

    def tearDown(self):
        frappe.set_user("Administrator")
        try:
            frappe.delete_doc("Agent", self.agent_name, force=True, ignore_permissions=True)
        except Exception:
            pass

    def _make_binding(self, policy, mode="Off", surface="Tool Selection"):
        """Create a decision binding row for testing."""
        return {
            "surface": surface,
            "policy": policy,
            "mode": mode,
            "priority": 100,
            "enabled": 1,
            "latency_budget_ms": None,
        }

    def _mock_allowed_tools(self):
        """Mock PermissionAwareToolRegistry.get_allowed_tools."""
        return [
            SimpleNamespace(
                tool_name="create_invoice",
                description="Create an invoice",
                service="Finance",
                provider_app="frappe",
            ),
            SimpleNamespace(
                tool_name="lookup_customer",
                description="Look up customer details",
                service="CRM",
                provider_app="frappe",
            ),
        ]

    def test_list_tool_groups_off_mode_returns_unchanged(self):
        """Test that Off mode returns the original list unchanged."""
        agent_mock = SimpleNamespace(
            name=self.agent_name,
            decision_bindings=[SimpleNamespace(**self._make_binding("some-policy", mode="Off"))],
        )

        with mock.patch(
            "huf.ai.tools.lazy_discovery._resolve_agent_doc",
            return_value=agent_mock,
        ), mock.patch(
            "huf.ai.tools.lazy_discovery.PermissionAwareToolRegistry.get_allowed_tools",
            return_value=self._mock_allowed_tools(),
        ):
            result = handle_list_tool_groups(agent_name=self.agent_name)

        parsed = json.loads(result)
        # Should have groups for Finance and CRM
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["service"], "Finance")
        self.assertEqual(parsed[1]["service"], "CRM")

    def test_list_tool_groups_no_binding_returns_unchanged(self):
        """Test that missing binding returns original list unchanged."""
        agent_mock = SimpleNamespace(
            name=self.agent_name,
            decision_bindings=[],
        )

        with mock.patch(
            "huf.ai.tools.lazy_discovery._resolve_agent_doc",
            return_value=agent_mock,
        ), mock.patch(
            "huf.ai.tools.lazy_discovery.PermissionAwareToolRegistry.get_allowed_tools",
            return_value=self._mock_allowed_tools(),
        ):
            result = handle_list_tool_groups(agent_name=self.agent_name)

        parsed = json.loads(result)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["service"], "Finance")

    def test_list_tool_groups_advise_appends_hint(self):
        """Test that Advise mode appends a decision hint to the result."""
        agent_mock = SimpleNamespace(
            name=self.agent_name,
            decision_bindings=[SimpleNamespace(**self._make_binding("advise-policy", mode="Advise"))],
        )

        response = DecisionResponse(
            status=DecisionStatus.SUCCESS,
            answers={
                "pick": DecisionAnswer(
                    "pick",
                    QuestionKind.SCORE,
                    value=None,
                    probabilities={"Finance": 0.9, "CRM": 0.7},
                )
            },
        )

        with mock.patch(
            "huf.ai.tools.lazy_discovery._resolve_agent_doc",
            return_value=agent_mock,
        ), mock.patch(
            "huf.ai.tools.lazy_discovery.PermissionAwareToolRegistry.get_allowed_tools",
            return_value=self._mock_allowed_tools(),
        ), mock.patch(
            "huf.ai.decision.agent_surfaces.service.run_policy",
            return_value=ServiceResult(status=DecisionStatus.SUCCESS, response=response),
        ):
            result = handle_list_tool_groups(
                agent_name=self.agent_name,
                agent_run_id="ar-123",
                conversation_id="conv-123",
            )

        parsed = json.loads(result)
        # Should have original groups + hint entry
        self.assertGreaterEqual(len(parsed), 2)
        # Last entry should be the hint
        last_entry = parsed[-1]
        self.assertEqual(last_entry["service"], "_decision_hint")
        self.assertIn("Finance", last_entry["summary"])

    def test_list_tool_groups_enforce_narrows(self):
        """Test that Enforce mode narrows and reorders the result."""
        agent_mock = SimpleNamespace(
            name=self.agent_name,
            decision_bindings=[SimpleNamespace(**self._make_binding("enforce-policy", mode="Enforce"))],
        )

        response = DecisionResponse(
            status=DecisionStatus.SUCCESS,
            answers={
                "pick": DecisionAnswer(
                    "pick",
                    QuestionKind.SELECT,
                    value="Finance",
                )
            },
        )

        with mock.patch(
            "huf.ai.tools.lazy_discovery._resolve_agent_doc",
            return_value=agent_mock,
        ), mock.patch(
            "huf.ai.tools.lazy_discovery.PermissionAwareToolRegistry.get_allowed_tools",
            return_value=self._mock_allowed_tools(),
        ), mock.patch(
            "huf.ai.decision.agent_surfaces.service.run_policy",
            return_value=ServiceResult(status=DecisionStatus.SUCCESS, response=response),
        ):
            result = handle_list_tool_groups(
                agent_name=self.agent_name,
                agent_run_id="ar-123",
                conversation_id="conv-123",
            )

        parsed = json.loads(result)
        # Should only have Finance
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["service"], "Finance")

    def test_search_tools_off_mode_returns_unchanged(self):
        """Test that Off mode returns the original search results unchanged."""
        agent_mock = SimpleNamespace(
            name=self.agent_name,
            decision_bindings=[SimpleNamespace(**self._make_binding("some-policy", mode="Off"))],
        )

        with mock.patch(
            "huf.ai.tools.lazy_discovery._resolve_agent_doc",
            return_value=agent_mock,
        ), mock.patch(
            "huf.ai.tools.lazy_discovery.PermissionAwareToolRegistry.get_allowed_tools",
            return_value=self._mock_allowed_tools(),
        ), mock.patch(
            "huf.ai.capability_discovery.actions.search_app_actions",
            return_value=[{"title": "create_invoice", "description": "Create an invoice"}],
        ):
            result = handle_search_tools(
                query="invoice",
                agent_name=self.agent_name,
            )

        parsed = json.loads(result)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["tool_name"], "create_invoice")

    def test_search_tools_advise_appends_hint(self):
        """Test that Advise mode appends a decision hint to search results."""
        agent_mock = SimpleNamespace(
            name=self.agent_name,
            decision_bindings=[SimpleNamespace(**self._make_binding("advise-policy", mode="Advise"))],
        )

        response = DecisionResponse(
            status=DecisionStatus.SUCCESS,
            answers={
                "pick": DecisionAnswer(
                    "pick",
                    QuestionKind.SCORE,
                    value=None,
                    probabilities={"create_invoice": 0.95, "lookup_customer": 0.6},
                )
            },
        )

        with mock.patch(
            "huf.ai.tools.lazy_discovery._resolve_agent_doc",
            return_value=agent_mock,
        ), mock.patch(
            "huf.ai.tools.lazy_discovery.PermissionAwareToolRegistry.get_allowed_tools",
            return_value=self._mock_allowed_tools(),
        ), mock.patch(
            "huf.ai.capability_discovery.actions.search_app_actions",
            return_value=[
                {"title": "create_invoice", "description": "Create an invoice"},
                {"title": "lookup_customer", "description": "Look up customer"},
            ],
        ), mock.patch(
            "huf.ai.decision.agent_surfaces.service.run_policy",
            return_value=ServiceResult(status=DecisionStatus.SUCCESS, response=response),
        ):
            result = handle_search_tools(
                query="customer",
                agent_name=self.agent_name,
                agent_run_id="ar-123",
                conversation_id="conv-123",
            )

        parsed = json.loads(result)
        # Should have original results + hint entry
        self.assertGreaterEqual(len(parsed), 2)
        # Last entry should be the hint
        last_entry = parsed[-1]
        self.assertEqual(last_entry["tool_name"], "_decision_hint")
        self.assertIn("create_invoice", last_entry["description"])

    def test_search_tools_enforce_narrows(self):
        """Test that Enforce mode narrows and reorders search results."""
        agent_mock = SimpleNamespace(
            name=self.agent_name,
            decision_bindings=[SimpleNamespace(**self._make_binding("enforce-policy", mode="Enforce"))],
        )

        response = DecisionResponse(
            status=DecisionStatus.SUCCESS,
            answers={
                "pick": DecisionAnswer(
                    "pick",
                    QuestionKind.SELECT,
                    value="create_invoice",
                )
            },
        )

        with mock.patch(
            "huf.ai.tools.lazy_discovery._resolve_agent_doc",
            return_value=agent_mock,
        ), mock.patch(
            "huf.ai.tools.lazy_discovery.PermissionAwareToolRegistry.get_allowed_tools",
            return_value=self._mock_allowed_tools(),
        ), mock.patch(
            "huf.ai.capability_discovery.actions.search_app_actions",
            return_value=[
                {"title": "create_invoice", "description": "Create an invoice"},
                {"title": "lookup_customer", "description": "Look up customer"},
            ],
        ), mock.patch(
            "huf.ai.decision.agent_surfaces.service.run_policy",
            return_value=ServiceResult(status=DecisionStatus.SUCCESS, response=response),
        ):
            result = handle_search_tools(
                query="customer",
                agent_name=self.agent_name,
                agent_run_id="ar-123",
                conversation_id="conv-123",
            )

        parsed = json.loads(result)
        # Should only have create_invoice
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["tool_name"], "create_invoice")

    def test_decision_error_returns_unchanged(self):
        """Test that decision errors return original results unchanged."""
        agent_mock = SimpleNamespace(
            name=self.agent_name,
            decision_bindings=[SimpleNamespace(**self._make_binding("bad-policy", mode="Enforce"))],
        )

        with mock.patch(
            "huf.ai.tools.lazy_discovery._resolve_agent_doc",
            return_value=agent_mock,
        ), mock.patch(
            "huf.ai.tools.lazy_discovery.PermissionAwareToolRegistry.get_allowed_tools",
            return_value=self._mock_allowed_tools(),
        ), mock.patch(
            "huf.ai.decision.agent_surfaces.service.run_policy",
            return_value=ServiceResult(status=DecisionStatus.TIMEOUT),
        ):
            result = handle_list_tool_groups(agent_name=self.agent_name)

        parsed = json.loads(result)
        # Should have original groups despite timeout
        self.assertEqual(len(parsed), 2)

    def test_golden_test_off_mode_byte_identical(self):
        """Golden test: Off mode output is byte-identical to baseline (no binding)."""
        agent_off = SimpleNamespace(
            name=self.agent_name,
            decision_bindings=[SimpleNamespace(**self._make_binding("some-policy", mode="Off"))],
        )
        agent_no_binding = SimpleNamespace(
            name=self.agent_name + "_no_binding",
            decision_bindings=[],
        )

        with mock.patch(
            "huf.ai.tools.lazy_discovery._resolve_agent_doc",
            side_effect=lambda kwargs: (
                agent_off if kwargs.get("agent_name") == self.agent_name else agent_no_binding
            ),
        ), mock.patch(
            "huf.ai.tools.lazy_discovery.PermissionAwareToolRegistry.get_allowed_tools",
            return_value=self._mock_allowed_tools(),
        ):
            result_off = handle_list_tool_groups(agent_name=self.agent_name)
            result_no_binding = handle_list_tool_groups(
                agent_name=self.agent_name + "_no_binding"
            )

        # Byte-identical JSON output
        self.assertEqual(result_off, result_no_binding)


if __name__ == "__main__":
    unittest.main()
