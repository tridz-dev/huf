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

# Canonical AuthStatus.state vocabulary per huf/ai/subscription/types.py's
# docstring / plan §60.1. Callers (subscription_api.py, executor.py) only
# recognize these values -- anything else (e.g. "authenticated") silently
# parks every run. See Track-Item: fix-c1-auth-status-vocabulary.
CANONICAL_AUTH_STATES = {"ready", "required", "waiting_user", "verifying", "failed", "unknown"}

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
		filtered = []
		skip_next = False
		for arg in argv:
			if skip_next:
				skip_next = False
				continue
			if arg in self._FAKE_CLI_UNSUPPORTED_FLAGS:
				continue
			if arg == "--tools":
				# fake_cli.py doesn't know --tools either; drop the flag AND
				# its value ("") together, unlike the plain boolean flags above.
				skip_next = True
				continue
			filtered.append(arg)
		# argv[0] is the python interpreter; splice the fake_cli.py script in
		# as the actual "command" so it runs as `python fake_cli.py <rest>`.
		return [filtered[0], str(FAKE_CLI_PATH)] + filtered[1:]


def _fake_transport() -> LocalTransport:
	return LocalTransport(executable=sys.executable)


def test_create_session_refuses_and_points_to_run_turn(fake_cli_env):
	"""H4/H5 fix: create_session's fixed signature (adapters/base.py) carries
	no `runtime` handle, so it structurally cannot resolve `runtime.cli_path`
	or a safe `runtime.working_directory`/scratch cwd -- exactly how it used
	to end up hardcoding "claude" with no cwd. It now refuses clearly instead
	of running a turn with the wrong binary/no working directory; the real
	executor (executor.py::_execute_inner) never calls this method anyway, it
	always goes through run_turn."""
	adapter = FakeCLIAdapter(_fake_transport())
	request = _make_request(text="hello world")

	with pytest.raises(SubscriptionCLIError) as excinfo:
		_run(adapter.create_session(request))

	assert "run_turn" in str(excinfo.value)


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


def test_create_session_refuses_even_with_files(fake_cli_env):
	"""create_session now refuses unconditionally (see
	test_create_session_refuses_and_points_to_run_turn) -- it never reaches
	the point of inspecting request.files, so this stays CLI_PROCESS_FAILED
	rather than VISION_UNSUPPORTED. run_turn is what still enforces the
	vision-unsupported rejection (see test_run_turn_rejects_files_with_vision_unsupported)."""
	adapter = FakeCLIAdapter(_fake_transport())
	request = _make_request(text="hi", files=["/tmp/some-image.png"])

	with pytest.raises(SubscriptionCLIError) as excinfo:
		_run(adapter.create_session(request))

	assert excinfo.value.code == SubscriptionErrorCode.CLI_PROCESS_FAILED


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

	assert status.state == "ready"
	assert status.method == "claude.ai"


class _StubTransportWithStdout:
	def __init__(self, stdout: str = "", stderr: str = "", exit_code: int = 0):
		self._stdout = stdout
		self._stderr = stderr
		self._exit_code = exit_code

	async def run(self, argv, **kwargs):
		return ProcessResult(stdout=self._stdout, stderr=self._stderr, exit_code=self._exit_code)


@pytest.mark.parametrize(
	"stdout,stderr,exit_code",
	[
		# Logged in (real fixture shape).
		(json.dumps({"loggedIn": True, "authMethod": "claude.ai"}), "", 0),
		# Logged out.
		(json.dumps({"loggedIn": False}), "", 0),
		# Malformed / non-JSON stdout.
		("not json at all {{{", "some stderr", 1),
		# Empty stdout, process errored.
		("", "boom", 1),
	],
)
def test_check_auth_never_returns_non_canonical_state(stdout, stderr, exit_code):
	"""CRITICAL regression guard (Track-Item: fix-c1-auth-status-vocabulary):
	check_auth() must only ever report a state from the canonical vocabulary
	documented on AuthStatus -- every caller only recognizes those values, so
	anything else (e.g. the old "authenticated"/"unauthenticated" bug) makes
	the executor park every run forever."""
	adapter = ClaudeAdapter(transport=_StubTransportWithStdout(stdout, stderr, exit_code))
	status = _run(adapter.check_auth(runtime=None))
	assert status.state in CANONICAL_AUTH_STATES


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


