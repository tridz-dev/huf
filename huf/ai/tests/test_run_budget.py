"""Tests for RunBudget class creation and basic operations.

ST-09.1: Tests for RunBudget class initialization and methods.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import frappe
from huf.ai.run_budget import RunBudget, RunBudgetExceeded


class TestRunBudgetBasics:
    """Basic RunBudget initialization and field access."""

    def test_runbudget_init(self):
        """RunBudget initializes with all required fields."""
        deadline = datetime.now() + timedelta(seconds=900)
        budget = RunBudget(
            deadline_at=deadline,
            max_turns_ceiling=20,
            depth=0,
            ancestry=[],
            spend_cap_usd=100.0
        )

        assert budget.deadline_at == deadline
        assert budget.max_turns_ceiling == 20
        assert budget.current_depth == 0
        assert budget.ancestry == []
        assert budget.spend_cap_usd == 100.0
        assert budget.spend_so_far_usd == 0.0

    def test_runbudget_with_ancestry(self):
        """RunBudget preserves ancestry chain."""
        ancestors = ["run_1", "run_2"]
        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=2,
            ancestry=ancestors,
            spend_cap_usd=0
        )

        assert budget.current_depth == 2
        assert budget.ancestry == ancestors
        assert len(budget.ancestry) == 2


class TestRunBudgetDeadlineCheck:
    """Test deadline checking methods."""

    def test_check_deadline_valid(self):
        """check_deadline() with future deadline succeeds."""
        future_deadline = datetime.now() + timedelta(seconds=100)
        budget = RunBudget(
            deadline_at=future_deadline,
            max_turns_ceiling=10,
            depth=0,
            ancestry=[],
            spend_cap_usd=0
        )

        # Should not raise
        budget.check_deadline()

    def test_check_deadline_expired(self):
        """check_deadline() with expired deadline raises."""
        past_deadline = datetime.now() - timedelta(seconds=100)
        budget = RunBudget(
            deadline_at=past_deadline,
            max_turns_ceiling=10,
            depth=0,
            ancestry=[],
            spend_cap_usd=0
        )

        with pytest.raises(frappe.ValidationError) as exc_info:
            budget.check_deadline()
        assert RunBudgetExceeded in type(exc_info.value).__mro__


class TestRunBudgetDepthCheck:
    """Test depth checking methods."""

    def test_check_depth_valid(self):
        """check_depth() with depth below ceiling succeeds."""
        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=1,
            ancestry=["run_1"],
            spend_cap_usd=0
        )

        # Should not raise
        budget.check_depth(max_depth=3)

    def test_check_depth_at_ceiling(self):
        """check_depth() with depth equal to ceiling succeeds."""
        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=3,
            ancestry=[],
            spend_cap_usd=0
        )

        # Should not raise (depth < max_depth uses >=)
        budget.check_depth(max_depth=3)

    def test_check_depth_exceeds(self):
        """check_depth() with depth >= ceiling raises."""
        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=4,
            ancestry=[],
            spend_cap_usd=0
        )

        with pytest.raises(frappe.ValidationError) as exc_info:
            budget.check_depth(max_depth=3)
        assert "depth" in str(exc_info.value).lower()


class TestRunBudgetSpendCheck:
    """Test spend checking methods."""

    def test_check_spend_valid(self):
        """check_spend() within budget succeeds."""
        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=0,
            ancestry=[],
            spend_cap_usd=100.0
        )
        budget.spend_so_far_usd = 50.0

        # Should not raise
        budget.check_spend(49.0)

    def test_check_spend_exceeds(self):
        """check_spend() over budget raises."""
        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=0,
            ancestry=[],
            spend_cap_usd=100.0
        )
        budget.spend_so_far_usd = 90.0

        with pytest.raises(frappe.ValidationError) as exc_info:
            budget.check_spend(20.0)  # Total would be 110.0 > 100.0
        assert "spend" in str(exc_info.value).lower() or "budget" in str(exc_info.value).lower()

    def test_check_spend_unlimited(self):
        """check_spend() with spend_cap=0 (unlimited) never raises."""
        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=0,
            ancestry=[],
            spend_cap_usd=0  # Unlimited
        )
        budget.spend_so_far_usd = 1000000.0

        # Should not raise
        budget.check_spend(999999.0)
