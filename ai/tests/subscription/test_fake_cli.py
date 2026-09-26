"""
Tests for fake_cli.py — deterministic CLI test fixture.

Exercises all major code paths and behavior contracts:
- New session creation with JSON output
- Session resumption with context continuity
- Resume with unknown session (plain-text stderr error)
- Auth status checks (ready and required states)
- Timeout simulation
- Image support (accept and reject)
- Fixed session ID determinism
- State persistence across invocations
"""

import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path


def run_fake_cli(*args, env_overrides=None):
	"""Run fake_cli.py subprocess and capture stdout/stderr/exit code.

	Args:
		*args: Command-line arguments to pass to fake_cli.py
		env_overrides: Dict of environment variable overrides

	Returns:
		Tuple of (stdout_text, stderr_text, exit_code)
	"""
	fake_cli_path = Path(__file__).parent / 'fixtures' / 'fake_cli.py'

	env = os.environ.copy()
	if env_overrides:
		env.update(env_overrides)

	result = subprocess.run(
		[sys.executable, str(fake_cli_path)] + list(args),
		capture_output=True,
		text=True,
		env=env,
	)

	return result.stdout.strip(), result.stderr.strip(), result.returncode


class TestFakeCliNewSession:
	"""Test new session creation."""

	def test_new_session_json_output(self, tmp_path):
		"""A new session should return valid JSON with session_id, result, and usage."""
		state_dir = tmp_path / 'state'
		state_dir.mkdir()

		stdout, stderr, exit_code = run_fake_cli(
			'-p', 'hello world',
			'--output-format', 'json',
			'--state-dir', str(state_dir),
		)

		assert exit_code == 0, f"Exit code should be 0, got {exit_code}. stderr: {stderr}"
		assert stderr == '', f"stderr should be empty, got: {stderr}"

		# Parse JSON response
		response = json.loads(stdout)

		# Validate structure
		assert 'session_id' in response
		assert 'result' in response
		assert 'usage' in response
		assert response['is_error'] is False
		assert response['type'] == 'result'

		# Session ID should be a valid UUID
		try:
			uuid.UUID(response['session_id'])
		except ValueError:
			raise AssertionError(f"session_id is not a valid UUID: {response['session_id']}")

		# Usage should have token counts
		assert 'input_tokens' in response['usage']
		assert 'output_tokens' in response['usage']
		assert response['usage']['input_tokens'] > 0
		assert response['usage']['output_tokens'] > 0

	def test_new_session_text_output(self, tmp_path):
		"""A new session with text format should return plain text."""
		state_dir = tmp_path / 'state'
		state_dir.mkdir()

		stdout, stderr, exit_code = run_fake_cli(
			'-p', 'hello world',
			'--output-format', 'text',
			'--state-dir', str(state_dir),
		)

		assert exit_code == 0
		assert stderr == ''
		assert 'HELLO' in stdout

	def test_new_session_fixed_session_id(self, tmp_path):
		"""With FAKE_CLI_FIXED_SESSION_ID, session ID should be deterministic."""
		state_dir = tmp_path / 'state'
		state_dir.mkdir()
		fixed_id = 'my-fixed-test-id-12345'

		stdout1, stderr1, exit_code1 = run_fake_cli(
			'-p', 'hello',
			'--output-format', 'json',
			'--state-dir', str(state_dir),
			env_overrides={'FAKE_CLI_FIXED_SESSION_ID': fixed_id},
		)

		stdout2, stderr2, exit_code2 = run_fake_cli(
			'-p', 'hello',
			'--output-format', 'json',
			'--state-dir', str(state_dir),
			env_overrides={'FAKE_CLI_FIXED_SESSION_ID': fixed_id},
		)

		response1 = json.loads(stdout1)
		response2 = json.loads(stdout2)

		# Both should have the fixed ID
		assert response1['session_id'] == fixed_id
		assert response2['session_id'] == fixed_id


