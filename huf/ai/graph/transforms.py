"""Transform operation registry for the shared graph IR (T-12).

**Frappe-free by design** (GT-03/I3/I4): this module imports nothing from ``frappe`` and must stay
importable/runnable as a bare script or under plain ``pytest``/``unittest``, with no bench. Model:
``huf.ai.tools.execution_sandbox`` (the other frappe-free module in this codebase).

Contract (see ``$TRACK/spec/graph-ir.md`` section 5 and ``spec/graph-ir.schema.json``'s
``$defs/TransformOp``): there are **exactly eleven** transform operations. This module implements
exactly those eleven, dispatched by name from a static dict (``REGISTRY``) -- not an expression
language, not a general-purpose eval loop. The complete operation set is knowable by reading
``REGISTRY`` once; nothing here can add an operation at runtime (I3).

Totality (I2, I7, GT-03's anti-pattern): every operation is a **total function** over well-typed
input -- it never raises for ordinary data, including empty input, missing keys, null fields, and
type-mismatched values. Behaviour for every one of those edge cases is documented per-op below and is
exactly what ``graph-ir.md`` section 5's table specifies. Where an operation is handed input so
malformed it cannot even be interpreted as "well typed but empty/null" (e.g. ``rows`` is a string
instead of a list, or a required key is absent from ``config.input`` entirely), that is a contract
violation, not an ordinary-data edge case -- it is reported as a typed :class:`TransformError` in the
returned :class:`TransformResult` (``ok=False``) so the calling node FAILS instead of silently
succeeding with a wrong answer. This is the fix for the documented anti-pattern in
``huf/ai/flow_engine.py``'s ``_exec_transform`` (:1065), which swallows per-transformation errors into
a result *string* and still reports success.

Determinism (I nothing-new, just good practice + explicit test requirement): every op produces the
same output for the same logical input regardless of Python dict insertion order, and ``sort`` /
``group_by`` are stable / deterministically ordered. No wall-clock, randomness, network, or filesystem
access anywhere in this module.

Limits: callers pass a :class:`Limits` object (mirroring the IR's ``ResourceLimits.max_rows`` /
``max_output_bytes``); every op that produces or consumes row lists enforces ``max_rows`` and fails
closed (returns a typed error) rather than silently truncating.
"""

from __future__ import annotations

import ast
import json
import math
import operator
from dataclasses import dataclass
from typing import Any, Callable

# --------------------------------------------------------------------------------------------------
# Limits and results
# --------------------------------------------------------------------------------------------------

DEFAULT_MAX_ROWS = 10_000
DEFAULT_MAX_OUTPUT_BYTES = 1_000_000


@dataclass(frozen=True)
class Limits:
	"""Subset of the IR's ``ResourceLimits`` relevant to transform execution.

	Both fields fail closed: exceeding either produces a typed error result, never a truncated
	silent success.
	"""

	max_rows: int = DEFAULT_MAX_ROWS
	max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES


@dataclass(frozen=True)
class TransformError:
	"""A typed, structured failure. Never a bare string -- see module docstring."""

	code: str
	message: str
	op: str | None = None

	def to_dict(self) -> dict:
		return {"code": self.code, "message": self.message, "op": self.op}


@dataclass(frozen=True)
class TransformResult:
	"""The outcome of executing one transform op.

	``ok=True`` -> ``value`` holds the op's output (per the IR's per-op output type).
	``ok=False`` -> ``error`` holds a :class:`TransformError`; the caller must fail the node.
	"""

	ok: bool
	value: Any = None
	error: TransformError | None = None

	@staticmethod
	def success(value: Any) -> "TransformResult":
		return TransformResult(ok=True, value=value)

	@staticmethod
	def failure(code: str, message: str, op: str | None = None) -> "TransformResult":
		return TransformResult(ok=False, error=TransformError(code=code, message=message, op=op))


