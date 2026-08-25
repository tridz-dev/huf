"""Subprocess security guard for ACP stdio spawns.

Provides:

- environment/cwd/fd scrubbing
- validation of the working directory
- a Redis-backed site-wide subprocess ceiling

This module imports ``frappe`` lazily so it remains usable by the standalone
``huf-acp`` CLI and by unit tests without a bench.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from typing import Any, Protocol

from .exceptions import AcpCapacityError, AcpSecurityError

LOGGER = logging.getLogger("huf.ai.acp.subprocess_guard")

#: Default site-wide maximum concurrent ACP subprocesses.
DEFAULT_MAX_SUBPROCESSES = 20

#: Default TTL (seconds) for the Redis subprocess-count key. A short TTL keeps
#: the counter from leaking when a worker crashes, but it must be longer than
#: the typical subprocess lifetime so active sessions are not double-counted.
DEFAULT_COUNTER_TTL_SECONDS = 60

#: Default per-subprocess stdout/stderr capture cap (bytes).
DEFAULT_MAX_OUTPUT_BYTES = 10 * 1024 * 1024

#: Default hard cap on per-session wall-clock time (seconds).
DEFAULT_MAX_WALL_TIME_SECONDS = 600

#: Environment-variable name fragments (case-insensitive) that are never passed
#: to an ACP child process. This list is intentionally conservative: if a var
#: might carry a secret, influence dynamic linking, or expose Frappe internals,
#: it is denied by default.
ENV_DENY_LIST_FRAGMENTS: frozenset[str] = frozenset(
	{
		"SECRET",
		"TOKEN",
		"PASSWORD",
		"PRIVATE_KEY",
		"API_KEY",
		"LD_PRELOAD",
		"LD_LIBRARY_PATH",
		"DYLD_INSERT_LIBRARIES",
		"NODE_OPTIONS",
		"PYTHONPATH",
		"FRAPPE_",
		"DB_PASSWORD",
		"REDIS_",
		"DATABASE_URL",
	}
)

#: Exact environment-variable names that are denied even if they do not match a
#: fragment above.
ENV_DENY_LIST_EXACT: frozenset[str] = frozenset(
	{
		"LD_PRELOAD",
		"LD_LIBRARY_PATH",
		"DYLD_INSERT_LIBRARIES",
		"DYLD_LIBRARY_PATH",
		"NODE_OPTIONS",
		"PYTHONPATH",
		"FRAPPE_BENCH_DIR",
	}
)

#: Math-library thread limits to prevent subprocess thread storms.
THREAD_LIMIT_ENV: dict[str, str] = {
	"OPENBLAS_NUM_THREADS": "1",
	"OMP_NUM_THREADS": "1",
	"MKL_NUM_THREADS": "1",
	"VECLIB_MAXIMUM_THREADS": "1",
	"NUMEXPR_NUM_THREADS": "1",
}

#: File/path fragments that a working directory must not contain.
FORBIDDEN_CWD_FRAGMENTS: frozenset[str] = frozenset(
	{
		"sites/common_config.json",
		"site_config.json",
		"MariaDB",
		"redis",
	}
)


class _CounterBackend(Protocol):
	"""Minimal backend protocol for the subprocess ceiling counter."""

	def incr(self, key: str) -> int: ...
	def decr(self, key: str) -> int: ...
	def expire(self, key: str, seconds: int) -> None: ...
	def delete(self, key: str) -> None: ...
	def get(self, key: str) -> int | None: ...


class _MemoryCounterBackend:
	"""In-memory counter backend for tests and standalone use."""

	def __init__(self) -> None:
		self._data: dict[str, int] = {}
		self._lock = threading.Lock()

	def incr(self, key: str) -> int:
		with self._lock:
			self._data[key] = self._data.get(key, 0) + 1
			return self._data[key]

	def decr(self, key: str) -> int:
		with self._lock:
			value = max(0, self._data.get(key, 0) - 1)
			self._data[key] = value
			return value

	def expire(self, key: str, seconds: int) -> None:
		pass

	def delete(self, key: str) -> None:
		with self._lock:
			self._data.pop(key, None)

	def get(self, key: str) -> int | None:
		with self._lock:
			return self._data.get(key)


class AcpSubprocessCounter:
	"""Site-wide ceiling on concurrent ACP subprocesses.

	The counter is keyed by Frappe site name so multi-tenant workers do not share
	a single limit. It uses Redis by default (via ``frappe.cache()``) and falls
	back to an in-memory backend when Redis is unavailable.
	"""

	def __init__(
		self,
		max_subprocesses: int = DEFAULT_MAX_SUBPROCESSES,
		ttl_seconds: int = DEFAULT_COUNTER_TTL_SECONDS,
		backend: _CounterBackend | None = None,
	) -> None:
		self.max_subprocesses = max(1, int(max_subprocesses))
		self.ttl_seconds = max(1, int(ttl_seconds))
		self._backend = backend
		self._key: str | None = None

	@property
	def backend(self) -> _CounterBackend:
		if self._backend is None:
			self._backend = _resolve_counter_backend()
		return self._backend

	def _make_key(self) -> str:
		import frappe

		local = getattr(frappe, "local", None)
		site = getattr(local, "site", None) if local is not None else None
		site = site or os.environ.get("FRAPPE_SITE") or "localhost"
		return f"huf:acp:subprocess_count:{site}"

	def acquire(self) -> None:
		"""Increment the counter; raise AcpCapacityError if the ceiling is reached."""
		key = self._make_key()
		count = self.backend.incr(key)
		try:
			self.backend.expire(key, self.ttl_seconds)
		except Exception as exc:  # noqa: BLE001
			LOGGER.debug("Could not set expiry on subprocess counter: %s", exc)

		if count > self.max_subprocesses:
			self.backend.decr(key)
			raise AcpCapacityError(
				f"Site-wide ACP subprocess ceiling reached ({self.max_subprocesses}). "
				f"Wait for an existing session to finish before launching another."
			)
		self._key = key

	def release(self) -> None:
		"""Decrement the counter and clean up the key if it reaches zero."""
		key = self._key or self._make_key()
		try:
			count = self.backend.decr(key)
			if count <= 0:
				self.backend.delete(key)
		except Exception as exc:  # noqa: BLE001
			LOGGER.debug("Failed to release subprocess counter: %s", exc)
		finally:
			self._key = None

	def current(self) -> int:
		"""Return the current counter value (best-effort)."""
		key = self._make_key()
		value = self.backend.get(key)
		return int(value or 0)


def _resolve_counter_backend() -> _CounterBackend:
	"""Return a Redis-backed backend if frappe.cache() is available, else memory."""
	try:
		import frappe

		cache = frappe.cache()
		# Sanity-check that the cache looks like a Redis-backed object.
		if hasattr(cache, "incr") and hasattr(cache, "decr"):
			return cache  # type: ignore[return-value]
	except Exception as exc:  # noqa: BLE001
		LOGGER.debug("frappe.cache() unavailable for subprocess ceiling: %s", exc)
	return _MemoryCounterBackend()


def scrub_environment(env: dict[str, str] | None) -> dict[str, str]:
	"""Return a scrubbed environment dict safe for an ACP subprocess.

	Removes any key that matches a deny-list fragment or exact name. Then pins
	math-library thread limits. The input is never modified in place.
	"""
	scrubbed: dict[str, str] = {}
	for key, value in (env or {}).items():
		if not isinstance(key, str):
			continue
		if key in ENV_DENY_LIST_EXACT:
			continue
		upper = key.upper()
		# Auth-injection keys under the HUF_ACP_ namespace are explicitly allowed.
		if upper.startswith("HUF_ACP_"):
			scrubbed[key] = str(value)
			continue
		if any(fragment in upper for fragment in ENV_DENY_LIST_FRAGMENTS):
			continue
		scrubbed[key] = str(value)

	for key, value in THREAD_LIMIT_ENV.items():
		scrubbed.setdefault(key, value)

	return scrubbed


def validate_working_directory(cwd: str) -> None:
	"""Validate that ``cwd`` is safe to use as an ACP subprocess working directory.

	Raises ``AcpSecurityError`` if the path is relative, does not exist, is not a
	directory, or overlaps with Frappe/MariaDB/Redis runtime paths.
	"""
	if not cwd:
		raise AcpSecurityError("working_directory is required")
	if not os.path.isabs(cwd):
		raise AcpSecurityError(f"working_directory must be absolute: {cwd!r}")

	real_cwd = os.path.realpath(cwd)
	if not os.path.isdir(real_cwd):
		raise AcpSecurityError(f"working_directory does not exist or is not a directory: {cwd!r}")

	# Ensure the directory is writable. Some platforms allow listing without write.
	if not os.access(real_cwd, os.W_OK):
		raise AcpSecurityError(f"working_directory is not writable: {cwd!r}")

	for fragment in FORBIDDEN_CWD_FRAGMENTS:
		if fragment in real_cwd:
			raise AcpSecurityError(
				f"working_directory must not contain {fragment!r}: {cwd!r}"
			)

	# Reject the Frappe site directory and bench root by looking for sentinel files.
	for sentinel in ("sites/common_config.json", "site_config.json"):
		if os.path.exists(os.path.join(real_cwd, sentinel)) or sentinel in real_cwd:
			raise AcpSecurityError(
				f"working_directory must not be a Frappe site/bench directory: {cwd!r}"
			)


#: Valid env-var name pattern: uppercase + digits + underscore, no leading digit.
_VALID_ENV_KEY_PATTERN = re.compile(r"^[A-Z_][A-Z0-9_]*$")


def validate_env_key(key: str) -> None:
	"""Validate that ``key`` is a safe environment-variable name."""
	if not isinstance(key, str) or not key:
		raise AcpSecurityError("Environment variable name must be a non-empty string")
	if not _VALID_ENV_KEY_PATTERN.match(key):
		raise AcpSecurityError(f"Environment variable name is invalid: {key!r}")
	upper = key.upper()
	if upper.startswith("HUF_ACP_"):
		return
	if any(fragment in upper for fragment in ENV_DENY_LIST_FRAGMENTS):
		raise AcpSecurityError(f"Environment variable name is deny-listed: {key!r}")


def get_site_config_int(key: str, default: int) -> int:
	"""Read an integer site config value, falling back to ``default``."""
	try:
		import frappe

		value = frappe.local.conf.get(key) if hasattr(frappe.local, "conf") else None
		if value is None:
			value = os.environ.get(key.upper())
		if value is not None:
			return int(value)
	except Exception as exc:  # noqa: BLE001
		LOGGER.debug("Could not read site config %s: %s", key, exc)
	return default


def make_default_counter() -> AcpSubprocessCounter:
	"""Build a counter using site-configured limits (or defaults)."""
	max_subprocesses = get_site_config_int("huf_acp_max_subprocesses", DEFAULT_MAX_SUBPROCESSES)
	ttl_seconds = get_site_config_int("huf_acp_counter_ttl_seconds", DEFAULT_COUNTER_TTL_SECONDS)
	return AcpSubprocessCounter(max_subprocesses=max_subprocesses, ttl_seconds=ttl_seconds)


# Backwards-compatible alias used by early unit tests.
_MEMORY_COUNTER_BACKEND = _MemoryCounterBackend
