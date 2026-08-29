"""Value-producing expression evaluator for the shared graph IR (T-13, extends GT-03/D1).

**Frappe-free by design** (GT-03/I3/I4): this module imports nothing from ``frappe`` and must stay
importable/runnable under plain ``pytest``/``unittest`` with no bench, mirroring
``huf.ai.tools.execution_sandbox`` and ``huf.ai.graph.transforms``.

Security shape (modeled directly on ``huf/ai/flow_eval.py``'s ``safe_eval_expression`` /
``_eval_node``, GT-03; do NOT edit that module -- Flow still depends on its exact bool-only
behaviour and T-01 pins it with tests):

- ``ast.parse(expression, mode="eval")``, never anything looser.
- An explicit AST **node-type allow-list**, walked once at parse time. Anything not on the list --
  most importantly ``ast.Call`` and ``ast.Attribute``, but also imports, comprehensions, lambdas,
  the walrus operator, f-strings, and starred expressions -- is rejected before any evaluation ever
  runs.
- A hard length cap (``MAX_EXPRESSION_LENGTH``, matches ``$defs/Expression.maxLength`` = 500) and a
  hard AST-depth cap (``MAX_EXPRESSION_DEPTH``) so a syntactically "allowed" but pathologically
  nested expression cannot be used to blow the recursion stack.

What this module adds on top of that shape, per ``spec/graph-ir.md`` section 4.2:

- The evaluator returns the **value**, not ``bool(value)``. Boolean coercion happens only where the
  IR itself structurally requires a boolean (``condition``, ``applies_when``, ``validate``) --
  see :func:`evaluate_bool`.
- ``ast.Subscript`` resolution gains **list-index support** (``row["items"][0]``), matching the
  ``Reference`` path grammar in section 4.1 (:func:`resolve_path`) so the two mechanisms -- a
  standalone ``{"$from": "..."}`` reference and a variable access embedded inside a larger
  ``Expression`` -- stay conceptually identical.
- Operators: ``Eq, NotEq, Lt, LtE, Gt, GtE, In, NotIn, And, Or, Not, Add, Sub, Mult, Mod`` (carried
  over from ``flow_eval.py``) plus ``Div`` (null on division by zero, never raises -- see totality
  below) and ``UAdd``/``USub`` for signed literals. Still no ``Pow``, no bitwise operators.
- The only bare ``Name`` nodes ever in scope are the roots from section 4.1 (``input``, ``trigger``,
  ``row``, ``foreach``, or a ``<node_id>``); which names are actually bound is entirely up to the
  caller's ``bindings`` dict -- this module does not hardcode the root list.

Totality (I2, I7): once an expression has been **parsed** (:func:`parse_expression`), evaluating it
(:func:`evaluate_value` / :func:`evaluate_bool`) never raises for ordinary data. Missing keys and
out-of-range list indices resolve to ``None``/``null`` (never ``KeyError``/``IndexError``), division
by zero resolves to ``None`` (never ``ZeroDivisionError``), and type-mismatched comparisons or binary
operations resolve to ``None`` (never ``TypeError``) -- EXCEPT where a boolean is structurally
required, where a non-boolean/None result is coerced with Python truthiness exactly as
``flow_eval.py`` does today (:func:`evaluate_bool`). Malformed or disallowed expressions are instead
rejected **at parse time** with a typed :class:`ExpressionError` -- that is the one place this module
is allowed to raise on bad input; nothing downstream of a successful :func:`parse_expression` call
raises.

Public API:

- :func:`parse_expression` -- compile-time: string -> :class:`ParsedExpression`, or raises
  :class:`ExpressionError`. Call this once per graph version (e.g. at validation time), not once per
  evaluation.
- :func:`evaluate_value` -- runtime: ``(ParsedExpression, bindings) -> Any``, total, never raises.
- :func:`evaluate_bool` -- runtime: ``(ParsedExpression, bindings) -> bool``, total, never raises.
  Use for ``condition.config.expression``, ``applies_when[]``, ``validate.assertions[].expression``.
- :func:`evaluate_predicate` -- **the T-12 integration point.** ``(expression: str, row: dict) ->
  bool``, total, never raises, parses AND evaluates in one call with a single ``row`` root binding.
  ``huf/ai/graph/transforms.py`` (T-12) currently ships its own small ``eval_row_predicate`` AST
  walker for exactly this shape (``filter``'s ``where: Expression``) because T-12 has no dependency
  on T-13 and needed *something* self-contained. That duplication is not meant to ship long-term:
  ``transforms.py`` is expected to replace its local ``eval_row_predicate`` with a call to
  ``evaluate_predicate`` from this module (the two signatures match: ``(expression, row) -> bool``),
  once T-13 lands and T-12 can take the dependency. See ``transforms.py``'s own comment block above
  its evaluator for the acknowledgement.
- :func:`resolve_path` -- resolves a ``Reference`` path (section 4.1: ``root.segment...``, segments
  are ``.identifier`` or ``[integer]``) against a bindings dict. Total: any failure is ``None``.

Explicitly NOT used: ``frappe.safe_eval`` / ``frappe.utils.safe_exec.get_safe_globals``. Both expose a
far larger surface (string methods, ``frappe.utils`` helpers, safe builtins) than this trust boundary
allows -- GT-03 calls this out as "far too permissive." This module's allow-list is deliberately much
narrower.
"""

