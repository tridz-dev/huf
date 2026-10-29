"""String templating for the ``{"$template": ..., "vars": {...}}`` reference form.

Frappe-free. Syntax: ``{name}`` is replaced by ``vars[name]``; ``{{`` and ``}}`` are literal braces.
Variable names are identifiers only (no attribute access, no format specs, no calls), so a template
can never evaluate anything. Substituted values are never re-scanned for placeholders.

Behaviour (documented contract):

* A placeholder naming a variable that is not declared in ``vars`` is an authoring error: it raises
  :class:`TemplateError`, which fails the node with a clear message.
* A declared variable whose value is null (e.g. a ``$from`` that resolved to nothing) renders as
  the empty string.
* bool -> ``true``/``false``; numbers via ``str``.
* A list or object is never pasted in as JSON (a customer would read it in an email or a Slack message):
  it becomes a short readable summary (``Ada Lovelace``, ``Total: 450, Status: paid``, ``3 items: A, B and 1
  more``). ``objects="json"`` keeps JSON for text a model reads (agent prompts).
* Template and rendered output are length-capped. Error messages are plain sentences for a flow author.
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


def _stringify(value: Any, objects: str = "summary") -> str:
	if value is None:
		return ""
	if isinstance(value, bool):
		return "true" if value else "false"
	if isinstance(value, str):
		return value
	if isinstance(value, (int, float)):
		return str(value)
	if objects == "json":
		return json.dumps(value, default=str)
	from huf.ai.flow.support.humanize import summarize

	return summarize(value) or ""


def render_template(template: str, values: Mapping[str, Any], objects: str = "summary") -> str:
	if not isinstance(template, str) or len(template) > MAX_TEMPLATE_CHARS:
		raise TemplateError(f"This text is longer than {MAX_TEMPLATE_CHARS} characters. Shorten it.")

	def sub(match: re.Match) -> str:
		tok = match.group(0)
		if tok == "{{":
			return "{"
		if tok == "}}":
			return "}"
		name = match.group(1)
		if name is None:
			raise TemplateError(
				"This text has a stray { or } brace. Type {{ or }} to show a brace, or remove it."
			)
		if name not in values:
			raise TemplateError(
				f"This text uses {{{name}}} but no data was chosen for it. Choose the data for it or remove it."
			)
		return _stringify(values[name], objects)

	out = _TOKEN_RE.sub(sub, template)
	if len(out) > MAX_RENDERED_CHARS:
		raise TemplateError(
			f"The finished text is longer than {MAX_RENDERED_CHARS} characters. Shorten it or use less data."
		)
	return out
