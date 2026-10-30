"""Rules -> condition expression (the Python side of the Condition builder, UX-13).

The Condition step stores one string, ``config.expression``, in the graph-IR expression language
(``huf.ai.graph.expressions``). The builder on screen edits a small rules model and writes that string.
The browser does the same with ``frontend/src/lib/flow-condition/compile.ts``; both implementations must give the
**same text** for the same model, which ``frontend/src/lib/flow-condition/condition_vectors.json`` pins (both test suites
read that one file).

Frappe-free by design (like ``huf.ai.graph.expressions``): it imports nothing from ``frappe``.

The model
---------
::

    model := {"match": "all" | "any", "items": [rule | group, ...]}
    group := {"type": "group", "match": "all" | "any", "items": [rule, ...]}          # one level only
    rule  := {"type": "rule", "field": "input.amount", "op": <operator>,
              "value": <operand>?, "numeric": bool?, "ignoreCase": bool?}
    operand := {"kind": "text", "text": "Paid"} | {"kind": "number", "text": "100"}
             | {"kind": "ref", "ref": "n1.customer.name"}
             | {"kind": "list", "items": [{"kind": "text"|"number", "text": "..."}, ...]}

``field`` and ``ref`` are reference paths (FIELD_CONTRACT section 2): ``input.customer.name``, ``n1.items[0].sku``,
``foreach.item.sku``. They are written the way the evaluator reads them: ``input['customer']['name']``.

An **incomplete** rule (no field, or a missing value for an operator that needs one) and a group with no complete rule
are left out; a model with nothing complete compiles to ``""`` (the step then says "Add at least one rule").

What the text looks like (``F`` is the field, ``V`` the value)
--------------------------------------------------------------
============================  =============================================================
is / is not                   ``F == V`` / ``F != V``
is more than / less than      ``F > V`` / ``F < V``;  at least / at most: ``F >= V`` / ``F <= V``
contains / does not contain   ``V in F`` / ``not (V in F)``
starts with / ends with       ``startswith(F, V)`` / ``endswith(F, V)``
is empty / is not empty       ``F in [None, '', [], {}]`` / ``F not in [None, '', [], {}]``
is yes / is no                ``F == True`` / ``F == False``
is one of / is none of        ``F in [V1, V2]`` / ``F not in [V1, V2]``
============================  =============================================================

* ``numeric`` (comparing as numbers, for a number or a field value): ``number(F)`` replaces ``F`` and ``number(V)`` replaces
  a reference ``V``, so the text ``"150"`` from a form compares as 150 and text that is no number never matches.
* ``ignoreCase`` (text only): ``lower(F)`` replaces ``F`` and the text value is written in lower case.
* Rules are joined with `` and `` (all) or `` or `` (any); a group is written in brackets, also when it holds one rule.
"""

from __future__ import annotations

import re

MAX_EXPRESSION_LENGTH = 500

OPERATORS = (
	"is",
	"is_not",
	"gt",
	"lt",
	"gte",
	"lte",
	"contains",
	"not_contains",
	"starts_with",
	"ends_with",
	"is_empty",
	"is_not_empty",
	"is_yes",
	"is_no",
	"one_of",
	"none_of",
)

NO_VALUE = frozenset({"is_empty", "is_not_empty", "is_yes", "is_no"})
_COMPARE = {"is": "==", "is_not": "!=", "gt": ">", "lt": "<", "gte": ">=", "lte": "<="}
_NUMERIC_OPS = frozenset(_COMPARE) | {"one_of", "none_of"}
_TEXT_OPS = frozenset({"is", "is_not", "contains", "not_contains", "starts_with", "ends_with", "one_of", "none_of"})
EMPTY_LIST = "[None, '', [], {}]"

