"""Local subprocess execution transport.

This transport executes commands using local subprocess with controlled environment,
bounded resource limits, and managed temporary file staging.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

from huf.ai.subscription.transports.base import (
	ExecutionTransport,
	ProcessResult,
	StagedFile,
	TransportProbe,
)


class LocalTransport(ExecutionTransport):
	"""Execute commands locally using subprocess with environment isolation.

	Features:
	- Bounded timeout with process group cleanup (no zombies)
	- Controlled environment (explicit allowlist of safe variables)
	- Temporary file staging with automatic cleanup
	- Bounded stdout/stderr capture
	"""

	# Safe environment variables to pass through from parent process
	ALLOWED_ENV_VARS = {
		"PATH",
		"HOME",
		"LANG",
		"LC_ALL",
		"LC_COLLATE",
		"LC_CTYPE",
		"LC_MESSAGES",
		"LC_MONETARY",
		"LC_NUMERIC",
		"LC_TIME",
		"TZ",
		"TMPDIR",
		"TEMP",
		"USER",
		"LOGNAME",
		"SHELL",
	}

	# Default bounds for resource limits
	MAX_STDOUT_BYTES = 10 * 1024 * 1024  # 10 MB
	MAX_STDERR_BYTES = 10 * 1024 * 1024  # 10 MB
	DEFAULT_TIMEOUT_SECONDS = 60

	def __init__(
		self,
		executable: str,
		*,
		runtime_dir: str | None = None,
	):
		"""Initialize LocalTransport.

		Args:
			executable: Path or name of the executable to run
			runtime_dir: Base directory for runtime workspace (default: system temp)
		"""
		self.executable = executable
		if runtime_dir:
			self.runtime_dir = Path(runtime_dir)
		else:
			self.runtime_dir = Path(tempfile.gettempdir()) / "huf-subscription" / "runtime"

		self.runtime_dir.mkdir(parents=True, exist_ok=True)
		self._staging_dirs: dict[str, Path] = {}

	async def probe(self) -> TransportProbe:
		"""Check if the executable exists and is executable.

		Returns:
			TransportProbe with reachable=True if executable is found and runnable
		"""
		try:
			# Try to find the executable
			which_result = shutil.which(self.executable)
			if not which_result:
				return TransportProbe(
					reachable=False,
					detail=f"Executable '{self.executable}' not found in PATH",
				)

			# Verify it's actually executable
			executable_path = Path(which_result)
			if not os.access(executable_path, os.X_OK):
				return TransportProbe(
					reachable=False,
					detail=f"Executable '{which_result}' is not executable",
				)

			return TransportProbe(
				reachable=True,
				detail=f"Executable found at: {which_result}",
			)
		except Exception as e:
			return TransportProbe(
				reachable=False,
				detail=f"Error probing executable: {str(e)}",
			)

	async def run(
		self,
		argv: list[str],
		*,
		cwd: str | None = None,
		env: dict[str, str] | None = None,
		stdin: str | None = None,
		timeout: int | None = None,
	) -> ProcessResult:
		"""Execute a command with bounded timeout and controlled environment.

		Args:
			argv: Command as list of arguments
			cwd: Working directory (default: runtime directory)
			env: Additional environment variables (merged with allowlist)
			stdin: Standard input string
			timeout: Timeout in seconds (default: 60)

		Returns:
			ProcessResult with stdout, stderr, exit_code, and timed_out flag
		"""
		if timeout is None:
			timeout = self.DEFAULT_TIMEOUT_SECONDS

		if cwd is None:
			cwd = str(self.runtime_dir)

		# Build controlled environment: allowlist safe vars + explicit extras
		process_env = {}
		for var in self.ALLOWED_ENV_VARS:
			if var in os.environ:
				process_env[var] = os.environ[var]

		if env:
			process_env.update(env)

		try:
			# Start the process
			process = await asyncio.create_subprocess_exec(
				*argv,
				cwd=cwd,
				env=process_env,
				stdin=asyncio.subprocess.PIPE if stdin else None,
				stdout=asyncio.subprocess.PIPE,
				stderr=asyncio.subprocess.PIPE,
				preexec_fn=os.setsid if hasattr(os, "setsid") else None,  # Create process group
			)

			# Run with timeout
			try:
				stdout_data, stderr_data = await asyncio.wait_for(
					process.communicate(input=stdin.encode() if stdin else None),
					timeout=timeout,
				)
				exit_code = process.returncode
				timed_out = False

			except asyncio.TimeoutError:
				# Timeout: kill the entire process group
				timed_out = True
				try:
					if hasattr(os, "killpg"):
						os.killpg(os.getpgid(process.pid), 9)  # Kill process group
					else:
						process.kill()  # Fallback for Windows
				except Exception:
					pass  # Process may already be dead

				# Wait for cleanup
				try:
					await asyncio.wait_for(process.wait(), timeout=2)
				except asyncio.TimeoutError:
					pass

				stdout_data = b""
				stderr_data = b""
				exit_code = None

			# Decode with error handling
			stdout = stdout_data.decode(errors="replace")[: self.MAX_STDOUT_BYTES]
			stderr = stderr_data.decode(errors="replace")[: self.MAX_STDERR_BYTES]

			return ProcessResult(
				stdout=stdout,
				stderr=stderr,
				exit_code=exit_code,
				timed_out=timed_out,
			)

		except Exception as e:
			return ProcessResult(
				stdout="",
				stderr=f"Error executing command: {str(e)}",
				exit_code=None,
				timed_out=False,
			)

	async def stage_file(
		self,
		source_path: str,
		*,
		target_name: str | None = None,
	) -> StagedFile:
		"""Copy a file to a temporary staging directory.

		Creates a per-run staging directory and copies the file into it.
		Returns a StagedFile with a cleanup callable.

		Args:
			source_path: Path to the source file
			target_name: Optional filename to use on the target

		Returns:
			StagedFile with remote_path and cleanup callable
		"""
		source = Path(source_path)
		if not source.exists():
			raise FileNotFoundError(f"Source file not found: {source_path}")

		# Generate a unique staging directory for this run
		run_id = str(uuid.uuid4())
		staging_dir = self.runtime_dir / "staged" / run_id
		staging_dir.mkdir(parents=True, exist_ok=True)

		# Store for later cleanup
		self._staging_dirs[run_id] = staging_dir

		# Determine target filename
		if target_name is None:
			target_name = source.name

		target_path = staging_dir / target_name

		# Copy the file
		shutil.copy2(source, target_path)

		# Create cleanup callable
		def cleanup() -> None:
			try:
				if staging_dir.exists():
					shutil.rmtree(staging_dir)
				self._staging_dirs.pop(run_id, None)
			except Exception:
				pass

		return StagedFile(
			remote_path=str(target_path),
			local_path=source_path,
			cleanup=cleanup,
		)

	async def remove_staged_file(self, staged_file: StagedFile) -> None:
		"""Remove a staged file and its staging directory.

		Args:
			staged_file: StagedFile to remove
		"""
		if staged_file.cleanup:
			staged_file.cleanup()
