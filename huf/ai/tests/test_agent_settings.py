"""Tests for Agent Settings budget fields and max_turns ceiling.

ST-09.4: Tests for Agent Settings fields and server-side max_turns ceiling.
"""

from frappe.tests import IntegrationTestCase
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

import frappe
from huf.ai.run_budget import RunBudget


class TestAgentSettingsBudgetFields(IntegrationTestCase):
    """Test Agent Settings budget configuration fields."""

    @patch("frappe.get_value")
    def test_runbudget_from_agent_reads_settings(self, mock_get_value):
        """RunBudget.from_agent reads budget fields from Agent Settings."""
        # Mock Agent Settings values
        def get_value_side_effect(doctype, name, field):
            settings_defaults = {
                "deadline_seconds": 900,
                "max_turns_ceiling": 20,
                "max_depth": 3,
                "spend_cap_usd": 50.0,
            }
            return settings_defaults.get(field)

        mock_get_value.side_effect = get_value_side_effect

        # Create mock agent
        agent_doc = Mock()
        agent_doc.name = "test_agent"
        agent_doc.max_turns = 15
        agent_doc.model = "gpt-4o"

        budget = RunBudget.from_agent(agent_doc)

        assert budget.deadline_at > datetime.now()
        assert budget.max_turns_ceiling == 15  # min(15, 20)
        assert budget.spend_cap_usd == 50.0

    @patch("frappe.get_value")
    def test_runbudget_clamps_max_turns_to_ceiling(self, mock_get_value):
        """RunBudget clamps agent.max_turns to Agent Settings ceiling."""
        def get_value_side_effect(doctype, name, field):
            if field == "max_turns_ceiling":
                return 10
            elif field == "deadline_seconds":
                return 900
            elif field == "spend_cap_usd":
                return 0
            return None

        mock_get_value.side_effect = get_value_side_effect

        agent_doc = Mock()
        agent_doc.name = "test_agent"
        agent_doc.max_turns = 25  # Above ceiling
        agent_doc.model = "gpt-4o"

        budget = RunBudget.from_agent(agent_doc)

        # Should clamp to ceiling
        assert budget.max_turns_ceiling == 10

    @patch("frappe.get_value")
    def test_agent_below_ceiling_unclamped(self, mock_get_value):
        """Agent with max_turns below ceiling is not clamped."""
        def get_value_side_effect(doctype, name, field):
            if field == "max_turns_ceiling":
                return 20
            elif field == "deadline_seconds":
                return 900
            elif field == "spend_cap_usd":
                return 0
            return None

        mock_get_value.side_effect = get_value_side_effect

        agent_doc = Mock()
        agent_doc.name = "test_agent"
        agent_doc.max_turns = 5  # Below ceiling
        agent_doc.model = "gpt-4o"

        budget = RunBudget.from_agent(agent_doc)

        # Should use agent's value
        assert budget.max_turns_ceiling == 5


class TestAgentSettingsSpendCap(IntegrationTestCase):
    """Test spend cap field behavior."""

    @patch("frappe.get_value")
    def test_spend_cap_zero_means_unlimited(self, mock_get_value):
        """spend_cap_usd=0 is treated as unlimited."""
        def get_value_side_effect(doctype, name, field):
            if field == "spend_cap_usd":
                return 0  # Explicitly unlimited
            elif field == "deadline_seconds":
                return 900
            elif field == "max_turns_ceiling":
                return 20
            return None

        mock_get_value.side_effect = get_value_side_effect

        agent_doc = Mock()
        agent_doc.name = "test_agent"
        agent_doc.max_turns = 10
        agent_doc.model = "gpt-4o"

        budget = RunBudget.from_agent(agent_doc)

        assert budget.spend_cap_usd == 0

        # Unlimited cap should never raise
        budget.spend_so_far_usd = 10000.0
        budget.check_spend(5000.0)  # Should not raise

    @patch("frappe.get_value")
    def test_spend_cap_none_defaults_to_zero(self, mock_get_value):
        """Unset spend_cap defaults to 0 (unlimited), not a hard cap."""
        def get_value_side_effect(doctype, name, field):
            if field == "spend_cap_usd":
                return None  # Unset
            elif field == "deadline_seconds":
                return 900
            elif field == "max_turns_ceiling":
                return 20
            return None

        mock_get_value.side_effect = get_value_side_effect

        agent_doc = Mock()
        agent_doc.name = "test_agent"
        agent_doc.max_turns = 10
        agent_doc.model = "gpt-4o"

        budget = RunBudget.from_agent(agent_doc)

        # Should default to unlimited (0), not 100 or other hard cap
        assert budget.spend_cap_usd == 0


class TestAgentSettingsDeadline(IntegrationTestCase):
    """Test deadline field configuration."""

    @patch("frappe.get_value")
    def test_deadline_seconds_respected(self, mock_get_value):
        """deadline_seconds from Agent Settings is used."""
        def get_value_side_effect(doctype, name, field):
            if field == "deadline_seconds":
                return 600  # 10 minutes
            elif field == "max_turns_ceiling":
                return 20
            elif field == "spend_cap_usd":
                return 0
            return None

        mock_get_value.side_effect = get_value_side_effect

        agent_doc = Mock()
        agent_doc.name = "test_agent"
        agent_doc.max_turns = 10
        agent_doc.model = "gpt-4o"

        before = datetime.now()
        budget = RunBudget.from_agent(agent_doc)
        after = datetime.now()

        # Deadline should be ~600 seconds in future
        time_until_deadline = (budget.deadline_at - after).total_seconds()
        assert 590 <= time_until_deadline <= 610


class TestAgentSettingsMaxDepth(IntegrationTestCase):
    """Test max_depth configuration."""

    @patch("frappe.get_value")
    def test_max_depth_used_for_checks(self, mock_get_value):
        """max_depth from Agent Settings is used in check_depth."""
        def get_value_side_effect(doctype, name, field):
            if field == "max_depth":
                return 3
            elif field == "deadline_seconds":
                return 900
            elif field == "max_turns_ceiling":
                return 20
            elif field == "spend_cap_usd":
                return 0
            return None

        mock_get_value.side_effect = get_value_side_effect

        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=20,
            depth=3,
            ancestry=[],
            spend_cap_usd=0
        )

        # Should use default from Agent Settings
        with self.assertRaises(frappe.ValidationError):
            budget.check_depth()  # Uses default from settings
