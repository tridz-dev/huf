# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""How a tool's raw return value becomes the result of a flow step. Split out of ``engine.py``, which re-exports it."""

import json


def normalize_tool_result(raw) -> dict:
	"""Collapse whatever a tool returned into ``{"success", "result", "error"}``.

	The invocation layer wraps results as ``{"success", "result", "error"}``, but many tools
	return a JSON *string* such as ``{"success": false, "error": "..."}`` (or ``{"error": ...}``)
	as their ``result`` and the wrapper still says success. A tool that reports ``success: false``,
	or carries a truthy ``error`` key, is a failure here, so the node is marked failed instead of
	green. A JSON string result is parsed so later nodes can read fields with ``{"$from": "<node>.x"}``.
	"""
	if isinstance(raw, dict) and "success" in raw:
		success = bool(raw.get("success"))
		inner = raw.get("result")
		error = raw.get("error") or ""
	else:
		success, inner, error = True, raw, ""

	if isinstance(inner, str) and inner.lstrip()[:1] in ("{", "["):
		try:
			inner = json.loads(inner)
		except (ValueError, TypeError):
			pass

	if isinstance(inner, dict):
		reported_error = inner.get("error")
		if inner.get("success") is False or reported_error:
			success = False
			if not error:
				error = str(reported_error or inner.get("message") or "tool reported failure")

	if not success and not error:
		error = "tool failed"
	return {"success": success, "result": inner, "error": error if not success else ""}
