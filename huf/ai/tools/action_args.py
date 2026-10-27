"""Declarative per-action argument tables for multi-action agent tools.

A tool module declares ONE table: ``arg_types`` (name -> JSON type + description) and ``action_args``
(action -> {argument: required}). ``ActionTable`` turns it into

- the registry parameter rows shown to the model (``registry_parameters``),
- the one-line usage text of the tool description (``usage`` / ``usage_summary``),
- strict validation that runs before anything else (``validate``): unknown argument, missing required
  argument and wrong type are refused with the valid names.

Internal arguments (injected by the harness, never shown to the model) are accepted by ``validate`` but are
not part of an action's valid names.

Plain data and stdlib only: the registry imports this without touching Frappe.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Iterable, Mapping

# Words a model uses for "the main value" when it guesses an argument name.
GENERIC_VALUE_NAMES = frozenset({"text", "value", "content", "message", "body", "string"})
_A = {"array": "an", "object": "an"}
_TRUE_FALSE = ("true", "false", "1", "0", "yes", "no", "on", "off")


class ArgumentRefusal(Exception):
	"""An argument problem; ``code`` is always ``invalid_argument``."""

	def __init__(self, message: str, **extra: Any) -> None:
		super().__init__(message)
		self.code = "invalid_argument"
		self.message = message
		self.extra = extra


class ActionTable:
	def __init__(
		self,
		arg_types: Mapping[str, tuple[str, str]],
		action_args: Mapping[str, Mapping[str, bool]],
		*,
		internal: Iterable[str] = (),
		enums: Mapping[str, tuple[str, ...]] | None = None,
		text_lists: Iterable[str] = (),
	) -> None:
		"""``text_lists`` names array arguments that may also be given as plain text (not only JSON)."""
		self.arg_types = arg_types
		self.action_args = action_args
		self.internal = frozenset(internal)
		self.enums = dict(enums or {})
		self.text_lists = frozenset(text_lists)
		self.choices = "|".join(action_args)

	# -- documentation ----------------------------------------------------------------------------

	def usage(self, action: str) -> str:
		spec = self.action_args[action]
		return f"{action}({', '.join(k if req else k + '?' for k, req in spec.items())})"

	def usage_summary(self) -> str:
		return "; ".join(self.usage(a) for a in self.action_args)

	def names(self) -> list[str]:
		"""Every model-visible argument name, in first-use order."""
		out: list[str] = []
		for spec in self.action_args.values():
			for n in spec:
				if n not in out:
					out.append(n)
		return out

	def used_by(self, name: str) -> list[str]:
		return [a for a, s in self.action_args.items() if name in s]

	def registry_parameters(
		self, p: Callable[..., dict], *, action_description: str | None = None
	) -> list[dict]:
		"""Registry rows (``p`` is the registry's row builder) generated from the table."""
		rows = [
			p(
				"action",
				required=True,
				description=action_description or f"Action to perform. One of: {self.choices}",
			)
		]
		for name in self.names():
			kind, desc = self.arg_types[name]
			used = self.used_by(name)
			req = [a for a in used if self.action_args[a][name]]
			note = f" Used by: {', '.join(used)}."
			if req:
				note += f" Required for: {', '.join(req)}."
			rows.append(p(name, type="string" if kind == "chat" else kind, description=desc + note))
		return rows

	# -- validation -------------------------------------------------------------------------------

	def _bad(self, action: str, name: str, expect: str) -> ArgumentRefusal:
		return ArgumentRefusal(
			f"argument '{name}' for {action} must be {expect}",
			valid_arguments=list(self.action_args[action]),
		)

	def _coerce(self, action: str, name: str, value: Any) -> None:
		kind = self.arg_types[name][0]
		if kind == "chat":
			if isinstance(value, bool) or not isinstance(value, (int, str)):
				raise self._bad(action, name, "a numeric chat id or @username")
		elif kind == "integer":
			if isinstance(value, bool) or not (
				isinstance(value, int) or (isinstance(value, str) and value.strip().lstrip("-").isdigit())
			):
				raise self._bad(action, name, "an integer")
		elif kind == "number":
			try:
				ok = not isinstance(value, bool) and float(value) == float(value)
			except (TypeError, ValueError):
				ok = False
			if not ok:
				raise self._bad(action, name, "a number")
		elif kind == "boolean":
			if not (isinstance(value, bool) or str(value).strip().lower() in _TRUE_FALSE):
				raise self._bad(action, name, "true or false")
		elif kind == "string":
			if not isinstance(value, str):
				raise self._bad(action, name, "a string")
			allowed = self.enums.get(name)
			if allowed and value not in allowed:
				raise self._bad(action, name, "one of " + ", ".join(allowed))
		elif kind in ("array", "object"):
			want = list if kind == "array" else dict
			if isinstance(value, str):
				try:
					parsed = json.loads(value)
				except ValueError:
					parsed = None
				if not (
					isinstance(parsed, want)
					or (kind == "array" and name in self.text_lists and value.strip())
				):
					raise self._bad(action, name, f"an {kind} (or its JSON text)")
			elif not isinstance(value, want):
				raise self._bad(action, name, f"an {kind}")

	def validate(self, action: str, args: Mapping[str, Any]) -> Mapping[str, Any]:
		"""Return ``args`` after checking names, presence and types; raise ``ArgumentRefusal`` otherwise."""
		spec = self.action_args[action]
		valid = list(spec)
		unknown = [k for k in args if k not in spec and k not in self.internal]
		if unknown:
			hints = []
			for k in unknown:
				if k in GENERIC_VALUE_NAMES:
					near = [a for a, req in spec.items() if req and self.arg_types[a][0] == "string"][:1]
				else:
					near = [a for a in spec if k in a or a in k]
				hints.append(f"unknown argument '{k}' for {action}" + (f"; use '{near[0]}'" if near else ""))
			raise ArgumentRefusal(
				"; ".join(hints) + f". Valid arguments for {action}: {', '.join(valid) or '(none)'}.",
				unknown_arguments=unknown,
				valid_arguments=valid,
			)
		missing = [k for k, req in spec.items() if req and args.get(k) is None]
		if missing:
			raise ArgumentRefusal(
				f"missing required argument(s) for {action}: {', '.join(missing)}. "
				f"Valid arguments for {action}: {', '.join(valid) or '(none)'}.",
				missing_arguments=missing,
				valid_arguments=valid,
			)
		for k, v in args.items():
			if v is not None and k in spec:
				self._coerce(action, k, v)
		return args
