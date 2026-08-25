"""Per-connection keyed pool for ACP subprocess sessions.

V1 uses a keyed semaphore rather than a pool of warm processes: each connection
has a bounded number of concurrent session slots (``max_concurrent_sessions``).
Sessions are torn down after each call; the semaphore simply prevents a
connection storm when many agents fan out to the same external ACP target.

This module is intentionally free of Frappe imports.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, ClassVar

from .exceptions import AcpCapacityError

LOGGER = logging.getLogger("huf.ai.acp.pool")

#: Default concurrent-session limit per connection.
DEFAULT_MAX_CONCURRENT_SESSIONS = 3

#: Maximum value allowed for ``max_concurrent_sessions``.
MAX_ALLOWED_SESSIONS = 50

#: Default timeout (seconds) to wait for a pool slot before failing.
DEFAULT_SLOT_TIMEOUT_SECONDS = 30.0


class _ConnectionSlot:
	"""Token held while a caller owns a slot in a connection pool."""

	def __init__(self, pool: AcpConnectionPool) -> None:
		self._pool = pool
		self._released = False

	def release(self) -> None:
		if not self._released:
			self._pool._release()
			self._released = True


class AcpConnectionPool:
	"""Keyed semaphore limiting concurrent ACP sessions per connection."""

	_pools: ClassVar[dict[str, AcpConnectionPool]] = {}
	_lock: ClassVar[asyncio.Lock] = asyncio.Lock()

	def __init__(self, connection_name: str, max_concurrent_sessions: int) -> None:
		self.connection_name = connection_name
		self.max_concurrent_sessions = max(1, min(int(max_concurrent_sessions), MAX_ALLOWED_SESSIONS))
		self._semaphore = asyncio.Semaphore(self.max_concurrent_sessions)
		self._active = 0

	# -------------------------------------------------------------------------
	# Factory / registry
	# -------------------------------------------------------------------------
	@classmethod
	async def for_connection(
		cls,
		connection_name: str,
		max_concurrent_sessions: int = DEFAULT_MAX_CONCURRENT_SESSIONS,
		max_sessions: int | None = None,
	) -> AcpConnectionPool:
		# ``max_sessions`` is an older alias kept for backwards compatibility with
		# early unit tests; ``max_concurrent_sessions`` takes precedence.
		if max_sessions is not None and max_concurrent_sessions == DEFAULT_MAX_CONCURRENT_SESSIONS:
			max_concurrent_sessions = max_sessions
		"""Get or create the pool for ``connection_name``."""
		if connection_name in cls._pools:
			pool = cls._pools[connection_name]
			# Update the limit if it grew; shrinking an active semaphore is unsafe.
			new_limit = max(1, min(int(max_concurrent_sessions), MAX_ALLOWED_SESSIONS))
			if new_limit > pool.max_concurrent_sessions:
				pool.max_concurrent_sessions = new_limit
				pool._semaphore = asyncio.Semaphore(new_limit)
			return pool

		async with cls._lock:
			if connection_name not in cls._pools:
				cls._pools[connection_name] = cls(connection_name, max_concurrent_sessions)
			return cls._pools[connection_name]

	@classmethod
	def get_pool(cls, connection_name: str) -> AcpConnectionPool | None:
		"""Return an existing pool or ``None``."""
		return cls._pools.get(connection_name)

	@classmethod
	def reset(cls) -> None:
		"""Drop all pools. Intended for tests."""
		cls._pools.clear()

	# -------------------------------------------------------------------------
	# Slot management
	# -------------------------------------------------------------------------
	async def acquire(
		self,
		*,
		timeout: float = DEFAULT_SLOT_TIMEOUT_SECONDS,
	) -> _ConnectionSlot:
		"""Acquire a session slot, raising AcpCapacityError on timeout."""
		try:
			await asyncio.wait_for(self._semaphore.acquire(), timeout=timeout)
		except asyncio.TimeoutError as exc:
			raise AcpCapacityError(
				f"Connection '{self.connection_name}' has no free ACP session slot "
				f"(limit={self.max_concurrent_sessions}); wait for an existing session to finish."
			) from exc
		self._active += 1
		LOGGER.debug(
			"Acquired ACP session slot for %s (%d/%d active)",
			self.connection_name,
			self._active,
			self.max_concurrent_sessions,
		)
		return _ConnectionSlot(self)

	def _release(self) -> None:
		"""Release a previously acquired slot."""
		self._active = max(0, self._active - 1)
		try:
			self._semaphore.release()
		except ValueError:
			# Semaphore over-release; ignore to keep the pool healthy.
			pass
		LOGGER.debug(
			"Released ACP session slot for %s (%d/%d active)",
			self.connection_name,
			self._active,
			self.max_concurrent_sessions,
		)

	@property
	def active(self) -> int:
		return self._active

	@property
	def available(self) -> int:
		"""Approximate number of free slots."""
		return max(0, self.max_concurrent_sessions - self._active)


async def acquire_connection_slot(
	connection_name: str,
	*,
	max_concurrent_sessions: int = DEFAULT_MAX_CONCURRENT_SESSIONS,
	timeout: float = DEFAULT_SLOT_TIMEOUT_SECONDS,
) -> _ConnectionSlot:
	"""Convenience helper to acquire a slot for ``connection_name``."""
	pool = await AcpConnectionPool.for_connection(connection_name, max_concurrent_sessions)
	return await pool.acquire(timeout=timeout)