from __future__ import annotations

import ast
import operator
import re
from dataclasses import dataclass
from typing import Any

MAX_EXPRESSION_LENGTH = 500

# Depth cap on the parsed AST (counting from the ``Expression`` root). Generous enough for any
# realistic graph expression, tight enough that a deeply nested literal (``[[[[[...]]]]]``) cannot be
# used to blow the interpreter's recursion limit either at parse-validation or at eval time.
MAX_EXPRESSION_DEPTH = 40

# Reference / path-segment grammar (spec/graph-ir.md section 4.1):
#   root       := "input" | "trigger" | "row" | "foreach.item" | "foreach.index" | <node_id>
#   segment    := "." <identifier>  |  "[" <integer> "]"
#   reference  := root segment*
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SEGMENT_RE = re.compile(r"\.([A-Za-z_][A-Za-z0-9_]*)|\[(-?\d+)\]")


class ExpressionError(Exception):
	"""Raised only by :func:`parse_expression` for malformed or disallowed expression source.

	Never raised by evaluation of an already-parsed expression -- that is the totality contract
	this module exists to provide.
	"""


@dataclass(frozen=True)
class ParsedExpression:
	"""An expression that has already passed allow-list, length, and depth validation.

	Opaque to callers beyond that; evaluate it with :func:`evaluate_value` / :func:`evaluate_bool`.
	"""

	source: str
	_tree: ast.expr


# ----------------------------------------------------------------------------------------------
# Allowed operators (flow_eval.py's SAFE_OPS, extended with Div/UAdd/USub per graph-ir.md 4.2)
# ----------------------------------------------------------------------------------------------


def _safe_div(a: Any, b: Any) -> Any:
	try:
		return a / b
	except (ZeroDivisionError, TypeError):
		return None


_BIN_OPS: dict[type, Any] = {
	ast.Add: operator.add,
	ast.Sub: operator.sub,
	ast.Mult: operator.mul,
	ast.Mod: operator.mod,
	ast.Div: _safe_div,
}

_CMP_OPS: dict[type, Any] = {
	ast.Eq: operator.eq,
	ast.NotEq: operator.ne,
	ast.Lt: operator.lt,
	ast.LtE: operator.le,
	ast.Gt: operator.gt,
	ast.GtE: operator.ge,
	ast.In: lambda a, b: a in b if isinstance(b, (list, tuple, dict, str, set)) else None,
	ast.NotIn: lambda a, b: a not in b if isinstance(b, (list, tuple, dict, str, set)) else None,
}

# Explicit node-type allow-list. Anything not a key here (ast.Call, ast.Attribute, ast.Lambda,
# comprehensions, ast.NamedExpr, ast.JoinedStr/FormattedValue, ast.Starred, ast.Import*, ...) is
# rejected at parse time.
_ALLOWED_NODES: tuple[type, ...] = (
	ast.Expression,
	ast.Constant,
	ast.Name,
	ast.Load,
	ast.Subscript,
	ast.Slice,
	ast.Index,  # py<3.9 shim; harmless no-op on 3.9+ where Subscript.slice is the value directly
	ast.Compare,
	ast.BoolOp,
	ast.And,
	ast.Or,
	ast.UnaryOp,
	ast.Not,
	ast.USub,
	ast.UAdd,
	ast.BinOp,
	ast.IfExp,
	ast.List,
	ast.Dict,
	ast.Tuple,
	*_BIN_OPS.keys(),
	*_CMP_OPS.keys(),
)


