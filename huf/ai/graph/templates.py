"""String templating for the ``{"$template": ..., "vars": {...}}`` reference form.

Frappe-free. Syntax: ``{name}`` is replaced by ``vars[name]``; ``{{`` and ``}}`` are literal braces.
Variable names are identifiers only (no attribute access, no format specs, no calls), so a template
can never evaluate anything. Substituted values are never re-scanned for placeholders.

Behaviour (documented contract):

* A placeholder naming a variable that is not declared in ``vars`` is an authoring error: it raises
  :class:`TemplateError`, which fails the node with a clear message.
* A declared variable whose value is null (e.g. a ``$from`` that resolved to nothing) renders as
  the empty string.
* bool -> ``true``/``false``; numbers via ``str``; list/dict -> compact JSON.
* Template and rendered output are length-capped.
"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping

MAX_TEMPLATE_CHARS = 4_000
MAX_RENDERED_CHARS = 10_000

_TOKEN_RE = re.compile(r"\{\{|\}\}|\{([A-Za-z_][A-Za-z0-9_]*)\}|[{}]")


class TemplateError(ValueError):
	"""Template is malformed, references an undefined variable, or is too large."""


def _stringify(value: Any) -> str:
	if value is None:
		return ""
	if isinstance(value, bool):
		return "true" if value else "false"
	if isinstance(value, str):
		return value
	if isinstance(value, (int, float)):
		return str(value)
	return json.dumps(value, default=str)


def render_template(template: str, values: Mapping[str, Any]) -> str:
	if not isinstance(template, str) or len(template) > MAX_TEMPLATE_CHARS:
		raise TemplateError(f"template must be a string of at most {MAX_TEMPLATE_CHARS} characters")

	def sub(match: re.Match) -> str:
		tok = match.group(0)
		if tok == "{{":
			return "{"
		if tok == "}}":
			return "}"
		name = match.group(1)
		if name is None:
			raise TemplateError(f"template has an unescaped or malformed brace: {template[:60]!r}")
		if name not in values:
			raise TemplateError(f"template references undefined variable {name!r}")
		return _stringify(values[name])

	out = _TOKEN_RE.sub(sub, template)
	if len(out) > MAX_RENDERED_CHARS:
		raise TemplateError(f"rendered template exceeds {MAX_RENDERED_CHARS} characters")
	return out