# Error codes are a closed, documented set -- part of the contract callers can branch on.
ERR_BAD_INPUT = "bad_input"
ERR_ROWS_LIMIT_EXCEEDED = "rows_limit_exceeded"
ERR_OUTPUT_LIMIT_EXCEEDED = "output_limit_exceeded"
ERR_UNKNOWN_OP = "unknown_op"


# --------------------------------------------------------------------------------------------------
# Path resolution: "string path" grammar shared by sort/group_by/join/lookup/distinct keys.
#
# graph-ir.md section 4.1 defines the general reference grammar (root + "." segment | "[" int "]").
# Transform "key"/"field" values are always relative to a single row (no root token), so this is a
# narrower, purely-local variant: a dotted/bracketed path evaluated against one dict, total, missing
# keys/out-of-range indices resolve to None rather than raising. This mirrors flow_eval.py's dict
# subscript behaviour, extended to list indices, but does NOT implement the full reference/expression
# grammar owned by T-13 (huf/ai/graph/expressions.py) -- only what row-key resolution needs.
# --------------------------------------------------------------------------------------------------

def _split_path(path: str) -> list[str | int]:
	"""Split "a.b[0].c" into ["a", "b", 0, "c"]. Never raises; unparsable paths yield []."""

	if not isinstance(path, str) or not path:
		return []
	segments: list[str | int] = []
	token = ""
	i = 0
	n = len(path)
	while i < n:
		ch = path[i]
		if ch == ".":
			if token:
				segments.append(token)
				token = ""
			i += 1
		elif ch == "[":
			if token:
				segments.append(token)
				token = ""
			end = path.find("]", i)
			if end == -1:
				return segments  # malformed trailing bracket: stop, keep what we have (total, no raise)
			inner = path[i + 1 : end]
			try:
				segments.append(int(inner))
			except ValueError:
				pass  # non-integer bracket contents: skip this segment, stay total
			i = end + 1
		else:
			token += ch
			i += 1
	if token:
		segments.append(token)
	return segments


def resolve_path(row: Any, path: str) -> Any:
	"""Resolve a dotted/bracketed path against ``row``. Total: any failure yields None."""

	current = row
	for segment in _split_path(path):
		if isinstance(segment, int):
			if isinstance(current, (list, tuple)) and -len(current) <= segment < len(current):
				current = current[segment]
			else:
				return None
		else:
			if isinstance(current, dict):
				current = current.get(segment)
			else:
				return None
	return current


# --------------------------------------------------------------------------------------------------
# Minimal, total, frappe-free predicate evaluator for `filter`'s `where: Expression`.
#
# graph-ir.md section 4 defines a shared reference/expression grammar owned by T-13
# (huf/ai/graph/expressions.py, a sibling task, not a dependency of T-12). T-12 does not depend on
# T-13, so `filter` needs its own self-contained evaluator for the row-scoped subset of that grammar:
# `row["field"]` subscripting, comparisons, boolean connectives, and literals -- the same restricted
# AST-walker shape as flow_eval.py's safe_eval_expression (GT-03/D1), extended so a raising or
# type-mismatched predicate resolves False for that row rather than aborting the whole op (per the
# `filter` row in graph-ir.md section 5's table). This is deliberately a subset of T-13's eventual
# evaluator, not a replacement for it -- transforms.py only ever needs boolean row predicates.
# --------------------------------------------------------------------------------------------------

MAX_WHERE_EXPRESSION_LENGTH = 500

_BIN_OPS: dict[type, Callable[[Any, Any], Any]] = {
	ast.Add: operator.add,
	ast.Sub: operator.sub,
	ast.Mult: operator.mul,
	ast.Mod: operator.mod,
}

_CMP_OPS: dict[type, Callable[[Any, Any], Any]] = {
	ast.Eq: operator.eq,
	ast.NotEq: operator.ne,
	ast.Lt: operator.lt,
	ast.LtE: operator.le,
	ast.Gt: operator.gt,
	ast.GtE: operator.ge,
	ast.In: lambda a, b: a in b,
	ast.NotIn: lambda a, b: a not in b,
	ast.Is: operator.is_,
	ast.IsNot: operator.is_not,
}


