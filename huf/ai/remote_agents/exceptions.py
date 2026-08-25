"""Exceptions shared across Huf's remote-agent integration paths."""

from __future__ import annotations

try:
	import frappe

	_PolicyErrorBase = frappe.PermissionError
except Exception:  # pragma: no cover - importable outside Frappe for unit tests  # noqa: BLE001
	_PolicyErrorBase = PermissionError


class RemoteAgentError(Exception):
	"""Base class for outbound/inbound remote-agent errors."""


class RemoteAgentRecursionError(RemoteAgentError):
	"""Raised when a remote-agent call would create a cycle or exceed the max chain depth."""

	def __init__(self, message: str, chain: list[str], attempted_hop: str):
		super().__init__(message)
		self.chain = chain
		self.attempted_hop = attempted_hop


# When frappe.PermissionError is just ``Exception`` (test stubs), inheriting both
# Exception and RemoteAgentError creates an MRO conflict because RemoteAgentError
# already derives from Exception. In that case fall back to RemoteAgentError only.
if _PolicyErrorBase is Exception:
	class RemoteAgentPolicyError(RemoteAgentError):
		"""Raised when a caller or requested agent is denied by Remote Agent Policy."""

		def __init__(self, message: str):
			super().__init__(message)
else:
	class RemoteAgentPolicyError(_PolicyErrorBase, RemoteAgentError):
		"""Raised when a caller or requested agent is denied by Remote Agent Policy."""

		def __init__(self, message: str):
			super().__init__(message)


class RemoteAgentNotImplementedError(RemoteAgentError, NotImplementedError):
	"""Raised when a protocol-specific feature is not yet implemented."""

	def __init__(self, message: str):
		super().__init__(message)
