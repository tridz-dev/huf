"""Tests for ClaudeAdapter.

Two kinds of coverage, per the task:

1. End-to-end tests against the deterministic fake CLI
   (fixtures/fake_cli.py) run via subprocess through a real LocalTransport.
2. Parser-only tests that feed the REAL captured fixture content from
   fixtures/real/claude/ directly into the adapter's parsing helpers, with
   no subprocess involved, to prove the parser handles actual real-world
   output shapes -- including the plain-text-stderr-on-malformed-resume case.

No pytest-asyncio is installed in this environment, so async adapter methods
are driven with asyncio.run() inside ordinary sync test functions.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from huf.ai.subscription.adapters.claude import ClaudeAdapter
from huf.ai.subscription.errors import SubscriptionCLIError, SubscriptionError, SubscriptionErrorCode
from huf.ai.subscription.transports.base import ProcessResult
from huf.ai.subscription.transports.local import LocalTransport
from huf.ai.subscription.types import SubscriptionTurnRequest

# Fixtures live in a sibling top-level directory outside the `huf` app
# package (ai/tests/subscription/fixtures/, at the worktree root), not
# alongside this test file -- mirrors test_adapter_codex.py's convention.
FIXTURES_DIR = Path(__file__).resolve().parents[4] / "ai" / "tests" / "subscription" / "fixtures"
REAL_CLAUDE_DIR = FIXTURES_DIR / "real" / "claude"
FAKE_CLI_PATH = FIXTURES_DIR / "fake_cli.py"


def _run(coro):
	return asyncio.run(coro)


def _make_request(
	*,
	text: str = "hello",
	provider_session_id: str | None = None,
	files: list[str] | None = None,
	model_override: str | None = None,
	run_id: str | None = None,
	timeout_seconds: int = 30,
) -> SubscriptionTurnRequest:
	return SubscriptionTurnRequest(
		runtime_name="claude-test-runtime",
		provider_session_id=provider_session_id,
		text=text,
		files=files or [],
		model_override=model_override,
		run_id=run_id or str(uuid.uuid4()),
		conversation_id=None,
		timeout_seconds=timeout_seconds,
	)


# ---------------------------------------------------------------------------
# Fake-CLI (subprocess, via LocalTransport) tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_cli_env(tmp_path, monkeypatch):
	"""Isolate fake_cli's session state per test and point at a fixed session id."""
	state_dir = tmp_path / "fake_cli_state"
	monkeypatch.setenv("FAKE_CLI_STATE_DIR", str(state_dir))
	monkeypatch.delenv("FAKE_CLI_AUTH_STATE", raising=False)
	monkeypatch.delenv("FAKE_CLI_SUPPORTS_IMAGES", raising=False)
	monkeypatch.delenv("FAKE_CLI_SLEEP_SECONDS", raising=False)
	monkeypatch.delenv("FAKE_CLI_FIXED_SESSION_ID", raising=False)
	return state_dir


class FakeCLIAdapter(ClaudeAdapter):
	"""ClaudeAdapter pointed at the deterministic fake CLI instead of `claude`.

	fake_cli.py (huf/ai/tests/subscription/fixtures/fake_cli.py, prior task's
	shared fixture) is a generic stand-in for a subscription CLI and only
	implements the cross-provider surface documented in its own module
	docstring (-p/--resume/--session-id/--output-format/--auth-status/--image)
	-- it does not know Claude-specific flags like --strict-mcp-config or
	--restricted. Those two flags are exercised directly in the argv
	self-check tests below instead; here they're stripped so the fake CLI
	subprocess run exercises the adapter's session-lifecycle and error-parsing
	logic end to end.
	"""

	DEFAULT_EXECUTABLE = sys.executable
	_FAKE_CLI_UNSUPPORTED_FLAGS = {"--strict-mcp-config", "--restricted"}

	def _build_argv(self, **kwargs):
		argv = super()._build_argv(**kwargs)
		filtered = [a for a in argv if a not in self._FAKE_CLI_UNSUPPORTED_FLAGS]
		# argv[0] is the python interpreter; splice the fake_cli.py script in
		# as the actual "command" so it runs as `python fake_cli.py <rest>`.
		return [filtered[0], str(FAKE_CLI_PATH)] + filtered[1:]


def _fake_transport() -> LocalTransport:
	return LocalTransport(executable=sys.executable)