class TestFakeCliResume:
	"""Test session resumption."""

	def test_resume_known_session(self, tmp_path):
		"""Resuming a known session should preserve session ID and show prior context."""
		state_dir = tmp_path / 'state'
		state_dir.mkdir()

		# Create a session
		create_out, _, create_exit = run_fake_cli(
			'-p', 'initial prompt',
			'--output-format', 'json',
			'--state-dir', str(state_dir),
			env_overrides={'FAKE_CLI_FIXED_SESSION_ID': 'test-session-123'},
		)

		create_response = json.loads(create_out)
		session_id = create_response['session_id']
		initial_result = create_response['result']

		assert create_exit == 0

		# Resume that session
		resume_out, resume_err, resume_exit = run_fake_cli(
			'-p', 'follow-up prompt',
			'--resume', session_id,
			'--output-format', 'json',
			'--state-dir', str(state_dir),
		)

		assert resume_exit == 0, f"Resume exit code should be 0, got {resume_exit}. stderr: {resume_err}"
		assert resume_err == '', f"Resume stderr should be empty, got: {resume_err}"

		resume_response = json.loads(resume_out)

		# Session ID should be stable
		assert resume_response['session_id'] == session_id, \
			"Session ID should not change on resume"

		# Result should include prior context
		assert 'previous' in resume_response['result'].lower() or \
		       'initial' in resume_response['result'].lower(), \
			f"Result should include prior context, got: {resume_response['result']}"

	def test_resume_unknown_session_error(self, tmp_path):
		"""Resuming an unknown session should return plain-text error to stderr."""
		state_dir = tmp_path / 'state'
		state_dir.mkdir()

		unknown_id = 'not-a-real-session-id-xyz'

		stdout, stderr, exit_code = run_fake_cli(
			'-p', 'hello',
			'--resume', unknown_id,
			'--output-format', 'json',
			'--state-dir', str(state_dir),
		)

		# Should exit non-zero
		assert exit_code != 0, f"Exit code should be non-zero for unknown resume, got {exit_code}"

		# Error should be plain text on stderr (NOT JSON)
		assert stderr != '', "stderr should contain error message"
		assert stdout == '', "stdout should be empty on error"

		# Error message should mention the problem
		assert 'not-a-real-session-id-xyz' in stderr or 'session' in stderr.lower()

		# Crucially: stderr is plain text, not JSON
		try:
			json.loads(stderr)
			assert False, "stderr should NOT be valid JSON (real CLI behavior)"
		except json.JSONDecodeError:
			pass  # Expected: stderr is plain text


class TestFakeCliAuthStatus:
	"""Test auth status checks."""

	def test_auth_status_ready(self, tmp_path):
		"""With default auth state, --auth-status should return ready."""
		state_dir = tmp_path / 'state'
		state_dir.mkdir()

		stdout, stderr, exit_code = run_fake_cli(
			'--auth-status',
			'--state-dir', str(state_dir),
		)

		assert exit_code == 0

		response = json.loads(stdout)
		assert response['loggedIn'] is True
		assert response['authMethod'] == 'claude.ai'
		assert response['subscriptionType'] == 'max'

	def test_auth_status_required(self, tmp_path):
		"""With FAKE_CLI_AUTH_STATE=required, invocation should fail."""
		state_dir = tmp_path / 'state'
		state_dir.mkdir()

		stdout, stderr, exit_code = run_fake_cli(
			'-p', 'hello',
			'--output-format', 'json',
			'--state-dir', str(state_dir),
			env_overrides={'FAKE_CLI_AUTH_STATE': 'required'},
		)

		# Should exit non-zero
		assert exit_code != 0, "Exit code should be non-zero when auth required"

		# Error on stderr (plain text)
		assert stderr != '', "stderr should contain auth error"
		assert 'auth' in stderr.lower()


class TestFakeCliTimeout:
	"""Test timeout simulation."""

	def test_sleep_seconds(self, tmp_path):
		"""FAKE_CLI_SLEEP_SECONDS should cause a delay before response."""
		state_dir = tmp_path / 'state'
		state_dir.mkdir()

		import time

		start = time.time()

		stdout, stderr, exit_code = run_fake_cli(
			'-p', 'hello',
			'--output-format', 'json',
			'--state-dir', str(state_dir),
			env_overrides={'FAKE_CLI_SLEEP_SECONDS': '0.5'},
		)

		elapsed = time.time() - start

		assert exit_code == 0
		assert elapsed >= 0.4, f"Should have slept at least 0.4s, elapsed: {elapsed}"

		# Response should still be valid
		response = json.loads(stdout)
		assert 'session_id' in response


