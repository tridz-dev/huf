"""Helper functions an expression may call: a closed set, fixed names and arity, total (no exceptions).

Frappe-free (imports only ``re`` and ``typing``), so it loads under plain ``pytest``/``unittest`` next to
``huf.ai.graph.expressions``, which re-exports :data:`HELPERS` for the evaluator.
"""

from __future__ import annotations

import re
from typing import Any

_NUMBER_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)$")


def _h_number(value: Any) -> Any:
	"""A number from a number or from text that is only a number (``"150"``, `` 2.5 ``); anything else is ``None``."""
	if isinstance(value, bool):
		return None
	if isinstance(value, (int, float)):
		return value
	if isinstance(value, str):
		text = value.strip()
		if len(text) <= 64 and _NUMBER_RE.match(text):
			try:
				return float(text) if "." in text else int(text)
			except (ValueError, OverflowError):
				return None
	return None


def _h_lower(value: Any) -> Any:
	"""Text in lower case (so two texts can be compared ignoring capital letters); other values are returned as they are."""
	return value.lower() if isinstance(value, str) else value


def _h_startswith(value: Any, prefix: Any) -> bool:
	return isinstance(value, str) and isinstance(prefix, str) and value.startswith(prefix)


def _h_endswith(value: Any, suffix: Any) -> bool:
	return isinstance(value, str) and isinstance(suffix, str) and value.endswith(suffix)


# name -> (function, number of positional arguments)
HELPERS: dict[str, tuple[Any, int]] = {
	"number": (_h_number, 1),
	"lower": (_h_lower, 1),
	"startswith": (_h_startswith, 2),
	"endswith": (_h_endswith, 2),
}