# FIELD_CONTRACT reference grammar: root (input | trigger | row | foreach.item | foreach.index | <node id>), then .name or [n].
REF_RE = re.compile(r"^(input|trigger|row|foreach\.(?:item|index)|[A-Za-z_][A-Za-z0-9_]*)((?:\.[A-Za-z_][A-Za-z0-9_]*|\[\d+\])*)$")
_SEGMENT_RE = re.compile(r"\.([A-Za-z_][A-Za-z0-9_]*)|\[(\d+)\]")
NUMBER_RE = re.compile(r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?$")


def is_valid_ref(ref) -> bool:
	return isinstance(ref, str) and REF_RE.match(ref) is not None


def is_number_text(text) -> bool:
	return isinstance(text, str) and NUMBER_RE.match(text) is not None


def py_string(value: str) -> str:
	"""A single-quoted literal that reads back as exactly ``value`` (backslashes, quotes, newlines, control characters)."""
	out = ["'"]
	for ch in value:
		code = ord(ch)
		if ch == "\\":
			out.append("\\\\")
		elif ch == "'":
			out.append("\\'")
		elif ch == "\n":
			out.append("\\n")
		elif ch == "\r":
			out.append("\\r")
		elif ch == "\t":
			out.append("\\t")
		elif code < 0x20 or 0x7F <= code <= 0x9F:
			out.append(f"\\x{code:02x}")
		elif code in (0x2028, 0x2029):
			out.append(f"\\u{code:04x}")
		elif 0xD800 <= code <= 0xDFFF:
			out.append(f"\\u{code:04x}")
		else:
			out.append(ch)
	out.append("'")
	return "".join(out)


def reference_expression(ref: str) -> str | None:
	"""``input.customer.name`` -> ``input['customer']['name']``; ``n1.items[0].sku`` -> ``n1['items'][0]['sku']``. None if not a reference."""
	m = REF_RE.match(ref) if isinstance(ref, str) else None
	if not m:
		return None
	root, rest = m.group(1), m.group(2)
	if root.startswith("foreach."):
		out = f"foreach['{root.split('.', 1)[1]}']"
	else:
		out = root
	for seg in _SEGMENT_RE.finditer(rest):
		out += f"['{seg.group(1)}']" if seg.group(1) is not None else f"[{seg.group(2)}]"
	return out


def _operand_kind(value) -> str | None:
	return value.get("kind") if isinstance(value, dict) else None


def _complete_value(op: str, value) -> bool:
	if op in NO_VALUE:
		return True
	kind = _operand_kind(value)
	if kind == "text":
		return isinstance(value.get("text"), str) and value["text"] != ""
	if kind == "number":
		return is_number_text(value.get("text"))
	if kind == "ref":
		return is_valid_ref(value.get("ref"))
	if kind == "list" and op in ("one_of", "none_of"):
		items = value.get("items")
		return isinstance(items, list) and len(items) > 0 and all(_complete_value(op, i) and _operand_kind(i) in ("text", "number") for i in items)
	return False


def _scalar_only(op: str) -> bool:
	return op not in ("one_of", "none_of")


def compile_rule(rule: dict) -> str | None:
	"""The text of one rule, or None when it is not complete."""
	if not isinstance(rule, dict):
		return None
	op = rule.get("op")
	if op not in OPERATORS:
		return None
	field = reference_expression(rule.get("field"))
	if field is None:
		return None
	value = rule.get("value")
	if not _complete_value(op, value):
		return None
	if op == "is_empty":
		return f"{field} in {EMPTY_LIST}"
	if op == "is_not_empty":
		return f"{field} not in {EMPTY_LIST}"
	if op == "is_yes":
		return f"{field} == True"
	if op == "is_no":
		return f"{field} == False"

	kind = _operand_kind(value)
	if not _scalar_only(op) and kind != "list":
		return None
	if _scalar_only(op) and kind == "list":
		return None

	# Compare as numbers: only for a number or a field value (never for text), and only where it means something.
	if kind == "list":
		all_numbers = all(i.get("kind") == "number" for i in value["items"])
		numeric = bool(rule.get("numeric")) and all_numbers
	else:
		numeric = bool(rule.get("numeric")) and kind in ("number", "ref") and op in _NUMERIC_OPS
	# Ignore capital letters: text matching only, and never together with a numeric comparison.
	has_text = kind in ("text", "ref") or (kind == "list" and any(i.get("kind") == "text" for i in value["items"]))
	ignore_case = bool(rule.get("ignoreCase")) and not numeric and has_text and op in _TEXT_OPS

	def field_side() -> str:
		return f"number({field})" if numeric else f"lower({field})" if ignore_case else field

	def scalar(v: dict) -> str:
		k = v["kind"]
		if k == "text":
			return py_string(v["text"].lower() if ignore_case else v["text"])
		if k == "number":
			return v["text"]
		ref = reference_expression(v["ref"])
		return f"number({ref})" if numeric else f"lower({ref})" if ignore_case else ref

	if op in _COMPARE:
		return f"{field_side()} {_COMPARE[op]} {scalar(value)}"
	if op == "contains":
		return f"{scalar(value)} in {field_side()}"
	if op == "not_contains":
		return f"not ({scalar(value)} in {field_side()})"
	if op == "starts_with":
		return f"startswith({field_side()}, {scalar(value)})"
	if op == "ends_with":
		return f"endswith({field_side()}, {scalar(value)})"
	# one_of / none_of
	listed = "[" + ", ".join(scalar(i) for i in value["items"]) + "]"
	return f"{field_side()} {'in' if op == 'one_of' else 'not in'} {listed}"


def _compile_items(match: str, items: list, allow_groups: bool) -> list[str]:
	parts: list[str] = []
	for item in items or []:
		if not isinstance(item, dict):
			continue
		if item.get("type") == "group":
			if not allow_groups:
				continue
			inner = _compile_items(item.get("match"), item.get("items"), False)
			if inner:
				parts.append("(" + (" or " if item.get("match") == "any" else " and ").join(inner) + ")")
		else:
			text = compile_rule(item)
			if text is not None:
				parts.append(text)
	return parts


def compile_condition(model: dict) -> str:
	"""The expression for a rules model; ``""`` when there is no complete rule."""
	if not isinstance(model, dict):
		return ""
	parts = _compile_items(model.get("match"), model.get("items"), True)
	return (" or " if model.get("match") == "any" else " and ").join(parts)
