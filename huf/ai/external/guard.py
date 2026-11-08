"""Guard that keeps external-intelligence agents away from the built-in runner.

Agents with ``execution_mode`` other than Native are driven through the External Intelligence
session bridge and have no provider or model, so the native runner must refuse them.
"""

from __future__ import annotations

NATIVE_MODE = "Native"
NATIVE_ONLY_MESSAGE = "This agent uses external intelligence and cannot be run by the built-in runner."


def is_native_mode(value: str | None) -> bool:
	"""Return True when an ``execution_mode`` value means the built-in runner may execute the agent."""
	return value in (None, "", NATIVE_MODE)


def assert_native_execution(agent_doc) -> None:
	"""Raise PermissionError unless ``agent_doc`` is a native-mode agent. Accepts a doc object or a dict."""
	if isinstance(agent_doc, dict):
		mode = agent_doc.get("execution_mode")
	else:
		mode = getattr(agent_doc, "execution_mode", None)
	if is_native_mode(mode):
		return

	import frappe

	frappe.throw(NATIVE_ONLY_MESSAGE, frappe.PermissionError)
