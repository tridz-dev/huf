"""Unit tests for GeminiAdapter.

Covers:
- Defensive JSON parsing of `--output-format json` turn output: a well-formed guess
  shape, and a plausible unexpected/malformed shape that must raise
  CLI_OUTPUT_PARSE_FAILED cleanly instead of crashing.
- delete_session() treating provider failure as non-fatal (plan §17.2).
- The passthrough-boundary self-check: argv sent to the transport never contains
  HUF-generated system-prompt/MCP/tool content, only the current turn's text.

NOTE: Gemini CLI was not installed/authenticated during the Stage 0 spike, so there
is no real captured JSON response to assert against (see
huf/ai/tests/subscription/fixtures/real/gemini/create_session.meta.md). These tests
exercise the adapter's own defensive-parsing contract, not a confirmed live schema.
"""

from __future__ import annotations

import json

import pytest

from huf.ai.subscription.adapters.gemini import GeminiAdapter
from huf.ai.subscription.errors import SubscriptionCLIError, SubscriptionErrorCode
from huf.ai.subscription.adapters.base import DeleteSessionResult
from huf.ai.subscription.transports.base import ExecutionTransport, ProcessResult, StagedFile, TransportProbe
from huf.ai.subscription.types import SubscriptionTurnRequest

# Canonical AuthStatus.state vocabulary per huf/ai/subscription/types.py's
# docstring / plan §60.1. Callers (subscription_api.py, executor.py) only
# recognize these values -- anything else (e.g. "authenticated") silently
# parks every run. See Track-Item: fix-c1-auth-status-vocabulary.
CANONICAL_AUTH_STATES = {"ready", "required", "waiting_user", "verifying", "failed", "unknown"}


class FakeRuntime:
	def __init__(self, working_directory: str = "/work/proj", executable: str = "gemini", name: str = "gemini-rt"):
		self.working_directory = working_directory
		self.executable = executable
		self.name = name


class RecordingTransport(ExecutionTransport):
	"""Transport stub that records every argv it was asked to run and returns a
	pre-scripted ProcessResult (or a queue of them)."""

	def __init__(self, results: list[ProcessResult] | None = None):
		self.calls: list[dict] = []
		self._results = list(results) if results else []
		self._default_result = ProcessResult(stdout="", stderr="", exit_code=0)

	async def probe(self) -> TransportProbe:
		return TransportProbe(reachable=True)

	async def run(self, argv, *, cwd=None, env=None, stdin=None, timeout=None) -> ProcessResult:
		self.calls.append({"argv": argv, "cwd": cwd, "env": env, "stdin": stdin, "timeout": timeout})
		if self._results:
			return self._results.pop(0)
		return self._default_result

	async def stage_file(self, source_path: str, *, target_name: str | None = None) -> StagedFile:
		raise NotImplementedError

	async def remove_staged_file(self, staged_file: StagedFile) -> None:
		pass


def make_request(text: str = "hello", session_id: str | None = "sess-uuid-1", files=None) -> SubscriptionTurnRequest:
	return SubscriptionTurnRequest(
		runtime_name="gemini-rt",
		provider_session_id=session_id,
		text=text,
		files=files or [],
		model_override=None,
		run_id="run-1",
		conversation_id="conv-1",
		timeout_seconds=60,
	)


class TestParseTurnOutputWellFormed:
	"""A plausible well-formed guess shape (result/session_id/usage keys) parses cleanly."""

	@pytest.mark.asyncio
	async def test_well_formed_guess_shape_parses(self):
		payload = {
			"result": "Hello back!",
			"session_id": "sess-uuid-1",
			"usage": {"input_tokens": 5, "output_tokens": 3},
		}
		transport = RecordingTransport([ProcessResult(stdout=json.dumps(payload), stderr="", exit_code=0)])
		adapter = GeminiAdapter(transport)
		runtime = FakeRuntime()

		result = await adapter.run_turn(runtime, make_request())

		assert result.status == "success"
		assert result.final_text == "Hello back!"
		assert result.provider_session_id == "sess-uuid-1"
		assert result.usage == {"input_tokens": 5, "output_tokens": 3}

	@pytest.mark.asyncio
	async def test_alternate_key_names_also_parse(self):
		"""Parser tries multiple plausible key names since the real schema is unconfirmed."""
		payload = {"response": "Alt shape response", "sessionId": "sess-uuid-2", "tokenUsage": {"total": 10}}
		transport = RecordingTransport([ProcessResult(stdout=json.dumps(payload), stderr="", exit_code=0)])
		adapter = GeminiAdapter(transport)
		runtime = FakeRuntime()

		result = await adapter.run_turn(runtime, make_request(session_id=None))

		assert result.final_text == "Alt shape response"
		assert result.provider_session_id == "sess-uuid-2"
		assert result.usage == {"total": 10}


