# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""A step the author turned off: the flow steps over it and carries on with the next step (UX-8)."""

#: Steps with one way in and one way out, which a flow can simply step over. Branching steps cannot be turned off.
SKIPPABLE_NODE_TYPES = frozenset(
	{"agent.run", "tool.call", "transform", "state.get", "state.set", "state.delete", "doc.create", "code.run"}
)


def is_turned_off(node: dict) -> bool:
	return node.get("_disabled") is True and node.get("type") in SKIPPABLE_NODE_TYPES


def turned_off_result() -> dict:
	return {"status": "success", "result": None, "output": None, "skipped": True}
