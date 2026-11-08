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


def pin_external_identity(
	args: dict[str, Any] | None,
	*,
	conversation_id: str | None,
	agent_run_id: str | None,
	agent_name: str | None,
	call_id: str | None = None,
) -> dict[str, Any]:
	"""Return a copy of tool ``args`` with identity fields set from server-side state.

	Identity comes only from server-side session state, never from the model. Every key in
	``IDENTITY_KEYS`` is removed from the copy regardless of its value (blank values included),
	then the keyword values are written back when they are not None.

	This must run BEFORE the args reach ``invoke_tool_sync``, because its run-context merge
	never overwrites a non-blank caller value.

	The input mapping is never mutated.
	"""
	pinned: dict[str, Any] = dict(args or {})
	for key in IDENTITY_KEYS:
		pinned.pop(key, None)

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