def test_argv_includes_tools_disabled_alongside_restricted():
	"""H5 fix: --restricted alone still 'confines the file tools to the
	working directories' per help_output.txt -- Read/Write/Edit remain
	available there. --tools "" additionally disables every built-in tool,
	which is the strictest documented combination and costs nothing since
	this adapter never wires HUF tools to the CLI anyway."""
	adapter = ClaudeAdapter(transport=None)
	argv = adapter._build_argv(
		text="anything", session_id=str(uuid.uuid4()), resume_id=None, model_override=None
	)
	assert "--tools" in argv
	assert argv[argv.index("--tools") + 1] == ""


# ---------------------------------------------------------------------------
# H4: turn-execution argv must use runtime.cli_path, not a hardcoded "claude"
# ---------------------------------------------------------------------------


def test_build_argv_uses_configured_executable_not_hardcoded_claude():
	adapter = ClaudeAdapter(transport=None)
	argv = adapter._build_argv(
		text="hi",
		session_id=str(uuid.uuid4()),
		resume_id=None,
		model_override=None,
		executable="/opt/custom/claude-cli",
	)
	assert argv[0] == "/opt/custom/claude-cli"


def test_build_argv_falls_back_to_bare_claude_when_no_executable_given():
	adapter = ClaudeAdapter(transport=None)
	argv = adapter._build_argv(
		text="hi", session_id=str(uuid.uuid4()), resume_id=None, model_override=None
	)
	assert argv[0] == ClaudeAdapter.DEFAULT_EXECUTABLE == "claude"


def test_run_turn_uses_runtime_cli_path_not_hardcoded_claude(fake_cli_env):
	"""Regression guard for H4: run_turn is the actual turn-execution path the
	real executor calls (create_session is unreachable in practice -- see its
	docstring) and previously always started argv with the bare string
	"claude" instead of `runtime.cli_path`, unlike probe/check_auth/
	begin_auth/logout (fixed in commit 8fb114c6)."""
	adapter = ClaudeAdapter(_fake_transport())
	seen_argv: list[list[str]] = []

	class _RecordingTransport:
		async def run(self, argv, **kwargs):
			seen_argv.append(argv)
			return ProcessResult(
				stdout=json.dumps({"result": "HELLO", "session_id": str(uuid.uuid4()), "usage": {}}),
				stderr="",
				exit_code=0,
			)

	adapter.transport = _RecordingTransport()
	runtime = SimpleNamespace(cli_path="/opt/custom/claude-cli", working_directory=None)
	request = _make_request(text="hello")

	result = _run(adapter.run_turn(runtime, request))

	assert result.status == "success"
	assert seen_argv, "transport.run was never called"
	assert seen_argv[0][0] == "/opt/custom/claude-cli"
	assert seen_argv[0][0] != ClaudeAdapter.DEFAULT_EXECUTABLE


# ---------------------------------------------------------------------------
# H5: turn-execution must always pass an explicit cwd, never $HOME/unset
# ---------------------------------------------------------------------------


def test_run_turn_passes_configured_working_directory_as_cwd(tmp_path):
	adapter = ClaudeAdapter(_fake_transport())
	seen_kwargs: list[dict] = []

	class _RecordingTransport:
		async def run(self, argv, **kwargs):
			seen_kwargs.append(kwargs)
			return ProcessResult(
				stdout=json.dumps({"result": "HELLO", "session_id": str(uuid.uuid4()), "usage": {}}),
				stderr="",
				exit_code=0,
			)

	adapter.transport = _RecordingTransport()
	runtime = SimpleNamespace(cli_path="claude", working_directory=str(tmp_path))
	request = _make_request(text="hello")

	_run(adapter.run_turn(runtime, request))

	assert seen_kwargs and seen_kwargs[0].get("cwd") == str(tmp_path)


