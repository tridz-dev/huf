# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Turning a finished code ``Agent Tool Call`` into a Flow step's output or a plain-sentence error.

Part of ``huf.ai.flow.code_node`` (which re-exports these names); no database access.
"""

from __future__ import annotations

import html
import json
import re

from frappe import _

DEFAULT_TIMEOUT_S = 30


# The user code is compiled as "<huf-exec>"; Frappe's text-field sanitizer may drop or escape that name, so
# match any traceback frame whose file is not a .py file (the sandbox's own frames are).
_LINE_RE = re.compile(r'File "(?![^"]*\.py")[^"]*", line (\d+)')


def error_text(exit_status: str | None, stderr: str | None, limits: dict | None = None) -> str:
	"""A plain sentence for why a code step failed (no traceback)."""
	limits = limits or {}
	status = exit_status or "Error"
	if status == "Timeout":
		return str(
			_("The code ran longer than {0} seconds and was stopped.").format(int(limits.get("max_wall_time_s") or DEFAULT_TIMEOUT_S))
		)
	if status == "OOM":
		return str(
			_("The code used more memory than the {0} MB allowed and was stopped.").format(
				int(limits.get("max_memory_mb") or 0)
			)
		)
	if status == "Killed":
		return str(_("The code was stopped before it finished."))
	text = html.unescape(stderr or "").strip()
	if not text:
		return str(_("The code failed without a message."))
	from huf.ai.graph.error_copy import _EXC_PREFIX, code_error_copy, plain_error

	if "Traceback (most recent call last)" not in text and not text.startswith(("SyntaxError", "[huf-exec]")):
		return plain_error(text)[:500]  # already a sentence (for example: the request was rejected)
	lines = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("[huf-exec]")]
	last = lines[-1].strip() if lines else text[:200]
	line_numbers = _LINE_RE.findall(text)
	line = line_numbers[-1] if line_numbers else None
	m = _EXC_PREFIX.match(last)
	if m:
		return code_error_copy(m.group(1), last[m.end():], line)
	return code_error_copy("", last, line)


def _json_value(value):
	if isinstance(value, str):
		try:
			return json.loads(value)
		except (TypeError, ValueError):
			return value
	return value


def output_from_call(call) -> tuple[bool, dict, str | None]:
	"""``(ok, node_output, error)`` for a finished ``Agent Tool Call``.

	The output is ``{"stdout", "result", "exit_status", "truncated"}`` (also for a failed step, so
	Run details can show what was printed before the failure).
	"""
	stored = _json_value(call.get("tool_result")) if call.get("tool_result") else None
	stored = stored if isinstance(stored, dict) else {}
	exit_status = call.get("exit_status") or stored.get("exit_status") or ("Ok" if call.status == "Completed" else "Error")
	output = {
		"stdout": stored.get("stdout") or "",
		"result": stored.get("result"),
		"exit_status": exit_status,
		"truncated": bool(stored.get("truncated")),
	}
	if call.status == "Completed" and exit_status == "Ok":
		return True, output, None
	snapshot = _json_value(call.get("execution_profile_snapshot")) or {}
	limits = snapshot.get("limits") if isinstance(snapshot, dict) else {}
	return False, output, error_text(exit_status, call.get("error_message"), limits)
