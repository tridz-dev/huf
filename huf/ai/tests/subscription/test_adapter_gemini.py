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