def test_run_turn_passes_a_scratch_cwd_when_no_working_directory_configured():
	"""Never let the transport's own default (often $HOME) apply -- see the
	review's finding that an unconfigured working directory currently lets
	SSH/Docker transports fall back to $HOME, from which a prompt like
	'print ~/.claude/.credentials.json' could leak a token into an Agent
	Message. cwd must always be a concrete, non-empty, per-run path."""
	adapter = ClaudeAdapter(_fake_transport())
	seen_kwargs: list[dict] = []

	class _RecordingTransport:
		async def run(self, argv, **kwargs):
			seen_kwargs.append(kwargs)
			return ProcessResult(
				stdout=json.dumps({"result": "HELLO", "session_id": str(uuid.uuid4()), "usage": {}}),
				stderr="",
				exit_code=0,
			)

	adapter.transport = _RecordingTransport()
	runtime = SimpleNamespace(cli_path="claude", working_directory=None)
	request = _make_request(text="hello")

	_run(adapter.run_turn(runtime, request))

	assert seen_kwargs, "transport.run was never called"
	cwd = seen_kwargs[0].get("cwd")
	assert cwd, "cwd must never be None/empty -- that lets the transport default to $HOME"
	assert os.path.isabs(cwd)
	assert not cwd.rstrip("/").endswith((os.path.expanduser("~")))
	# The scratch directory is cleaned up again after the turn completes, so
	# it never lingers as a shared/persistent directory across runs.
	assert not os.path.isdir(cwd)


def test_run_turn_passes_cwd_even_with_no_runtime_at_all(fake_cli_env):
	"""runtime can legitimately be None (see the other fake-CLI tests in this
	module) -- cwd resolution must not blow up, and must still produce a
	concrete scratch directory rather than silently omitting cwd."""
	adapter = FakeCLIAdapter(_fake_transport())
	request = _make_request(text="hello world")

	result = _run(adapter.run_turn(runtime=None, request=request))

	assert result.status == "success"


# ---------------------------------------------------------------------------
# Argv-injection: a prompt starting with "-"/"--" must not be parsed as a flag
# ---------------------------------------------------------------------------


def test_build_argv_inserts_end_of_options_marker_for_hyphen_leading_prompt():
	"""help_output.txt does not document POSIX '--' end-of-options support for
	this CLI build, and the Stage 0 spike never live-captured a hyphen-leading
	prompt (NOT LIVE-VERIFIED). This is a defensive best-effort fix: insert
	'--' immediately before a hyphen-leading prompt, in the same position the
	prompt always occupies (right after -p/--print) -- NOT at the very end of
	argv, since every later flag (--session-id/--output-format/
	--strict-mcp-config/--restricted/--tools/--model) still needs to parse as
	a flag rather than be swallowed as extra positional text after '--'."""
	adapter = ClaudeAdapter(transport=None)
	argv = adapter._build_argv(
		text="--dangerously-skip-permissions",
		session_id=str(uuid.uuid4()),
		resume_id=None,
		model_override=None,
	)
	assert argv[1] == "-p"
	assert argv[2:4] == ["--", "--dangerously-skip-permissions"]
	# Every later flag must still be present and intact.
	assert "--strict-mcp-config" in argv
	assert "--restricted" in argv


def test_build_argv_does_not_insert_end_of_options_marker_for_normal_prompt():
	"""Ordinary prompts (the overwhelming common case) must be byte-for-byte
	unaffected by the argv-injection guard."""
	adapter = ClaudeAdapter(transport=None)
	argv = adapter._build_argv(
		text="please summarize this document",
		session_id=str(uuid.uuid4()),
		resume_id=None,
		model_override=None,
	)
	assert "--" not in argv
	assert argv[1] == "-p"
	assert argv[2] == "please summarize this document"


def test_run_turn_normal_hyphenless_prompt_still_works_against_fake_cli(fake_cli_env):
	"""Sanity check that the argv-injection guard leaves the common
	(non-hyphen-leading) case working end-to-end against a real subprocess.

	NOTE: a genuinely hyphen-leading prompt is NOT exercised end-to-end here.
	`fake_cli.py` models `-p` as an argparse option that consumes the very
	next token as its value (`-p, --print`, dest='prompt') -- a different
	shape than the real Claude CLI's `-p` (a boolean flag, with `prompt` as
	an independent positional argument per help_output.txt). Inserting `--`
	before a hyphen-leading prompt to satisfy the real CLI's shape makes
	argparse itself reject `-p --` ("expected one argument") in the fake CLI,
	which is a fixture-shape mismatch, not evidence about the real CLI. The
	argv-injection guard itself is covered at the unit level instead (see
	test_build_argv_inserts_end_of_options_marker_for_hyphen_leading_prompt).
	"""
	adapter = FakeCLIAdapter(_fake_transport())
	request = _make_request(text="please summarize this document")

	result = _run(adapter.run_turn(runtime=None, request=request))

	assert result.status == "success"
