"""Tests for SubscriptionCLIAdapter abstract base class."""

from __future__ import annotations

import pytest

from huf.ai.subscription.adapters.base import (
	DeleteSessionResult,
	ProviderSession,
	SubscriptionCLIAdapter,
	SessionStatus,
)
from huf.ai.subscription.capabilities import RuntimeCapabilities
from huf.ai.subscription.types import AuthChallenge, AuthStatus, SubscriptionTurnRequest, SubscriptionTurnResult
from huf.ai.subscription.transports.base import ExecutionTransport, ProcessResult, TransportProbe


class DummyTransport(ExecutionTransport):
	"""Minimal ExecutionTransport for testing."""

	async def probe(self) -> TransportProbe:
		return TransportProbe(reachable=True)

	async def run(self, argv: list[str], *, cwd: str | None = None, env: dict[str, str] | None = None, stdin: str | None = None, timeout: int | None = None) -> ProcessResult:
		return ProcessResult(stdout="", stderr="", exit_code=0)

	async def stage_file(self, source_path: str, *, target_name: str | None = None):
		raise NotImplementedError

	async def remove_staged_file(self, staged_file):
		pass


class ConcreteAdapter(SubscriptionCLIAdapter):
	"""Minimal concrete implementation of SubscriptionCLIAdapter for testing."""

	async def probe(self, runtime: object) -> RuntimeCapabilities:
		return RuntimeCapabilities()

	async def check_auth(self, runtime: object) -> AuthStatus:
		return AuthStatus(state="authenticated", account_hint="user@example.com", method="token", message="Ready", checked_at="2026-09-26T00:00:00Z")

	async def begin_auth(self, runtime: object) -> AuthChallenge:
		return AuthChallenge(challenge_id="ch_001", provider="example", mode="token", verification_url=None, user_code=None, requires_huf_input=True, prompt="Enter token:", expires_at=None, poll_supported=False)

	async def submit_auth_input(self, runtime: object, challenge_id: str, value: str) -> AuthStatus:
		return AuthStatus(state="authenticated", account_hint="user@example.com", method="token", message="Token accepted", checked_at="2026-09-26T00:00:00Z")

	async def poll_auth(self, runtime: object, challenge_id: str) -> AuthStatus:
		return AuthStatus(state="authenticated", account_hint="user@example.com", method="token", message="Approved", checked_at="2026-09-26T00:00:00Z")

	async def create_session(self, request: SubscriptionTurnRequest) -> ProviderSession:
		return ProviderSession(session_id="sess_001", created_at="2026-09-26T00:00:00Z")

	async def validate_session(self, runtime: object, session_id: str) -> SessionStatus:
		return SessionStatus(exists=True, detail="Session is active")

	async def delete_session(self, runtime: object, session_id: str) -> DeleteSessionResult:
		return DeleteSessionResult(cleanup_status="deleted")

	async def run_turn(self, runtime: object, request: SubscriptionTurnRequest) -> SubscriptionTurnResult:
		return SubscriptionTurnResult(status="success", final_text="Hello from concrete adapter", provider_session_id="sess_001")


class TestSubscriptionCLIAdapterAbstractness:
	"""Test that SubscriptionCLIAdapter properly enforces abstract methods."""

	def test_cannot_instantiate_abstract_adapter(self):
		"""Instantiating SubscriptionCLIAdapter directly should raise TypeError."""
		transport = DummyTransport()
		with pytest.raises(TypeError, match="Can't instantiate abstract class"):
			SubscriptionCLIAdapter(transport)

	def test_concrete_adapter_instantiation(self):
		"""A concrete implementation with all abstract methods can be instantiated."""
		transport = DummyTransport()
		adapter = ConcreteAdapter(transport)
		assert adapter is not None
		assert adapter.transport is transport

	def test_default_no_op_methods(self):
		"""Default no-op methods (cancel_auth, logout) should be callable."""
		transport = DummyTransport()
		adapter = ConcreteAdapter(transport)

		# These should not raise, even though they're not abstract
		import asyncio
		asyncio.run(adapter.cancel_auth(object(), "ch_001"))
		asyncio.run(adapter.logout(object()))

	def test_provider_session_dataclass(self):
		"""ProviderSession dataclass should validate inputs."""
		# Valid construction
		session = ProviderSession(session_id="sess_001", created_at="2026-09-26T00:00:00Z")
		assert session.session_id == "sess_001"

		# Empty session_id should raise
		with pytest.raises(ValueError, match="session_id is required"):
			ProviderSession(session_id="", created_at="2026-09-26T00:00:00Z")

		# Empty created_at should raise
		with pytest.raises(ValueError, match="created_at"):
			ProviderSession(session_id="sess_001", created_at="")

	def test_session_status_dataclass(self):
		"""SessionStatus dataclass should be constructible."""
		status = SessionStatus(exists=True, detail="Active")
		assert status.exists is True
		assert status.detail == "Active"

		# detail is optional
		status_no_detail = SessionStatus(exists=False)
		assert status_no_detail.exists is False
		assert status_no_detail.detail is None

	def test_delete_session_result_validation(self):
		"""DeleteSessionResult should validate cleanup_status."""
		# Valid statuses
		for status_str in ["deleted", "discarded_reference", "provider_retained", "cleanup_failed"]:
			result = DeleteSessionResult(cleanup_status=status_str)
			assert result.cleanup_status == status_str

		# Invalid status should raise
		with pytest.raises(ValueError, match="cleanup_status must be one of"):
			DeleteSessionResult(cleanup_status="invalid")
