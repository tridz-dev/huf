"""Tests for cumulative spend cap enforcement.

ST-09.6: Tests for spend-cap checks before enqueuing child runs.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import frappe
from huf.ai.run_budget import RunBudget, RunBudgetExceeded


class TestSpendCapBasics:
    """Basic spend cap initialization and tracking."""

    def test_spend_cap_initialized(self):
        """RunBudget initializes spend_cap_usd and spend_so_far_usd."""
        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=0,
            ancestry=[],
            spend_cap_usd=100.0
        )

        assert budget.spend_cap_usd == 100.0
        assert budget.spend_so_far_usd == 0.0

    def test_spend_tracking(self):
        """Spend can be accumulated."""
        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=0,
            ancestry=[],
            spend_cap_usd=100.0
        )

        # Simulate spending
        budget.spend_so_far_usd = 25.50
        assert budget.spend_so_far_usd == 25.50

        budget.spend_so_far_usd += 10.25
        assert budget.spend_so_far_usd == 35.75


class TestSpendCapEnforcement:
    """Test check_spend behavior with various amounts."""

    def test_spend_well_below_cap(self):
        """Spend well below cap succeeds."""
        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=0,
            ancestry=[],
            spend_cap_usd=100.0
        )
        budget.spend_so_far_usd = 10.0

        # Should not raise
        budget.check_spend(5.0)

    def test_spend_at_exactly_cap(self):
        """Spend that would reach cap exactly is allowed."""
        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=0,
            ancestry=[],
            spend_cap_usd=100.0
        )
        budget.spend_so_far_usd = 90.0

        # Should not raise (total = 100.0)
        budget.check_spend(10.0)

    def test_spend_exceeds_cap(self):
        """Spend that would exceed cap raises."""
        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=0,
            ancestry=[],
            spend_cap_usd=100.0
        )
        budget.spend_so_far_usd = 90.0

        with pytest.raises(frappe.ValidationError) as exc_info:
            budget.check_spend(15.0)  # Total = 105.0 > 100.0
        assert "spend" in str(exc_info.value).lower() or "budget" in str(exc_info.value).lower()

    def test_spend_fractionally_over_cap(self):
        """Even small overspend raises."""
        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=0,
            ancestry=[],
            spend_cap_usd=100.0
        )
        budget.spend_so_far_usd = 99.99

        with pytest.raises(frappe.ValidationError):
            budget.check_spend(0.02)  # Total = 100.01 > 100.0


class TestUnlimitedSpendCap:
    """Test unlimited spend cap (0 = unlimited)."""

    def test_unlimited_cap_never_raises(self):
        """Spend cap of 0 never raises regardless of amount."""
        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=0,
            ancestry=[],
            spend_cap_usd=0  # Unlimited
        )

        # Should not raise for any amount
        budget.spend_so_far_usd = 1000000.0
        budget.check_spend(1000000.0)

    def test_unlimited_with_high_spend_so_far(self):
        """Unlimited cap works even with massive spend_so_far."""
        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=0,
            ancestry=[],
            spend_cap_usd=0  # Unlimited
        )

        budget.spend_so_far_usd = 10**10  # Huge amount

        # Should not raise
        budget.check_spend(10**10)


class TestSpendCapErrorMessages:
    """Test error messages for spend cap violations."""

    def test_spend_error_includes_amounts(self):
        """Error message includes cost and budget info."""
        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=0,
            ancestry=[],
            spend_cap_usd=50.0
        )
        budget.spend_so_far_usd = 40.0

        with pytest.raises(frappe.ValidationError) as exc_info:
            budget.check_spend(15.0)
        error_msg = str(exc_info.value).lower()
        # Should mention spend/cost/budget
        assert any(word in error_msg for word in ["spend", "budget", "cost", "exceed"])


class TestSpendCapIntegration:
    """Test spend cap in combination with other constraints."""

    def test_spend_cap_independent_of_deadline(self):
        """Spend cap and deadline are checked independently."""
        # Future deadline, but low cap
        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=0,
            ancestry=[],
            spend_cap_usd=10.0
        )
        budget.spend_so_far_usd = 9.0

        # Deadline check passes
        budget.check_deadline()

        # Spend check fails
        with pytest.raises(frappe.ValidationError):
            budget.check_spend(2.0)

    def test_spend_cap_independent_of_depth(self):
        """Spend cap and depth are checked independently."""
        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=0,  # Low depth
            ancestry=[],
            spend_cap_usd=10.0
        )
        budget.spend_so_far_usd = 9.0

        # Depth check passes
        budget.check_depth(max_depth=3)

        # Spend check fails
        with pytest.raises(frappe.ValidationError):
            budget.check_spend(2.0)


class TestMultipleSpendChecks:
    """Test multiple spend checks in sequence."""

    def test_sequential_spend_checks(self):
        """Multiple spending decisions can be made on same budget."""
        budget = RunBudget(
            deadline_at=datetime.now() + timedelta(seconds=900),
            max_turns_ceiling=10,
            depth=0,
            ancestry=[],
            spend_cap_usd=100.0
        )

        # First child
        budget.check_spend(30.0)  # OK
        budget.spend_so_far_usd += 30.0

        # Second child
        budget.check_spend(40.0)  # OK
        budget.spend_so_far_usd += 40.0

        # Third child
        budget.check_spend(20.0)  # OK
        budget.spend_so_far_usd += 20.0

        # Now at cap, fourth child blocked
        with pytest.raises(frappe.ValidationError):
            budget.check_spend(5.0)  # Would exceed
