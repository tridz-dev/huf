"""Stable HUF-owned errors for subscription CLI provider integration."""

from __future__ import annotations

from enum import Enum


class SubscriptionErrorCode(str, Enum):
	"""Error codes for subscription CLI operations."""

	CLI_NOT_INSTALLED = "SUBSCRIPTION_CLI_NOT_INSTALLED"
	CLI_UNSUPPORTED_VERSION = "SUBSCRIPTION_CLI_UNSUPPORTED_VERSION"
	RUNTIME_UNREACHABLE = "SUBSCRIPTION_RUNTIME_UNREACHABLE"
	RUNTIME_PERMISSION_DENIED = "SUBSCRIPTION_RUNTIME_PERMISSION_DENIED"
	AUTH_REQUIRED = "SUBSCRIPTION_AUTH_REQUIRED"
	AUTH_CHALLENGE_FAILED = "SUBSCRIPTION_AUTH_CHALLENGE_FAILED"
	AUTH_CHALLENGE_EXPIRED = "SUBSCRIPTION_AUTH_CHALLENGE_EXPIRED"
	AUTH_REQUIRED_TIMEOUT = "SUBSCRIPTION_AUTH_REQUIRED_TIMEOUT"
	SESSION_NOT_FOUND = "SUBSCRIPTION_SESSION_NOT_FOUND"
	SESSION_RESUME_FAILED = "SUBSCRIPTION_SESSION_RESUME_FAILED"
	SESSION_PROVIDER_MISMATCH = "SUBSCRIPTION_SESSION_PROVIDER_MISMATCH"
	MODEL_UNAVAILABLE = "SUBSCRIPTION_MODEL_UNAVAILABLE"
	VISION_UNSUPPORTED = "SUBSCRIPTION_VISION_UNSUPPORTED"
	USAGE_UNAVAILABLE = "SUBSCRIPTION_USAGE_UNAVAILABLE"
	CLI_OUTPUT_PARSE_FAILED = "SUBSCRIPTION_CLI_OUTPUT_PARSE_FAILED"
	CLI_PROCESS_TIMEOUT = "SUBSCRIPTION_CLI_PROCESS_TIMEOUT"
	CLI_PROCESS_FAILED = "SUBSCRIPTION_CLI_PROCESS_FAILED"
	FILE_TOO_LARGE = "SUBSCRIPTION_FILE_TOO_LARGE"
	INVALID_FILE_TYPE = "SUBSCRIPTION_INVALID_FILE_TYPE"


class SubscriptionError(Exception):
	"""Base subscription error; provider details are kept out of its message."""

	def __init__(self, code: SubscriptionErrorCode, message: str | None = None):
		self.code = code
		super().__init__(message or code.value)


class SubscriptionCLIError(SubscriptionError):
	"""CLI execution or communication failure."""

	pass


class SubscriptionAuthError(SubscriptionError):
	"""Authentication or authorization failure."""

	pass


class SubscriptionRuntimeError(SubscriptionError):
	"""Subscription runtime/provider failure."""

	pass
