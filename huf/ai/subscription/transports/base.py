"""Abstract base class for execution transports.

Execution transports abstract the mechanism for running commands in a target
environment (local, Docker, SSH) and managing temporary files.

This module defines the interface that all transport implementations must follow.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class TransportProbe:
	"""Result of a transport probe (reachability check).

	Attributes:
		reachable: True if the transport target is reachable and healthy
		detail: Optional diagnostic message (e.g., error reason if unreachable)
	"""

	reachable: bool
	detail: str | None = None


@dataclass(frozen=True, slots=True)
class ProcessResult:
	"""Result of running a command over a transport.

	Attributes:
		stdout: Standard output (UTF-8, errors replaced)
		stderr: Standard error (UTF-8, errors replaced)
		exit_code: Process exit code (None if not available)
		timed_out: True if execution was terminated due to timeout
	"""

	stdout: str
	stderr: str
	exit_code: int | None
	timed_out: bool = False


@dataclass(frozen=True, slots=True)
class StagedFile:
	"""Reference to a file staged on the transport target.

	Attributes:
		remote_path: Path where the file is accessible on the target
		local_path: Original source path on the HUF host
		cleanup: Optional callable that removes the staged file when invoked
	"""

	remote_path: str
	local_path: str
	cleanup: Callable[[], None] | None = None


class ExecutionTransport(ABC):
	"""Abstract base class for execution transports.

	Implementations support executing commands and managing files in a target
	environment, abstracting away the mechanism (local subprocess, Docker, SSH).

	All methods are async and should handle timeouts gracefully.
	"""

	@abstractmethod
	async def probe(self) -> TransportProbe:
		"""Check if the transport target is reachable.

		Returns:
			TransportProbe with reachable status and optional detail message
		"""
		pass

	@abstractmethod
	async def run(
		self,
		argv: list[str],
		*,
		cwd: str | None = None,
		env: dict[str, str] | None = None,
		stdin: str | None = None,
		timeout: int | None = None,
	) -> ProcessResult:
		"""Execute a command over the transport.

		Args:
			argv: Command as list of arguments (e.g., ['echo', 'hello'])
			cwd: Working directory for command execution (optional)
			env: Environment variables for command (optional; merges with default)
			stdin: Standard input string (optional)
			timeout: Timeout in seconds (optional)

		Returns:
			ProcessResult with stdout, stderr, exit_code, and timed_out flag

		Raises:
			Exception: Transport-specific errors (connection, permission, etc.)
		"""
		pass

	@abstractmethod
	async def stage_file(
		self,
		source_path: str,
		*,
		target_name: str | None = None,
	) -> StagedFile:
		"""Copy a file to the transport target for later use.

		Stages a file into a temporary location on the target (e.g., /tmp/huf-<id>/).
		The returned StagedFile has a cleanup callable that can be invoked to
		remove the staged file.

		Args:
			source_path: Local path to the file on the HUF host
			target_name: Optional filename to use on the target (defaults to basename)

		Returns:
			StagedFile with remote_path, local_path, and cleanup callable

		Raises:
			Exception: Transport-specific errors (connection, permission, file not found)
		"""
		pass

	@abstractmethod
	async def remove_staged_file(self, staged_file: StagedFile) -> None:
		"""Remove a staged file from the transport target.

		Convenience method to explicitly clean up a staged file.
		Usually the StagedFile.cleanup callable is preferred.

		Args:
			staged_file: StagedFile returned from stage_file()

		Raises:
			Exception: Transport-specific errors (connection, permission)
		"""
		pass
