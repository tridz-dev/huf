"""Remote-agent adapter ABC and ACP stdio implementation.

This module is the canonical home of the protocol-agnostic ``RemoteAgentAdapter`` seam and
its ACP stdio implementation. The legacy shim in ``huf.ai.acp.adapter`` re-exports from here
so existing tests and PR #661's factory patching continue to work.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from huf.ai.acp.client import DEFAULT_COMMAND_TIMEOUT_SECONDS, AcpClient
from huf.ai.remote_agents.exceptions import RemoteAgentNotImplementedError, RemoteAgentRecursionError
from huf.ai.remote_agents.recursion_guard import CallChain, check_and_extend

LOGGER = logging.getLogger("huf.ai.remote_agents.adapter")

# Default env key used when a connection injects an auth secret into the child process.
DEFAULT_AUTH_ENV_KEY = "HUF_ACP_TARGET_TOKEN"


class RemoteAgentAdapter(ABC):
	"""Protocol-agnostic adapter for invoking an external agent."""

	@abstractmethod
	def fetch_manifest(self) -> dict[str, Any]: ...

	@abstractmethod
	def create_run(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...

	@abstractmethod
	def get_run(self, run_id: str) -> dict[str, Any]: ...

	@abstractmethod
	def get_events(self, run_id: str, cursor: str | None = None) -> dict[str, Any]: ...

	@abstractmethod
	def cancel_run(self, run_id: str) -> dict[str, Any]: ...


class AcpStdioAdapter(RemoteAgentAdapter):
	"""Adapter that invokes an external ACP agent over stdio.

	Configuration is expected as kwargs matching a ``Remote Agent Connection``
	row (or the fields planned for ACP support): ``connection_name``,
	``launch_command``, ``launch_args``, ``working_directory``, ``auth_secret``,
	``auth_env_key``, etc.
	"""

	def __init__(
		self,
		*,
		connection_name: str,
		launch_command: str,
		launch_args: list[str] | None = None,
		working_directory: str | None = None,
		env: dict[str, str] | None = None,
		auth_secret: str | None = None,
		auth_env_key: str | None = None,
		timeout: float = DEFAULT_COMMAND_TIMEOUT_SECONDS,
		call_chain: list[str] | None = None,
	) -> None:
		self.connection_name = connection_name
		self.launch_command = launch_command
		self.launch_args = launch_args or []
		self.working_directory = working_directory
		self.timeout = timeout
		self.call_chain = call_chain or []
		self._client: AcpClient | None = None
		self._session_id: str | None = None
		self._result_text: str = ""
		self._env: dict[str, str] = dict(env) if env else {}
		if auth_secret:
			key = auth_env_key or DEFAULT_AUTH_ENV_KEY
			self._env[key] = auth_secret

	async def fetch_manifest(self) -> dict[str, Any]:
		"""Run ``initialize`` and return a normalized capability manifest."""
		client = AcpClient(
			[self.launch_command, *self.launch_args],
			cwd=self.working_directory,
			env=self._env,
			timeout=self.timeout,
		)
		try:
			result = await client.start()
		finally:
			await client.close()

		return {
			"server_name": result.get("agentInfo", {}).get("name", "unknown"),
			"protocol_version": result.get("protocolVersion"),
			"agents": [],
			"raw_manifest": result,
		}

	async def create_run(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
		"""Map ``create_run`` to ``session/new`` + ``session/prompt``.

		Applies the recursion guard before creating the outbound session. A cycle or
		max-depth violation surfaces as a structured error dict rather than raising.
		"""
		hop_id = f"acp:{self.connection_name}:{agent_id}"
		chain = CallChain.from_header_value(",".join(self.call_chain))
		try:
			new_chain = check_and_extend(chain, hop_id)
		except RemoteAgentRecursionError as exc:
			return {
				"run_id": None,
				"status": "error",
				"error": "recursive_call",
				"message": str(exc),
				"chain": exc.chain,
			}

		self._client = AcpClient(
			[self.launch_command, *self.launch_args],
			cwd=self.working_directory,
			env=self._env,
			timeout=self.timeout,
		)
		await self._client.start()

		session_payload: dict[str, Any] = {"cwd": self.working_directory or ""}
		meta = payload.get("_meta") or {}
		meta["huf_call_chain"] = new_chain.to_header_value()
		session_payload["_meta"] = meta

		session = await self._client.new_session(cwd=self.working_directory)
		self._session_id = session.get("sessionId")

		prompt_text = payload.get("prompt", "")
		self._result_text = await self._client.prompt(prompt_text)

		return {
			"run_id": self._session_id,
			"status": "success",
			"response": self._result_text,
			"error": None,
			"raw_response": {"session": session, "text": self._result_text},
			"call_chain": new_chain.to_header_value(),
		}

	async def get_run(self, run_id: str) -> dict[str, Any]:
		"""ACP has no separate "get" call; return last-known state."""
		return {
			"run_id": run_id,
			"status": "success" if run_id == self._session_id else "unknown",
			"response": self._result_text,
			"error": None,
			"raw_response": {},
		}

	async def get_events(self, run_id: str, cursor: str | None = None) -> dict[str, Any]:
		"""Return buffered notifications from the last session."""
		if self._client is None:
			return {"events": [], "cursor": cursor}
		notifications = [
			{"method": n["method"], "params": n["params"]}
			for n in getattr(self._client, "_notifications", [])
		]
		return {"events": notifications, "cursor": cursor or "0"}

	async def cancel_run(self, run_id: str) -> dict[str, Any]:
		"""Map ``cancel_run`` to ``session/delete`` (or ``session/cancel``)."""
		if self._client is None:
			return {"run_id": run_id, "status": "not_found"}
		try:
			await self._client.delete_session()
		except Exception as exc:
			LOGGER.exception("cancel_run failed")
			return {"run_id": run_id, "status": "error", "error": str(exc)}
		else:
			return {"run_id": run_id, "status": "cancelled"}
		finally:
			await self._client.close()
			self._client = None


def get_adapter(protocol_type: str, **kwargs: Any) -> RemoteAgentAdapter:
	"""Factory for ``RemoteAgentAdapter`` implementations."""
	if protocol_type == "acp_stdio":
		return AcpStdioAdapter(**kwargs)
	raise RemoteAgentNotImplementedError(
		f"Unsupported or unimplemented protocol_type: {protocol_type!r}"
	)
