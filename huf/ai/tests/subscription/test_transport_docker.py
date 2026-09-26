"""Tests for DockerExecTransport.

Tests cover:
- Initialization validation
- Probe: docker availability, container running status
- Exec: stdout/stderr/exit-code capture, timeout enforcement, environment variables, working directory
- File staging and cleanup via docker cp
- Error handling and sanitization
- Integration test (optional, skipped if docker unavailable)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from huf.ai.subscription.transports.base import ProcessResult, StagedFile
from huf.ai.subscription.transports.docker import DockerExecTransport


class TestDockerExecTransportInitialization:
	"""Test transport initialization and validation."""

	def test_init_with_valid_container(self):
		"""Test successful initialization with container name."""
		transport = DockerExecTransport("test-container")

		assert transport.container == "test-container"
		assert transport.docker_context is None
		assert transport.workdir is None
		assert transport.timeout == 60

	def test_init_with_context(self):
		"""Test initialization with docker context."""
		transport = DockerExecTransport(
			"test-container",
			docker_context="remote-context",
		)

		assert transport.container == "test-container"
		assert transport.docker_context == "remote-context"

	def test_init_with_workdir(self):
		"""Test initialization with working directory."""
		transport = DockerExecTransport(
			"test-container",
			workdir="/app",
		)

		assert transport.workdir == "/app"

	def test_init_with_custom_timeout(self):
		"""Test initialization with custom timeout."""
		transport = DockerExecTransport(
			"test-container",
			timeout=120,
		)

		assert transport.timeout == 120

	def test_init_empty_container_raises(self):
		"""Test initialization fails with empty container name."""
		with pytest.raises(ValueError, match="Container name or ID is required"):
			DockerExecTransport("")

	def test_init_none_container_raises(self):
		"""Test initialization fails with None container."""
		with pytest.raises(ValueError, match="Container name or ID is required"):
			DockerExecTransport(None)

	def test_init_whitespace_container_raises(self):
		"""Test initialization fails with whitespace-only container."""
		with pytest.raises(ValueError, match="Container name or ID is required"):
			DockerExecTransport("   ")


class TestDockerExecTransportProbe:
	"""Test the probe() method for reachability checks."""

	@pytest.mark.asyncio
	async def test_probe_success(self):
		"""Test successful probe when docker and container are ready."""
		with patch("shutil.which") as mock_which, \
		     patch("subprocess.run") as mock_run:

			mock_which.return_value = "/usr/bin/docker"
			mock_result = MagicMock()
			mock_result.returncode = 0
			mock_result.stdout = "true"
			mock_run.return_value = mock_result

			transport = DockerExecTransport("test-container")
			probe_result = await transport.probe()

			assert probe_result.reachable is True
			assert probe_result.detail is None

	@pytest.mark.asyncio
	async def test_probe_docker_not_found(self):
		"""Test probe fails when docker CLI is not in PATH."""
		with patch("shutil.which") as mock_which:
			mock_which.return_value = None

			transport = DockerExecTransport("test-container")
			probe_result = await transport.probe()

			assert probe_result.reachable is False
			assert "Docker CLI not found" in probe_result.detail

	@pytest.mark.asyncio
	async def test_probe_container_not_found(self):
		"""Test probe fails when container doesn't exist."""
		with patch("shutil.which") as mock_which, \
		     patch("subprocess.run") as mock_run:

			mock_which.return_value = "/usr/bin/docker"
			mock_result = MagicMock()
			mock_result.returncode = 1
			mock_run.return_value = mock_result

			transport = DockerExecTransport("nonexistent-container")
			probe_result = await transport.probe()

			assert probe_result.reachable is False
			assert "not found" in probe_result.detail

	@pytest.mark.asyncio
	async def test_probe_container_not_running(self):
		"""Test probe fails when container exists but is not running."""
		with patch("shutil.which") as mock_which, \
		     patch("subprocess.run") as mock_run:

			mock_which.return_value = "/usr/bin/docker"
			mock_result = MagicMock()
			mock_result.returncode = 0
			mock_result.stdout = "false"
			mock_run.return_value = mock_result

			transport = DockerExecTransport("stopped-container")
			probe_result = await transport.probe()

			assert probe_result.reachable is False
			assert "not running" in probe_result.detail

	@pytest.mark.asyncio
	async def test_probe_timeout(self):
		"""Test probe fails on timeout."""
		with patch("shutil.which") as mock_which, \
		     patch("subprocess.run") as mock_run:

			mock_which.return_value = "/usr/bin/docker"
			mock_run.side_effect = subprocess.TimeoutExpired("docker", 10)

			transport = DockerExecTransport("test-container", timeout=5)
			probe_result = await transport.probe()

			assert probe_result.reachable is False
			assert "timed out" in probe_result.detail


