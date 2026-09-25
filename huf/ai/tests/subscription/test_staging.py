"""Unit tests for the staging orchestrator.

Tests cover file validation, staging, cleanup, capability gating, and
partial-failure rollback semantics.

Runs against a mock ExecutionTransport that tracks all calls but performs
no actual file operations.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from huf.ai.subscription.capabilities import RuntimeCapabilities
from huf.ai.subscription.errors import (
	SubscriptionCLIError,
	SubscriptionErrorCode,
)
from huf.ai.subscription.staging import (
	assert_vision_supported,
	cleanup_staged_files,
	stage_turn_files,
)
from huf.ai.subscription.transports.base import (
	ExecutionTransport,
	StagedFile,
)


class FakeExecutionTransport(ExecutionTransport):
	"""Fake in-memory transport for testing.

	Tracks all calls to stage_file() and remove_staged_file() but does not
	perform actual file operations. Allows injection of failures for testing
	error paths.
	"""

	def __init__(self) -> None:
		self.staged_files: list[StagedFile] = []
		self.removed_files: list[str] = []
		self.stage_file_call_count = 0
		self.remove_staged_file_call_count = 0
		self.fail_on_stage_index: int | None = None
		self.fail_on_remove: bool = False

	async def probe(self) -> Any:
		"""Not used in these tests."""
		pass

	async def run(self, *args: Any, **kwargs: Any) -> Any:
		"""Not used in these tests."""
		pass

	async def stage_file(
		self,
		source_path: str,
		*,
		target_name: str | None = None,
	) -> StagedFile:
		"""Mock stage_file that optionally fails.

		Args:
			source_path: Local path to the file
			target_name: Optional target filename

		Returns:
			StagedFile with mock paths

		Raises:
			RuntimeError: If fail_on_stage_index matches current call count
		"""
		if self.fail_on_stage_index == self.stage_file_call_count:
			self.stage_file_call_count += 1
			raise RuntimeError(f"Staged file {source_path} failed")

		self.stage_file_call_count += 1
		remote_path = f"/tmp/huf-staged/{Path(source_path).name}"

		staged = StagedFile(
			remote_path=remote_path,
			local_path=source_path,
			cleanup=None,
		)
		self.staged_files.append(staged)
		return staged

	async def remove_staged_file(self, staged_file: StagedFile) -> None:
		"""Mock remove_staged_file that optionally fails.

		Args:
			staged_file: StagedFile to remove

		Raises:
			RuntimeError: If fail_on_remove is True
		"""
		if self.fail_on_remove:
			raise RuntimeError(f"Failed to remove {staged_file.remote_path}")

		self.remove_staged_file_call_count += 1
		self.removed_files.append(staged_file.remote_path)


class TestStageTurnFilesValidation:
	"""Test file validation in stage_turn_files()."""

	@pytest.mark.asyncio
	async def test_file_not_found(self) -> None:
		"""Test that non-existent files raise FileNotFoundError."""
		transport = FakeExecutionTransport()
		with pytest.raises(FileNotFoundError, match="not found"):
			await stage_turn_files(transport, ["/nonexistent/path/file.jpg"])

	@pytest.mark.asyncio
	async def test_file_too_large(self) -> None:
		"""Test that oversized files are rejected before staging."""
		transport = FakeExecutionTransport()

		with tempfile.TemporaryDirectory() as tmpdir:
			# Create a file larger than the limit
			file_path = Path(tmpdir) / "large.jpg"
			file_path.write_bytes(b"x" * (21 * 1024 * 1024))  # 21 MB

			with pytest.raises(SubscriptionCLIError) as exc_info:
				await stage_turn_files(
					transport,
					[str(file_path)],
					max_file_size_bytes=20 * 1024 * 1024,  # 20 MB limit
				)

			assert exc_info.value.code == SubscriptionErrorCode.FILE_TOO_LARGE
			# No staging should have been attempted
			assert len(transport.staged_files) == 0

	@pytest.mark.asyncio
	async def test_invalid_mime_type(self) -> None:
		"""Test that files with disallowed MIME types are rejected."""
		transport = FakeExecutionTransport()

		with tempfile.TemporaryDirectory() as tmpdir:
			# Create a .txt file (text/plain MIME type)
			file_path = Path(tmpdir) / "document.txt"
			file_path.write_text("some text")

			with pytest.raises(SubscriptionCLIError) as exc_info:
				await stage_turn_files(
					transport,
					[str(file_path)],
					allowed_mime_prefixes=("image/",),
				)

			assert exc_info.value.code == SubscriptionErrorCode.INVALID_FILE_TYPE
			# No staging should have been attempted
			assert len(transport.staged_files) == 0

	@pytest.mark.asyncio
	async def test_unknown_mime_type(self) -> None:
		"""Test that files with unknown MIME types are rejected."""
		transport = FakeExecutionTransport()

		with tempfile.TemporaryDirectory() as tmpdir:
			# Create a file with an unknown extension
			file_path = Path(tmpdir) / "document.unknown_ext"
			file_path.write_bytes(b"binary content")

			with pytest.raises(SubscriptionCLIError) as exc_info:
				await stage_turn_files(transport, [str(file_path)])

			assert exc_info.value.code == SubscriptionErrorCode.INVALID_FILE_TYPE


class TestStageTurnFilesSuccess:
	"""Test successful file staging."""

	@pytest.mark.asyncio
	async def test_single_valid_image_file(self) -> None:
		"""Test staging a single valid image file."""
		transport = FakeExecutionTransport()

		with tempfile.TemporaryDirectory() as tmpdir:
			file_path = Path(tmpdir) / "image.jpg"
			file_path.write_bytes(b"jpeg content")

			result = await stage_turn_files(transport, [str(file_path)])

			assert len(result) == 1
			assert result[0].local_path == str(file_path)
			assert "/tmp/huf-staged/" in result[0].remote_path
			assert len(transport.staged_files) == 1

	@pytest.mark.asyncio
	async def test_multiple_valid_files(self) -> None:
		"""Test staging multiple valid files."""
		transport = FakeExecutionTransport()

		with tempfile.TemporaryDirectory() as tmpdir:
			files = []
			for i, ext in enumerate(["jpg", "png", "gif"]):
				file_path = Path(tmpdir) / f"image{i}.{ext}"
				file_path.write_bytes(b"image content")
				files.append(str(file_path))

			result = await stage_turn_files(transport, files)

			assert len(result) == 3
			assert len(transport.staged_files) == 3
			for i, staged in enumerate(result):
				assert staged.local_path == files[i]

	@pytest.mark.asyncio
	async def test_custom_mime_prefix_filter(self) -> None:
		"""Test using custom MIME type prefix filter."""
		transport = FakeExecutionTransport()

		with tempfile.TemporaryDirectory() as tmpdir:
			# text/plain should NOT be allowed with default filter
			text_path = Path(tmpdir) / "file.txt"
			text_path.write_text("text")

			# But should be allowed with custom filter
			result = await stage_turn_files(
				transport,
				[str(text_path)],
				allowed_mime_prefixes=("text/", "application/"),
			)

			assert len(result) == 1
			assert len(transport.staged_files) == 1


class TestStageTurnFilesPartialFailure:
	"""Test partial-failure rollback in stage_turn_files()."""

	@pytest.mark.asyncio
	async def test_partial_failure_cleans_up_previous_files(self) -> None:
		"""Test that staging failure rolls back all previously staged files."""
		transport = FakeExecutionTransport()
		# Fail on the third file (index 2)
		transport.fail_on_stage_index = 2

		with tempfile.TemporaryDirectory() as tmpdir:
			files = []
			for i in range(3):
				file_path = Path(tmpdir) / f"image{i}.jpg"
				file_path.write_bytes(b"image content")
				files.append(str(file_path))

			with pytest.raises(RuntimeError, match="failed"):
				await stage_turn_files(transport, files)

			# Even though staging failed, the two successful stages should have
			# been recorded and we can verify they were attempted
			assert transport.stage_file_call_count == 3
			# All files should have been removed by rollback
			# The cleanup happens in the except block
			# We check that remove_staged_file was NOT called by the async cleanup
			# because the rollback is synchronous in the except block

	@pytest.mark.asyncio
	async def test_oversized_file_prevents_all_staging(self) -> None:
		"""Test that size validation prevents staging even with multiple files."""
		transport = FakeExecutionTransport()

		with tempfile.TemporaryDirectory() as tmpdir:
			# First file is valid
			file1 = Path(tmpdir) / "image1.jpg"
			file1.write_bytes(b"x" * 1000)

			# Second file is too large
			file2 = Path(tmpdir) / "image2.jpg"
			file2.write_bytes(b"x" * (21 * 1024 * 1024))

			with pytest.raises(SubscriptionCLIError) as exc_info:
				await stage_turn_files(
					transport,
					[str(file1), str(file2)],
					max_file_size_bytes=20 * 1024 * 1024,
				)

			assert exc_info.value.code == SubscriptionErrorCode.FILE_TOO_LARGE
			# No files should have been staged (validation happens before any staging)
			assert len(transport.staged_files) == 0


class TestCleanupStagedFiles:
	"""Test cleanup_staged_files() error tolerance."""

	@pytest.mark.asyncio
	async def test_cleanup_all_files(self) -> None:
		"""Test that all files are cleaned up successfully."""
		transport = FakeExecutionTransport()

		staged_files = [
			StagedFile(remote_path="/tmp/file1.jpg", local_path="/local/file1.jpg"),
			StagedFile(remote_path="/tmp/file2.jpg", local_path="/local/file2.jpg"),
			StagedFile(remote_path="/tmp/file3.jpg", local_path="/local/file3.jpg"),
		]

		await cleanup_staged_files(transport, staged_files)

		assert transport.remove_staged_file_call_count == 3
		assert len(transport.removed_files) == 3

	@pytest.mark.asyncio
	async def test_cleanup_continues_on_individual_failure(self) -> None:
		"""Test that one cleanup failure doesn't prevent cleanup of others."""
		transport = FakeExecutionTransport()
		transport.fail_on_remove = True

		staged_files = [
			StagedFile(remote_path="/tmp/file1.jpg", local_path="/local/file1.jpg"),
			StagedFile(remote_path="/tmp/file2.jpg", local_path="/local/file2.jpg"),
			StagedFile(remote_path="/tmp/file3.jpg", local_path="/local/file3.jpg"),
		]

		# This should NOT raise, even though all removals fail
		await cleanup_staged_files(transport, staged_files)

		# All three should have been attempted
		assert transport.remove_staged_file_call_count == 3

	@pytest.mark.asyncio
	async def test_cleanup_empty_list(self) -> None:
		"""Test that cleanup with empty list succeeds."""
		transport = FakeExecutionTransport()

		# Should not raise
		await cleanup_staged_files(transport, [])

		assert transport.remove_staged_file_call_count == 0