# ----------------------------------------------------------------------------------------------
# Parse-time validation (the only place this module raises)
# ----------------------------------------------------------------------------------------------


def parse_expression(expression: str) -> ParsedExpression:
	"""Compile-time validation: string -> :class:`ParsedExpression`.

	Raises :class:`ExpressionError` for anything malformed or outside the allow-list. Never raises
	any other exception type -- syntax errors, disallowed nodes, over-length input, and over-depth
	input are all normalized to :class:`ExpressionError`.
	"""

	if not isinstance(expression, str) or not expression.strip():
		raise ExpressionError("expression must be a non-empty string")

	source = expression.strip()
	if len(source) > MAX_EXPRESSION_LENGTH:
		raise ExpressionError(f"expression too long ({len(source)} chars, max {MAX_EXPRESSION_LENGTH})")

	try:
		tree = ast.parse(source, mode="eval")
	except SyntaxError as exc:
		raise ExpressionError(f"invalid expression syntax: {exc}") from exc

	_validate_node(tree, depth=0)
	return ParsedExpression(source=source, _tree=tree.body)


def _validate_node(node: ast.AST, depth: int) -> None:
	if depth > MAX_EXPRESSION_DEPTH:
		raise ExpressionError(f"expression nested too deeply (max depth {MAX_EXPRESSION_DEPTH})")

	if not isinstance(node, _ALLOWED_NODES):
		raise ExpressionError(f"disallowed expression element: {type(node).__name__}")

	if isinstance(node, ast.Name) and not _IDENTIFIER_RE.match(node.id):
		raise ExpressionError(f"invalid identifier: {node.id!r}")

	if isinstance(node, ast.Constant) and isinstance(node.value, (bytes, complex, type(...))):
		raise ExpressionError(f"disallowed constant type: {type(node.value).__name__}")

	for child in ast.iter_child_nodes(node):
		_validate_node(child, depth + 1)


# ----------------------------------------------------------------------------------------------
# Runtime evaluation -- total, never raises once parse_expression has succeeded
# ----------------------------------------------------------------------------------------------


def evaluate_value(parsed: ParsedExpression, bindings: dict) -> Any:
	"""Evaluate a parsed expression against ``bindings``, returning the raw value.

	Total: never raises. Any runtime problem (unknown name, type-mismatched operator, division by
	zero, bad subscript) resolves to ``None`` rather than propagating.
	"""

	try:
		return _eval(parsed._tree, bindings if isinstance(bindings, dict) else {})
	except Exception:
		return None


def evaluate_bool(parsed: ParsedExpression, bindings: dict) -> bool:
	"""Evaluate a parsed expression, coercing the result to ``bool`` with Python truthiness.

	Use this -- never :func:`evaluate_value` -- for ``condition.config.expression``,
	``applies_when[]``, and ``validate.assertions[].expression``, which structurally require a
	boolean (spec/graph-ir.md section 4.2's one coercion point, carried over unchanged from
	``flow_eval.py`` / GT-03). Total: never raises.
	"""

	try:
		return bool(evaluate_value(parsed, bindings))
	except Exception:
		return False


def evaluate_predicate(expression: str, row: dict) -> bool:
	"""The T-12 integration point: evaluate a row predicate, total, returning ``bool``.

	Parses ``expression`` and evaluates it with a single ``row`` root binding (spec/graph-ir.md
	section 4.1: ``row`` is meaningful inside a ``filter``/``sort`` transform predicate, bound to
	the current row). Total end-to-end: a malformed expression, a disallowed construct, an
	over-length string, or any runtime evaluation problem all resolve to ``False`` rather than
	raising -- matching the `filter` semantics table in spec/graph-ir.md section 5 ("a
	raising/type-mismatched predicate resolves `false` for that row, never aborts the whole op").

	This mirrors ``huf/ai/graph/transforms.py``'s local ``eval_row_predicate(expression, row) ->
	bool`` exactly in signature and semantics -- T-12's ``filter`` op is expected to replace its own
	small AST-walker copy with a call to this function once it can depend on T-13, to remove the
	duplication both tasks' specs call out.
	"""

	if not isinstance(row, dict):
		row = {}
	try:
		parsed = parse_expression(expression)
	except ExpressionError:
		return False
	return evaluate_bool(parsed, {"row": row})