class TestParseTurnOutputMalformed:
	"""Plausible unexpected/malformed shapes must raise CLI_OUTPUT_PARSE_FAILED cleanly."""

	@pytest.mark.asyncio
	async def test_unrecognized_top_level_shape_raises_cleanly(self):
		"""A JSON object with none of the plausible field names must not crash the
		adapter with a raw KeyError; it must raise CLI_OUTPUT_PARSE_FAILED."""
		payload = {"weird_field": "no idea what this is", "another": 123}
		transport = RecordingTransport([ProcessResult(stdout=json.dumps(payload), stderr="", exit_code=0)])
		adapter = GeminiAdapter(transport)
		runtime = FakeRuntime()

		with pytest.raises(SubscriptionCLIError) as excinfo:
			await adapter.run_turn(runtime, make_request())
		assert excinfo.value.code == SubscriptionErrorCode.CLI_OUTPUT_PARSE_FAILED

	@pytest.mark.asyncio
	async def test_non_json_stdout_raises_cleanly(self):
		"""Non-JSON stdout must not crash with a raw JSONDecodeError."""
		transport = RecordingTransport([ProcessResult(stdout="not json at all {{{", stderr="", exit_code=0)])
		adapter = GeminiAdapter(transport)
		runtime = FakeRuntime()

		with pytest.raises(SubscriptionCLIError) as excinfo:
			await adapter.run_turn(runtime, make_request())
		assert excinfo.value.code == SubscriptionErrorCode.CLI_OUTPUT_PARSE_FAILED

	@pytest.mark.asyncio
	async def test_json_array_top_level_raises_cleanly(self):
		"""A top-level JSON array (not an object) must not crash with a raw TypeError."""
		transport = RecordingTransport([ProcessResult(stdout=json.dumps([1, 2, 3]), stderr="", exit_code=0)])
		adapter = GeminiAdapter(transport)
		runtime = FakeRuntime()

		with pytest.raises(SubscriptionCLIError) as excinfo:
			await adapter.run_turn(runtime, make_request())
		assert excinfo.value.code == SubscriptionErrorCode.CLI_OUTPUT_PARSE_FAILED

	@pytest.mark.asyncio
	async def test_empty_stdout_raises_cleanly(self):
		transport = RecordingTransport([ProcessResult(stdout="", stderr="", exit_code=0)])
		adapter = GeminiAdapter(transport)
		runtime = FakeRuntime()

		with pytest.raises(SubscriptionCLIError) as excinfo:
			await adapter.run_turn(runtime, make_request())
		assert excinfo.value.code == SubscriptionErrorCode.CLI_OUTPUT_PARSE_FAILED


class TestDeleteSessionNonFatal:
	"""delete_session must never raise on failure (plan §17.2)."""

	@pytest.mark.asyncio
	async def test_delete_success(self):
		transport = RecordingTransport([ProcessResult(stdout="", stderr="", exit_code=0)])
		adapter = GeminiAdapter(transport)
		runtime = FakeRuntime()

		result = await adapter.delete_session(runtime, "sess-uuid-1")

		assert isinstance(result, DeleteSessionResult)
		assert result.cleanup_status == "deleted"

	@pytest.mark.asyncio
	async def test_delete_nonzero_exit_is_cleanup_failed_not_raised(self):
		transport = RecordingTransport([ProcessResult(stdout="", stderr="session not found", exit_code=1)])
		adapter = GeminiAdapter(transport)
		runtime = FakeRuntime()

		result = await adapter.delete_session(runtime, "sess-uuid-1")

		assert result.cleanup_status == "cleanup_failed"

	@pytest.mark.asyncio
	async def test_delete_transport_exception_is_cleanup_failed_not_raised(self):
		class RaisingTransport(RecordingTransport):
			async def run(self, argv, *, cwd=None, env=None, stdin=None, timeout=None):
				self.calls.append({"argv": argv})
				raise ConnectionError("ssh dropped")

		transport = RaisingTransport()
		adapter = GeminiAdapter(transport)
		runtime = FakeRuntime()

		# Must not raise.
		result = await adapter.delete_session(runtime, "sess-uuid-1")
		assert result.cleanup_status == "cleanup_failed"

	@pytest.mark.asyncio
	async def test_delete_missing_stable_cwd_is_cleanup_failed_not_raised(self):
		transport = RecordingTransport()
		adapter = GeminiAdapter(transport)
		runtime = FakeRuntime(working_directory="")

		result = await adapter.delete_session(runtime, "sess-uuid-1")
		assert result.cleanup_status == "cleanup_failed"
		# Should not even have attempted a transport call without a stable cwd.
		assert transport.calls == []