class TestDockerExecTransportRun:
	"""Test the run() method for command execution."""

	@pytest.mark.asyncio
	async def test_run_simple_command(self):
		"""Test successful exec with simple command."""
		with patch("subprocess.run") as mock_run:
			mock_result = MagicMock()
			mock_result.returncode = 0
			mock_result.stdout = "hello"
			mock_result.stderr = ""
			mock_run.return_value = mock_result

			transport = DockerExecTransport("test-container")
			result = await transport.run(["echo", "hello"])

			assert result.stdout == "hello"
			assert result.stderr == ""
			assert result.exit_code == 0
			assert result.timed_out is False

			# Verify the command structure
			call_args = mock_run.call_args[0][0]
			assert call_args[0] == "docker"
			assert call_args[1] == "exec"
			assert call_args[2] == "test-container"
			assert call_args[3] == "echo"
			assert call_args[4] == "hello"

	@pytest.mark.asyncio
	async def test_run_with_docker_context(self):
		"""Test exec includes --context when configured."""
		with patch("subprocess.run") as mock_run:
			mock_result = MagicMock()
			mock_result.returncode = 0
			mock_result.stdout = "test"
			mock_result.stderr = ""
			mock_run.return_value = mock_result

			transport = DockerExecTransport(
				"test-container",
				docker_context="remote-ctx",
			)
			result = await transport.run(["echo", "test"])

			call_args = mock_run.call_args[0][0]
			assert call_args[0] == "docker"
			assert call_args[1] == "--context"
			assert call_args[2] == "remote-ctx"
			assert call_args[3] == "exec"
			assert call_args[4] == "test-container"

	@pytest.mark.asyncio
	async def test_run_with_environment_variables(self):
		"""Test exec with environment variables."""
		with patch("subprocess.run") as mock_run:
			mock_result = MagicMock()
			mock_result.returncode = 0
			mock_result.stdout = ""
			mock_result.stderr = ""
			mock_run.return_value = mock_result

			transport = DockerExecTransport("test-container")
			result = await transport.run(
				["env"],
				env={"FOO": "bar", "BAZ": "qux"},
			)

			call_args = mock_run.call_args[0][0]
			# Should have -e flags before the container
			assert "-e" in call_args
			foo_idx = call_args.index("-e")
			assert call_args[foo_idx + 1] in ["FOO=bar", "BAZ=qux"]

	@pytest.mark.asyncio
	async def test_run_with_working_directory(self):
		"""Test exec with working directory."""
		with patch("subprocess.run") as mock_run:
			mock_result = MagicMock()
			mock_result.returncode = 0
			mock_result.stdout = ""
			mock_result.stderr = ""
			mock_run.return_value = mock_result

			transport = DockerExecTransport(
				"test-container",
				workdir="/app",
			)
			result = await transport.run(["pwd"])

			call_args = mock_run.call_args[0][0]
			# Should have -w flag
			assert "-w" in call_args
			w_idx = call_args.index("-w")
			assert call_args[w_idx + 1] == "/app"

	@pytest.mark.asyncio
	async def test_run_with_explicit_cwd_overrides_workdir(self):
		"""Test that explicit cwd parameter overrides instance workdir."""
		with patch("subprocess.run") as mock_run:
			mock_result = MagicMock()
			mock_result.returncode = 0
			mock_result.stdout = ""
			mock_result.stderr = ""
			mock_run.return_value = mock_result

			transport = DockerExecTransport(
				"test-container",
				workdir="/app",
			)
			result = await transport.run(["pwd"], cwd="/home")

			call_args = mock_run.call_args[0][0]
			w_idx = call_args.index("-w")
			assert call_args[w_idx + 1] == "/home"

	@pytest.mark.asyncio
	async def test_run_timeout_enforcement(self):
		"""Test timeout is enforced."""
		with patch("subprocess.run") as mock_run:
			mock_run.side_effect = subprocess.TimeoutExpired("docker", 5)

			transport = DockerExecTransport("test-container", timeout=5)
			result = await transport.run(["sleep", "100"], timeout=5)

			assert result.timed_out is True
			assert result.exit_code is None
			assert "timed out" in result.stderr.lower()

	@pytest.mark.asyncio
	async def test_run_custom_timeout_overrides_default(self):
		"""Test custom timeout parameter overrides instance timeout."""
		with patch("subprocess.run") as mock_run:
			mock_result = MagicMock()
			mock_result.returncode = 0
			mock_result.stdout = ""
			mock_result.stderr = ""
			mock_run.return_value = mock_result

			transport = DockerExecTransport("test-container", timeout=60)
			result = await transport.run(["echo", "test"], timeout=30)

			# Check that timeout=30 was passed to subprocess.run
			call_kwargs = mock_run.call_args[1]
			assert call_kwargs.get("timeout") == 30

	@pytest.mark.asyncio
	async def test_run_non_zero_exit_code(self):
		"""Test exec returns non-zero exit code."""
		with patch("subprocess.run") as mock_run:
			mock_result = MagicMock()
			mock_result.returncode = 42
			mock_result.stdout = "output"
			mock_result.stderr = "error"
			mock_run.return_value = mock_result

			transport = DockerExecTransport("test-container")
			result = await transport.run(["false"])

			assert result.exit_code == 42
			assert result.timed_out is False

	@pytest.mark.asyncio
	async def test_run_empty_argv(self):
		"""Test run with empty argv returns empty result."""
		transport = DockerExecTransport("test-container")
		result = await transport.run([])

		assert result.stdout == ""
		assert result.stderr == ""
		assert result.exit_code is None

	@pytest.mark.asyncio
	async def test_run_exception_handling(self):
		"""Test run handles subprocess exceptions."""
		with patch("subprocess.run") as mock_run:
			mock_run.side_effect = Exception("Docker error")

			transport = DockerExecTransport("test-container")
			result = await transport.run(["echo", "test"])

			assert result.exit_code is None
			assert "Docker exec error" in result.stderr


