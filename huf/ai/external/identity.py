from __future__ import annotations

from typing import Any

# Keys that carry identity or privilege. Model-supplied values for these are never trusted.
IDENTITY_KEYS = (
	"user",
	"session_id",
	"conversation_id",
	"agent_run_id",
	"agent_name",
	"call_id",
	"ignore_permissions",
	"_dx_pin",
)


def _normalize_key(key: Any) -> str:
	"""Lowercase a key and drop ``-`` and ``_`` so spelling variants compare equal."""
	return str(key).lower().replace("-", "").replace("_", "")


_NORMALIZED_IDENTITY_KEYS = frozenset(_normalize_key(key) for key in IDENTITY_KEYS)


def pin_external_identity(
	args: dict[str, Any] | None,
	*,
	conversation_id: str | None,
	agent_run_id: str | None,
	agent_name: str | None,
	call_id: str | None = None,
) -> dict[str, Any]:
	"""Return a copy of tool ``args`` with identity fields set from server-side state.

	Identity comes only from server-side session state, never from the model. Any top-level
	key that matches an entry in ``IDENTITY_KEYS`` is removed from the copy regardless of its
	value (blank values included). Matching is case-insensitive and ignores ``-`` and ``_``,
	so ``"User"``, ``"Agent_Run_Id"`` and ``"agent-name"`` are all stripped. The keyword values
	are then written back under their canonical names when they are not None.

	Only top-level keys are inspected. Nested values are the tool handler's responsibility.

	This must run BEFORE the args reach ``invoke_tool_sync``, because its run-context merge
	never overwrites a non-blank caller value.

	The input mapping is never mutated.
	"""
	pinned: dict[str, Any] = {
		key: value for key, value in (args or {}).items() if _normalize_key(key) not in _NORMALIZED_IDENTITY_KEYS
	}

	trusted = {
		"conversation_id": conversation_id,
		"agent_run_id": agent_run_id,
		"agent_name": agent_name,
		"call_id": call_id,
	}
	for key, value in trusted.items():
		if value is not None:
			pinned[key] = value

	return pinned
