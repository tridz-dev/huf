"""Orchestrator for staging files to execution transports.

This module coordinates file staging for subscription CLI providers. It does NOT
perform any semantic pre-processing (no OCR, summarization, image transformation).
It is a passthrough-mode orchestrator only — it stages raw file bytes for the
provider CLI to consume directly, with validation-gate responsibility remaining
with HUF before provider invocation.

Key responsibilities:
- Validate files exist and meet size/MIME-type constraints
- Call transport.stage_file() for each validated file
- Clean up all staged files on partial failure (rollback)
- Gate vision support via RuntimeCapabilities

Transport implementations (local, Docker, SSH) already handle the actual
copy/mount mechanics — this module coordinates their orchestration.
"""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from typing import Sequence

from huf.ai.subscription.capabilities import RuntimeCapabilities
from huf.ai.subscription.errors import (
	SubscriptionCLIError,
	SubscriptionErrorCode,
)
from huf.ai.subscription.transports.base import (
	ExecutionTransport,
	StagedFile,
)


logger = logging.getLogger(__name__)


async def stage_turn_files(
	transport: ExecutionTransport,
	file_paths: Sequence[str],
	*,
	max_file_size_bytes: int = 20_000_000,
	allowed_mime_prefixes: tuple[str, ...] = ("image/",),
) -> list[StagedFile]:
	"""Stage a sequence of files for provider CLI consumption.

	Validates each file (existence, size, MIME type) before staging. On any
	validation failure OR staging failure after partial success, cleans up all
	already-staged files and raises. No orphaned staged files on partial failure.

	Args:
		transport: ExecutionTransport to stage files on
		file_paths: List of local file paths to stage
		max_file_size_bytes: Maximum allowed file size (default: 20 MB)
		allowed_mime_prefixes: Tuple of MIME type prefixes to allow
			(default: ("image/",))

	Returns:
		List of StagedFile objects for staged files

	Raises:
		SubscriptionCLIError (FILE_TOO_LARGE): File exceeds max_file_size_bytes
		SubscriptionCLIError (INVALID_FILE_TYPE): File MIME type not in allowed list
		FileNotFoundError: File does not exist
		SubscriptionCLIError: Transport staging failed (all previously staged files cleaned up)
	"""
	staged: list[StagedFile] = []

	try:
		for file_path in file_paths:
			# Validate file exists
			path = Path(file_path)
			if not path.exists():
				raise FileNotFoundError(f"File not found: {file_path}")

			# Validate file size
			file_size = path.stat().st_size
			if file_size > max_file_size_bytes:
				raise SubscriptionCLIError(
					SubscriptionErrorCode.FILE_TOO_LARGE,
					f"File {path.name} exceeds maximum size of {max_file_size_bytes} bytes "
					f"({file_size} bytes)",
				)

			# Validate MIME type using mimetypes module
			mime_type, _ = mimetypes.guess_type(file_path)
			if mime_type is None:
				raise SubscriptionCLIError(
					SubscriptionErrorCode.INVALID_FILE_TYPE,
					f"Could not determine MIME type for {path.name}",
				)

			# Check if MIME type matches allowed prefixes
			if not any(mime_type.startswith(prefix) for prefix in allowed_mime_prefixes):
				raise SubscriptionCLIError(
					SubscriptionErrorCode.INVALID_FILE_TYPE,
					f"File type {mime_type} not allowed for {path.name}. "
					f"Allowed types: {', '.join(allowed_mime_prefixes)}",
				)

			# Stage the file via transport
			staged_file = await transport.stage_file(file_path)
			staged.append(staged_file)

	except Exception as e:
		# On any failure, clean up all staged files
		for staged_file in staged:
			try:
				await transport.remove_staged_file(staged_file)
			except Exception as cleanup_error:
				logger.exception(
					"Failed to clean up staged file %s during rollback: %s",
					staged_file.remote_path,
					cleanup_error,
				)
		raise

	return staged


async def cleanup_staged_files(
	transport: ExecutionTransport,
	staged_files: Sequence[StagedFile],
) -> None:
	"""Clean up staged files from transport target.

	Logs individual cleanup failures but does not raise — this function is
	meant to be called in a finally block to ensure cleanup happens even
	if other errors occurred.

	Args:
		transport: ExecutionTransport to clean files from
		staged_files: List of StagedFile objects to clean up
	"""
	for staged_file in staged_files:
		try:
			await transport.remove_staged_file(staged_file)
		except Exception as e:
			logger.warning(
				"Failed to clean up staged file %s: %s",
				staged_file.remote_path,
				e,
			)


def assert_vision_supported(
	capabilities: RuntimeCapabilities,
	file_paths: Sequence[str],
) -> None:
	"""Assert that vision/image input is supported if files are provided.

	Per plan §20.3: "HUF should fail clearly rather than silently dropping
	the image" when capabilities forbid it.

	Args:
		capabilities: RuntimeCapabilities to check
		file_paths: List of file paths being staged

	Raises:
		SubscriptionCLIError (VISION_UNSUPPORTED): File paths provided but
			capabilities.supports_images is False
	"""
	if file_paths and not capabilities.supports_images:
		raise SubscriptionCLIError(
			SubscriptionErrorCode.VISION_UNSUPPORTED,
			"This runtime does not support image/file input",
		)
