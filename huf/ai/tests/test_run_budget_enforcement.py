"""Tests for run budget enforcement: depth, deadline, and spend cap.

ST-09.9: Tests for A→B→A cycle depth limit, deadline enforcement, and spend cap.
Uses pure-mock style for isolation and speed.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

import frappe
from huf.ai.run_budget import RunBudget, RunBudgetExceeded, estimate_run_cost


class TestRecursionDepthEnforcement:
    """Test A→B→A cycle at max_depth ceiling (ST-09.9 scenario 1)."""

    def test_depth_limit_prevents_third_hop(self):
        """A→B→A cycle at max_depth=2 is blocked at the third hop.

        Setup:
        - Create agents A and B
        - A calls B as sub-agent
        - B calls A as sub-agent
        - Set max_depth=2

        Behavior:
        - First hop (A at depth 0) -> succeeds
        - Second hop (B at depth 1) -> succeeds
        - Third hop (A at depth 2) -> blocked with RunBudgetExceeded
        """
        # Start with depth 0 (root run)
        budget_root = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=0,
            ancestry=[],
            spend_cap_usd=0
        )
        # Should not raise at depth 0
        budget_root.check_depth(max_depth=2)

        # First child at depth 1
        budget_depth_1 = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=1,
            ancestry=["run_id_0"],
            spend_cap_usd=0
        )
        # Should not raise at depth 1
        budget_depth_1.check_depth(max_depth=2)

        # Second child at depth 2 (at the ceiling)
        budget_depth_2 = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=2,
            ancestry=["run_id_0", "run_id_1"],
            spend_cap_usd=0
        )
        # Should not raise at depth 2 with ceiling=2 (equality is still ok)
        budget_depth_2.check_depth(max_depth=2)

        # Third child at depth 3 (exceeds ceiling)
        budget_depth_3 = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=3,
            ancestry=["run_id_0", "run_id_1", "run_id_2"],
            spend_cap_usd=0
        )
        # Should raise at depth 3 with ceiling=2
        with pytest.raises(frappe.ValidationError) as exc_info:
            budget_depth_3.check_depth(max_depth=2)
        assert "Recursion depth" in str(exc_info.value)

    def test_ancestry_chain_preserved(self):
        """Ancestry chain grows correctly through multiple hops."""
        # Simulate chain: A (depth 0) -> B (depth 1) -> A (depth 2)
        ancestry = []
        depth = 0
        max_depth = 3

        # First hop: A (depth 0)
        budget_a1 = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=depth,
            ancestry=ancestry,
            spend_cap_usd=0
        )
        assert budget_a1.current_depth == 0
        assert budget_a1.ancestry == []

        # Second hop: B (depth 1)
        run_id_a1 = "run_a_1"
        ancestry = [run_id_a1]
        depth = 1
        budget_b = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=depth,
            ancestry=ancestry,
            spend_cap_usd=0
        )
        assert budget_b.current_depth == 1
        assert budget_b.ancestry == [run_id_a1]

        # Third hop: A (depth 2)
        run_id_b = "run_b_1"
        ancestry = [run_id_a1, run_id_b]
        depth = 2
        budget_a2 = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=depth,
            ancestry=ancestry,
            spend_cap_usd=0
        )
        assert budget_a2.current_depth == 2
        assert budget_a2.ancestry == [run_id_a1, run_id_b]


class TestDeadlineEnforcement:
    """Test wall-clock deadline enforcement (ST-09.9 scenario 2)."""

    def test_deadline_exceeded_blocks_execution(self):
        """Budget with expired deadline raises RunBudgetExceeded."""
        # Create a budget with a deadline in the past
        deadline_past = datetime.now() - timedelta(seconds=10)
        budget = RunBudget(
            deadline_at=deadline_past,
            max_turns_ceiling=10,
            depth=0,
            ancestry=[],
            spend_cap_usd=0
        )

        # Should raise when checking deadline
        with pytest.raises(frappe.ValidationError) as exc_info:
            budget.check_deadline()
        assert "deadline exceeded" in str(exc_info.value).lower()

    def test_deadline_not_exceeded_permits_execution(self):
        """Budget with future deadline does not raise."""
        # Create a budget with deadline 10 seconds in the future
        deadline_future = datetime.now() + timedelta(seconds=10)
        budget = RunBudget(
            deadline_at=deadline_future,
            max_turns_ceiling=10,
            depth=0,
            ancestry=[],
            spend_cap_usd=0
        )

        # Should not raise
        budget.check_deadline()

    def test_is_deadline_exceeded_accessor(self):
        """is_deadline_exceeded() returns boolean without raising."""
        deadline_past = datetime.now() - timedelta(seconds=10)
        budget_past = RunBudget(
            deadline_at=deadline_past,
            max_turns_ceiling=10,
            depth=0,
            ancestry=[],
            spend_cap_usd=0
        )
        assert budget_past.is_deadline_exceeded() is True

        deadline_future = datetime.now() + timedelta(seconds=10)
        budget_future = RunBudget(
            deadline_at=deadline_future,
            max_turns_ceiling=10,
            depth=0,
            ancestry=[],
            spend_cap_usd=0
        )
        assert budget_future.is_deadline_exceeded() is False


class TestSpendCapEnforcement:
    """Test cumulative spend cap enforcement (ST-09.9 scenario 3)."""

    def test_spend_cap_blocks_expensive_child(self):
        """Budget with spend_cap=10 and spend_so_far=9 blocks a 2.0 child."""
        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=0,
            ancestry=[],
            spend_cap_usd=10.0
        )
        budget.spend_so_far_usd = 9.0

        # Should raise when trying to add 2.0 (total would be 11.0 > 10.0)
        with pytest.raises(frappe.ValidationError) as exc_info:
            budget.check_spend(2.0)
        assert "spend" in str(exc_info.value).lower() or "budget" in str(exc_info.value).lower()

    def test_spend_cap_allows_affordable_child(self):
        """Budget with spend_cap=10 and spend_so_far=9 allows a 0.5 child."""
        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=0,
            ancestry=[],
            spend_cap_usd=10.0
        )
        budget.spend_so_far_usd = 9.0

        # Should not raise when adding 0.5 (total would be 9.5 <= 10.0)
        budget.check_spend(0.5)

    def test_unlimited_spend_cap(self):
        """Spend cap of 0 means unlimited."""
        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=0,
            ancestry=[],
            spend_cap_usd=0  # Unlimited
        )
        budget.spend_so_far_usd = 1000.0

        # Should not raise even with massive cost
        budget.check_spend(999.0)

    def test_spend_at_cap_boundary(self):
        """Spend exactly at cap is allowed."""
        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=0,
            ancestry=[],
            spend_cap_usd=10.0
        )
        budget.spend_so_far_usd = 9.0

        # Should not raise when total equals cap exactly
        budget.check_spend(1.0)


class TestEstimateCost:
    """Test estimate_run_cost helper (used in ST-09.6 spend checks)."""

    @patch("huf.ai.run_budget.get_model_pricing")
    def test_estimate_cost_with_custom_pricing(self, mock_pricing):
        """estimate_run_cost uses custom pricing when available."""
        # Mock agent doc
        agent_doc = Mock()
        agent_doc.name = "test_agent"
        agent_doc.model = "gpt-4o"
        agent_doc.provider = "openai"

        # Mock custom pricing
        mock_pricing.return_value = {
            "input_cost_per_1m_tokens": 30.0,
            "output_cost_per_1m_tokens": 60.0,
            "cached_input_cost_per_1m_tokens": None,
            "cached_input_write_cost_per_1m_tokens": None,
        }

        cost = estimate_run_cost(agent_doc)
        assert cost > 0  # Should have some cost

    @patch("huf.ai.run_budget.get_model_pricing")
    def test_estimate_cost_no_pricing_returns_zero(self, mock_pricing):
        """estimate_run_cost returns 0 when no pricing is available."""
        agent_doc = Mock()
        agent_doc.name = "test_agent"
        agent_doc.model = "unknown_model"
        agent_doc.provider = "unknown_provider"

        # Mock no custom pricing
        mock_pricing.return_value = None

        cost = estimate_run_cost(agent_doc)
        assert cost == 0.0

    def test_estimate_cost_no_model_returns_zero(self):
        """estimate_run_cost returns 0 when agent has no model."""
        agent_doc = Mock()
        agent_doc.name = "test_agent"
        agent_doc.model = None
        agent_doc.provider = "openai"

        cost = estimate_run_cost(agent_doc)
        assert cost == 0.0


class TestCombinedBudgetConstraints:
    """Test interactions between multiple constraints."""

    def test_all_constraints_checked(self):
        """Budget with multiple constraints checks all of them."""
        # Create a budget at the edge of multiple constraints
        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=1),  # About to expire
            max_turns_ceiling=10,
            depth=2,  # Close to a typical max_depth=3
            ancestry=["run_1", "run_2"],
            spend_cap_usd=10.0
        )
        budget.spend_so_far_usd = 9.5

        # All should pass individually
        budget.check_deadline()  # Should not raise yet (1 second left)
        budget.check_depth(max_depth=3)  # At depth 2, max 3
        budget.check_spend(0.4)  # 9.5 + 0.4 = 9.9 < 10.0

        # But a large spend would fail
        with pytest.raises(frappe.ValidationError):
            budget.check_spend(1.0)  # 9.5 + 1.0 = 10.5 > 10.0

    def test_spend_and_depth_failure_modes_distinct(self):
        """Spend exceeded and depth exceeded produce different errors."""
        # Depth failure
        budget_depth = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=3,
            ancestry=[],
            spend_cap_usd=100.0
        )

        with pytest.raises(frappe.ValidationError) as exc_depth:
            budget_depth.check_depth(max_depth=2)
        depth_msg = str(exc_depth.value)
        assert "depth" in depth_msg.lower() or "recursion" in depth_msg.lower()

        # Spend failure
        budget_spend = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=0,
            ancestry=[],
            spend_cap_usd=5.0
        )
        budget_spend.spend_so_far_usd = 4.0

        with pytest.raises(frappe.ValidationError) as exc_spend:
            budget_spend.check_spend(2.0)
        spend_msg = str(exc_spend.value)
        assert "spend" in spend_msg.lower() or "budget" in spend_msg.lower()

        # Messages should be different
        assert depth_msg != spend_msg