class TestFakeCliImage:
	"""Test image input handling."""

	def test_image_supported(self, tmp_path):
		"""With images supported (default), --image should be accepted."""
		state_dir = tmp_path / 'state'
		state_dir.mkdir()

		# Create a dummy image file
		image_file = tmp_path / 'test.png'
		image_file.write_text('fake image data')

		stdout, stderr, exit_code = run_fake_cli(
			'-p', 'describe this image',
			'--image', str(image_file),
			'--output-format', 'json',
			'--state-dir', str(state_dir),
		)

		assert exit_code == 0
		assert stderr == ''

		response = json.loads(stdout)
		assert 'image received' in response['result'].lower()

	def test_image_unsupported(self, tmp_path):
		"""With FAKE_CLI_SUPPORTS_IMAGES=0, --image should be rejected."""
		state_dir = tmp_path / 'state'
		state_dir.mkdir()

		# Create a dummy image file
		image_file = tmp_path / 'test.png'
		image_file.write_text('fake image data')

		stdout, stderr, exit_code = run_fake_cli(
			'-p', 'describe this image',
			'--image', str(image_file),
			'--output-format', 'json',
			'--state-dir', str(state_dir),
			env_overrides={'FAKE_CLI_SUPPORTS_IMAGES': '0'},
		)

		# Should exit non-zero
		assert exit_code != 0

		# Error should be JSON on stdout (image validation error)
		error_response = json.loads(stdout)
		assert error_response['is_error'] is True
		assert 'image' in error_response['error'].lower()


class TestFakeCliStateFile:
	"""Test session state persistence."""

	def test_state_persistence(self, tmp_path):
		"""Sessions should persist to the state file and be retrievable."""
		state_dir = tmp_path / 'state'
		state_dir.mkdir()

		# Create a session
		stdout1, _, _ = run_fake_cli(
			'-p', 'first turn',
			'--output-format', 'json',
			'--state-dir', str(state_dir),
			env_overrides={'FAKE_CLI_FIXED_SESSION_ID': 'persist-test'},
		)

		response1 = json.loads(stdout1)
		session_id = response1['session_id']

		# Check state file exists
		state_file = state_dir / '.fake_cli_sessions.json'
		assert state_file.exists(), "State file should be created"

		# Read state file
		with open(state_file) as f:
			state_data = json.load(f)

		assert session_id in state_data
		assert 'created' in state_data[session_id]
		assert 'last_result' in state_data[session_id]
		assert state_data[session_id]['turns'] == 1

		# Resume should increment turns
		_, _, _ = run_fake_cli(
			'-p', 'second turn',
			'--resume', session_id,
			'--output-format', 'json',
			'--state-dir', str(state_dir),
		)

		# Re-read state file
		with open(state_file) as f:
			state_data2 = json.load(f)

		assert state_data2[session_id]['turns'] == 2


class TestFakeCliExecution:
	"""Test basic execution and error handling."""

	def test_missing_prompt(self, tmp_path):
		"""Running without -p should exit non-zero and show help."""
		state_dir = tmp_path / 'state'
		state_dir.mkdir()

		stdout, stderr, exit_code = run_fake_cli(
			'--state-dir', str(state_dir),
		)

		# Should exit non-zero
		assert exit_code != 0

	def test_py_compile_success(self):
		"""fake_cli.py should pass py_compile syntax check."""
		import py_compile

		fake_cli_path = Path(__file__).parent / 'fixtures' / 'fake_cli.py'

		try:
			py_compile.compile(str(fake_cli_path), doraise=True)
		except py_compile.PyCompileError as e:
			raise AssertionError(f"fake_cli.py has syntax errors: {e}")


def pytest_generate_tests(metafunc):
	"""Support for pytest fixtures if available."""
	if 'tmp_path' in metafunc.fixturenames:
		# Pytest handles tmp_path automatically
		pass


if __name__ == '__main__':
	# Allow running tests without pytest
	print("Run with: python -m pytest test_fake_cli.py -v")
	sys.exit(1)
