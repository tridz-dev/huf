# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Facts about flow members, read from apps while a condition runs (H-W2-22) and never stored.

An app declares one entry per fact family in ``hooks.py``::

	huf_flow_facts_providers = [{"facts": ["tier", "points"], "handler": "myapp.facts.balance"}]

The handler is ``handler(member_keys, facts, context) -> {member_key: {fact: value}}`` with
``context = {"flow_id": str}``; it leaves out what it does not know. The first declaration of a fact name wins.

Code that evaluates many members of one flow wraps the work in :func:`batch`: each family is then asked once for all
of them. Outside a batch, a lookup is a batch of one. Values live only in the batch object.

Fail closed: a lookup returns either every requested value or a reason code. A provider error is logged as hook path
plus exception class only, and nothing raises from a frame that holds a value.

frappe is imported inside functions so the module also loads without a bench.
"""

from __future__ import annotations

import ast
import contextlib
import contextvars
import json
import time

HOOK = "huf_flow_facts_providers"
ROOT = "facts"
FACTS_ERROR = "facts_error"
FACTS_TIMEOUT = "facts_timeout"
TIMEOUT_KEY = "huf_flow_facts_timeout_s"
DEFAULT_TIMEOUT_S = 5

_current: contextvars.ContextVar = contextvars.ContextVar("huf_flow_facts_batch", default=None)


def names_used(parsed) -> tuple[list[str], bool]:
	"""``(fact names, dynamic)`` a parsed expression reads. ``dynamic``: it uses ``facts`` in a way no name can be told."""
	names: list[str] = []
	named = set()
	dynamic = False
	for node in ast.walk(parsed._tree):  # breadth first: a subscript is seen before the name inside it
		if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == ROOT:
			key = node.slice
			if isinstance(key, ast.Constant) and isinstance(key.value, str):
				names.append(key.value)
				named.add(id(node.value))
		elif isinstance(node, ast.Name) and node.id == ROOT and id(node) not in named:
			dynamic = True
	return list(dict.fromkeys(names)), dynamic


def providers() -> list[tuple[list[str], str]]:
	"""``(fact names, handler path)`` per well-formed declaration; a name belongs to its first declaration only."""
	import frappe

	from huf.ai.flow.catalog.node_registry import _entries

	families: list[tuple[list[str], str]] = []
	taken: set[str] = set()
	for app in frappe.get_installed_apps():
		for raw_hook in frappe.get_hooks(HOOK, app_name=app) or []:
			for entry in _entries(raw_hook):
				names, handler = entry.get("facts"), entry.get("handler")
				if not isinstance(names, (list, tuple)) or not isinstance(handler, str) or "." not in handler:
					_warn(app, "invalid declaration")
					continue
				own = [n for n in dict.fromkeys(n for n in names if isinstance(n, str) and n) if n not in taken]
				if own:
					taken.update(own)
					families.append((own, handler))
	return families


def offered_names() -> set[str]:
	return {name for names, _handler in providers() for name in names}


def timeout_seconds() -> float:
	import frappe

	value = frappe.conf.get(TIMEOUT_KEY)
	if isinstance(value, bool) or not isinstance(value, (int, float)) or not value > 0:
		return DEFAULT_TIMEOUT_S
	return min(max(value, 1), 30)


class _Batch:
	def __init__(self, flow_id: str, member_keys):
		self.flow_id = flow_id
		self.members = list(dict.fromkeys(k for k in member_keys if k))
		self._member_set = set(self.members)
		self.values: dict[str, dict] = {member: {} for member in self.members}
		self.asked: dict[str, str | None] = {}  # fact name -> reason code of the call that fetched it, or None
		self._families = None

	def covers(self, flow_id: str, member_key: str) -> bool:
		return flow_id == self.flow_id and member_key in self._member_set

	def lookup(self, member_key: str, names: list[str]) -> tuple[dict | None, str | None]:
		self._fetch([n for n in names if n not in self.asked])
		reasons = [self.asked.get(n, FACTS_ERROR) for n in names]  # a name no family offers was never asked
		if FACTS_TIMEOUT in reasons:
			return None, FACTS_TIMEOUT
		known = self.values[member_key]
		if any(reasons) or any(known.get(n) is None for n in names):
			return None, FACTS_ERROR
		return json.loads(json.dumps({n: known[n] for n in names})), None  # a copy per reader

	def _fetch(self, missing: list[str]) -> None:
		if not missing:
			return
		if self._families is None:
			try:
				self._families = providers()
			except Exception as error:  # noqa: BLE001 - fail closed
				_warn(HOOK, type(error).__name__)
				return
		for offered, path in self._families:
			wanted = [n for n in missing if n in offered]
			if not wanted:
				continue
			reason = self._call(path, wanted)
			self.asked.update(dict.fromkeys(wanted, reason))

	def _call(self, path: str, wanted: list[str]) -> str | None:
		"""One provider call for the whole batch. Returns a reason code; never raises."""
		try:
			import frappe

			handler = frappe.get_attr(path)
			limit = timeout_seconds()
			started = time.monotonic()
			answer = handler(list(self.members), list(wanted), {"flow_id": self.flow_id})
			if time.monotonic() - started > limit:
				_warn(path, "timeout")
				return FACTS_TIMEOUT  # a late answer is discarded
			if not isinstance(answer, dict):
				_warn(path, "invalid result")
				return FACTS_ERROR
			found = {}
			for member in self.members:
				given = answer.get(member)
				if given is None:
					continue
				if not isinstance(given, dict):
					_warn(path, "invalid result")
					return FACTS_ERROR
				found[member] = json.loads(json.dumps({n: given[n] for n in wanted if n in given}, allow_nan=False))
		except Exception as error:  # noqa: BLE001 - fail closed; the message may hold personal data
			_warn(path, type(error).__name__)
			return FACTS_ERROR
		for member, values in found.items():
			self.values[member].update(values)
		return None


@contextlib.contextmanager
def batch(flow_id: str, member_keys):
	"""Share facts between the lookups of these members until the block ends."""
	token = _current.set(_Batch(flow_id, member_keys))
	try:
		yield
	finally:
		_current.reset(token)


def lookup(flow_id: str, member_key: str | None, names: list[str]) -> tuple[dict | None, str | None]:
	"""``({fact: value}, None)`` with every name present, or ``(None, reason code)``."""
	if not member_key:
		return None, FACTS_ERROR
	current = _current.get()
	if current is None or not current.covers(flow_id, member_key):
		current = _Batch(flow_id, [member_key])
	return current.lookup(member_key, names)


def _warn(path: str, what: str) -> None:
	try:
		import frappe

		frappe.logger("flow").warning(f"flow facts provider {path}: {what}")
	except Exception:  # noqa: BLE001, S110 - logging must never turn a fallback into an error
		pass