class _RowEvalError(Exception):
	"""Internal-only: any AST shape or runtime error the evaluator refuses. Caught at the boundary."""


def _eval_row_expr(node: ast.AST, row: dict) -> Any:
	if isinstance(node, ast.Constant):
		return node.value
	if isinstance(node, ast.List):
		return [_eval_row_expr(e, row) for e in node.elts]
	if isinstance(node, ast.Tuple):
		return tuple(_eval_row_expr(e, row) for e in node.elts)
	if isinstance(node, ast.Dict):
		return {
			_eval_row_expr(k, row): _eval_row_expr(v, row)
			for k, v in zip(node.keys, node.values, strict=True)
		}
	if isinstance(node, ast.Name):
		if node.id == "row":
			return row
		if node.id == "None":
			return None
		if node.id == "True":
			return True
		if node.id == "False":
			return False
		raise _RowEvalError(f"unknown name: {node.id}")
	if isinstance(node, ast.Subscript):
		value = _eval_row_expr(node.value, row)
		key = _eval_row_expr(node.slice, row)
		if isinstance(value, dict):
			return value.get(key)
		if isinstance(value, (list, tuple)) and isinstance(key, int):
			if -len(value) <= key < len(value):
				return value[key]
			return None
		return None
	if isinstance(node, ast.BoolOp):
		values = [_eval_row_expr(v, row) for v in node.values]
		if isinstance(node.op, ast.And):
			result = True
			for v in values:
				result = result and v
			return result
		result = False
		for v in values:
			result = result or v
		return result
	if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
		return not _eval_row_expr(node.operand, row)
	if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
		operand = _eval_row_expr(node.operand, row)
		return -operand
	if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
		left = _eval_row_expr(node.left, row)
		right = _eval_row_expr(node.right, row)
		return _BIN_OPS[type(node.op)](left, right)
	if isinstance(node, ast.Compare):
		left = _eval_row_expr(node.left, row)
		for op_node, comparator in zip(node.ops, node.comparators, strict=True):
			right = _eval_row_expr(comparator, row)
			fn = _CMP_OPS.get(type(op_node))
			if fn is None:
				raise _RowEvalError(f"unsupported comparison: {type(op_node).__name__}")
			if not fn(left, right):
				return False
			left = right
		return True
	raise _RowEvalError(f"unsupported expression node: {type(node).__name__}")


def eval_row_predicate(expression: str, row: dict) -> bool:
	"""Evaluate ``expression`` (graph-ir.md section 4.1's `row` root, a restricted subset) against one
	row. TOTAL: any parse failure, disallowed construct, or runtime error (type mismatch, etc.)
	resolves to ``False`` for that row -- per the `filter` semantics table, this never aborts the op.
	"""

	if not isinstance(expression, str) or not expression or len(expression) > MAX_WHERE_EXPRESSION_LENGTH:
		return False
	try:
		tree = ast.parse(expression, mode="eval")
		return bool(_eval_row_expr(tree.body, row if isinstance(row, dict) else {}))
	except Exception:
		return False


# --------------------------------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------------------------------


def _as_row_list(value: Any) -> list | None:
	"""Return value if it is a list, else None (caller decides bad_input vs. treat-as-empty)."""

	return value if isinstance(value, list) else None


def _check_rows_limit(rows: list, limits: Limits, op: str) -> TransformResult | None:
	if len(rows) > limits.max_rows:
		return TransformResult.failure(
			ERR_ROWS_LIMIT_EXCEEDED,
			f"{len(rows)} rows exceeds max_rows={limits.max_rows}",
			op=op,
		)
	return None