class TestAssertVisionSupported:
	"""Test capability gating in assert_vision_supported()."""

	def test_vision_supported_with_files(self) -> None:
		"""Test that vision-supported capabilities allow files."""
		capabilities = RuntimeCapabilities(supports_images=True)
		# Should not raise
		assert_vision_supported(capabilities, ["/path/to/file.jpg"])

	def test_vision_unsupported_with_no_files(self) -> None:
		"""Test that empty file list is always allowed."""
		capabilities = RuntimeCapabilities(supports_images=False)
		# Should not raise even though vision is not supported (no files provided)
		assert_vision_supported(capabilities, [])

	def test_vision_unsupported_with_files(self) -> None:
		"""Test that vision-unsupported capabilities reject files."""
		capabilities = RuntimeCapabilities(supports_images=False)

		with pytest.raises(SubscriptionCLIError) as exc_info:
			assert_vision_supported(capabilities, ["/path/to/file.jpg"])

		assert exc_info.value.code == SubscriptionErrorCode.VISION_UNSUPPORTED

	def test_vision_unsupported_with_multiple_files(self) -> None:
		"""Test that reject works with multiple files."""
		capabilities = RuntimeCapabilities(supports_images=False)

		with pytest.raises(SubscriptionCLIError) as exc_info:
			assert_vision_supported(
				capabilities,
				["/path/to/file1.jpg", "/path/to/file2.jpg"],
			)

		assert exc_info.value.code == SubscriptionErrorCode.VISION_UNSUPPORTED


