"""
Safe expression evaluator for Flow Engine expression edges.

Provides restricted evaluation of expressions against flow context.
Only allows dict-safe access patterns; no imports, no frappe access,
no attribute access beyond simple key lookups.
"""

import ast
import operator

import frappe
from frappe import _


# Allowed comparison and binary operators
SAFE_OPS = {
	ast.Eq: operator.eq,
	ast.NotEq: operator.ne,
	ast.Lt: operator.lt,
	ast.LtE: operator.le,
	ast.Gt: operator.gt,
	ast.GtE: operator.ge,
	ast.Is: operator.is_,
	ast.IsNot: operator.is_not,
	ast.In: lambda a, b: a in b,
	ast.NotIn: lambda a, b: a not in b,
	ast.Add: operator.add,
	ast.Sub: operator.sub,
	ast.Mult: operator.mul,
	ast.Mod: operator.mod,
	ast.And: None,  # handled specially
	ast.Or: None,  # handled specially
	ast.Not: operator.not_,
}

MAX_EXPRESSION_LENGTH = 500


def safe_eval_expression(expression: str, context: dict) -> bool:
	"""
	Safely evaluate an expression string against flow context.

	Only allows:
	- Dict key access via subscript: context["key"]
	- Simple comparisons: ==, !=, <, >, <=, >=, in, not in
	- Boolean operators: and, or, not
	- Literals: strings, numbers, booleans, None, lists, dicts
	- Simple arithmetic: +, -, *, %

	Does NOT allow:
	- Function calls
	- Attribute access (no dot notation for arbitrary objects)
	- Import statements
	- Assignment
	- Lambda/comprehensions

	Args:
	    expression: Expression string to evaluate
	    context: Flow context dict (available as 'context' variable)

	Returns:
	    bool: Result of expression evaluation (coerced to bool)

	Raises:
	    frappe.ValidationError: If expression is invalid or uses disallowed features
	"""
	if not expression or not isinstance(expression, str):
		frappe.throw(_("Expression must be a non-empty string"), frappe.ValidationError)

	expression = expression.strip()

	if len(expression) > MAX_EXPRESSION_LENGTH:
		frappe.throw(
			_("Expression too long ({0} chars, max {1})").format(len(expression), MAX_EXPRESSION_LENGTH),
			frappe.ValidationError,
		)

	try:
		tree = ast.parse(expression, mode="eval")
	except SyntaxError as e:
		frappe.throw(_("Invalid expression syntax: {0}").format(str(e)), frappe.ValidationError)

	try:
		result = _eval_node(tree.body, {"context": context})
		return bool(result)
	except frappe.ValidationError:
		raise
	except Exception as e:
		frappe.throw(_("Expression evaluation error: {0}").format(str(e)), frappe.ValidationError)


def _eval_node(node, env: dict):
	"""Recursively evaluate an AST node in restricted mode."""

	# Constants: 42, "hello", True, None
	if isinstance(node, ast.Constant):
		return node.value

	# Name lookup: context
	if isinstance(node, ast.Name):
		if node.id not in env:
			frappe.throw(
				_("Unknown variable '{0}'. Only 'context' is available.").format(node.id),
				frappe.ValidationError,
			)
		return env[node.id]

	# Subscript: context["key"] or context["key"]["subkey"]
	if isinstance(node, ast.Subscript):
		value = _eval_node(node.value, env)
		if isinstance(node.slice, ast.Constant):
			key = node.slice.value
		else:
			key = _eval_node(node.slice, env)

		if not isinstance(value, (dict, list)):
			frappe.throw(
				_("Subscript access is only allowed on dicts and lists"),
				frappe.ValidationError,
			)

		try:
			return value[key]
		except (KeyError, IndexError, TypeError):
			return None

	# Comparison: a == b, a > b, a in b
	if isinstance(node, ast.Compare):
		left = _eval_node(node.left, env)
		for op, comparator in zip(node.ops, node.comparators):
			op_type = type(op)
			if op_type not in SAFE_OPS:
				frappe.throw(
					_("Unsupported comparison operator: {0}").format(op_type.__name__),
					frappe.ValidationError,
				)
			right = _eval_node(comparator, env)
			op_func = SAFE_OPS[op_type]
			if not op_func(left, right):
				return False
			left = right
		return True

	# Boolean: a and b, a or b
	if isinstance(node, ast.BoolOp):
		if isinstance(node.op, ast.And):
			result = True
			for value in node.values:
				result = _eval_node(value, env)
				if not result:
					return result
			return result
		elif isinstance(node.op, ast.Or):
			result = False
			for value in node.values:
				result = _eval_node(value, env)
				if result:
					return result
			return result

	# Unary: not x, -x
	if isinstance(node, ast.UnaryOp):
		operand = _eval_node(node.operand, env)
		if isinstance(node.op, ast.Not):
			return not operand
		elif isinstance(node.op, ast.USub):
			return -operand
		elif isinstance(node.op, ast.UAdd):
			return +operand
		frappe.throw(
			_("Unsupported unary operator: {0}").format(type(node.op).__name__),
			frappe.ValidationError,
		)

	# Binary: a + b, a - b, a * b, a % b
	if isinstance(node, ast.BinOp):
		left = _eval_node(node.left, env)
		right = _eval_node(node.right, env)
		op_type = type(node.op)
		if op_type not in SAFE_OPS:
			frappe.throw(
				_("Unsupported binary operator: {0}").format(op_type.__name__),
				frappe.ValidationError,
			)
		op_func = SAFE_OPS[op_type]
		return op_func(left, right)

	# If expression: a if cond else b
	if isinstance(node, ast.IfExp):
		test = _eval_node(node.test, env)
		if test:
			return _eval_node(node.body, env)
		return _eval_node(node.orelse, env)

	# List literal: [1, 2, 3]
	if isinstance(node, ast.List):
		return [_eval_node(elt, env) for elt in node.elts]

	# Dict literal: {"a": 1}
	if isinstance(node, ast.Dict):
		return {_eval_node(k, env): _eval_node(v, env) for k, v in zip(node.keys, node.values)}

	# Tuple literal: (1, 2)
	if isinstance(node, ast.Tuple):
		return tuple(_eval_node(elt, env) for elt in node.elts)

	# Attribute access - only allow .get() on dicts for safety
	if isinstance(node, ast.Attribute):
		frappe.throw(
			_("Attribute access is not allowed in expressions. Use subscript notation: context[\"key\"]"),
			frappe.ValidationError,
		)

	# Function calls are not allowed
	if isinstance(node, ast.Call):
		frappe.throw(
			_("Function calls are not allowed in expressions"),
			frappe.ValidationError,
		)

	frappe.throw(
		_("Unsupported expression element: {0}").format(type(node).__name__),
		frappe.ValidationError,
	)