def _check_output_bytes(value: Any, limits: Limits, op: str) -> TransformResult | None:
	try:
		size = len(json.dumps(value, default=str, sort_keys=True))
	except (TypeError, ValueError):
		return None  # non-serializable output is not this check's concern; ops only emit JSON-safe values
	if size > limits.max_output_bytes:
		return TransformResult.failure(
			ERR_OUTPUT_LIMIT_EXCEEDED,
			f"output of {size} bytes exceeds max_output_bytes={limits.max_output_bytes}",
			op=op,
		)
	return None


def _canonical_json(value: Any) -> str:
	"""Canonical form for `distinct` without a key: sorted keys, stable separators, total for JSON-safe
	values. Non-JSON-safe values fall back to `repr`, which is still deterministic per-process for the
	plain dict/list/scalar rows this module operates on."""

	try:
		return json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
	except (TypeError, ValueError):
		return repr(value)


def _is_numeric(value: Any) -> bool:
	return isinstance(value, (int, float)) and not isinstance(value, bool) and not (
		isinstance(value, float) and math.isnan(value)
	)


# --------------------------------------------------------------------------------------------------
# The eleven operations
# --------------------------------------------------------------------------------------------------


def op_select(input: dict, limits: Limits) -> TransformResult:
	"""rows: list<object>, fields: list<string> -> list<object>.

	Missing field on a row contributes null, never an error. Non-dict rows contribute an all-null
	projected row rather than raising.
	"""

	rows = _as_row_list(input.get("rows"))
	fields = input.get("fields")
	if rows is None or not isinstance(fields, list):
		return TransformResult.failure(ERR_BAD_INPUT, "select requires rows: list and fields: list", "select")
	if err := _check_rows_limit(rows, limits, "select"):
		return err
	out = []
	for row in rows:
		projected = {}
		for f in fields:
			if not isinstance(f, str):
				continue
			projected[f] = row.get(f) if isinstance(row, dict) else None
		out.append(projected)
	if err := _check_output_bytes(out, limits, "select"):
		return err
	return TransformResult.success(out)


def op_filter(input: dict, limits: Limits) -> TransformResult:
	"""rows: list<object>, where: Expression -> list<object>.

	`where` evaluated once per row with `row` bound (see eval_row_predicate). A raising or
	type-mismatched predicate resolves False for that row -- it never aborts the op.
	"""

	rows = _as_row_list(input.get("rows"))
	where = input.get("where")
	if rows is None or not isinstance(where, str):
		return TransformResult.failure(ERR_BAD_INPUT, "filter requires rows: list and where: string", "filter")
	if err := _check_rows_limit(rows, limits, "filter"):
		return err
	out = [row for row in rows if eval_row_predicate(where, row if isinstance(row, dict) else {})]
	if err := _check_output_bytes(out, limits, "filter"):
		return err
	return TransformResult.success(out)


def op_sort(input: dict, limits: Limits) -> TransformResult:
	"""rows: list<object>, key: string path, order: "asc"|"desc" -> list<object>.

	Stable sort. Rows missing `key` sort last regardless of order.
	"""

	rows = _as_row_list(input.get("rows"))
	key = input.get("key")
	order = input.get("order", "asc")
	if rows is None or not isinstance(key, str) or order not in ("asc", "desc"):
		return TransformResult.failure(
			ERR_BAD_INPUT, 'sort requires rows: list, key: string, order: "asc"|"desc"', "sort"
		)
	if err := _check_rows_limit(rows, limits, "sort"):
		return err

	# Missing-key rows always sort last, independent of order (per the spec table). Partition first
	# (stable, preserves relative order within each partition), then sort only the present partition.
	def has_key(r: Any) -> bool:
		return isinstance(r, dict) and resolve_path(r, key) is not None

	present = [r for r in rows if has_key(r)]
	missing_rows = [r for r in rows if not has_key(r)]
	try:
		present = sorted(present, key=lambda r: _SortWrapper(resolve_path(r, key)), reverse=(order == "desc"))
	except TypeError:
		pass  # _SortWrapper already makes this unreachable in practice; totality belt-and-suspenders
	out = present + missing_rows
	if err := _check_output_bytes(out, limits, "sort"):
		return err
	return TransformResult.success(out)