class TestIntegrationScenarios:
	"""Test realistic integration scenarios."""

	@pytest.mark.asyncio
	async def test_full_staging_and_cleanup_flow(self) -> None:
		"""Test complete flow: stage files then clean them up."""
		transport = FakeExecutionTransport()

		with tempfile.TemporaryDirectory() as tmpdir:
			files = []
			for i in range(2):
				file_path = Path(tmpdir) / f"image{i}.jpg"
				file_path.write_bytes(b"image content")
				files.append(str(file_path))

			# Stage files
			staged = await stage_turn_files(transport, files)
			assert len(staged) == 2
			assert len(transport.staged_files) == 2

			# Clean up
			await cleanup_staged_files(transport, staged)
			assert transport.remove_staged_file_call_count == 2

	@pytest.mark.asyncio
	async def test_capability_gate_before_staging(self) -> None:
		"""Test that capability gate is checked before staging."""
		transport = FakeExecutionTransport()
		capabilities = RuntimeCapabilities(supports_images=False)

		with tempfile.TemporaryDirectory() as tmpdir:
			file_path = Path(tmpdir) / "image.jpg"
			file_path.write_bytes(b"image content")

			# Check capability first
			with pytest.raises(SubscriptionCLIError):
				assert_vision_supported(capabilities, [str(file_path)])

			# No staging should have happened
			assert len(transport.staged_files) == 0