class TestDockerExecTransportFileStaging:
	"""Test file staging and cleanup."""

	@pytest.mark.asyncio
	async def test_stage_file_success(self):
		"""Test successful file staging."""
		with tempfile.NamedTemporaryFile(delete=False) as f:
			f.write(b"test content")
			temp_path = f.name

		try:
			with patch("subprocess.run") as mock_run:
				mock_result = MagicMock()
				mock_result.returncode = 0
				mock_result.stdout = ""
				mock_result.stderr = ""
				mock_run.return_value = mock_result

				transport = DockerExecTransport("test-container")
				staged = await transport.stage_file(temp_path)

				assert staged.local_path == temp_path
				assert staged.remote_path.startswith("/tmp/huf-subscription/")
				assert staged.remote_path.endswith(os.path.basename(temp_path))
				assert staged.cleanup is not None

				# Verify mkdir was called
				mkdir_call = mock_run.call_args_list[0]
				mkdir_args = mkdir_call[0][0]
				assert "mkdir" in mkdir_args
				assert "-p" in mkdir_args

				# Verify cp was called
				cp_call = mock_run.call_args_list[1]
				cp_args = cp_call[0][0]
				assert "cp" in cp_args
				assert temp_path in cp_args

		finally:
			os.unlink(temp_path)

	@pytest.mark.asyncio
	async def test_stage_file_custom_target_name(self):
		"""Test file staging with custom target name."""
		with tempfile.NamedTemporaryFile(delete=False) as f:
			f.write(b"test content")
			temp_path = f.name

		try:
			with patch("subprocess.run") as mock_run:
				mock_result = MagicMock()
				mock_result.returncode = 0
				mock_result.stdout = ""
				mock_result.stderr = ""
				mock_run.return_value = mock_result

				transport = DockerExecTransport("test-container")
				staged = await transport.stage_file(
					temp_path,
					target_name="custom.txt",
				)

				assert staged.remote_path.endswith("custom.txt")

		finally:
			os.unlink(temp_path)

	@pytest.mark.asyncio
	async def test_stage_file_not_found(self):
		"""Test staging a non-existent file raises FileNotFoundError."""
		transport = DockerExecTransport("test-container")

		with pytest.raises(FileNotFoundError):
			await transport.stage_file("/nonexistent/file.txt")

	@pytest.mark.asyncio
	async def test_stage_file_mkdir_failure(self):
		"""Test staging fails if mkdir command fails."""
		with tempfile.NamedTemporaryFile(delete=False) as f:
			f.write(b"test content")
			temp_path = f.name

		try:
			with patch("subprocess.run") as mock_run:
				mock_result = MagicMock()
				mock_result.returncode = 1
				mock_result.stdout = ""
				mock_result.stderr = "Permission denied"
				mock_run.return_value = mock_result

				transport = DockerExecTransport("test-container")

				with pytest.raises(Exception, match="Failed to create"):
					await transport.stage_file(temp_path)

		finally:
			os.unlink(temp_path)

	@pytest.mark.asyncio
	async def test_remove_staged_file(self):
		"""Test removing a staged file."""
		with patch("subprocess.run") as mock_run:
			mock_result = MagicMock()
			mock_result.returncode = 0
			mock_result.stdout = ""
			mock_result.stderr = ""
			mock_run.return_value = mock_result

			transport = DockerExecTransport("test-container")
			staged = StagedFile(
				remote_path="/tmp/huf-subscription/abc/file.txt",
				local_path="/local/file.txt",
			)

			await transport.remove_staged_file(staged)

			# Verify rm command was called
			call_args = mock_run.call_args[0][0]
			assert "rm" in call_args
			assert "-rf" in call_args
			assert "/tmp/huf-subscription/abc/file.txt" in call_args

	@pytest.mark.asyncio
	async def test_stage_file_cleanup_callable(self):
		"""Test cleanup callable removes staged file."""
		with tempfile.NamedTemporaryFile(delete=False) as f:
			f.write(b"test content")
			temp_path = f.name

		try:
			with patch("subprocess.run") as mock_run:
				mock_result = MagicMock()
				mock_result.returncode = 0
				mock_result.stdout = ""
				mock_result.stderr = ""
				mock_run.return_value = mock_result

				transport = DockerExecTransport("test-container")
				staged = await transport.stage_file(temp_path)

				# Call cleanup
				await staged.cleanup()

				# Verify rm was called (third call after mkdir and cp)
				rm_call = mock_run.call_args_list[2]
				rm_args = rm_call[0][0]
				assert "rm" in rm_args

		finally:
			os.unlink(temp_path)


