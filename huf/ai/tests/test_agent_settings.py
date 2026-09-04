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

    @patch("frappe.db.get_single_value")
    def test_runbudget_from_agent_reads_settings(self, mock_get_value):
        """RunBudget.from_agent reads budget fields from Agent Settings."""
        # Mock Agent Settings values
        def get_value_side_effect(doctype, field):
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

    @patch("frappe.db.get_single_value")
    def test_runbudget_clamps_max_turns_to_ceiling(self, mock_get_value):
        """RunBudget clamps agent.max_turns to Agent Settings ceiling."""
        def get_value_side_effect(doctype, field):
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

    @patch("frappe.db.get_single_value")
    def test_agent_below_ceiling_unclamped(self, mock_get_value):
        """Agent with max_turns below ceiling is not clamped."""
        def get_value_side_effect(doctype, field):
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

    @patch("frappe.db.get_single_value")
    def test_spend_cap_zero_means_unlimited(self, mock_get_value):
        """spend_cap_usd=0 is treated as unlimited."""
        def get_value_side_effect(doctype, field):
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

    @patch("frappe.db.get_single_value")
    def test_spend_cap_none_defaults_to_zero(self, mock_get_value):
        """Unset spend_cap defaults to 0 (unlimited), not a hard cap."""
        def get_value_side_effect(doctype, field):
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

    @patch("frappe.db.get_single_value")
    def test_deadline_seconds_respected(self, mock_get_value):
        """deadline_seconds from Agent Settings is used."""
        def get_value_side_effect(doctype, field):
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

    @patch("frappe.db.get_single_value")
    def test_max_depth_used_for_checks(self, mock_get_value):
        """max_depth from Agent Settings is used in check_depth."""
        def get_value_side_effect(doctype, field):
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


class TestAgentSettingsRealSingleTyping(IntegrationTestCase):
    """Unmocked reads of the Agent Settings Single doctype.

    Every other test in this module mocks the settings accessor and hands
    back a Python int or float. The real Single stores each value as a
    string in the generic ``tabSingles`` table, so a mock that returns
    ``0`` asserts against a value shape the database never produces.

    That gap let a total-outage bug ship: ``RunBudget.from_agent`` read
    the settings with ``frappe.get_value("Agent Settings", None, field)``,
    which does not apply the field's type cast, so ``max_turns_ceiling``
    arrived as the string ``"0"`` and ``min(int, str)`` raised TypeError on
    every agent run, on every site, whatever the configured values. The
    whole suite stayed green throughout.

    These tests therefore write real values and read them back through the
    real accessor. They must never be converted to mocks.
    """

    def setUp(self):
        self.settings = frappe.get_single("Agent Settings")
        self._saved = {
            f: self.settings.get(f)
            for f in ("max_turns_ceiling", "deadline_seconds",
                      "spend_cap_usd", "max_depth")
        }

    def tearDown(self):
        for field, value in self._saved.items():
            frappe.db.set_single_value("Agent Settings", field, value)
        frappe.db.commit()

    def _configure(self, **values):
        for field, value in values.items():
            frappe.db.set_single_value("Agent Settings", field, value)
        frappe.db.commit()

    def _agent(self, max_turns=15):
        agent_doc = Mock()
        agent_doc.name = "test_agent"
        agent_doc.max_turns = max_turns
        agent_doc.model = "gpt-4o"
        return agent_doc

    def test_settings_read_returns_numbers_not_strings(self):
        """The accessor RunBudget uses must apply the field's type cast."""
        self._configure(max_turns_ceiling=20, deadline_seconds=900,
                        spend_cap_usd=50.0, max_depth=3)

        for field in ("max_turns_ceiling", "deadline_seconds", "max_depth"):
            value = frappe.db.get_single_value("Agent Settings", field)
            self.assertIsInstance(
                value, int,
                f"{field} came back as {type(value).__name__} ({value!r}); "
                "Singles store strings, so RunBudget needs the cast")

        self.assertIsInstance(
            frappe.db.get_single_value("Agent Settings", "spend_cap_usd"), float)

    def test_from_agent_against_real_settings(self):
        """from_agent must not raise TypeError on real, unmocked settings."""
        self._configure(max_turns_ceiling=20, deadline_seconds=900,
                        spend_cap_usd=50.0, max_depth=3)

        budget = RunBudget.from_agent(self._agent(max_turns=15))

        self.assertEqual(budget.max_turns_ceiling, 15)  # min(15, 20)
        self.assertIsInstance(budget.max_turns_ceiling, int)
        self.assertEqual(budget.spend_cap_usd, 50.0)
        self.assertIsInstance(budget.spend_cap_usd, float)
        self.assertGreater(budget.deadline_at, datetime.now())

    def test_zero_ceiling_does_not_crash(self):
        """A stored 0 is the regression trigger: it round-trips as "0"."""
        self._configure(max_turns_ceiling=0, deadline_seconds=0,
                        spend_cap_usd=0, max_depth=0)

        budget = RunBudget.from_agent(self._agent(max_turns=15))

        # 0 is falsy, so each read falls through to its coded default.
        self.assertIsInstance(budget.max_turns_ceiling, int)
        self.assertEqual(budget.max_turns_ceiling, 15)  # min(15, 20 default)

    def test_zero_spend_cap_is_unlimited_not_a_hard_cap(self):
        """The quiet half of the bug: "0" is truthy, 0 is not.

        spend_cap_usd == 0 means unlimited (ST-09.4). Read untyped, the
        stored 0 arrived as the truthy string "0", so it never hit the
        ``is None`` branch and never read as falsy in check_spend's guard
        — silently inverting "unlimited" into a hard cap. This one never
        raised TypeError, so no crash would have revealed it.
        """
        self._configure(max_turns_ceiling=20, deadline_seconds=900,
                        spend_cap_usd=0, max_depth=3)

        budget = RunBudget.from_agent(self._agent())

        self.assertEqual(budget.spend_cap_usd, 0)
        self.assertFalse(
            budget.spend_cap_usd,
            "spend_cap_usd must be falsy for check_spend's unlimited guard")

        budget.spend_so_far_usd = 10_000.0
        budget.check_spend(9_999.0)  # must not raise

    def test_check_depth_against_real_settings(self):
        """check_depth compares current_depth >= max_depth numerically."""
        self._configure(max_depth=3, max_turns_ceiling=20,
                        deadline_seconds=900, spend_cap_usd=0)

        budget = RunBudget.from_agent(self._agent())
        budget.current_depth = 1
        budget.check_depth()  # below ceiling, must not raise

        budget.current_depth = 5
        with self.assertRaises(frappe.ValidationError):
            budget.check_depth()
