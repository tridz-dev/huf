"""Stable HUF-owned errors for bounded decision execution."""

from __future__ import annotations

from enum import Enum


class DecisionErrorCode(str, Enum):
	PROVIDER_UNAVAILABLE = "DECISION_PROVIDER_UNAVAILABLE"
	TIMEOUT = "DECISION_TIMEOUT"
	RATE_LIMITED = "DECISION_RATE_LIMITED"
	INVALID_RESPONSE = "DECISION_INVALID_RESPONSE"
	UNSUPPORTED_CAPABILITY = "DECISION_UNSUPPORTED_CAPABILITY"
	POLICY_INVALID = "DECISION_POLICY_INVALID"
	STATE_TOO_LARGE = "DECISION_STATE_TOO_LARGE"
	CANDIDATE_INVALID = "DECISION_CANDIDATE_INVALID"
	LOW_CONFIDENCE = "DECISION_LOW_CONFIDENCE"
	NO_MATCH = "DECISION_NO_MATCH"
	UNSUPPORTED_MODALITY = "DECISION_UNSUPPORTED_MODALITY"
	CANDIDATE_LIMIT_EXCEEDED = "DECISION_CANDIDATE_LIMIT_EXCEEDED"
	THROUGHPUT_BUDGET_EXHAUSTED = "DECISION_THROUGHPUT_BUDGET_EXHAUSTED"
	BACKEND_NOT_REGISTERED = "DECISION_BACKEND_NOT_REGISTERED"
	FAILED = "DECISION_FAILED"


class DecisionError(Exception):
	"""A safe, stable decision error; provider details are kept out of its message."""

	def __init__(self, code: DecisionErrorCode, message: str | None = None):
		self.code = code
		super().__init__(message or code.value)


class DecisionBackendError(DecisionError):
	"""Backend failure mapped to a HUF-owned error code."""
