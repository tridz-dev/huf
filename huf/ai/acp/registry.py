"""Runtime loader for ``ACP Command Registry`` records.

Builds a sanitized argv/env/cwd launch context from a registry entry. The
registry entry is the admin-curated, role-gated allow-list that replaces a
free-text ``launch_command`` on ``Remote Agent Connection``.

This module imports ``frappe`` lazily so it remains testable without a bench.
"""

from __future__ import annotations

import json
import os
import shutil
from typing import Any

from .exceptions import AcpLaunchError, AcpSecurityError
from .subprocess_guard import (
	ENV_DENY_LIST_FRAGMENTS,
	THREAD_LIMIT_ENV,
	scrub_environment,
	validate_working_directory,
)


def build_launch_context(registry_name: str, auth_secret: str | None = None) -> dict[str, Any]:
	"""Load an ``ACP Command Registry`` record and build a sanitized launch context.

	Returns a dict with keys:

		- ``cmd``: list[str] -- absolute binary path followed by fixed argv shape
		- ``cwd``: str -- fixed working directory
		- ``env``: dict[str, str] -- minimal, scrubbed environment
		- ``auth_env_key``: str | None -- env key under which auth_secret is injected
		- ``max_wall_time_seconds``: int -- per-session wall-clock timeout

	Raises ``AcpLaunchError`` if the registry entry is missing or disabled, and
	``AcpSecurityError`` if the recorded configuration violates the launch contract.
	"""
	import frappe

	try:
		registry = frappe.get_doc("ACP Command Registry", registry_name)
	except frappe.DoesNotExistError as exc:
		raise AcpLaunchError(f"ACP Command Registry '{registry_name}' not found") from exc

	if not getattr(registry, "enabled", 1):
		raise AcpLaunchError(f"ACP Command Registry '{registry_name}' is disabled")

	binary_path = str(registry.binary_path or "").strip()
	argv_shape = registry.argv_shape or []
	working_directory = str(registry.working_directory or "").strip()
	auth_required = bool(getattr(registry, "auth_required", 0))
	auth_env_key = str(getattr(registry, "auth_env_key", None) or "").strip()
	max_wall_time_seconds = int(getattr(registry, "max_wall_time_seconds", 300) or 300)

	_validate_binary_path(binary_path)
	_validate_argv_shape(argv_shape)

	cmd = [binary_path, *_normalize_argv(argv_shape)]

	if auth_required and not auth_secret:
		raise AcpSecurityError(
			f"ACP Command Registry '{registry_name}' requires auth_secret but none was supplied"
		)

	# If no auth_env_key is configured but a secret is supplied, use the default key.
	if auth_secret and not auth_env_key:
		auth_env_key = "HUF_ACP_TARGET_TOKEN"

	env = _build_env(registry, auth_secret, auth_env_key)
	env = scrub_environment(env)

	if working_directory:
		validate_working_directory(working_directory)
	else:
		# If the registry entry does not fix a cwd, fall back to a sandbox-scoped
		# temp directory. This should not happen for well-formed entries, but it
		# keeps the launcher safe if one is misconfigured.
		working_directory = _default_sandbox_dir(registry_name)
		os.makedirs(working_directory, exist_ok=True)

	return {
		"cmd": cmd,
		"cwd": working_directory,
		"env": env,
		"auth_env_key": auth_env_key or None,
		"max_wall_time_seconds": max_wall_time_seconds,
	}


def _validate_binary_path(binary_path: str) -> None:
	"""Require an absolute, executable path (or a discoverable absolute path)."""
	if not binary_path:
		raise AcpSecurityError("ACP Command Registry binary_path is required")
	if not os.path.isabs(binary_path):
		raise AcpSecurityError(f"ACP Command Registry binary_path must be absolute: {binary_path!r}")
	resolved = shutil.which(binary_path) or binary_path
	if not os.path.isfile(resolved) or not os.access(resolved, os.X_OK):
		raise AcpSecurityError(f"ACP Command Registry binary_path is not executable: {binary_path!r}")


def _validate_argv_shape(argv_shape: Any) -> None:
	"""Require a JSON list of strings."""
	if argv_shape is None:
		return
	if isinstance(argv_shape, str):
		try:
			argv_shape = json.loads(argv_shape)
		except json.JSONDecodeError as exc:
			raise AcpSecurityError(f"ACP Command Registry argv_shape is not valid JSON: {exc}") from exc
	if not isinstance(argv_shape, list):
		raise AcpSecurityError("ACP Command Registry argv_shape must be a JSON list")
	for idx, item in enumerate(argv_shape):
		if not isinstance(item, str):
			raise AcpSecurityError(
				f"ACP Command Registry argv_shape item at index {idx} must be a string, got {type(item).__name__}"
			)


def _normalize_argv(argv_shape: Any) -> list[str]:
	"""Return a list of strings from the stored argv_shape."""
	if argv_shape is None:
		return []
	if isinstance(argv_shape, str):
		parsed = json.loads(argv_shape)
		if not isinstance(parsed, list):
			raise AcpSecurityError("ACP Command Registry argv_shape must be a JSON list")
		return [str(item) for item in parsed]
	return [str(item) for item in argv_shape]


def _build_env(registry: Any, auth_secret: str | None, auth_env_key: str | None) -> dict[str, str]:
	"""Construct a minimal env from the registry entry's allow list.

	Never inherits the worker's full environment. Fixed values override values
	taken from the worker's env. Auth secret is injected under the registry's
	fixed auth_env_key.
	"""
	env: dict[str, str] = {}

	allow_list = getattr(registry, "env_allow_list", []) or []
	for row in allow_list:
		variable_name = str(getattr(row, "variable_name", "") or "").strip()
		fixed_value = getattr(row, "fixed_value", None)
		if not variable_name:
			continue
		if fixed_value is not None:
			env[variable_name] = str(fixed_value)
		elif variable_name in os.environ:
			# Only pass through explicitly allowed vars that exist in the worker.
			# This is still gated by the deny-list scrub below.
			env[variable_name] = os.environ[variable_name]

	# Inject auth secret under the registry-defined key (or the default).
	if auth_secret:
		key = auth_env_key or "HUF_ACP_TARGET_TOKEN"
		if not key.upper().startswith("HUF_ACP_") and any(fragment in key.upper() for fragment in ENV_DENY_LIST_FRAGMENTS):
			raise AcpSecurityError(f"auth_env_key collides with deny-list: {key!r}")
		env[key] = auth_secret

	# Pin math-library thread counts to prevent thread storms.
	for key, value in THREAD_LIMIT_ENV.items():
		env.setdefault(key, value)

	return env


def _default_sandbox_dir(registry_name: str) -> str:
	"""Return a per-registry fallback sandbox directory."""
	base = os.environ.get("HUF_ACP_SANDBOX_BASE", "/opt/huf/acp-sandboxes")
	return os.path.join(base, registry_name)