class _SortWrapper:
	"""Total, cross-type-safe ordering key: same-type values compare natively; mixed types fall back to
	a deterministic (type-name, str(value)) tuple so sort never raises TypeError."""

	__slots__ = ("value",)

	def __init__(self, value: Any) -> None:
		self.value = value

	def _key(self) -> tuple:
		return (type(self.value).__name__, self.value)

	def __lt__(self, other: "_SortWrapper") -> bool:
		try:
			return self.value < other.value
		except TypeError:
			return (type(self.value).__name__, str(self.value)) < (type(other.value).__name__, str(other.value))

	def __eq__(self, other: object) -> bool:
		return isinstance(other, _SortWrapper) and self.value == other.value


def op_limit(input: dict, limits: Limits) -> TransformResult:
	"""rows: list<object>, count: integer >= 0 -> list<object>. count beyond length is a no-op."""

	rows = _as_row_list(input.get("rows"))
	count = input.get("count")
	if rows is None or not isinstance(count, int) or isinstance(count, bool) or count < 0:
		return TransformResult.failure(ERR_BAD_INPUT, "limit requires rows: list and count: int >= 0", "limit")
	if err := _check_rows_limit(rows, limits, "limit"):
		return err
	out = rows[:count]
	if err := _check_output_bytes(out, limits, "limit"):
		return err
	return TransformResult.success(out)


def op_group_by(input: dict, limits: Limits) -> TransformResult:
	"""rows: list<object>, key: string path -> list<{key, rows: list<object>}>.

	Rows with a missing key group under key: null. Group order is first-seen (deterministic
	regardless of dict insertion order elsewhere, since it only depends on row iteration order).
	"""

	rows = _as_row_list(input.get("rows"))
	key = input.get("key")
	if rows is None or not isinstance(key, str):
		return TransformResult.failure(ERR_BAD_INPUT, "group_by requires rows: list and key: string", "group_by")
	if err := _check_rows_limit(rows, limits, "group_by"):
		return err
	order: list = []
	groups: dict[str, list] = {}
	seen_keys: dict[str, Any] = {}
	for row in rows:
		value = resolve_path(row, key) if isinstance(row, dict) else None
		token = _canonical_json(value)
		if token not in groups:
			groups[token] = []
			order.append(token)
			seen_keys[token] = value
		groups[token].append(row)
	out = [{"key": seen_keys[token], "rows": groups[token]} for token in order]
	if err := _check_output_bytes(out, limits, "group_by"):
		return err
	return TransformResult.success(out)


_AGG_OPS = {"count", "sum", "avg", "min", "max"}


def op_aggregate(input: dict, limits: Limits) -> TransformResult:
	"""rows: list<object>, op: "count"|"sum"|"avg"|"min"|"max", field: string path
	(required except for count) -> number | null.

	count([]) = 0; sum([]) = 0; avg/min/max([]) = null; non-numeric field values are skipped.
	"""

	rows = _as_row_list(input.get("rows"))
	agg_op = input.get("op")
	agg_field = input.get("field")
	if rows is None or agg_op not in _AGG_OPS:
		return TransformResult.failure(
			ERR_BAD_INPUT, 'aggregate requires rows: list and op in {"count","sum","avg","min","max"}', "aggregate"
		)
	if agg_op != "count" and not isinstance(agg_field, str):
		return TransformResult.failure(
			ERR_BAD_INPUT, "aggregate requires field: string (except for count)", "aggregate"
		)
	if err := _check_rows_limit(rows, limits, "aggregate"):
		return err

	if agg_op == "count":
		return TransformResult.success(len(rows))

	values = [
		resolve_path(row, agg_field) if isinstance(row, dict) else None for row in rows
	]
	numeric = [v for v in values if _is_numeric(v)]

	if agg_op == "sum":
		return TransformResult.success(sum(numeric) if numeric else 0)
	if not numeric:
		return TransformResult.success(None)
	if agg_op == "avg":
		return TransformResult.success(sum(numeric) / len(numeric))
	if agg_op == "min":
		return TransformResult.success(min(numeric))
	return TransformResult.success(max(numeric))  # max


