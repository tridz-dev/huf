"""Resource limits for the expression evaluator (security round 2, DECISIONS 13). Frappe-free, like ``expressions``.

An editor controls the expression text and run data controls the operands, so ``"x" * 10**9`` or ``[0] * 10**9``
(OOM kills the worker) must never be computed. Repeating text/lists is refused outright; integers are limited in
magnitude (so no result can grow without bound); a joined text or list may not exceed ``MAX_SEQUENCE_RESULT``.
"""

from __future__ import annotations

import operator
from typing import Any

MAX_INT_MAGNITUDE = 10**18
MAX_SEQUENCE_RESULT = 1_000_000
LIMIT_MESSAGE = (
	"This check works with numbers or text that are too large to calculate safely. "
	"Use smaller numbers, and do not repeat text or lists."
)


class ExpressionLimitError(Exception):
	"""An arithmetic resource limit was hit (repeat text/list, huge number, too-long result, out of memory).

	Raised inside evaluation only. :func:`evaluate_value` / :func:`evaluate_bool` stay total by default
	(the answer is ``None`` / ``False``); callers that must fail the step instead (the flow engine) pass
	``raise_limits=True`` and show ``str(exc)``, which is already plain language.
	"""

	def __init__(self, message: str = LIMIT_MESSAGE):
		super().__init__(message)


def _is_sequence(value: Any) -> bool:
	return isinstance(value, (str, bytes, list, tuple))


def _is_int(value: Any) -> bool:
	return isinstance(value, int) and not isinstance(value, bool)


def _check_int(value: Any) -> None:
	if _is_int(value) and abs(value) >= MAX_INT_MAGNITUDE:
		raise ExpressionLimitError()


def _check_result(value: Any) -> Any:
	_check_int(value)
	if _is_sequence(value) and len(value) > MAX_SEQUENCE_RESULT:
		raise ExpressionLimitError()
	return value


def _safe_mul(a: Any, b: Any) -> Any:
	# Repetition ("ab" * 3, [0] * n, True * "x") is how a short expression allocates gigabytes: refuse it.
	if (_is_sequence(a) and isinstance(b, int)) or (_is_sequence(b) and isinstance(a, int)):
		raise ExpressionLimitError()
	return operator.mul(a, b)


def _safe_mod(a: Any, b: Any) -> Any:
	# ``"%999999999d" % 1`` is string formatting and allocates a giant string: text on the left is refused.
	if isinstance(a, (str, bytes)):
		raise ExpressionLimitError()
	return operator.mod(a, b)


def _safe_add(a: Any, b: Any) -> Any:
	if _is_sequence(a) and _is_sequence(b) and len(a) + len(b) > MAX_SEQUENCE_RESULT:
		raise ExpressionLimitError()
	return operator.add(a, b)
