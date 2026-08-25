"""Tests for the ACP subprocess launcher."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from huf.ai.acp.exceptions import AcpLaunchError, AcpSecurityError, AcpTimeoutError
from huf.ai.acp.subprocess_guard import _MEMORY_COUNTER_BACKEND
from huf.ai.acp.subprocess_launcher import AcpSubprocessLauncher

_FAKE_ECHO_CODE = r"""
import sys
data = sys.stdin.read()
print(data, end="")
sys.stderr.write("err:" + data)
"""


@pytest.fixture
def launcher() -> AcpSubprocessLauncher:
	return AcpSubprocessLauncher(
		counter=AcpSubprocessCounterFixture(max_subprocesses=5),
		timeout=10.0,
	)


class AcpSubprocessCounterFixture:
	"""Test-only counter using the in-memory backend."""

	def __init__(self, max_subprocesses: int = 5) -> None:
		from huf.ai.acp.subprocess_guard import AcpSubprocessCounter

		self.counter = AcpSubprocessCounter(
			max_subprocesses=max_subprocesses,
			backend=_MEMORY_COUNTER_BACKEND(),
		)

	@property
	def max_subprocesses(self) -> int:
		return self.counter.max_subprocesses

	def acquire(self) -> None:
		self.counter.acquire()

	def release(self) -> None:
		self.counter.release()


class TestLauncherSpawnAndReap:
	async def _run_echo(self, launcher: AcpSubprocessLauncher, text: str) -> str:
		proc = await launcher.launch([sys.executable, "-c", _FAKE_ECHO_CODE])
		try:
			proc.stdin.write(text.encode("utf-8"))
			await proc.stdin.drain()
			proc.stdin.close()
			await proc.stdin.wait_closed()
			stdout = await proc.stdout.read()
			return stdout.decode("utf-8")
		finally:
			await launcher.reap(proc)

	def test_launch_and_reap_echo(self, launcher: AcpSubprocessLauncher) -> None:
		result = asyncio.run(self._run_echo(launcher, "hello"))
		assert result == "hello"

	def test_launch_validates_binary(self, launcher: AcpSubprocessLauncher) -> None:
		with pytest.raises(AcpSecurityError, match="not executable"):
			asyncio.run(launcher.launch(["/nonexistent/binary/for/acp"]))

	def test_launch_validates_command_shape(self, launcher: AcpSubprocessLauncher) -> None:
		with pytest.raises(AcpLaunchError, match="non-empty list"):
			asyncio.run(launcher.launch([]))

	def test_reap_is_idempotent(self, launcher: AcpSubprocessLauncher) -> None:
		async def _run() -> None:
			proc = await launcher.launch([sys.executable, "-c", "print('ok')"])
			await launcher.reap(proc)
			await launcher.reap(proc)

		asyncio.run(_run())


class TestLauncherRun:
	def test_run_communicates_and_reaps(self) -> None:
		launcher = AcpSubprocessLauncher(
			counter=AcpSubprocessCounterFixture(max_subprocesses=5),
			timeout=10.0,
		)
		returncode, stdout, stderr = asyncio.run(
			launcher.run([sys.executable, "-c", _FAKE_ECHO_CODE], timeout=5.0)
		)
		assert returncode == 0
		# communicate() feeds stdin then closes it; our echo script reads all input.
		assert stdout == b""
		assert stderr == b"err:"

	def test_run_times_out_slow_process(self) -> None:
		launcher = AcpSubprocessLauncher(
			counter=AcpSubprocessCounterFixture(max_subprocesses=5),
			timeout=10.0,
		)
		with pytest.raises(AcpTimeoutError, match="timeout"):
			asyncio.run(
				launcher.run(
					[sys.executable, "-c", "import time; time.sleep(30)"],
					timeout=0.5,
				)
			)

	def test_run_releases_counter_after_timeout(self) -> None:
		fixture = AcpSubprocessCounterFixture(max_subprocesses=1)
		launcher = AcpSubprocessLauncher(counter=fixture, timeout=10.0)
		with pytest.raises(AcpTimeoutError):
			asyncio.run(
				launcher.run(
					[sys.executable, "-c", "import time; time.sleep(30)"],
					timeout=0.5,
				)
			)
		assert fixture.counter.current() == 0


class TestLauncherCounter:
	def test_launch_acquires_and_reap_releases(self) -> None:
		fixture = AcpSubprocessCounterFixture(max_subprocesses=2)
		launcher = AcpSubprocessLauncher(counter=fixture, timeout=10.0)

		async def _run() -> None:
			proc1 = await launcher.launch([sys.executable, "-c", "print(1)"])
			assert fixture.counter.current() == 1
			await launcher.reap(proc1)
			assert fixture.counter.current() == 0

		asyncio.run(_run())

	def test_failed_launch_releases_counter(self) -> None:
		fixture = AcpSubprocessCounterFixture(max_subprocesses=2)
		launcher = AcpSubprocessLauncher(counter=fixture, timeout=10.0)

		with pytest.raises(AcpSecurityError):
			asyncio.run(launcher.launch(["/nonexistent"]))

		assert fixture.counter.current() == 0
