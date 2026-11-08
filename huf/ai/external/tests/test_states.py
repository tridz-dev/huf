# ruff: noqa: S101
from __future__ import annotations

import pytest

from huf.ai.external import states as s

EXPECTED_EDGES = {
	(s.ACTIVE, s.WAITING_INPUT),
	(s.ACTIVE, s.WAITING_APPROVAL),
	(s.ACTIVE, s.RUNTIME_OFFLINE),
	(s.ACTIVE, s.COMPLETED),
	(s.ACTIVE, s.FAILED),
	(s.ACTIVE, s.CANCELLED),
	(s.WAITING_INPUT, s.ACTIVE),
	(s.WAITING_INPUT, s.RUNTIME_OFFLINE),
	(s.WAITING_INPUT, s.COMPLETED),
	(s.WAITING_INPUT, s.FAILED),
	(s.WAITING_INPUT, s.CANCELLED),
	(s.WAITING_APPROVAL, s.ACTIVE),
	(s.WAITING_APPROVAL, s.RUNTIME_OFFLINE),
	(s.WAITING_APPROVAL, s.FAILED),
	(s.WAITING_APPROVAL, s.CANCELLED),
	(s.RUNTIME_OFFLINE, s.ACTIVE),
	(s.RUNTIME_OFFLINE, s.FAILED),
	(s.RUNTIME_OFFLINE, s.CANCELLED),
}


def test_all_states_order_and_content():
	assert s.ALL_STATES == (
		s.ACTIVE,
		s.WAITING_INPUT,
		s.WAITING_APPROVAL,
		s.RUNTIME_OFFLINE,
		s.COMPLETED,
		s.FAILED,
		s.CANCELLED,
	)


def test_terminal_states():
	assert s.TERMINAL_STATES == frozenset({s.COMPLETED, s.FAILED, s.CANCELLED})


@pytest.mark.parametrize("src,dst", sorted(EXPECTED_EDGES))
def test_every_allowed_edge(src, dst):
	assert s.can_transition(src, dst) is True
	s.assert_transition(src, dst)  # must not raise


def test_every_other_pair_is_rejected():
	for src in s.ALL_STATES:
		for dst in s.ALL_STATES:
			if (src, dst) in EXPECTED_EDGES:
				continue
			assert s.can_transition(src, dst) is False, (src, dst)
			with pytest.raises(ValueError):
				s.assert_transition(src, dst)


def test_transitions_table_matches_expected_edges():
	actual = {(src, dst) for src, dsts in s.TRANSITIONS.items() for dst in dsts}
	assert actual == EXPECTED_EDGES


@pytest.mark.parametrize("state", sorted(s.TERMINAL_STATES))
def test_terminal_states_have_no_exits(state):
	assert s.TRANSITIONS[state] == frozenset()
	assert s.is_terminal(state) is True
	for dst in s.ALL_STATES:
		assert s.can_transition(state, dst) is False


@pytest.mark.parametrize("state", [s.ACTIVE, s.WAITING_INPUT, s.WAITING_APPROVAL, s.RUNTIME_OFFLINE])
def test_non_terminal_states(state):
	assert s.is_terminal(state) is False


@pytest.mark.parametrize("state", s.ALL_STATES)
def test_same_state_is_not_a_transition(state):
	assert s.can_transition(state, state) is False
	with pytest.raises(ValueError):
		s.assert_transition(state, state)


def test_unknown_states_are_rejected():
	assert s.can_transition("Bogus", s.ACTIVE) is False
	assert s.can_transition(s.ACTIVE, "Bogus") is False
	assert s.can_transition("Bogus", "Bogus2") is False
	assert s.is_terminal("Bogus") is False
	with pytest.raises(ValueError):
		s.assert_transition("Bogus", s.ACTIVE)


def test_assert_transition_error_message():
	with pytest.raises(ValueError) as exc:
		s.assert_transition(s.COMPLETED, s.ACTIVE)
	assert str(exc.value) == "Invalid session transition: Completed -> Active"
