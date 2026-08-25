"""Tests for the ACP per-connection pool (keyed semaphore)."""

from __future__ import annotations

import asyncio

import pytest

from huf.ai.acp.exceptions import AcpCapacityError
from huf.ai.acp.pool import AcpConnectionPool


class TestAcpConnectionPool:
	async def _acquire_slot(self, name: str, max_sessions: int = 2, timeout: float = 0.1):
		pool = await AcpConnectionPool.for_connection(name, max_sessions)
		return await pool.acquire(timeout=timeout)

	@pytest.fixture(autouse=True)
	def _reset_pools(self) -> None:
		AcpConnectionPool.reset()
		yield
		AcpConnectionPool.reset()

	def test_single_connection_limited(self) -> None:
		async def _run() -> None:
			slot1 = await self._acquire_slot("conn-a", max_sessions=1)
			assert AcpConnectionPool.get_pool("conn-a").active == 1
			assert AcpConnectionPool.get_pool("conn-a").available == 0

			# Second acquire should time out because the pool only has one slot.
			with pytest.raises(AcpCapacityError, match="no free ACP session slot"):
				await self._acquire_slot("conn-a", max_sessions=1, timeout=0.05)

			slot1.release()
			assert AcpConnectionPool.get_pool("conn-a").active == 0

		asyncio.run(_run())

	def test_separate_connections_have_independent_limits(self) -> None:
		async def _run() -> None:
			slot_a = await self._acquire_slot("conn-a", max_sessions=1)
			slot_b = await self._acquire_slot("conn-b", max_sessions=1)
			assert AcpConnectionPool.get_pool("conn-a").active == 1
			assert AcpConnectionPool.get_pool("conn-b").active == 1
			slot_a.release()
			slot_b.release()

		asyncio.run(_run())

	def test_slot_release_is_idempotent(self) -> None:
		async def _run() -> None:
			slot = await self._acquire_slot("conn-a", max_sessions=1)
			slot.release()
			slot.release()
			assert AcpConnectionPool.get_pool("conn-a").active == 0

		asyncio.run(_run())

	def test_pool_factory_returns_same_instance(self) -> None:
		async def _run() -> None:
			pool1 = await AcpConnectionPool.for_connection("conn-a", max_sessions=2)
			pool2 = await AcpConnectionPool.for_connection("conn-a", max_sessions=2)
			assert pool1 is pool2

		asyncio.run(_run())

	def test_pool_limits_capped_at_max_allowed(self) -> None:
		async def _run() -> None:
			pool = await AcpConnectionPool.for_connection("conn-a", max_sessions=1000)
			assert pool.max_concurrent_sessions == 50

		asyncio.run(_run())