# ----------------------------------------------------------------------------------------------
# Reference path resolution (spec/graph-ir.md section 4.1), reused by Subscript evaluation below
# ----------------------------------------------------------------------------------------------


def resolve_path(bindings: dict, path: str) -> Any:
	"""Resolve a ``Reference`` path (``root.segment...``) against ``bindings``. Total: any failure,
	including a missing root, a missing key, or an out-of-range list index, resolves to ``None``.
	"""

	if not isinstance(path, str) or not path:
		return None
	root_match = re.match(r"^[A-Za-z_][A-Za-z0-9_]*", path)
	if not root_match:
		return None
	root = root_match.group(0)
	rest = path[root_match.end() :]

	if not isinstance(bindings, dict) or root not in bindings:
		return None
	current = bindings[root]

	for match in _SEGMENT_RE.finditer(rest):
		name, index = match.group(1), match.group(2)
		if name is not None:
			if isinstance(current, dict):
				current = current.get(name)
			else:
				return None
		else:
			idx = int(index)
			if isinstance(current, (list, tuple)) and -len(current) <= idx < len(current):
				current = current[idx]
			else:
				return None
	return current


# ----------------------------------------------------------------------------------------------
# AST walker
# ----------------------------------------------------------------------------------------------


def _eval(node: ast.AST, env: dict) -> Any:
	if isinstance(node, ast.Constant):
		return node.value

	if isinstance(node, ast.Name):
		return env.get(node.id)

	if isinstance(node, ast.Subscript):
		value = _eval(node.value, env)
		slice_node = node.slice
		if isinstance(slice_node, ast.Index):  # py<3.9 shim
			slice_node = slice_node.value
		key = _eval(slice_node, env)
		return _subscript(value, key)

	if isinstance(node, ast.Compare):
		left = _eval(node.left, env)
		for op, comparator in zip(node.ops, node.comparators):
			op_func = _CMP_OPS.get(type(op))
			if op_func is None:
				return None
			right = _eval(comparator, env)
			try:
				result = op_func(left, right)
			except TypeError:
				return None
			if result is None:
				return None
			if not result:
				return False
			left = right
		return True

	if isinstance(node, ast.BoolOp):
		values = node.values
		if isinstance(node.op, ast.And):
			result: Any = True
			for value in values:
				result = _eval(value, env)
				if not result:
					return result
			return result
		else:  # ast.Or
			result = False
			for value in values:
				result = _eval(value, env)
				if result:
					return result
			return result

	if isinstance(node, ast.UnaryOp):
		operand = _eval(node.operand, env)
		try:
			if isinstance(node.op, ast.Not):
				return not operand
			if isinstance(node.op, ast.USub):
				return -operand
			if isinstance(node.op, ast.UAdd):
				return +operand
		except TypeError:
			return None
		return None

	if isinstance(node, ast.BinOp):
		left = _eval(node.left, env)
		right = _eval(node.right, env)
		op_func = _BIN_OPS.get(type(node.op))
		if op_func is None:
			return None
		try:
			return op_func(left, right)
		except (TypeError, ZeroDivisionError):
			return None

	if isinstance(node, ast.IfExp):
		test = _eval(node.test, env)
		return _eval(node.body, env) if test else _eval(node.orelse, env)

	if isinstance(node, ast.List):
		return [_eval(elt, env) for elt in node.elts]

	if isinstance(node, ast.Dict):
		return {_eval(k, env): _eval(v, env) for k, v in zip(node.keys, node.values)}

	if isinstance(node, ast.Tuple):
		return tuple(_eval(elt, env) for elt in node.elts)

	# Anything else should be unreachable post parse_expression, but stay total regardless.
	return None


def _subscript(value: Any, key: Any) -> Any:
	if isinstance(value, dict):
		return value.get(key)
	if isinstance(value, (list, tuple)):
		if isinstance(key, bool):  # bool is an int subclass; not a valid list index here
			return None
		if isinstance(key, int) and -len(value) <= key < len(value):
			return value[key]
		return None
	return None