def test_create_session_against_fake_cli(fake_cli_env):
	adapter = FakeCLIAdapter(_fake_transport())
	request = _make_request(text="hello world")

	session = _run(adapter.create_session(request))

	assert session.session_id
	assert session.created_at


def test_run_turn_create_then_resume_against_fake_cli(fake_cli_env):
	adapter = FakeCLIAdapter(_fake_transport())

	first_request = _make_request(text="first turn")
	first_result = _run(adapter.run_turn(runtime=None, request=first_request))

	assert first_result.status == "success"
	assert first_result.provider_session_id
	assert first_result.final_text and "HELLO" in first_result.final_text

	second_request = _make_request(
		text="second turn", provider_session_id=first_result.provider_session_id
	)
	second_result = _run(adapter.run_turn(runtime=None, request=second_request))

	assert second_result.status == "success"
	assert second_result.provider_session_id == first_result.provider_session_id
	assert "previous" in (second_result.final_text or "")


def test_run_turn_resume_unknown_session_against_fake_cli(fake_cli_env):
	adapter = FakeCLIAdapter(_fake_transport())
	request = _make_request(text="hi", provider_session_id="not-a-real-session-id-000")

	result = _run(adapter.run_turn(runtime=None, request=request))

	assert result.status == "error"
	assert result.events
	assert result.events[0]["code"] == SubscriptionErrorCode.SESSION_NOT_FOUND.value


def test_run_turn_auth_required_against_fake_cli(fake_cli_env, monkeypatch):
	monkeypatch.setenv("FAKE_CLI_AUTH_STATE", "required")
	# LocalTransport only forwards an explicit allowlist of env vars to the
	# child process (security hardening from a prior task); extend it here so
	# the fake CLI's env-var-driven auth-failure simulation actually reaches
	# the subprocess.
	monkeypatch.setattr(
		LocalTransport, "ALLOWED_ENV_VARS", LocalTransport.ALLOWED_ENV_VARS | {"FAKE_CLI_AUTH_STATE"}
	)
	adapter = FakeCLIAdapter(_fake_transport())
	request = _make_request(text="hi")

	result = _run(adapter.run_turn(runtime=None, request=request))

	assert result.status == "error"
	assert result.events[0]["code"] == SubscriptionErrorCode.AUTH_REQUIRED.value


def test_run_turn_rejects_files_with_vision_unsupported(fake_cli_env):
	adapter = FakeCLIAdapter(_fake_transport())
	request = _make_request(text="hi", files=["/tmp/some-image.png"])

	with pytest.raises(SubscriptionError) as excinfo:
		_run(adapter.run_turn(runtime=None, request=request))

	assert excinfo.value.code == SubscriptionErrorCode.VISION_UNSUPPORTED


def test_create_session_rejects_files_with_vision_unsupported(fake_cli_env):
	adapter = FakeCLIAdapter(_fake_transport())
	request = _make_request(text="hi", files=["/tmp/some-image.png"])

	with pytest.raises(SubscriptionError) as excinfo:
		_run(adapter.create_session(request))

	assert excinfo.value.code == SubscriptionErrorCode.VISION_UNSUPPORTED


def test_delete_session_is_provider_retained(fake_cli_env):
	adapter = FakeCLIAdapter(_fake_transport())
	result = _run(adapter.delete_session(runtime=None, session_id="whatever"))
	assert result.cleanup_status == "provider_retained"


def test_validate_session_best_effort(fake_cli_env):
	adapter = FakeCLIAdapter(_fake_transport())
	status = _run(adapter.validate_session(runtime=None, session_id="whatever"))
	assert status.exists is True
	assert "not independently verifiable" in (status.detail or "")


# ---------------------------------------------------------------------------
# Parser-only tests against REAL captured fixtures (no subprocess)
# ---------------------------------------------------------------------------


def _load_real(name: str) -> str:
	return (REAL_CLAUDE_DIR / name).read_text()


def test_parses_real_create_session_json():
	adapter = ClaudeAdapter(transport=None)
	raw = _load_real("create_session.json")
	result = ProcessResult(stdout=raw, stderr="", exit_code=0)

	turn_result = adapter._parse_turn_output(argv=[], result=result)

	assert turn_result.status == "success"
	assert turn_result.final_text == "HELLO"
	assert turn_result.provider_session_id == "f50fa1d9-1f4f-4449-97b4-99aca3c6bbc7"
	assert turn_result.usage["input_tokens"] == 2
	assert turn_result.usage["cache_creation_input_tokens"] == 20685


