"""Tests for recursion depth limits and ancestry chains.

ST-09.5: Tests for depth enforcement across orchestration, sub-agent,
and automation vectors.
"""

from frappe.tests import IntegrationTestCase
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

import frappe
from huf.ai.run_budget import RunBudget, RunBudgetExceeded


class TestRecursionDepthChain(IntegrationTestCase):
    """Test building and enforcing recursion depth chains."""

    def test_depth_increments_with_ancestry(self):
        """Depth increments correctly as ancestry grows."""
        # Root run
        budget_0 = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=0,
            ancestry=[],
            spend_cap_usd=0
        )
        assert budget_0.current_depth == 0
        assert len(budget_0.ancestry) == 0

        # Child of root
        run_id_0 = "run_root"
        budget_1 = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=1,
            ancestry=[run_id_0],
            spend_cap_usd=0
        )
        assert budget_1.current_depth == 1
        assert budget_1.ancestry == [run_id_0]

        # Grandchild
        run_id_1 = "run_child_1"
        budget_2 = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=2,
            ancestry=[run_id_0, run_id_1],
            spend_cap_usd=0
        )
        assert budget_2.current_depth == 2
        assert budget_2.ancestry == [run_id_0, run_id_1]

    def test_ancestry_chain_does_not_duplicate(self):
        """Ancestry chain grows linearly without duplication."""
        ancestors = []
        for i in range(5):
            run_id = f"run_{i}"
            new_ancestors = ancestors + [run_id]
            assert len(new_ancestors) == i + 1
            assert new_ancestors[-1] == run_id
            ancestors = new_ancestors

        # Final chain should have 5 unique elements
        assert len(ancestors) == 5
        assert len(set(ancestors)) == 5  # All unique


class TestDepthCheckBehavior(IntegrationTestCase):
    """Test check_depth() behavior at various depths."""

    def test_depth_at_zero(self):
        """Depth 0 should pass at any reasonable ceiling."""
        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=0,
            ancestry=[],
            spend_cap_usd=0
        )

        # Should pass at any ceiling >= 0
        budget.check_depth(max_depth=1)
        budget.check_depth(max_depth=2)
        budget.check_depth(max_depth=10)

    def test_depth_equals_ceiling(self):
        """Depth equal to ceiling uses >= check (passes at equality)."""
        # The check is: if self.current_depth >= max_depth: raise
        # So at equality, it should raise
        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=3,
            ancestry=[],
            spend_cap_usd=0
        )

        # At equality, should raise
        with self.assertRaises(frappe.ValidationError):
            budget.check_depth(max_depth=3)

    def test_depth_below_ceiling(self):
        """Depth strictly below ceiling passes."""
        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=2,
            ancestry=[],
            spend_cap_usd=0
        )

        # Below ceiling, should pass
        budget.check_depth(max_depth=3)

    def test_depth_above_ceiling(self):
        """Depth above ceiling raises."""
        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=5,
            ancestry=[],
            spend_cap_usd=0
        )

        # Above ceiling, should raise
        with self.assertRaises(frappe.ValidationError):
            budget.check_depth(max_depth=3)


class TestDepthCheckUsesDefaults(IntegrationTestCase):
    """Test that check_depth uses Agent Settings defaults when no arg provided."""

    @patch("frappe.db.get_single_value")
    def test_check_depth_default_from_settings(self, mock_get_value):
        """check_depth() with no arg uses Agent Settings.max_depth."""
        mock_get_value.return_value = 4  # Default from settings

        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=3,
            ancestry=[],
            spend_cap_usd=0
        )

        # Should pass (depth 3 < default 4)
        budget.check_depth()

        # Should raise at equality
        budget.current_depth = 4
        with self.assertRaises(frappe.ValidationError):
            budget.check_depth()

    @patch("frappe.db.get_single_value")
    def test_check_depth_fallback_to_hardcoded_default(self, mock_get_value):
        """check_depth() falls back to 5 if Agent Settings not available."""
        mock_get_value.return_value = None  # Settings not available

        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=4,
            ancestry=[],
            spend_cap_usd=0
        )

        # Should pass (depth 4 < fallback 5)
        budget.check_depth()

        # Should raise at equality
        budget.current_depth = 5
        with self.assertRaises(frappe.ValidationError):
            budget.check_depth()


class TestAncestryEdgeCases(IntegrationTestCase):
    """Test edge cases in ancestry handling."""

    def test_empty_ancestry_at_root(self):
        """Root run has empty ancestry."""
        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=0,
            ancestry=[],
            spend_cap_usd=0
        )
        assert budget.ancestry == []
        assert len(budget.ancestry) == 0

    def test_single_element_ancestry(self):
        """First child has single-element ancestry."""
        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=1,
            ancestry=["parent_run_id"],
            spend_cap_usd=0
        )
        assert budget.ancestry == ["parent_run_id"]
        assert budget.current_depth == 1

    def test_long_ancestry_chain(self):
        """Long ancestry chains are preserved."""
        long_ancestry = [f"run_{i}" for i in range(10)]
        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=10,
            ancestry=long_ancestry,
            spend_cap_usd=0
        )
        assert budget.ancestry == long_ancestry
        assert len(budget.ancestry) == 10
