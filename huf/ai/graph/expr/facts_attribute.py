"""``facts.<name>`` rewrite for the expression parser. Frappe-free (imports only ``ast``)."""

from __future__ import annotations

import ast


class _FactsAttribute(ast.NodeTransformer):
	"""``facts.<name>`` is read as ``facts['<name>']``. Every other attribute stays and is rejected."""

	def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
		self.generic_visit(node)
		if isinstance(node.value, ast.Name) and node.value.id == "facts" and not node.attr.startswith("_"):
			return ast.copy_location(
				ast.Subscript(value=node.value, slice=ast.copy_location(ast.Constant(node.attr), node), ctx=ast.Load()),
				node,
			)
		return node