class TestPassthroughBoundary:
	"""Argv sent to the transport must only ever carry the current turn's text/files -
	never HUF-generated system-prompt, conversation-history, MCP, or tool content."""

	FORBIDDEN_MARKERS = [
		"SYSTEM PROMPT",
		"You are an AI agent",
		"HUF_AGENT_INSTRUCTIONS",
		"conversation_history",
		"mcp_config",
		"huf_tool_schema",
	]

	@pytest.mark.asyncio
	async def test_run_turn_argv_contains_only_turn_text(self):
		payload = {"result": "ok", "session_id": "sess-uuid-1", "usage": {}}
		transport = RecordingTransport([ProcessResult(stdout=json.dumps(payload), stderr="", exit_code=0)])
		adapter = GeminiAdapter(transport)
		runtime = FakeRuntime()

		request = make_request(text="What is 2+2?")
		await adapter.run_turn(runtime, request)

		assert len(transport.calls) == 1
		argv = transport.calls[0]["argv"]
		argv_joined = " ".join(argv)

		# The turn text itself must be present (that's the whole point of passthrough).
		assert "What is 2+2?" in argv

		# No HUF-internal context must ever leak into the CLI invocation.
		for marker in self.FORBIDDEN_MARKERS:
			assert marker not in argv_joined

		# argv must not contain anything from a hypothetical Agent instructions blob
		# or conversation history object - only fields present on
		# SubscriptionTurnRequest's closed field set.
		assert request.conversation_id not in argv  # conversation_id is metadata, not passed to the CLI

	@pytest.mark.asyncio
	async def test_check_auth_probe_call_carries_no_huf_context(self):
		transport = RecordingTransport([ProcessResult(stdout="{}", stderr="", exit_code=0)])
		adapter = GeminiAdapter(transport)
		runtime = FakeRuntime()

		await adapter.check_auth(runtime)

		assert len(transport.calls) == 1
		argv_joined = " ".join(transport.calls[0]["argv"])
		for marker in self.FORBIDDEN_MARKERS:
			assert marker not in argv_joined


class TestCheckAuthCanonicalVocabulary:
	"""CRITICAL regression guard (Track-Item: fix-c1-auth-status-vocabulary):
	check_auth() must only ever report a state from the canonical vocabulary
	documented on AuthStatus -- every caller only recognizes those values, so
	anything else (e.g. the old "authenticated"/"unauthenticated" bug) makes
	the executor park every run forever."""

	@pytest.mark.asyncio
	@pytest.mark.parametrize("exit_code", [0, 1, 2])
	async def test_check_auth_never_returns_non_canonical_state(self, exit_code):
		transport = RecordingTransport([ProcessResult(stdout="", stderr="not authenticated", exit_code=exit_code)])
		adapter = GeminiAdapter(transport)
		runtime = FakeRuntime()

		status = await adapter.check_auth(runtime)

		assert status.state in CANONICAL_AUTH_STATES

	@pytest.mark.asyncio
	async def test_check_auth_transport_exception_is_runtime_error_not_auth_status(self):
		"""A transport-level failure raises rather than fabricating an AuthStatus
		with an invalid state -- exercised here to document the boundary."""

		class RaisingTransport(RecordingTransport):
			async def run(self, argv, *, cwd=None, env=None, stdin=None, timeout=None):
				self.calls.append({"argv": argv})
				raise ConnectionError("ssh dropped")

		transport = RaisingTransport()
		adapter = GeminiAdapter(transport)
		runtime = FakeRuntime()

		with pytest.raises(Exception):
			await adapter.check_auth(runtime)


class TestVisionUnsupported:
	@pytest.mark.asyncio
	async def test_files_supplied_raises_vision_unsupported(self):
		transport = RecordingTransport(
			[
				ProcessResult(stdout="gemini 1.2.3", stderr="", exit_code=0),  # probe --version
			]
		)
		adapter = GeminiAdapter(transport)
		runtime = FakeRuntime()

		request = make_request(files=["/tmp/some_image.png"])

		with pytest.raises(Exception) as excinfo:
			await adapter.run_turn(runtime, request)
		assert "VISION_UNSUPPORTED" in str(getattr(excinfo.value, "code", excinfo.value))


