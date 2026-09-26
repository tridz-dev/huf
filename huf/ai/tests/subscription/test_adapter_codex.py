"""Tests for the Codex CLI subscription adapter.

Parser-level tests feed the REAL captured fixture content (from
``ai/tests/subscription/fixtures/real/codex/``, a sibling top-level fixtures
directory outside the ``huf.ai`` package) directly into the adapter's
JSONL-parsing helpers, per T-05-adapter-codex.

Async adapter methods are exercised via ``asyncio.run(...)`` inline (matching
the convention already used in test_adapter_base.py) rather than
pytest-asyncio, which is not a project dependency here.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from huf.ai.subscription.adapters.codex import (
	CODEX_APPROVAL_POLICY,
	CODEX_SANDBOX_MODE,
	CODEX_TRUST_FLAG,
	CodexAdapter,
	classify_codex_stderr,
	is_resume_not_found_error,
	parse_codex_jsonl,
	parse_codex_login_status,
	parse_codex_usage,
)
from huf.ai.subscription.errors import SubscriptionCLIError, SubscriptionErrorCode, SubscriptionRuntimeError
from huf.ai.subscription.transports.base import ExecutionTransport, ProcessResult, StagedFile, TransportProbe
from huf.ai.subscription.types import SubscriptionTurnRequest

# Canonical AuthStatus.state vocabulary per huf/ai/subscription/types.py's
# docstring / plan §60.1. Callers (subscription_api.py, executor.py) only
# recognize these values -- anything else (e.g. "authenticated") silently
# parks every run. See Track-Item: fix-c1-auth-status-vocabulary.
CANONICAL_AUTH_STATES = {"ready", "required", "waiting_user", "verifying", "failed", "unknown"}

# Fixtures live at the repo-root-relative path
# ai/tests/subscription/fixtures/real/codex/ — a top-level directory distinct
# from the huf.ai package tree this test file lives under.
FIXTURES_DIR = Path(__file__).resolve().parents[4] / "ai" / "tests" / "subscription" / "fixtures" / "real" / "codex"


def _read_fixture(name: str) -> str:
	path = FIXTURES_DIR / name
	if not path.exists():
		pytest.skip(f"real codex fixture not present on disk: {path}")
	return path.read_text()


class FakeTransport(ExecutionTransport):
	"""Records the argv/cwd it was called with and returns a canned result."""

	def __init__(self, result: ProcessResult) -> None:
		self.result = result
		self.calls: list[dict] = []

	async def probe(self) -> TransportProbe:
		return TransportProbe(reachable=True)

	async def run(self, argv, *, cwd=None, env=None, stdin=None, timeout=None) -> ProcessResult:
		self.calls.append({"argv": argv, "cwd": cwd, "env": env, "stdin": stdin, "timeout": timeout})
		return self.result

	async def stage_file(self, source_path: str, *, target_name: str | None = None) -> StagedFile:
		raise NotImplementedError

	async def remove_staged_file(self, staged_file: StagedFile) -> None:
		pass


class FakeRuntime:
	def __init__(self, working_directory: str | None = "/tmp/codex_ws"):
		self.name = "codex-runtime"
		self.transport_type = "local"
		self.executable = "codex"
		self.working_directory = working_directory


def _make_request(
	*, provider_session_id: str | None = None, text: str = "hello", files: list[str] | None = None
) -> SubscriptionTurnRequest:
	return SubscriptionTurnRequest(
		runtime_name="codex-runtime",
		provider_session_id=provider_session_id,
		text=text,
		files=files or [],
		model_override=None,
		run_id="run-1",
		conversation_id=None,
		timeout_seconds=60,
	)


# --- Parser tests against real fixture content ------------------------------


def test_parse_create_session_jsonl_real_fixture_extracts_thread_and_usage():
	stdout = _read_fixture("create_session.jsonl")
	parsed = parse_codex_jsonl(stdout)

	assert parsed["thread_id"] == "01a0da32-e450-7691-a8e5-579223d9a47a"
	assert parsed["final_text"] == "HELLO"
	assert parsed["turn_status"] == "completed"
	assert parsed["usage"] == {
		"input_tokens": 18669,
		"cached_input_tokens": 8960,
		"output_tokens": 6,
		"reasoning_output_tokens": 0,
	}


def test_parse_create_session_does_not_fail_turn_on_nonfatal_error_item():
	"""Real fixture: an item.completed(type='error') skills-budget warning
	appears mid-turn, but the turn still ends in turn.completed. Only
	turn.failed should mark failure."""
	stdout = _read_fixture("create_session.jsonl")
	parsed = parse_codex_jsonl(stdout)

	error_items = [item for item in parsed["items"] if item.get("type") == "error"]
	assert len(error_items) == 1
	assert "skills context budget" in error_items[0]["message"]

	# Despite the error-typed item, the turn is NOT considered failed.
	assert parsed["turn_status"] == "completed"
	assert parsed["turn_failed_reason"] is None


def test_parse_resume_turn_jsonl_real_fixture():
	stdout = _read_fixture("resume_turn.jsonl")
	parsed = parse_codex_jsonl(stdout)

	assert parsed["thread_id"] == "01a0da32-e450-7691-a8e5-579223d9a47a"
	assert parsed["final_text"] == "HELLO"
	assert parsed["turn_status"] == "completed"
	usage = parse_codex_usage(parsed["usage"])
	assert usage["cached_input_tokens"] == 27136


def test_parse_usage_normalizes_real_shape():
	raw = {"input_tokens": 1, "cached_input_tokens": 2, "output_tokens": 3, "reasoning_output_tokens": 4}
	assert parse_codex_usage(raw) == raw


# --- Malformed resume: plain-text stderr, not JSON --------------------------


def test_malformed_resume_is_plain_text_not_json():
	stderr = _read_fixture("error_malformed_resume.txt")
	assert is_resume_not_found_error(stderr)

	# Sanity: it truly is not JSON (would raise if json.loads succeeded on
	# the whole blob the way a JSONL event would parse per-line).
	with pytest.raises(json.JSONDecodeError):
		json.loads(stderr.strip())


def test_run_turn_classifies_malformed_resume_as_error_result_not_crash():
	stderr = _read_fixture("error_malformed_resume.txt")
	transport = FakeTransport(ProcessResult(stdout="", stderr=stderr, exit_code=1))
	adapter = CodexAdapter(transport)
	request = _make_request(provider_session_id="00000000-0000-0000-0000-000000000000", text="hi")

	result = asyncio.run(adapter.run_turn(FakeRuntime(), request))

	assert result.status == "error"
	assert result.provider_session_id == "00000000-0000-0000-0000-000000000000"
	assert "no rollout found" in (result.raw_debug_ref or "").lower()


# --- H9: resume-not-found / auth-required must populate a classified code ---
# in `events` so executor.py's _extract_error_code() can read it, matching
# the pattern adapters/claude.py already implements (see
# ClaudeAdapter._classify_stderr / _parse_turn_output).


def test_classify_codex_stderr_resume_not_found():
	stderr = _read_fixture("error_malformed_resume.txt")
	assert classify_codex_stderr(stderr) == SubscriptionErrorCode.SESSION_NOT_FOUND


def test_classify_codex_stderr_auth_required():
	assert classify_codex_stderr("Not logged in") == SubscriptionErrorCode.AUTH_REQUIRED
	assert classify_codex_stderr("Error: not authenticated with this account") == SubscriptionErrorCode.AUTH_REQUIRED


def test_classify_codex_stderr_generic_failure():
	assert classify_codex_stderr("boom: something else broke") == SubscriptionErrorCode.CLI_PROCESS_FAILED


def test_run_turn_resume_not_found_populates_classified_error_code_in_events():
	"""H9 regression guard: a prior version returned events=[] here, so
	executor.py::_extract_error_code() could never see SESSION_NOT_FOUND for
	Codex and the session binding was never marked Unavailable."""
	stderr = _read_fixture("error_malformed_resume.txt")
	transport = FakeTransport(ProcessResult(stdout="", stderr=stderr, exit_code=1))
	adapter = CodexAdapter(transport)
	request = _make_request(provider_session_id="00000000-0000-0000-0000-000000000000", text="hi")

	result = asyncio.run(adapter.run_turn(FakeRuntime(), request))

	assert result.status == "error"
	assert result.events, "events must not be empty -- executor._extract_error_code() reads events[0]['code']"
	assert result.events[0]["code"] == SubscriptionErrorCode.SESSION_NOT_FOUND.value


def test_run_turn_auth_required_mid_turn_populates_classified_error_code_not_generic_failure():
	"""Related H9 finding: 'Codex ... logouts fail the run instead of parking
	it' -- a runtime logout surfacing mid-turn (auth-required condition during
	what should be a normal resume) must come back as a classified
	AUTH_REQUIRED result, not raise a generic SubscriptionCLIError."""
	transport = FakeTransport(ProcessResult(stdout="", stderr="Not logged in", exit_code=1))
	adapter = CodexAdapter(transport)
	request = _make_request(provider_session_id="01a0da32-e450-7691-a8e5-579223d9a47a", text="hi")

	result = asyncio.run(adapter.run_turn(FakeRuntime(), request))

	assert result.status == "error"
	assert result.events[0]["code"] == SubscriptionErrorCode.AUTH_REQUIRED.value
	assert result.auth_reason is not None


# --- Auth status: plain text, no shared format ------------------------------


def test_parse_login_status_real_fixture_authenticated():
	stdout = _read_fixture("auth_status.txt")
	status = parse_codex_login_status(stdout)

	assert status.state == "ready"
	assert status.method == "ChatGPT"
	assert status.message == "Logged in using ChatGPT"


def test_parse_login_status_unauthenticated_text():
	status = parse_codex_login_status("Not logged in")
	assert status.state == "required"


def test_parse_login_status_unrecognized_shape_is_unknown_not_guessed():
	status = parse_codex_login_status("some future CLI output we've never seen")
	assert status.state == "unknown"


@pytest.mark.parametrize(
	"text",
	[
		"Logged in using ChatGPT",  # logged in
		"Not logged in",  # logged out
		"not authenticated with this account",  # logged out, alternate wording
		"some future CLI output we've never seen",  # unrecognized/malformed
		"",  # empty output
	],
)
def test_parse_login_status_never_returns_non_canonical_state(text):
	"""CRITICAL regression guard (Track-Item: fix-c1-auth-status-vocabulary):
	parse_codex_login_status() must only ever report a state from the
	canonical vocabulary documented on AuthStatus."""
	status = parse_codex_login_status(text)
	assert status.state in CANONICAL_AUTH_STATES


@pytest.mark.parametrize(
	"stdout,exit_code",
	[
		("Logged in using ChatGPT", 0),
		("Not logged in", 0),
		("garbage \x00 output", 1),
		("", 1),
	],
)
def test_check_auth_never_returns_non_canonical_state(stdout, exit_code):
	transport = FakeTransport(ProcessResult(stdout=stdout, stderr="", exit_code=exit_code))
	adapter = CodexAdapter(transport)

	status = asyncio.run(adapter.check_auth(FakeRuntime()))

	assert status.state in CANONICAL_AUTH_STATES


def test_check_auth_uses_parser():
	transport = FakeTransport(ProcessResult(stdout="Logged in using ChatGPT", stderr="", exit_code=0))
	adapter = CodexAdapter(transport)

	status = asyncio.run(adapter.check_auth(FakeRuntime()))

	assert status.state == "ready"
	assert transport.calls[0]["argv"] == ["codex", "login", "status"]


# --- Working-directory trust-check logic ------------------------------------


def test_run_turn_raises_runtime_unreachable_without_working_directory():
	transport = FakeTransport(ProcessResult(stdout="", stderr="", exit_code=0))
	adapter = CodexAdapter(transport)
	request = _make_request()

	with pytest.raises(SubscriptionRuntimeError) as excinfo:
		asyncio.run(adapter.run_turn(FakeRuntime(working_directory=None), request))

	assert excinfo.value.code == SubscriptionErrorCode.RUNTIME_UNREACHABLE
	# No CLI call should have been attempted.
	assert transport.calls == []


def test_run_turn_always_passes_documented_trust_flag_and_least_priv_sandbox():
	stdout = _read_fixture("create_session.jsonl")
	transport = FakeTransport(ProcessResult(stdout=stdout, stderr="", exit_code=0))
	adapter = CodexAdapter(transport)
	request = _make_request(text="Say hello and reply with exactly one word: HELLO")

	asyncio.run(adapter.run_turn(FakeRuntime(working_directory="/tmp/codex_ws"), request))

	assert len(transport.calls) == 1
	call = transport.calls[0]
	argv = call["argv"]
	assert call["cwd"] == "/tmp/codex_ws"
	assert CODEX_TRUST_FLAG in argv
	assert "--sandbox" in argv and CODEX_SANDBOX_MODE in argv
	assert "--ask-for-approval" in argv and CODEX_APPROVAL_POLICY in argv
	# Never the unattended-writes-allowed / bypass-everything modes.
	assert "workspace-write" not in argv
	assert "danger-full-access" not in argv
	assert "--dangerously-bypass-approvals-and-sandbox" not in argv


def test_run_turn_ask_for_approval_is_placed_before_exec_not_after():
	"""H2 regression guard: --ask-for-approval is documented ONLY under the
	TOP-LEVEL `codex --help` (help_output_top.txt) and does NOT appear at all
	in `codex exec --help` (help_output_exec.txt) -- it must come before the
	`exec` subcommand, e.g. `codex --ask-for-approval never exec ...`, never
	`codex exec --ask-for-approval never ...`."""
	stdout = _read_fixture("create_session.jsonl")
	transport = FakeTransport(ProcessResult(stdout=stdout, stderr="", exit_code=0))
	adapter = CodexAdapter(transport)
	request = _make_request(text="Say hello and reply with exactly one word: HELLO")

	asyncio.run(adapter.run_turn(FakeRuntime(working_directory="/tmp/codex_ws"), request))

	argv = transport.calls[0]["argv"]
	exec_index = argv.index("exec")
	approval_index = argv.index("--ask-for-approval")
	assert approval_index < exec_index, f"--ask-for-approval must precede exec, got argv={argv}"
	assert argv[approval_index + 1] == CODEX_APPROVAL_POLICY
	# --sandbox is documented on both sides of `exec` in the real fixtures, so
	# it is only required to appear somewhere in argv, not before `exec`.
	assert "--sandbox" in argv


def test_run_turn_exact_argv_for_create_session():
	"""Assert the full argv shape, not just membership, so a future edit that
	reorders flags in a way that changes CLI parsing is caught immediately."""
	stdout = _read_fixture("create_session.jsonl")
	transport = FakeTransport(ProcessResult(stdout=stdout, stderr="", exit_code=0))
	adapter = CodexAdapter(transport)
	request = _make_request(text="Say hello and reply with exactly one word: HELLO")

	asyncio.run(adapter.run_turn(FakeRuntime(working_directory="/tmp/codex_ws"), request))

	call = transport.calls[0]
	assert call["argv"] == [
		"codex",
		"--ask-for-approval",
		CODEX_APPROVAL_POLICY,
		"exec",
		"--json",
		CODEX_TRUST_FLAG,
		"--sandbox",
		CODEX_SANDBOX_MODE,
	]
	# H2/argv-injection fix: the prompt text goes over stdin, never argv.
	assert call["stdin"] == request.text
	assert request.text not in call["argv"]


def test_run_turn_resume_uses_documented_verbatim_flag_order():
	stdout = _read_fixture("resume_turn.jsonl")
	transport = FakeTransport(ProcessResult(stdout=stdout, stderr="", exit_code=0))
	adapter = CodexAdapter(transport)
	request = _make_request(
		provider_session_id="01a0da32-e450-7691-a8e5-579223d9a47a",
		text="What was the exact word I told you to reply with in the previous message? Answer in one word.",
	)

	result = asyncio.run(adapter.run_turn(FakeRuntime(working_directory="/tmp/codex_ws"), request))

	call = transport.calls[0]
	argv = call["argv"]
	# LIVE-VERIFIED against real codex-cli 0.144.6: `codex exec resume --help`
	# does not accept `--ask-for-approval` or `--sandbox` at all (only
	# `exec`, not `exec resume`, documents them) -- passing either causes
	# `error: unexpected argument '--sandbox' found` (exit 2) and the
	# resumed turn never runs. Sandbox/approval mode is fixed at session
	# creation and carries over automatically on resume.
	assert argv == [
		"codex",
		"exec",
		"resume",
		"--json",
		"01a0da32-e450-7691-a8e5-579223d9a47a",
		CODEX_TRUST_FLAG,
	]
	assert call["stdin"] == request.text
	assert "--sandbox" not in argv
	assert "--ask-for-approval" not in argv
	assert result.status == "success"
	assert result.final_text == "HELLO"
	assert result.provider_session_id == "01a0da32-e450-7691-a8e5-579223d9a47a"


# --- H5: cwd must always be explicitly passed to the transport ---------------


def test_run_turn_always_passes_explicit_cwd_never_none():
	stdout = _read_fixture("create_session.jsonl")
	transport = FakeTransport(ProcessResult(stdout=stdout, stderr="", exit_code=0))
	adapter = CodexAdapter(transport)
	request = _make_request(text="hello")

	asyncio.run(adapter.run_turn(FakeRuntime(working_directory="/tmp/codex_ws"), request))

	call = transport.calls[0]
	assert call["cwd"] == "/tmp/codex_ws"
	assert call["cwd"] is not None


# --- Passthrough boundary self-check ----------------------------------------


def test_run_turn_argv_never_contains_huf_generated_system_or_mcp_content():
	"""CRITICAL passthrough constraint: only request.text/request.files may
	appear in the constructed argv — never HUF Agent instructions, an
	HUF-generated MCP config, or conversation history."""
	stdout = _read_fixture("create_session.jsonl")
	transport = FakeTransport(ProcessResult(stdout=stdout, stderr="", exit_code=0))
	adapter = CodexAdapter(transport)

	forbidden_markers = [
		"HUF_SYSTEM_PROMPT",
		"AGENT_INSTRUCTIONS",
		"--mcp-config",
		"mcp_config.json",
		"CONVERSATION_HISTORY",
	]
	request = _make_request(text="Say hello and reply with exactly one word: HELLO")

	asyncio.run(adapter.run_turn(FakeRuntime(working_directory="/tmp/codex_ws"), request))

	call = transport.calls[0]
	joined = " ".join(call["argv"])
	for marker in forbidden_markers:
		assert marker not in joined
	# The only free-form content passed through at all is request.text, and it
	# travels via stdin (see argv-injection fix), never as an argv element.
	assert request.text not in call["argv"]
	assert call["stdin"] == request.text


def test_create_session_raises_cli_error_no_standalone_command():
	transport = FakeTransport(ProcessResult(stdout="", stderr="", exit_code=0))
	adapter = CodexAdapter(transport)
	request = _make_request()

	with pytest.raises(SubscriptionCLIError):
		asyncio.run(adapter.create_session(request))


def test_validate_session_reports_not_independently_verifiable():
	transport = FakeTransport(ProcessResult(stdout="", stderr="", exit_code=0))
	adapter = CodexAdapter(transport)

	status = asyncio.run(adapter.validate_session(FakeRuntime(), "some-id"))
	assert status.exists is True
	assert status.detail == "not independently verifiable"


def test_delete_session_reports_provider_retained():
	transport = FakeTransport(ProcessResult(stdout="", stderr="", exit_code=0))
	adapter = CodexAdapter(transport)

	result = asyncio.run(adapter.delete_session(FakeRuntime(), "some-id"))
	assert result.cleanup_status == "provider_retained"


def test_probe_reports_automation_not_supported_by_default():
	transport = FakeTransport(ProcessResult(stdout="codex-cli 0.144.6", stderr="", exit_code=0))
	adapter = CodexAdapter(transport)

	caps = asyncio.run(adapter.probe(FakeRuntime()))
	assert caps.automation_supported is False
	assert caps.supports_json is True
	assert caps.supports_session_resume is True
	# Track-Item: fix-h5-codex-credential-read-leak — live-verified against a
	# real, authenticated codex-cli 0.144.6 install that `--sandbox
	# read-only` does not confine filesystem *reads* to the working
	# directory (only writes/shell side effects are blocked); a forwarded
	# prompt can still read and echo back an arbitrary file, including the
	# runtime's own ~/.codex/auth.json. No CLI flag or env-var jail was
	# found that closes this, so probe() must report the gap rather than
	# silently claiming isolation. See codex.py's module docstring "ACTIVE
	# KNOWN LIMITATION" section for the full empirical transcript.
	assert caps.filesystem_isolation_verified is False
