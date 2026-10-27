"""Resolve backend adapters declared by installed applications only."""

from __future__ import annotations

import importlib
from typing import Any

from huf.ai.decision.errors import DecisionError, DecisionErrorCode

BUILTIN_BACKENDS = {"fake": "huf.ai.decision.backends.fake.FakeDecisionBackend"}


def discover_backends() -> dict[str, str]:
	"""Collect stable adapter IDs from built-ins and installed-app hook declarations."""
	registered = dict(BUILTIN_BACKENDS)
	try:
		import frappe

		installed_apps = frappe.get_installed_apps()
	except (ImportError, AttributeError):
		return registered
	for app in installed_apps:
		entries = frappe.get_hooks("huf_decision_backends", app_name=app) or {}
		if isinstance(entries, dict):
			items = entries.items()
		elif isinstance(entries, list):
			items = [pair for entry in entries if isinstance(entry, dict) for pair in entry.items()]
		else:
			continue
		for adapter_id, declared in items:
			paths = [declared] if isinstance(declared, str) else declared
			if not paths or not isinstance(paths[0], str) or not adapter_id:
				continue
			# Built-ins are intentionally not replaceable by installed apps.
			registered.setdefault(str(adapter_id), paths[0])
	return registered


def resolve_backend(adapter_id: str, *, registry: dict[str, str] | None = None) -> Any:
	"""Instantiate an adapter by ID from the installed-app registry.

	The import path is accepted only after resolving it from the hook registry; no
	caller or database value is ever imported directly.
	"""
	path = (registry if registry is not None else discover_backends()).get(adapter_id)
	if not path:
		raise DecisionError(DecisionErrorCode.BACKEND_NOT_REGISTERED)
	try:
		module_path, attribute = path.rsplit(".", 1)
		backend_class = getattr(importlib.import_module(module_path), attribute)
		instance = backend_class()
	except Exception as exc:
		raise DecisionError(DecisionErrorCode.BACKEND_NOT_REGISTERED, "Registered decision backend could not be loaded") from exc
	if not callable(getattr(instance, "evaluate", None)) or not callable(getattr(instance, "capabilities", None)):
		raise DecisionError(DecisionErrorCode.BACKEND_NOT_REGISTERED, "Registered backend does not implement the contract")
	return instance