def op_join(input: dict, limits: Limits) -> TransformResult:
	"""left, right: list<object>, left_key, right_key: string, how: "inner"|"left" -> list<object>.

	Equi-join on left[left_key] == right[right_key]. Matched right fields merged under a `right_`
	prefix. how="left" keeps unmatched left rows with right_* fields null.
	"""

	left = _as_row_list(input.get("left"))
	right = _as_row_list(input.get("right"))
	left_key = input.get("left_key")
	right_key = input.get("right_key")
	how = input.get("how", "inner")
	if (
		left is None
		or right is None
		or not isinstance(left_key, str)
		or not isinstance(right_key, str)
		or how not in ("inner", "left")
	):
		return TransformResult.failure(
			ERR_BAD_INPUT,
			'join requires left, right: list, left_key, right_key: string, how: "inner"|"left"',
			"join",
		)
	if err := _check_rows_limit(left, limits, "join"):
		return err
	if err := _check_rows_limit(right, limits, "join"):
		return err

	# Deterministic bucketing: build the right-side index in right's original order, so multiple
	# matches for the same key are consumed in a stable order regardless of dict hashing.
	right_index: dict[str, list] = {}
	right_order: list[str] = []
	for r in right:
		token = _canonical_json(resolve_path(r, right_key) if isinstance(r, dict) else None)
		if token not in right_index:
			right_index[token] = []
			right_order.append(token)
		right_index[token].append(r)

	out = []
	right_field_names: set[str] = set()
	for r in right:
		if isinstance(r, dict):
			right_field_names.update(r.keys())

	for l in left:  # noqa: E741
		l_value = resolve_path(l, left_key) if isinstance(l, dict) else None
		token = _canonical_json(l_value)
		matches = right_index.get(token, [])
		if matches:
			for m in matches:
				merged = dict(l) if isinstance(l, dict) else {}
				if isinstance(m, dict):
					for k, v in m.items():
						merged[f"right_{k}"] = v
				out.append(merged)
				if len(out) > limits.max_rows:
					return TransformResult.failure(
						ERR_ROWS_LIMIT_EXCEEDED, f"join output exceeds max_rows={limits.max_rows}", "join"
					)
		elif how == "left":
			merged = dict(l) if isinstance(l, dict) else {}
			for k in right_field_names:
				merged[f"right_{k}"] = None
			out.append(merged)
			if len(out) > limits.max_rows:
				return TransformResult.failure(
					ERR_ROWS_LIMIT_EXCEEDED, f"join output exceeds max_rows={limits.max_rows}", "join"
				)
	if err := _check_output_bytes(out, limits, "join"):
		return err
	return TransformResult.success(out)


def op_lookup(input: dict, limits: Limits) -> TransformResult:
	"""rows: list<object>, from: list<object>, key: string path, on: string path, as: string
	-> list<object>.

	Single-row enrichment: attaches the first `from` element where from[on] == row[key] under
	row[as]. No match -> row[as] = null.
	"""

	rows = _as_row_list(input.get("rows"))
	from_rows = _as_row_list(input.get("from"))
	key = input.get("key")
	on = input.get("on")
	as_field = input.get("as")
	if (
		rows is None
		or from_rows is None
		or not isinstance(key, str)
		or not isinstance(on, str)
		or not isinstance(as_field, str)
	):
		return TransformResult.failure(
			ERR_BAD_INPUT, "lookup requires rows, from: list, key, on, as: string", "lookup"
		)
	if err := _check_rows_limit(rows, limits, "lookup"):
		return err
	if err := _check_rows_limit(from_rows, limits, "lookup"):
		return err

	first_match: dict[str, Any] = {}
	seen: set[str] = set()
	for f in from_rows:
		token = _canonical_json(resolve_path(f, on) if isinstance(f, dict) else None)
		if token not in seen:
			seen.add(token)
			first_match[token] = f

	out = []
	for row in rows:
		row_value = resolve_path(row, key) if isinstance(row, dict) else None
		token = _canonical_json(row_value)
		enriched = dict(row) if isinstance(row, dict) else {}
		enriched[as_field] = first_match.get(token)
		out.append(enriched)
	if err := _check_output_bytes(out, limits, "lookup"):
		return err
	return TransformResult.success(out)


