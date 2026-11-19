# ruff: noqa: S101 - plain asserts are the pytest idiom
from __future__ import annotations

import pytest

from huf.ai.external.core.mailbox_logic import (
	DEFAULT_WAIT_SECONDS,
	MAX_WAIT_SECONDS,
	POLL_INTERVAL_SECONDS,
	clamp_wait,
	has_gap,
	is_replay,
	next_seq,
	select_deliverable,
)


def ev(seq, **extra):
	return {"seq": seq, **extra}


def test_constants():
	assert MAX_WAIT_SECONDS == 10
	assert DEFAULT_WAIT_SECONDS == 5
	assert POLL_INTERVAL_SECONDS == 1


class TestClampWait:
	@pytest.mark.parametrize("value", [None, "abc", "", "3.7", [], {}, object()])
	def test_missing_or_non_numeric_uses_default(self, value):
		assert clamp_wait(value) == DEFAULT_WAIT_SECONDS

	def test_in_range_int_passes_through(self):
		assert clamp_wait(3) == 3
		assert clamp_wait(0) == 0
		assert clamp_wait(MAX_WAIT_SECONDS) == MAX_WAIT_SECONDS

	def test_numeric_string_is_parsed(self):
		assert clamp_wait("7") == 7
		assert clamp_wait(" 4 ") == 4
		assert clamp_wait("0") == 0

	def test_float_is_truncated_to_int(self):
		assert clamp_wait(2.9) == 2

	def test_negative_clamps_to_zero(self):
		assert clamp_wait(-1) == 0
		assert clamp_wait("-5") == 0

	def test_huge_clamps_to_max(self):
		assert clamp_wait(MAX_WAIT_SECONDS + 1) == MAX_WAIT_SECONDS
		assert clamp_wait(10**30) == MAX_WAIT_SECONDS
		assert clamp_wait("999999") == MAX_WAIT_SECONDS

	def test_infinite_float_uses_default(self):
		assert clamp_wait(float("inf")) == DEFAULT_WAIT_SECONDS

	def test_nan_uses_default(self):
		assert clamp_wait(float("nan")) == DEFAULT_WAIT_SECONDS


class TestNextSeq:
	def test_increments(self):
		assert next_seq(0) == 1
		assert next_seq(41) == 42

	def test_none_and_zero_start_at_one(self):
		assert next_seq(None) == 1
		assert next_seq(0) == 1

	def test_numeric_string_is_accepted(self):
		assert next_seq("9") == 10


class TestIsReplay:
	def test_seq_at_or_below_acked_is_replay(self):
		assert is_replay(5, 5) is True
		assert is_replay(5, 1) is True

	def test_seq_above_acked_is_not_replay(self):
		assert is_replay(5, 6) is False

	def test_none_acked_treated_as_zero(self):
		assert is_replay(None, 0) is True
		assert is_replay(None, 1) is False

	def test_string_acked_is_parsed(self):
		assert is_replay("3", 3) is True
		assert is_replay("3", 4) is False


class TestSelectDeliverable:
	def test_empty_input(self):
		assert select_deliverable([], 0) == []

	def test_filters_out_acked_and_older(self):
		events = [ev(1), ev(2), ev(3), ev(4)]
		assert [e["seq"] for e in select_deliverable(events, 2)] == [3, 4]

	def test_all_acked_returns_empty(self):
		assert select_deliverable([ev(1), ev(2)], 2) == []

	def test_none_acked_keeps_all(self):
		assert [e["seq"] for e in select_deliverable([ev(1), ev(2)], None)] == [1, 2]

	def test_sorts_unsorted_input_ascending(self):
		events = [ev(5), ev(2), ev(4), ev(3)]
		assert [e["seq"] for e in select_deliverable(events, 0)] == [2, 3, 4, 5]

	def test_duplicates_collapse_keeping_first_occurrence(self):
		events = [ev(2, body="first"), ev(1), ev(2, body="second"), ev(3)]
		result = select_deliverable(events, 0)
		assert [e["seq"] for e in result] == [1, 2, 3]
		assert result[1]["body"] == "first"

	def test_duplicate_at_or_below_acked_is_dropped(self):
		events = [ev(2, body="a"), ev(2, body="b"), ev(3)]
		result = select_deliverable(events, 2)
		assert [e["seq"] for e in result] == [3]

	def test_does_not_mutate_input(self):
		events = [ev(3), ev(1)]
		select_deliverable(events, 0)
		assert [e["seq"] for e in events] == [3, 1]

	def test_string_seq_values_are_coerced(self):
		events = [{"seq": "3"}, {"seq": "1"}]
		assert [e["seq"] for e in select_deliverable(events, 0)] == ["1", "3"]


class TestHasGap:
	def test_empty_has_no_gap(self):
		assert has_gap([], 0) is False
		assert has_gap([], 7) is False

	def test_consecutive_from_acked_has_no_gap(self):
		assert has_gap([ev(3), ev(4), ev(5)], 2) is False

	def test_missing_first_seq_is_gap(self):
		assert has_gap([ev(4), ev(5)], 2) is True

	def test_hole_in_middle_is_gap(self):
		assert has_gap([ev(1), ev(3)], 0) is True

	def test_unsorted_consecutive_has_no_gap(self):
		assert has_gap([ev(4), ev(2), ev(3)], 1) is False

	def test_duplicates_do_not_create_gap(self):
		assert has_gap([ev(1), ev(1), ev(2), ev(2)], 0) is False

	def test_duplicate_with_hole_is_gap(self):
		assert has_gap([ev(1), ev(1), ev(3)], 0) is True

	def test_already_acked_events_ignored(self):
		assert has_gap([ev(1), ev(2), ev(3)], 2) is False

	def test_none_acked_starts_at_one(self):
		assert has_gap([ev(1), ev(2)], None) is False
		assert has_gap([ev(2)], None) is True
