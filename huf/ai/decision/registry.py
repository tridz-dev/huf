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


def resolve_backend(adapter_id: str, *, registry: dict[str, str] | None = None, deployment: Any = None, transport: Any = None) -> Any:
	"""Instantiate an adapter by ID from the installed-app registry.

	The import path is accepted only after resolving it from the hook registry; no
	caller or database value is ever imported directly.

	Args:
		adapter_id: The registered stable adapter ID (e.g., "fake", "jev_system_one").
		registry: Optional dict mapping adapter IDs to import paths. If None, uses discover_backends().
		deployment: Optional DeploymentSpec for backends that support deployment-driven instantiation.
			If provided and the backend class defines from_deployment, it will be called instead
			of the zero-argument constructor.
		transport: Optional callable or transport object to pass to from_deployment. Ignored if
			deployment is None or the backend does not define from_deployment.

	Returns:
		An instantiated backend object.

	Raises:
		DecisionError: If the adapter is not registered, cannot be loaded, or does not
			implement the required backend contract.
	"""
	path = (registry if registry is not None else discover_backends()).get(adapter_id)
	if not path:
		raise DecisionError(DecisionErrorCode.BACKEND_NOT_REGISTERED)
	try:
		module_path, attribute = path.rsplit(".", 1)
		backend_class = getattr(importlib.import_module(module_path), attribute)
		# Call from_deployment if deployment is provided and the class defines it
		if deployment is not None and hasattr(backend_class, "from_deployment"):
			instance = backend_class.from_deployment(deployment, transport)
		else:
			instance = backend_class()
	except Exception as exc:
		raise DecisionError(DecisionErrorCode.BACKEND_NOT_REGISTERED, "Registered decision backend could not be loaded") from exc
	if not callable(getattr(instance, "evaluate", None)) or not callable(getattr(instance, "capabilities", None)):
		raise DecisionError(DecisionErrorCode.BACKEND_NOT_REGISTERED, "Registered backend does not implement the contract")
	return instance
