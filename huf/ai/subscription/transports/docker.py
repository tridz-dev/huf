"""Docker-based execution transport for subscription provider runtime.

Provides remote command execution and file staging via Docker exec and cp using
a local Docker daemon or remote context.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import shutil
import subprocess
import uuid
from typing import Any

from huf.ai.subscription.transports.base import (
	ExecutionTransport,
	ProcessResult,
	StagedFile,
	TransportProbe,
)

# Directory for staging files inside the container
STAGING_BASE_DIR = "/tmp/huf-subscription"

# Default timeout for Docker operations
DEFAULT_DOCKER_TIMEOUT_S = 60


class DockerExecTransport(ExecutionTransport):
	"""Docker-based execution transport using docker exec and cp.

	Provides one-shot non-interactive command execution via docker exec and file
	staging through docker cp, with support for Docker contexts.

	Args:
		container: Container name or ID to execute in
		docker_context: Optional Docker context name to use
		workdir: Optional working directory inside the container
		timeout: Default timeout in seconds for docker operations

	Raises:
		ValueError: Container name/ID is empty
	"""

	def __init__(
		self,
		container: str,
		*,
		docker_context: str | None = None,
		workdir: str | None = None,
		timeout: int = DEFAULT_DOCKER_TIMEOUT_S,
	) -> None:
		"""Initialize Docker execution transport.

		Args:
			container: Container name or ID (required)
			docker_context: Optional Docker context to use
			workdir: Optional working directory inside the container
			timeout: Default timeout in seconds (default: 60)
		"""
		if not container or not isinstance(container, str) or not container.strip():
			raise ValueError("Container name or ID is required")

		self.container = container.strip()
		self.docker_context = docker_context
		self.workdir = workdir
		self.timeout = timeout
		self._staging_dir: str | None = None
		self._run_id = str(uuid.uuid4())

	def _build_docker_cmd(self) -> list[str]:
		"""Build the base docker command with context if configured.

		Returns:
			List starting with 'docker' (and --context if configured)
		"""
		cmd = ["docker"]
		if self.docker_context:
			cmd.extend(["--context", self.docker_context])
		return cmd

	async def probe(self) -> TransportProbe:
		"""Check if docker CLI is available and container is running.

		Returns:
			TransportProbe with reachable=True if docker and container are ready
		"""
		# Check if docker CLI is available
		if not shutil.which("docker"):
			return TransportProbe(
				reachable=False,
				detail="Docker CLI not found in PATH",
			)

		# Check if container is running
		try:
			cmd = self._build_docker_cmd() + [
				"inspect",
				"--format",
				"{{.State.Running}}",
				self.container,
			]
			result = subprocess.run(
				cmd,
				capture_output=True,
				text=True,
				timeout=self.timeout,
			)

			if result.returncode != 0:
				return TransportProbe(
					reachable=False,
					detail=f"Container '{self.container}' not found or not accessible",
				)

			# Check the output: should be "true" if running
			is_running = result.stdout.strip().lower() == "true"
			if not is_running:
				return TransportProbe(
					reachable=False,
					detail=f"Container '{self.container}' exists but is not running",
				)

			return TransportProbe(reachable=True)

		except subprocess.TimeoutExpired:
			return TransportProbe(
				reachable=False,
				detail="Docker probe timed out",
			)
		except Exception as e:
			return TransportProbe(
				reachable=False,
				detail=f"Error checking container: {str(e)}",
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
		"""Execute a command via docker exec.

		Executes the command as a single non-interactive remote exec call (no PTY).
		Arguments are passed directly (no shell escaping needed since we use argv).

		Args:
			argv: Command as list of arguments
			cwd: Working directory inside container (optional)
			env: Environment variables (optional)
			stdin: Standard input (optional)
			timeout: Timeout in seconds (overrides default)

		Returns:
			ProcessResult with captured stdout/stderr and exit code
		"""
		if not argv:
			return ProcessResult(stdout="", stderr="", exit_code=None)

		if timeout is None:
			timeout = self.timeout

		# Build environment variables args
		docker_env_args = []
		if env:
			for key, value in env.items():
				docker_env_args.extend(["-e", f"{key}={value}"])

		# Build working directory arg
		docker_cwd_args = []
		if cwd:
			docker_cwd_args.extend(["-w", cwd])
		elif self.workdir:
			docker_cwd_args.extend(["-w", self.workdir])

		# Build the docker exec command
		cmd = self._build_docker_cmd() + [
			"exec",
		] + docker_env_args + docker_cwd_args + [
			self.container,
		] + argv

		try:
			result = subprocess.run(
				cmd,
				capture_output=True,
				text=True,
				stdin=subprocess.PIPE if stdin else None,
				timeout=timeout,
			)

			return ProcessResult(
				stdout=result.stdout,
				stderr=result.stderr,
				exit_code=result.returncode,
				timed_out=False,
			)

		except subprocess.TimeoutExpired:
			return ProcessResult(
				stdout="",
				stderr="Command execution timed out",
				exit_code=None,
				timed_out=True,
			)
		except Exception as e:
			return ProcessResult(
				stdout="",
				stderr=f"Docker exec error: {str(e)}",
				exit_code=None,
				timed_out=False,
			)

	async def stage_file(
		self,
		source_path: str,
		*,
		target_name: str | None = None,
	) -> StagedFile:
		"""Copy a file into the container via docker cp.

		Creates a staging directory (/tmp/huf-subscription/<run-id>/) inside the
		container and copies the file there. Returns a StagedFile with a cleanup
		callable.

		Args:
			source_path: Local path to the file
			target_name: Optional filename inside container (defaults to basename)

		Returns:
			StagedFile with remote_path and cleanup callable

		Raises:
			FileNotFoundError: Source file not found
			Exception: Docker cp failed
		"""
		if not os.path.exists(source_path):
			raise FileNotFoundError(f"File not found: {source_path}")

		if target_name is None:
			target_name = os.path.basename(source_path)

		# Ensure staging directory exists in container
		if self._staging_dir is None:
			self._staging_dir = f"{STAGING_BASE_DIR}/{self._run_id}"
			mkdir_cmd = self._build_docker_cmd() + [
				"exec",
				self.container,
				"mkdir",
				"-p",
				self._staging_dir,
			]
			try:
				result = subprocess.run(
					mkdir_cmd,
					capture_output=True,
					text=True,
					timeout=self.timeout,
				)
				if result.returncode != 0:
					raise Exception(
						f"Failed to create staging directory in container: {result.stderr}"
					)
			except subprocess.TimeoutExpired:
				raise Exception("Timeout creating staging directory in container")

		# Prepare the destination path
		remote_path = f"{self._staging_dir}/{target_name}"

		# Use docker cp to copy the file into the container
		cp_cmd = self._build_docker_cmd() + [
			"cp",
			source_path,
			f"{self.container}:{remote_path}",
		]

		try:
			result = subprocess.run(
				cp_cmd,
				capture_output=True,
				text=True,
				timeout=self.timeout,
			)
			if result.returncode != 0:
				raise Exception(f"Docker cp failed: {result.stderr}")
		except subprocess.TimeoutExpired:
			raise Exception("Timeout copying file to container")

		# Create cleanup callable
		async def cleanup() -> None:
			"""Remove the staged file."""
			try:
				await self.remove_staged_file(StagedFile(remote_path, source_path))
			except Exception:
				pass  # Best effort; don't fail if cleanup doesn't work

		return StagedFile(
			remote_path=remote_path,
			local_path=source_path,
			cleanup=cleanup,
		)

	async def remove_staged_file(self, staged_file: StagedFile) -> None:
		"""Remove a staged file from the container.

		Args:
			staged_file: StagedFile returned from stage_file()
		"""
		try:
			rm_cmd = self._build_docker_cmd() + [
				"exec",
				self.container,
				"rm",
				"-rf",
				staged_file.remote_path,
			]
			result = subprocess.run(
				rm_cmd,
				capture_output=True,
				text=True,
				timeout=self.timeout,
			)
			if result.returncode != 0:
				# Log but don't raise; cleanup is best-effort
				import frappe

				frappe.log_error(
					title="HUF Docker Transport Staging Cleanup",
					message=f"Failed to remove {staged_file.remote_path}: {result.stderr}",
				)
		except subprocess.TimeoutExpired:
			pass  # Best effort; cleanup is optional
		except Exception as e:
			# Log but don't raise; cleanup is best-effort
			import frappe

			frappe.log_error(
				title="HUF Docker Transport Staging Cleanup",
				message=f"Error removing {staged_file.remote_path}: {e}",
			)
