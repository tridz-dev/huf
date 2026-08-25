"""ACP subprocess launcher: spawn, timeout, kill, and cleanup.

This module wraps ``asyncio.create_subprocess_exec`` with the security contract
from ``subprocess_guard``:

- site-wide subprocess ceiling via :class:`AcpSubprocessCounter`
- stdin/stdout/stderr pipe wiring only (no extra file descriptors)
- guaranteed terminate -> kill -> reap on cleanup

It is intentionally free of Frappe imports except when reading site config.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from typing import Any

from .exceptions import AcpLaunchError, AcpSecurityError, AcpTimeoutError
from .subprocess_guard import (
	DEFAULT_MAX_OUTPUT_BYTES,
	DEFAULT_MAX_WALL_TIME_SECONDS,
	AcpSubprocessCounter,
	make_default_counter,
	scrub_environment,
	validate_working_directory,
)

LOGGER = logging.getLogger("huf.ai.acp.subprocess_launcher")

#: Grace period after SIGTERM before SIGKILL.
TERMINATE_GRACE_SECONDS = 5.0


class AcpSubprocessLauncher:
	"""Launch and reap one ACP subprocess under the site-wide security guard."""

	def __init__(
		self,
		*,
		counter: AcpSubprocessCounter | None = None,
		timeout: float = DEFAULT_MAX_WALL_TIME_SECONDS,
		max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
	) -> None:
		self.counter = counter or make_default_counter()
		self.timeout = float(timeout)
		self.max_output_bytes = int(max_output_bytes)
		self._acquired = False

	async def launch(
		self,
		cmd: list[str],
		*,
		cwd: str | None = None,
		env: dict[str, str] | None = None,
	) -> asyncio.subprocess.Process:
		"""Acquire the ceiling and spawn the subprocess.

		Raises ``AcpLaunchError`` if the command is malformed or the ceiling is
		reached. Raises ``AcpSecurityError`` if the cwd/env fail validation.
		"""
		self._validate_command(cmd)

		if cwd is not None:
			validate_working_directory(cwd)
		else:
			cwd = os.getcwd()

		scrubbed_env = scrub_environment(env)

		# Acquire the site-wide ceiling before spawning.
		try:
			self.counter.acquire()
			self._acquired = True
		except Exception as exc:
			if not isinstance(exc, AcpLaunchError):
				raise AcpLaunchError(f"Failed to acquire subprocess slot: {exc}") from exc
			raise

		try:
			LOGGER.debug("Launching ACP subprocess: %s (cwd=%s)", cmd, cwd)
			proc = await asyncio.create_subprocess_exec(
				*cmd,
				stdin=asyncio.subprocess.PIPE,
				stdout=asyncio.subprocess.PIPE,
				stderr=asyncio.subprocess.PIPE,
				cwd=cwd,
				env=scrubbed_env,
				# Only stdio fds are wired; close_fds defaults to True on Python 3.10+.
			)
		except Exception as exc:
			self._release_counter()
			raise AcpLaunchError(f"Failed to spawn ACP subprocess {cmd!r}: {exc}") from exc

		return proc

	async def reap(
		self,
		proc: asyncio.subprocess.Process,
		*,
		timeout: float | None = None,
	) -> None:
		"""Terminate/kill and wait for the subprocess, then release the ceiling.

		This method is idempotent: if ``proc`` has already exited, only the
		ceiling is released.
		"""
		try:
			if proc.returncode is None:
				await self._terminate_and_wait(proc, timeout=timeout)
			else:
				# Already exited; just wait() to reap the zombie.
				try:
					await asyncio.wait_for(proc.wait(), timeout=5.0)
				except asyncio.TimeoutError:
					LOGGER.warning("ACP subprocess wait() timed out after exit; forcing kill")
					try:
						proc.kill()
					except ProcessLookupError:
						pass
		finally:
			self._release_counter()

	async def run(
		self,
		cmd: list[str],
		*,
		cwd: str | None = None,
		env: dict[str, str] | None = None,
		timeout: float | None = None,
	) -> tuple[int | None, bytes, bytes]:
		"""One-shot helper: launch, communicate with timeout, reap, return result.

		Raises ``AcpTimeoutError`` if the subprocess does not finish within the
		specified timeout.
		"""
		proc = await self.launch(cmd, cwd=cwd, env=env)
		try:
			stdout, stderr = await self._communicate_with_timeout(
				proc, timeout=timeout or self.timeout
			)
		finally:
			await self.reap(proc)
		return proc.returncode, stdout, stderr

	async def _terminate_and_wait(
		self,
		proc: asyncio.subprocess.Process,
		*,
		timeout: float | None = None,
	) -> None:
		"""Send SIGTERM, wait, then SIGKILL if necessary."""
		try:
			proc.terminate()
			await asyncio.wait_for(proc.wait(), timeout=TERMINATE_GRACE_SECONDS)
		except ProcessLookupError:
			return
		except asyncio.TimeoutError:
			LOGGER.warning("ACP subprocess did not terminate; killing")
		else:
			return

		try:
			proc.kill()
			await asyncio.wait_for(
				proc.wait(),
				timeout=timeout if timeout is not None else TERMINATE_GRACE_SECONDS,
			)
		except ProcessLookupError:
			return
		except asyncio.TimeoutError:
			LOGGER.exception("ACP subprocess did not exit even after kill")

	async def _communicate_with_timeout(
		self,
		proc: asyncio.subprocess.Process,
		*,
		timeout: float,
	) -> tuple[bytes, bytes]:
		"""communicate() with a hard wall-clock timeout and guaranteed kill."""
		try:
			return await asyncio.wait_for(
				proc.communicate(),
				timeout=timeout,
			)
		except asyncio.TimeoutError as exc:
			await self._terminate_and_wait(proc, timeout=TERMINATE_GRACE_SECONDS)
			raise AcpTimeoutError(
				f"ACP subprocess exceeded wall-clock timeout of {timeout}s"
			) from exc

	def _validate_command(self, cmd: list[str]) -> None:
		if not isinstance(cmd, list) or not cmd:
			raise AcpLaunchError("ACP subprocess command must be a non-empty list")
		for idx, item in enumerate(cmd):
			if not isinstance(item, str):
				raise AcpLaunchError(
					f"ACP subprocess command item at index {idx} must be a string"
				)
		binary = shutil.which(cmd[0]) or cmd[0]
		if not os.path.isfile(binary) or not os.access(binary, os.X_OK):
			raise AcpSecurityError(f"ACP subprocess binary is not executable: {cmd[0]!r}")

	def _release_counter(self) -> None:
		if self._acquired:
			self.counter.release()
			self._acquired = False


async def launch_acp_subprocess(
	cmd: list[str],
	*,
	cwd: str | None = None,
	env: dict[str, str] | None = None,
	counter: AcpSubprocessCounter | None = None,
) -> asyncio.subprocess.Process:
	"""Convenience helper: acquire ceiling and spawn.

	The caller is responsible for reaping the process with
	:class:`AcpSubprocessLauncher`.
	"""
	launcher = AcpSubprocessLauncher(counter=counter)
	return await launcher.launch(cmd, cwd=cwd, env=env)


async def run_acp_subprocess(
	cmd: list[str],
	*,
	cwd: str | None = None,
	env: dict[str, str] | None = None,
	timeout: float = DEFAULT_MAX_WALL_TIME_SECONDS,
	counter: AcpSubprocessCounter | None = None,
) -> tuple[int | None, bytes, bytes]:
	"""Convenience one-shot helper: launch, communicate, reap."""
	launcher = AcpSubprocessLauncher(counter=counter, timeout=timeout)
	return await launcher.run(cmd, cwd=cwd, env=env, timeout=timeout)