class TestDockerExecTransportCommandConstruction:
	"""Test correct command construction for edge cases."""

	@pytest.mark.asyncio
	async def test_command_with_special_characters(self):
		"""Test command args with special characters are passed safely."""
		with patch("subprocess.run") as mock_run:
			mock_result = MagicMock()
			mock_result.returncode = 0
			mock_result.stdout = ""
			mock_result.stderr = ""
			mock_run.return_value = mock_result

			transport = DockerExecTransport("test-container")
			result = await transport.run(
				["echo", "hello world", "with spaces", "and $pecial chars"],
			)

			# Verify args are passed as-is (not shell-quoted)
			call_args = mock_run.call_args[0][0]
			assert "hello world" in call_args
			assert "with spaces" in call_args
			assert "and $pecial chars" in call_args

	@pytest.mark.asyncio
	async def test_staged_file_path_with_spaces(self):
		"""Test file staging with spaces in filename."""
		with tempfile.NamedTemporaryFile(
			suffix=" with spaces.txt",
			delete=False,
		) as f:
			f.write(b"content")
			temp_path = f.name

		try:
			with patch("subprocess.run") as mock_run:
				mock_result = MagicMock()
				mock_result.returncode = 0
				mock_result.stdout = ""
				mock_result.stderr = ""
				mock_run.return_value = mock_result

				transport = DockerExecTransport("test-container")
				staged = await transport.stage_file(temp_path)

				# Verify the file path is preserved
				cp_call = mock_run.call_args_list[1]
				cp_args = cp_call[0][0]
				assert temp_path in cp_args

		finally:
			os.unlink(temp_path)


