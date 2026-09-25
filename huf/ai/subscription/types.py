"""Immutable, provider-neutral value objects for subscription CLI turns and auth."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class SubscriptionTurnRequest:
	"""
	A CLOSED request to the subscription CLI provider.

	This type intentionally carries ONLY the current turn's input and metadata.
	It must NEVER include conversation history, system prompts, tool schemas,
	or knowledge context — those must be managed outside this interface
	(passthrough design).
	"""

	runtime_name: str
	provider_session_id: str | None
	text: str
	files: list[str]
	model_override: str | None
	run_id: str
	conversation_id: str | None
	timeout_seconds: int

	def __post_init__(self) -> None:
		if not self.runtime_name or not self.runtime_name.strip():
			raise ValueError("runtime_name is required")
		if not self.text or not self.text.strip():
			raise ValueError("text is required")
		if not self.run_id or not self.run_id.strip():
			raise ValueError("run_id is required")
		if self.timeout_seconds <= 0:
			raise ValueError("timeout_seconds must be positive")


@dataclass(frozen=True, slots=True)
class SubscriptionTurnResult:
	"""Result of a subscription CLI turn."""

	status: str
	final_text: str | None
	provider_session_id: str | None
	usage: dict[str, Any] = field(default_factory=dict)
	reasoning_summary: str | None = None
	events: list[dict[str, Any]] = field(default_factory=list)
	raw_debug_ref: str | None = None
	exit_code: int | None = None
	auth_reason: str | None = None

	def __post_init__(self) -> None:
		if not self.status or not self.status.strip():
			raise ValueError("status is required")


@dataclass(frozen=True, slots=True)
class AuthStatus:
	"""Current authentication status for a subscription CLI provider."""

	state: str
	account_hint: str | None
	method: str | None
	message: str | None
	checked_at: str

	def __post_init__(self) -> None:
		if not self.state or not self.state.strip():
			raise ValueError("state is required")
		if not self.checked_at or not self.checked_at.strip():
			raise ValueError("checked_at (ISO datetime string) is required")


@dataclass(frozen=True, slots=True)
class AuthChallenge:
	"""An authentication challenge presented by a subscription CLI provider."""

	challenge_id: str
	provider: str
	mode: str
	verification_url: str | None
	user_code: str | None
	requires_huf_input: bool
	prompt: str | None
	expires_at: str | None
	poll_supported: bool

	def __post_init__(self) -> None:
		if not self.challenge_id or not self.challenge_id.strip():
			raise ValueError("challenge_id is required")
		if not self.provider or not self.provider.strip():
			raise ValueError("provider is required")
		if not self.mode or not self.mode.strip():
			raise ValueError("mode is required")