class TestStableWorkingDirectory:
	@pytest.mark.asyncio
	async def test_missing_working_directory_raises(self):
		transport = RecordingTransport()
		adapter = GeminiAdapter(transport)
		runtime = FakeRuntime(working_directory="")

		with pytest.raises(Exception):
			await adapter.run_turn(runtime, make_request())

	@pytest.mark.asyncio
	async def test_same_cwd_used_across_calls(self):
		payload = {"result": "ok", "session_id": "sess-uuid-1", "usage": {}}
		transport = RecordingTransport(
			[
				ProcessResult(stdout=json.dumps(payload), stderr="", exit_code=0),
				ProcessResult(stdout=json.dumps(payload), stderr="", exit_code=0),
			]
		)
		adapter = GeminiAdapter(transport)
		runtime = FakeRuntime(working_directory="/stable/project/path")

		await adapter.run_turn(runtime, make_request())
		await adapter.run_turn(runtime, make_request())

		cwds = [call["cwd"] for call in transport.calls]
		assert all(cwd == "/stable/project/path" for cwd in cwds)


class TestNewSessionNeverSendsEmptySessionId:
	"""H3 regression test (Track-Item: fix-gemini-h3-h9): a brand-new-session turn
	must never send `--session-id ""` (or `--session-id` with any value) -- Gemini's
	help_output.txt does not document `--session-id` at all, only `-r/--resume`."""

	@pytest.mark.asyncio
	async def test_new_session_turn_omits_session_id_flag(self):
		payload = {"result": "ok", "session_id": "gemini-generated-id", "usage": {}}
		transport = RecordingTransport([ProcessResult(stdout=json.dumps(payload), stderr="", exit_code=0)])
		adapter = GeminiAdapter(transport)
		runtime = FakeRuntime()

		# No provider_session_id -> new session.
		request = make_request(session_id=None)
		result = await adapter.run_turn(runtime, request)

		assert len(transport.calls) == 1
		argv = transport.calls[0]["argv"]

		assert "--session-id" not in argv
		# The provider-generated session id from the response is still surfaced.
		assert result.provider_session_id == "gemini-generated-id"

	@pytest.mark.asyncio
	async def test_resume_turn_still_uses_resume_flag(self):
		"""Sanity check: an existing session still resumes via -r, unaffected by the fix."""
		payload = {"result": "ok", "session_id": "sess-uuid-1", "usage": {}}
		transport = RecordingTransport([ProcessResult(stdout=json.dumps(payload), stderr="", exit_code=0)])
		adapter = GeminiAdapter(transport)
		runtime = FakeRuntime()

		request = make_request(session_id="sess-uuid-1")
		await adapter.run_turn(runtime, request)

		argv = transport.calls[0]["argv"]
		assert "-r" in argv
		assert argv[argv.index("-r") + 1] == "sess-uuid-1"
		assert "--session-id" not in argv


class TestAuthFailureClassification:
	"""H9 regression test (Track-Item: fix-gemini-h3-h9): a CLI failure whose stderr
	looks auth/logout-shaped must be classified as AUTH_REQUIRED in `events` so
	executor.py::_extract_error_code() can park the run instead of failing it."""

	@pytest.mark.asyncio
	async def test_auth_keyword_in_stderr_classified_as_auth_required(self):
		transport = RecordingTransport(
			[ProcessResult(stdout="", stderr="Error: not authenticated, please login again", exit_code=1)]
		)
		adapter = GeminiAdapter(transport)
		runtime = FakeRuntime()

		result = await adapter.run_turn(runtime, make_request())

		assert result.status == "failed"
		assert result.events
		assert result.events[0]["code"] == SubscriptionErrorCode.AUTH_REQUIRED.value
		assert result.auth_reason is not None

	@pytest.mark.asyncio
	async def test_unauthorized_keyword_classified_as_auth_required(self):
		transport = RecordingTransport(
			[ProcessResult(stdout="", stderr="401 Unauthorized: invalid credential", exit_code=1)]
		)
		adapter = GeminiAdapter(transport)
		runtime = FakeRuntime()

		result = await adapter.run_turn(runtime, make_request())

		assert result.events[0]["code"] == SubscriptionErrorCode.AUTH_REQUIRED.value

	@pytest.mark.asyncio
	async def test_non_auth_failure_not_misclassified(self):
		transport = RecordingTransport(
			[ProcessResult(stdout="", stderr="Error: rate limit exceeded", exit_code=1)]
		)
		adapter = GeminiAdapter(transport)
		runtime = FakeRuntime()

		result = await adapter.run_turn(runtime, make_request())

		assert result.status == "failed"
		assert result.events[0]["code"] == SubscriptionErrorCode.CLI_PROCESS_FAILED.value
		assert result.auth_reason is None