# Integration test (skipped if docker unavailable)
@pytest.mark.skipif(
	not shutil.which("docker"),
	reason="Docker CLI not available",
)
class TestDockerExecTransportIntegration:
	"""Integration tests with real Docker (requires docker available)."""

	@pytest.fixture
	def test_container(self):
		"""Start a lightweight test container."""
		import uuid

		container_name = f"huf-sub-test-{uuid.uuid4().hex[:8]}"

		try:
			# Start container
			result = subprocess.run(
				[
					"docker",
					"run",
					"-d",
					"--rm",
					"--name",
					container_name,
					"alpine:latest",
					"sleep",
					"300",
				],
				capture_output=True,
				text=True,
				timeout=30,
			)

			if result.returncode != 0:
				pytest.skip(f"Could not start test container: {result.stderr}")

			yield container_name

		finally:
			# Cleanup
			try:
				subprocess.run(
					["docker", "stop", container_name],
					capture_output=True,
					timeout=10,
				)
			except Exception:
				pass

	@pytest.mark.asyncio
	async def test_integration_probe_success(self, test_container):
		"""Test probe on real container."""
		transport = DockerExecTransport(test_container)
		probe_result = await transport.probe()

		assert probe_result.reachable is True

	@pytest.mark.asyncio
	async def test_integration_run_command(self, test_container):
		"""Test executing a command in real container."""
		transport = DockerExecTransport(test_container)
		result = await transport.run(["echo", "hello from docker"])

		assert result.exit_code == 0
		assert "hello from docker" in result.stdout

	@pytest.mark.asyncio
	async def test_integration_stage_and_execute_file(self, test_container):
		"""Test staging a file and executing it."""
		with tempfile.NamedTemporaryFile(
			mode="w",
			suffix=".sh",
			delete=False,
		) as f:
			f.write("#!/bin/sh\necho 'hello from staged file'\n")
			temp_path = f.name

		try:
			transport = DockerExecTransport(test_container)

			# Stage the file
			staged = await transport.stage_file(temp_path)

			# Make it executable
			result = await transport.run(["chmod", "+x", staged.remote_path])
			assert result.exit_code == 0

			# Execute it
			result = await transport.run(["/bin/sh", staged.remote_path])
			assert result.exit_code == 0
			assert "hello from staged file" in result.stdout

			# Cleanup
			await staged.cleanup()

		finally:
			os.unlink(temp_path)
