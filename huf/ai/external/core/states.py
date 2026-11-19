from __future__ import annotations

ACTIVE = "Active"
WAITING_INPUT = "Waiting for Input"
WAITING_APPROVAL = "Waiting for Approval"
RUNTIME_OFFLINE = "Runtime Offline"
COMPLETED = "Completed"
FAILED = "Failed"
CANCELLED = "Cancelled"

ALL_STATES = (
	ACTIVE,
	WAITING_INPUT,
	WAITING_APPROVAL,
	RUNTIME_OFFLINE,
	COMPLETED,
	FAILED,
	CANCELLED,
)

TERMINAL_STATES = frozenset({COMPLETED, FAILED, CANCELLED})

TRANSITIONS: dict[str, frozenset[str]] = {
	ACTIVE: frozenset({WAITING_INPUT, WAITING_APPROVAL, RUNTIME_OFFLINE, COMPLETED, FAILED, CANCELLED}),
	WAITING_INPUT: frozenset({ACTIVE, RUNTIME_OFFLINE, COMPLETED, FAILED, CANCELLED}),
	WAITING_APPROVAL: frozenset({ACTIVE, RUNTIME_OFFLINE, FAILED, CANCELLED}),
	RUNTIME_OFFLINE: frozenset({ACTIVE, FAILED, CANCELLED}),
	COMPLETED: frozenset(),
	FAILED: frozenset(),
	CANCELLED: frozenset(),
}


def is_terminal(state: str) -> bool:
	return state in TERMINAL_STATES


def can_transition(src: str, dst: str) -> bool:
	if src == dst:
		return False
	return dst in TRANSITIONS.get(src, frozenset())


def assert_transition(src: str, dst: str) -> None:
	if not can_transition(src, dst):
		raise ValueError(f"Invalid session transition: {src} -> {dst}")  # noqa: TRY003
