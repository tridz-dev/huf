"""Integration tests for the executor <-> staging wiring around vision/files.

`test_staging.py` (T-08) already covers `staging.py`'s own unit behavior in
isolation against a mock transport (validation, rollback, cleanup logging).
This module does NOT re-test that. Instead it verifies the INTEGRATION
points that only exist at the `executor.py` call sites:

- `staging.assert_vision_supported` is called before `staging.stage_turn_files`
  (fail fast, never touch the filesystem for an unsupported adapter).
- `staging.cleanup_staged_files` is guaranteed to run even if the adapter's
  `run_turn()` raises mid-turn (the "cleanup in finally" contract).
- Each landed adapter's declared `supports_images` capability actually gates
  whether a vision-carrying request proceeds or raises `VISION_UNSUPPORTED`.
- A full staged-file lifecycle through the real `LocalTransport`, proven
  against the real filesystem (not a mock assertion).
- An oversized file is rejected before any adapter method is ever invoked.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from huf.ai.subscription import staging
from huf.ai.subscription.adapters.claude import ClaudeAdapter
from huf.ai.subscription.adapters.codex import CodexAdapter
from huf.ai.subscription.adapters.gemini import GeminiAdapter
from huf.ai.subscription.capabilities import RuntimeCapabilities
from huf.ai.subscription.errors import SubscriptionCLIError, SubscriptionErrorCode
from huf.ai.subscription.transports.base import (
	ExecutionTransport,
	ProcessResult,
	StagedFile,
	TransportProbe,
)
from huf.ai.subscription.transports.local import LocalTransport


def _run(coro):
	return asyncio.run(coro)


class FakeTransport(ExecutionTransport):
	"""Minimal fake transport for the executor-integration tests below.

	Distinct from `test_staging.py`'s `FakeExecutionTransport`: this one also
	exposes a `stage_file_called` flag so tests can assert staging was never
	attempted at all (the oversized-file / vision-gate scenarios).
	"""

	def __init__(self) -> None:
		self.stage_file_called = False
		self.staged: list[StagedFile] = []
		self.removed: list[StagedFile] = []

	async def probe(self) -> TransportProbe:
		return TransportProbe(reachable=True)

	async def run(self, argv, *, cwd=None, env=None, stdin=None, timeout=None) -> ProcessResult:
		return ProcessResult(stdout="", stderr="", exit_code=0)

	async def stage_file(self, source_path: str, *, target_name: str | None = None) -> StagedFile:
		self.stage_file_called = True
		staged = StagedFile(remote_path=f"/staged/{Path(source_path).name}", local_path=source_path)
		self.staged.append(staged)
		return staged

	async def remove_staged_file(self, staged_file: StagedFile) -> None:
		self.removed.append(staged_file)


def _write_temp_image(tmp_path: Path, name: str = "photo.png", size_bytes: int = 128) -> str:
	path = tmp_path / name
	path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * size_bytes)
	return str(path)


# ---------------------------------------------------------------------------
# Executor call-site wiring: staging is invoked, cleanup runs even on error.
# ---------------------------------------------------------------------------


class TestExecutorStagingWiring:
	"""Simulates executor.py's step 6/7 sequence (see SubscriptionPassthroughExecutor.execute):

	    if files:
	        capabilities = probe(...)
	        staging.assert_vision_supported(capabilities, files)
	        staged_files = staging.stage_turn_files(adapter.transport, files)
	    try:
	        result = adapter.run_turn(...)
	    finally:
	        if staged_files:
	            staging.cleanup_staged_files(adapter.transport, staged_files)

	This mirrors the real control flow at
	`huf/ai/subscription/executor.py` (the `staged_files`/`finally` block),
	rather than importing the whole executor (which requires a live Frappe
	site to construct Agent Run/Conversation docs).
	"""

	def test_stage_turn_files_called_when_request_has_files(self, tmp_path):
		transport = FakeTransport()
		image_path = _write_temp_image(tmp_path)

		capabilities = RuntimeCapabilities(supports_images=True)
		staging.assert_vision_supported(capabilities, [image_path])
		staged = _run(staging.stage_turn_files(transport, [image_path]))

		assert transport.stage_file_called is True
		assert len(staged) == 1

	def test_cleanup_runs_even_if_adapter_run_turn_raises(self, tmp_path):
		"""The critical 'cleanup in finally' contract.

		Verifies the actual pattern used in executor.py: staged_files is
		populated in the `try` before the adapter call, and
		`cleanup_staged_files` executes in the `finally` regardless of
		whether the adapter raises. If executor.py did NOT wrap the adapter
		call this way, a raising adapter would leak staged files forever.
		"""
		transport = FakeTransport()
		image_path = _write_temp_image(tmp_path)

		capabilities = RuntimeCapabilities(supports_images=True)
		staging.assert_vision_supported(capabilities, [image_path])
		staged_files = _run(staging.stage_turn_files(transport, [image_path]))

		adapter_run_turn = AsyncMock(side_effect=RuntimeError("adapter blew up mid-turn"))

		with pytest.raises(RuntimeError, match="adapter blew up mid-turn"):
			try:
				_run(adapter_run_turn())
			finally:
				if staged_files:
					_run(staging.cleanup_staged_files(transport, staged_files))

		assert transport.removed == staged_files, (
			"cleanup_staged_files must run in the finally block even when "
			"adapter.run_turn() raises — otherwise staged files leak on every "
			"mid-turn adapter failure."
		)

	def test_vision_gate_runs_before_any_staging_attempt(self, tmp_path):
		"""assert_vision_supported must fail BEFORE stage_turn_files ever
		touches the transport/filesystem — no partial staging for a runtime
		that doesn't support images at all.
		"""
		transport = FakeTransport()
		image_path = _write_temp_image(tmp_path)
		capabilities = RuntimeCapabilities(supports_images=False)

		with pytest.raises(SubscriptionCLIError) as exc_info:
			staging.assert_vision_supported(capabilities, [image_path])
			# stage_turn_files below is intentionally never reached if the
			# assert above raises, which is exactly what this test verifies.
			_run(staging.stage_turn_files(transport, [image_path]))

		assert exc_info.value.code == SubscriptionErrorCode.VISION_UNSUPPORTED
		assert transport.stage_file_called is False, (
			"stage_file must never be called once assert_vision_supported "
			"has raised for this request"
		)


# ---------------------------------------------------------------------------
# Verify executor.py itself is actually wired this way (not just assumed).
# ---------------------------------------------------------------------------


def test_executor_source_wraps_adapter_call_in_try_finally_with_cleanup():
	"""Static check on the real executor.py source: confirms step 6/7's
	`staged_files`/adapter-call/`finally: cleanup_staged_files` structure
	is actually present, not just assumed by the simulation above.
	"""
	import inspect

	from huf.ai.subscription import executor

	source = inspect.getsource(executor.SubscriptionPassthroughExecutor.execute)

	# The adapter call and the cleanup call must both exist...
	assert "adapter.run_turn(runtime, request)" in source
	assert "staging.cleanup_staged_files(adapter.transport, staged_files)" in source

	# ...and the cleanup call must be inside a `finally:` block that covers
	# the adapter invocation, not just called unconditionally after it inline.
	finally_index = source.index("finally:")
	adapter_call_index = source.index("adapter.run_turn(runtime, request)")
	cleanup_call_index = source.index("staging.cleanup_staged_files(adapter.transport, staged_files)")
	assert adapter_call_index < finally_index < cleanup_call_index, (
		"executor.py must call adapter.run_turn() inside a try whose "
		"finally: block runs staging.cleanup_staged_files — this is the "
		"resource-leak-on-exception contract T-T11 exists to verify."
	)


def test_executor_source_checks_vision_before_staging():
	"""Static check: assert_vision_supported must appear before
	stage_turn_files in the source, matching the fail-fast requirement.
	"""
	import inspect

	from huf.ai.subscription import executor

	source = inspect.getsource(executor.SubscriptionPassthroughExecutor.execute)
	vision_index = source.index("staging.assert_vision_supported(")
	stage_index = source.index("staging.stage_turn_files(")
	assert vision_index < stage_index


# ---------------------------------------------------------------------------
# Per-adapter supports_images gating (Claude, Codex, Gemini).
# ---------------------------------------------------------------------------


class TestAdapterVisionCapabilityGating:
	"""Each adapter's own file declares supports_images differently:

	- ClaudeAdapter: hardcoded `supports_images=False` (adapters/claude.py) —
	  no dedicated image/vision flag in the CLI's help output.
	- GeminiAdapter: hardcoded `supports_images=False` (adapters/gemini.py) —
	  not documented in fetched docs.
	- CodexAdapter: dynamic — `supports_images="-i, --image" in
	  _get_exec_help_text()` (adapters/codex.py), true only if the installed
	  `codex exec --help` output advertises an image flag.

	These tests probe each adapter's real `probe()` (transport mocked to
	avoid a live CLI) and confirm a vision-carrying request is gated
	accordingly through the same `assert_vision_supported` used by the
	executor.
	"""

	def test_claude_adapter_declares_no_vision_support(self):
		transport = MagicMock()
		transport.run = AsyncMock(
			return_value=ProcessResult(stdout="claude 1.0.0", stderr="", exit_code=0)
		)
		adapter = ClaudeAdapter(transport)
		capabilities = _run(adapter.probe(runtime=MagicMock()))

		assert capabilities.supports_images is False
		with pytest.raises(SubscriptionCLIError) as exc_info:
			staging.assert_vision_supported(capabilities, ["/tmp/some.png"])
		assert exc_info.value.code == SubscriptionErrorCode.VISION_UNSUPPORTED

	def test_gemini_adapter_declares_no_vision_support(self):
		transport = MagicMock()
		transport.run = AsyncMock(
			return_value=ProcessResult(stdout="0.1.0", stderr="", exit_code=0)
		)
		adapter = GeminiAdapter(transport)
		capabilities = _run(adapter.probe(runtime=MagicMock()))

		assert capabilities.supports_images is False
		with pytest.raises(SubscriptionCLIError) as exc_info:
			staging.assert_vision_supported(capabilities, ["/tmp/some.png"])
		assert exc_info.value.code == SubscriptionErrorCode.VISION_UNSUPPORTED

	def test_codex_adapter_vision_support_follows_help_text(self, monkeypatch):
		transport = MagicMock()
		transport.run = AsyncMock(
			return_value=ProcessResult(stdout="codex-cli 0.1.0", stderr="", exit_code=0)
		)
		adapter = CodexAdapter(transport)

		# Help text WITHOUT the image flag -> capability False -> gated.
		monkeypatch.setattr(
			"huf.ai.subscription.adapters.codex._get_exec_help_text",
			lambda: "usage: codex exec [OPTIONS]\n  --model, -m\n",
		)
		capabilities_no_image = _run(adapter.probe(runtime=MagicMock()))
		assert capabilities_no_image.supports_images is False
		with pytest.raises(SubscriptionCLIError) as exc_info:
			staging.assert_vision_supported(capabilities_no_image, ["/tmp/some.png"])
		assert exc_info.value.code == SubscriptionErrorCode.VISION_UNSUPPORTED

		# Help text WITH the image flag -> capability True -> allowed through.
		monkeypatch.setattr(
			"huf.ai.subscription.adapters.codex._get_exec_help_text",
			lambda: "usage: codex exec [OPTIONS]\n  -i, --image <PATH>\n",
		)
		capabilities_with_image = _run(adapter.probe(runtime=MagicMock()))
		assert capabilities_with_image.supports_images is True
		# Must not raise.
		staging.assert_vision_supported(capabilities_with_image, ["/tmp/some.png"])


# ---------------------------------------------------------------------------
# Real filesystem lifecycle through LocalTransport (already-landed transport).
# ---------------------------------------------------------------------------


class TestLocalTransportRealFilesystemLifecycle:
	"""Proves the "cleanup proven" acceptance criterion (plan §42/§77) with
	real filesystem checks, not mock-call assertions.
	"""

	def test_stage_then_cleanup_round_trip_on_real_disk(self, tmp_path):
		runtime_dir = tmp_path / "runtime"
		transport = LocalTransport("true", runtime_dir=str(runtime_dir))

		source_path = tmp_path / "source.png"
		source_path.write_bytes(b"\x89PNG\r\n\x1a\nfake-image-bytes")

		staged_files = _run(staging.stage_turn_files(transport, [str(source_path)]))
		assert len(staged_files) == 1
		staged = staged_files[0]

		staged_path = Path(staged.remote_path)
		assert staged_path.exists(), "staged file must be readable at its staged path"
		assert staged_path.read_bytes() == source_path.read_bytes()
		# Source file must be untouched (copy, not move).
		assert source_path.exists()

		_run(staging.cleanup_staged_files(transport, staged_files))

		assert not staged_path.exists(), (
			"cleanup_staged_files must actually remove the staged file from "
			"disk — this is a real filesystem check, not a mock assertion"
		)
		# The per-run staging directory should also be gone.
		assert not staged_path.parent.exists()
		# Source file is never touched by cleanup.
		assert source_path.exists()


# ---------------------------------------------------------------------------
# Oversized/invalid file rejected before any adapter method is ever invoked.
# ---------------------------------------------------------------------------


class TestOversizedFileNeverReachesAdapter:
	def test_oversized_file_raises_before_adapter_invoked(self, tmp_path):
		transport = FakeTransport()
		oversized_path = _write_temp_image(tmp_path, size_bytes=1024)

		adapter_run_turn = AsyncMock()

		with pytest.raises(SubscriptionCLIError) as exc_info:
			staged_files = _run(
				staging.stage_turn_files(transport, [oversized_path], max_file_size_bytes=100)
			)
			# Unreachable if stage_turn_files raises, which is what we assert.
			_run(adapter_run_turn(staged_files))

		assert exc_info.value.code == SubscriptionErrorCode.FILE_TOO_LARGE
		adapter_run_turn.assert_not_called()
		assert transport.stage_file_called is False, (
			"an oversized file must be rejected by validation before "
			"transport.stage_file is ever called"
		)

	def test_invalid_mime_type_never_reaches_adapter(self, tmp_path):
		transport = FakeTransport()
		text_path = tmp_path / "notes.txt"
		text_path.write_text("not an image")

		adapter_run_turn = AsyncMock()

		with pytest.raises(SubscriptionCLIError) as exc_info:
			_run(staging.stage_turn_files(transport, [str(text_path)]))
			_run(adapter_run_turn())

		assert exc_info.value.code == SubscriptionErrorCode.INVALID_FILE_TYPE
		adapter_run_turn.assert_not_called()
		assert transport.stage_file_called is False
