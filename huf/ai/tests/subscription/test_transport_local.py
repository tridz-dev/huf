"""Unit tests for LocalTransport.

Tests cover:
- Successful new-session run with fake_cli
- Resume via session file (state persistence)
- Timeout enforcement with process group cleanup
- Environment variable isolation (safe allowlist)
- File staging and cleanup
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

import pytest

from huf.ai.subscription.transports.local import LocalTransport


# Path to fake_cli.py fixture
FIXTURES_DIR = Path(__file__).parent / "fixtures"
FAKE_CLI_PATH = FIXTURES_DIR / "fake_cli.py"


class TestLocalTransportProbe:
	"""Test transport probing and executable discovery."""

	@pytest.mark.asyncio
	async def test_probe_finds_existing_executable(self) -> None:
		"""Test that probe() finds a known executable."""
		transport = LocalTransport("python3")
		probe = await transport.probe()
		assert probe.reachable is True
		assert probe.detail is not None
		assert "python3" in probe.detail or "found" in probe.detail.lower()

	@pytest.mark.asyncio
	async def test_probe_fails_for_nonexistent_executable(self) -> None:
		"""Test that probe() fails gracefully for missing executable."""
		transport = LocalTransport("nonexistent_executable_xyz_12345")
		probe = await transport.probe()
		assert probe.reachable is False
		assert probe.detail is not None
		assert "not found" in probe.detail.lower()

	@pytest.mark.asyncio
	async def test_probe_with_full_path(self) -> None:
		"""Test probe() with full path to executable."""
		# Use sys.executable which always works
		transport = LocalTransport(sys.executable)
		probe = await transport.probe()
		assert probe.reachable is True


class TestLocalTransportRun:
	"""Test command execution."""

	@pytest.mark.asyncio
	async def test_run_simple_command(self) -> None:
		"""Test running a simple Python command."""
		transport = LocalTransport(sys.executable)
		result = await transport.run([sys.executable, "-c", "print('hello')"])
		assert result.exit_code == 0
		assert "hello" in result.stdout

	@pytest.mark.asyncio
	async def test_run_with_stderr(self) -> None:
		"""Test capturing stderr."""
		transport = LocalTransport(sys.executable)
		result = await transport.run(
			[sys.executable, "-c", "import sys; sys.stderr.write('error')"]
		)
		assert result.exit_code == 0
		assert "error" in result.stderr

	@pytest.mark.asyncio
	async def test_run_with_nonzero_exit_code(self) -> None:
		"""Test command with non-zero exit code."""
		transport = LocalTransport(sys.executable)
		result = await transport.run([sys.executable, "-c", "exit(42)"])
		assert result.exit_code == 42

	@pytest.mark.asyncio
	async def test_run_with_stdin(self) -> None:
		"""Test providing stdin to a command."""
		transport = LocalTransport(sys.executable)
		result = await transport.run(
			[sys.executable, "-c", "import sys; print(sys.stdin.read())"],
			stdin="hello from stdin",
		)
		assert "hello from stdin" in result.stdout

	@pytest.mark.asyncio
	async def test_run_with_custom_working_directory(self) -> None:
		"""Test running with a custom working directory."""
		with tempfile.TemporaryDirectory() as tmpdir:
			transport = LocalTransport(sys.executable)
			result = await transport.run(
				[sys.executable, "-c", "import os; print(os.getcwd())"],
				cwd=tmpdir,
			)
			assert tmpdir in result.stdout

	@pytest.mark.asyncio
	async def test_run_with_extra_env_vars(self) -> None:
		"""Test running with extra environment variables."""
		transport = LocalTransport(sys.executable)
		result = await transport.run(
			[sys.executable, "-c", "import os; print(os.environ.get('MY_VAR', 'not found'))"],
			env={"MY_VAR": "test_value"},
		)
		assert "test_value" in result.stdout

	@pytest.mark.asyncio
	async def test_run_timeout_enforcement(self) -> None:
		"""Test that timeout terminates long-running processes."""
		transport = LocalTransport(sys.executable)
		result = await transport.run(
			[sys.executable, "-c", "import time; time.sleep(5)"],
			timeout=1,
		)
		assert result.timed_out is True
		assert result.exit_code is None

	@pytest.mark.asyncio
	async def test_run_env_var_isolation(self) -> None:
		"""Test that arbitrary env vars are not leaked to subprocess.

		This test sets a sentinel variable in the parent process and verifies
		it is NOT visible in the child unless explicitly passed through env.
		"""
		# Set sentinel var in parent
		os.environ["SENTINEL_TEST_VAR_XYZ"] = "parent_secret"

		try:
			transport = LocalTransport(sys.executable)

			# First: verify the var is NOT passed by default
			result = await transport.run(
				[
					sys.executable,
					"-c",
					"import os; print(os.environ.get('SENTINEL_TEST_VAR_XYZ', 'not found'))",
				],
			)
			assert "not found" in result.stdout, (
				"Env var leaked to subprocess without explicit allowlist"
			)

			# Second: verify it IS passed when explicitly added
			result = await transport.run(
				[
					sys.executable,
					"-c",
					"import os; print(os.environ.get('SENTINEL_TEST_VAR_XYZ', 'not found'))",
				],
				env={"SENTINEL_TEST_VAR_XYZ": "parent_secret"},
			)
			assert "parent_secret" in result.stdout

		finally:
			# Cleanup
			os.environ.pop("SENTINEL_TEST_VAR_XYZ", None)

	@pytest.mark.asyncio
	async def test_run_with_fake_cli_new_session(self) -> None:
		"""Test running fake_cli.py for a new session."""
		if not FAKE_CLI_PATH.exists():
			pytest.skip(f"fake_cli.py not found at {FAKE_CLI_PATH}")

		with tempfile.TemporaryDirectory() as state_dir:
			transport = LocalTransport(sys.executable)
			result = await transport.run(
				[
					sys.executable,
					str(FAKE_CLI_PATH),
					"-p",
					"hello world",
					"--output-format",
					"json",
				],
				env={"FAKE_CLI_STATE_DIR": state_dir},
			)

			assert result.exit_code == 0
			assert not result.timed_out

			# Parse response
			response = json.loads(result.stdout)
			assert response["is_error"] is False
			assert "HELLO" in response["result"]
			assert "session_id" in response
			session_id = response["session_id"]

			# Second run: resume the same session
			result2 = await transport.run(
				[
					sys.executable,
					str(FAKE_CLI_PATH),
					"-p",
					"follow up",
					"--resume",
					session_id,
					"--output-format",
					"json",
				],
				env={"FAKE_CLI_STATE_DIR": state_dir},
			)

			assert result2.exit_code == 0
			response2 = json.loads(result2.stdout)
			assert response2["session_id"] == session_id  # Session ID stays stable
			assert "[previous:" in response2["result"]  # Shows prior context

	@pytest.mark.asyncio
	async def test_run_with_fake_cli_resume_unknown_session(self) -> None:
		"""Test fake_cli.py error handling for unknown resume."""
		if not FAKE_CLI_PATH.exists():
			pytest.skip(f"fake_cli.py not found at {FAKE_CLI_PATH}")

		with tempfile.TemporaryDirectory() as state_dir:
			transport = LocalTransport(sys.executable)
			result = await transport.run(
				[
					sys.executable,
					str(FAKE_CLI_PATH),
					"-p",
					"hello",
					"--resume",
					"not-a-real-session-id",
					"--output-format",
					"json",
				],
				env={"FAKE_CLI_STATE_DIR": state_dir},
			)

			# Resume unknown session: exit non-zero, plain-text error to stderr
			assert result.exit_code != 0
			assert "Error" in result.stderr or "error" in result.stderr.lower()

	@pytest.mark.asyncio
	async def test_run_with_fake_cli_timeout(self) -> None:
		"""Test timeout handling with fake_cli.py."""
		if not FAKE_CLI_PATH.exists():
			pytest.skip(f"fake_cli.py not found at {FAKE_CLI_PATH}")

		with tempfile.TemporaryDirectory() as state_dir:
			transport = LocalTransport(sys.executable)

			# Run with FAKE_CLI_SLEEP_SECONDS > timeout
			result = await transport.run(
				[
					sys.executable,
					str(FAKE_CLI_PATH),
					"-p",
					"hello",
					"--output-format",
					"json",
				],
				env={
					"FAKE_CLI_STATE_DIR": state_dir,
					"FAKE_CLI_SLEEP_SECONDS": "5",
				},
				timeout=1,
			)

			assert result.timed_out is True
			assert result.exit_code is None


class TestLocalTransportFileStaging:
	"""Test file staging and cleanup."""

	@pytest.mark.asyncio
	async def test_stage_file_copies_to_temp_directory(self) -> None:
		"""Test that stage_file copies a file to a staging directory."""
		with tempfile.TemporaryDirectory() as tmpdir:
			# Create a source file
			source = Path(tmpdir) / "source.txt"
			source.write_text("test content")

			transport = LocalTransport(sys.executable, runtime_dir=tmpdir)
			staged = await transport.stage_file(str(source))

			# Verify the file was copied
			assert Path(staged.remote_path).exists()
			assert Path(staged.remote_path).read_text() == "test content"
			assert staged.local_path == str(source)

	@pytest.mark.asyncio
	async def test_stage_file_with_custom_target_name(self) -> None:
		"""Test stage_file with a custom target filename."""
		with tempfile.TemporaryDirectory() as tmpdir:
			source = Path(tmpdir) / "original.txt"
			source.write_text("content")

			transport = LocalTransport(sys.executable, runtime_dir=tmpdir)
			staged = await transport.stage_file(str(source), target_name="renamed.txt")

			# Verify it was renamed
			assert "renamed.txt" in staged.remote_path
			assert Path(staged.remote_path).exists()

	@pytest.mark.asyncio
	async def test_stage_file_cleanup_callable(self) -> None:
		"""Test that the cleanup callable removes the staged file."""
		with tempfile.TemporaryDirectory() as tmpdir:
			source = Path(tmpdir) / "source.txt"
			source.write_text("test")

			transport = LocalTransport(sys.executable, runtime_dir=tmpdir)
			staged = await transport.stage_file(str(source))

			staged_path = Path(staged.remote_path)
			assert staged_path.exists()

			# Call cleanup
			if staged.cleanup:
				staged.cleanup()

			# Verify file is gone
			assert not staged_path.exists()

	@pytest.mark.asyncio
	async def test_remove_staged_file(self) -> None:
		"""Test remove_staged_file() method."""
		with tempfile.TemporaryDirectory() as tmpdir:
			source = Path(tmpdir) / "source.txt"
			source.write_text("test")

			transport = LocalTransport(sys.executable, runtime_dir=tmpdir)
			staged = await transport.stage_file(str(source))
			staged_path = Path(staged.remote_path)
			assert staged_path.exists()

			# Remove via method
			await transport.remove_staged_file(staged)
			assert not staged_path.exists()

	@pytest.mark.asyncio
	async def test_stage_file_creates_unique_staging_dirs(self) -> None:
		"""Test that each staged file gets a unique staging directory."""
		with tempfile.TemporaryDirectory() as tmpdir:
			source = Path(tmpdir) / "source.txt"
			source.write_text("test")

			transport = LocalTransport(sys.executable, runtime_dir=tmpdir)

			staged1 = await transport.stage_file(str(source), target_name="file1.txt")
			staged2 = await transport.stage_file(str(source), target_name="file2.txt")

			# Verify different staging directories
			dir1 = Path(staged1.remote_path).parent
			dir2 = Path(staged2.remote_path).parent
			assert dir1 != dir2

	@pytest.mark.asyncio
	async def test_stage_file_nonexistent_source(self) -> None:
		"""Test that stage_file raises error for nonexistent file."""
		with tempfile.TemporaryDirectory() as tmpdir:
			transport = LocalTransport(sys.executable, runtime_dir=tmpdir)

			with pytest.raises(FileNotFoundError):
				await transport.stage_file("/nonexistent/file.txt")


class TestLocalTransportIntegration:
	"""Integration tests combining multiple features."""

	@pytest.mark.asyncio
	async def test_full_fake_cli_workflow(self) -> None:
		"""Full integration test: stage file, run, cleanup."""
		if not FAKE_CLI_PATH.exists():
			pytest.skip(f"fake_cli.py not found at {FAKE_CLI_PATH}")

		with tempfile.TemporaryDirectory() as tmpdir:
			# Create a test data file
			test_file = Path(tmpdir) / "test_input.txt"
			test_file.write_text("input data")

			# Create transport
			transport = LocalTransport(sys.executable, runtime_dir=tmpdir)

			# Stage the file
			staged = await transport.stage_file(str(test_file))
			assert Path(staged.remote_path).exists()

			# Run fake_cli with a prompt
			state_dir = Path(tmpdir) / "state"
			state_dir.mkdir(exist_ok=True)

			result = await transport.run(
				[
					sys.executable,
					str(FAKE_CLI_PATH),
					"-p",
					"test prompt",
					"--output-format",
					"json",
				],
				env={"FAKE_CLI_STATE_DIR": str(state_dir)},
			)

			assert result.exit_code == 0
			response = json.loads(result.stdout)
			session_id = response["session_id"]

			# Clean up staged file
			await transport.remove_staged_file(staged)
			assert not Path(staged.remote_path).exists()

			# Verify session persistence: do another turn
			result2 = await transport.run(
				[
					sys.executable,
					str(FAKE_CLI_PATH),
					"-p",
					"follow up",
					"--resume",
					session_id,
					"--output-format",
					"json",
				],
				env={"FAKE_CLI_STATE_DIR": str(state_dir)},
			)

			assert result2.exit_code == 0
			response2 = json.loads(result2.stdout)
			assert response2["session_id"] == session_id

	@pytest.mark.asyncio
	async def test_default_runtime_dir_creation(self) -> None:
		"""Test that default runtime directory is created."""
		# Use a unique temp location
		with tempfile.TemporaryDirectory() as base_tmp:
			custom_runtime = Path(base_tmp) / "custom_runtime"
			transport = LocalTransport(sys.executable, runtime_dir=str(custom_runtime))

			assert custom_runtime.exists()
			assert custom_runtime.is_dir()


if __name__ == "__main__":
	# Run with: python -m pytest huf/ai/tests/subscription/test_transport_local.py -v
	pytest.main([__file__, "-v"])