def test_parses_real_resume_turn_json_keeps_same_session_id():
	adapter = ClaudeAdapter(transport=None)
	raw = _load_real("resume_turn.json")
	result = ProcessResult(stdout=raw, stderr="", exit_code=0)

	turn_result = adapter._parse_turn_output(argv=[], result=result)

	assert turn_result.status == "success"
	assert turn_result.provider_session_id == "f50fa1d9-1f4f-4449-97b4-99aca3c6bbc7"
	assert turn_result.final_text == "HELLO"


def test_parses_real_malformed_resume_plain_text_stderr_without_raising():
	"""The CRITICAL case: real Claude emits plain-text stderr, not JSON,
	on a malformed --resume id, even with --output-format json requested.
	The parser must map this to a status="error" result, never raise.
	"""
	adapter = ClaudeAdapter(transport=None)
	stderr_text = _load_real("error_malformed_resume.txt")
	# stdout is empty on this real failure (non-JSON, exit 1)
	result = ProcessResult(stdout="", stderr=stderr_text, exit_code=1)

	turn_result = adapter._parse_turn_output(argv=[], result=result)

	assert turn_result.status == "error"
	assert turn_result.final_text is None
	assert turn_result.events
	assert turn_result.events[0]["code"] == SubscriptionErrorCode.SESSION_NOT_FOUND.value
	# Sanitized message still carries the diagnostic substrings from the real CLI
	assert "not a UUID" in turn_result.events[0]["message"]


def test_parses_real_auth_status_json():
	adapter = ClaudeAdapter(transport=None)
	raw = json.loads(_load_real("auth_status.json"))
	assert raw["loggedIn"] is True
	assert raw["authMethod"] == "claude.ai"
	# Exercise check_auth's parsing logic directly via a fake transport that
	# returns this exact real JSON body.

	class _StubTransport:
		async def run(self, argv, **kwargs):
			return ProcessResult(stdout=_load_real("auth_status.json"), stderr="", exit_code=0)

	adapter2 = ClaudeAdapter(transport=_StubTransport())
	status = _run(adapter2.check_auth(runtime=None))

	assert status.state == "authenticated"
	assert status.method == "claude.ai"


def test_classify_stderr_matches_real_malformed_resume_text():
	adapter = ClaudeAdapter(transport=None)
	stderr_text = _load_real("error_malformed_resume.txt")
	code = adapter._classify_stderr(stderr_text)
	assert code == SubscriptionErrorCode.SESSION_NOT_FOUND


# ---------------------------------------------------------------------------
# Passthrough-boundary self-check
# ---------------------------------------------------------------------------

_FORBIDDEN_ARGV_PATTERNS = ("--mcp-config", "--append-system-prompt")


def test_argv_never_contains_forbidden_passthrough_flags_create():
	adapter = ClaudeAdapter(transport=None)
	argv = adapter._build_argv(
		text="anything",
		session_id=str(uuid.uuid4()),
		resume_id=None,
		model_override="claude-opus-5-5",
	)
	for forbidden in _FORBIDDEN_ARGV_PATTERNS:
		assert forbidden not in argv, f"forbidden flag {forbidden!r} found in argv: {argv}"


def test_argv_never_contains_forbidden_passthrough_flags_resume():
	adapter = ClaudeAdapter(transport=None)
	argv = adapter._build_argv(
		text="anything",
		session_id=None,
		resume_id=str(uuid.uuid4()),
		model_override=None,
	)
	for forbidden in _FORBIDDEN_ARGV_PATTERNS:
		assert forbidden not in argv, f"forbidden flag {forbidden!r} found in argv: {argv}"


def test_argv_includes_strict_mcp_config_and_restricted_but_no_mcp_config_value():
	"""--strict-mcp-config suppresses ambient MCP config (allowed); --mcp-config
	(which would carry an actual config, HUF-generated or otherwise) must never
	appear."""
	adapter = ClaudeAdapter(transport=None)
	argv = adapter._build_argv(
		text="anything", session_id=str(uuid.uuid4()), resume_id=None, model_override=None
	)
	assert "--strict-mcp-config" in argv
	assert "--restricted" in argv
	assert "--mcp-config" not in argv