def op_batch(input: dict, limits: Limits) -> TransformResult:
	"""rows: list<object>, size: integer >= 1 -> list<list<object>>. Last chunk may be smaller."""

	rows = _as_row_list(input.get("rows"))
	size = input.get("size")
	if rows is None or not isinstance(size, int) or isinstance(size, bool) or size < 1:
		return TransformResult.failure(ERR_BAD_INPUT, "batch requires rows: list and size: int >= 1", "batch")
	if err := _check_rows_limit(rows, limits, "batch"):
		return err
	out = [rows[i : i + size] for i in range(0, len(rows), size)]
	if err := _check_output_bytes(out, limits, "batch"):
		return err
	return TransformResult.success(out)


def op_distinct(input: dict, limits: Limits) -> TransformResult:
	"""rows: list<object>, key: string path (optional) -> list<object>.

	Dedupe keeping first occurrence. Without key, rows compared by canonical JSON form.
	"""

	rows = _as_row_list(input.get("rows"))
	key = input.get("key")
	if rows is None or (key is not None and not isinstance(key, str)):
		return TransformResult.failure(
			ERR_BAD_INPUT, "distinct requires rows: list and optional key: string", "distinct"
		)
	if err := _check_rows_limit(rows, limits, "distinct"):
		return err
	seen: set[str] = set()
	out = []
	for row in rows:
		token = _canonical_json(resolve_path(row, key) if key and isinstance(row, dict) else row)
		if token not in seen:
			seen.add(token)
			out.append(row)
	if err := _check_output_bytes(out, limits, "distinct"):
		return err
	return TransformResult.success(out)


def op_coalesce(input: dict, limits: Limits) -> TransformResult:
	"""values: list<Value> -> the first non-null value in values, or null."""

	values = input.get("values")
	if not isinstance(values, list):
		return TransformResult.failure(ERR_BAD_INPUT, "coalesce requires values: list", "coalesce")
	for v in values:
		if v is not None:
			return TransformResult.success(v)
	return TransformResult.success(None)


# --------------------------------------------------------------------------------------------------
# Registry (I3: the static, complete, invocable operation set)
# --------------------------------------------------------------------------------------------------

REGISTRY: dict[str, Callable[[dict, Limits], TransformResult]] = {
	"select": op_select,
	"filter": op_filter,
	"sort": op_sort,
	"limit": op_limit,
	"group_by": op_group_by,
	"aggregate": op_aggregate,
	"join": op_join,
	"lookup": op_lookup,
	"batch": op_batch,
	"distinct": op_distinct,
	"coalesce": op_coalesce,
}


def run_transform(op: str, input: dict, limits: Limits | None = None) -> TransformResult:
	"""Dispatch ``op`` from the static REGISTRY against ``input``. Total: an unknown op name is a
	typed failure (ERR_UNKNOWN_OP), never an exception, never a silent no-op.
	"""

	limits = limits or Limits()
	if not isinstance(input, dict):
		return TransformResult.failure(ERR_BAD_INPUT, "input must be an object", op)
	fn = REGISTRY.get(op)
	if fn is None:
		return TransformResult.failure(ERR_UNKNOWN_OP, f"unknown transform op: {op!r}", op)
	return fn(input, limits)
