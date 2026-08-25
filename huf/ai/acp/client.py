"""ACP client role — ``Huf as an ACP client``.

Spawns an external ACP server (e.g. ``kimi acp``) as a subprocess, drives the
``initialize`` / ``session/new`` / ``session/prompt`` handshake, and returns the
final text response. Subprocess lifecycle includes timeouts, kill, and env/cwd
scrubbing.

This module is async and free of Frappe imports.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
from typing import Any

from .protocol import (
	CONTENT_TYPE_TEXT,
	METHOD_EXIT,
	METHOD_INITIALIZE,
	METHOD_INITIALIZED,
	METHOD_SESSION_DELETE,
	METHOD_SESSION_NEW,
	METHOD_SESSION_PROMPT,
	JsonRpcResponse,
	make_client_capabilities,
	make_text_prompt,
)
from .subprocess_launcher import AcpSubprocessLauncher
from .transport import AcpRpcError, AcpTransport, AcpTransportClosed, TranscriptRecorder

LOGGER = logging.getLogger("huf.ai.acp.client")


class AcpClientError(Exception):
	"""Raised when the ACP client is used incorrectly."""


class NoActiveSessionError(AcpClientError):
	"""No ACP session has been created."""

	def __init__(self) -> None:
		super().__init__("No active ACP session; call new_session() first")


class ClientNotStartedError(AcpClientError):
	"""The ACP client has not been started."""

	def __init__(self) -> None:
		super().__init__("ACP client not started")


DEFAULT_COMMAND_TIMEOUT_SECONDS = 120.0


class AcpClient:
	"""Subprocess ACP client that drives a single external ACP session."""

	def __init__(
		self,
		command: list[str],
		*,
		cwd: str | None = None,
		env: dict[str, str] | None = None,
		timeout: float = DEFAULT_COMMAND_TIMEOUT_SECONDS,
		recorder: TranscriptRecorder | None = None,
	) -> None:
		self.command = command
		self.cwd = cwd
		self.env = env
		self.timeout = timeout
		self.recorder = recorder
		self._launcher: AcpSubprocessLauncher | None = None
		self._process: asyncio.subprocess.Process | None = None
		self._transport: AcpTransport | None = None
		self._session_id: str | None = None
		self._response_chunks: list[str] = []
		self._notifications: list[dict[str, Any]] = []

	async def __aenter__(self) -> AcpClient:
		await self.start()
		return self

	async def __aexit__(self, exc_type, exc, tb) -> None:
		await self.close()

	async def start(self) -> dict[str, Any]:
		"""Spawn the subprocess and run the ``initialize`` handshake."""
		self._launcher = AcpSubprocessLauncher(timeout=self.timeout)
		self._process = await self._launcher.launch(
			self.command,
			cwd=self.cwd,
			env=self._build_env(),
		)

		self._transport = AcpTransport.for_subprocess(
			self._process,
			notification_handler=self._on_notification,
			recorder=self.recorder,
		)
		self._transport.start()

		result = await self._transport.call(
			METHOD_INITIALIZE,
			{
				"protocolVersion": 1,
				"capabilities": make_client_capabilities(),
				"clientInfo": {"name": "huf-acp-client", "version": "1.0.0"},
			},
			timeout=self.timeout,
		)

		# Acknowledge server capabilities.
		await self._transport.notify(METHOD_INITIALIZED, {})
		return result

	async def new_session(self, cwd: str | None = None, mcp_servers: list | None = None) -> dict[str, Any]:
		"""Call ``session/new`` and store the returned session id."""
		params: dict[str, Any] = {
			"cwd": cwd or os.getcwd(),
			"mcpServers": mcp_servers if mcp_servers is not None else {},
		}
		result = await self._transport.call(METHOD_SESSION_NEW, params, timeout=self.timeout)
		self._session_id = result.get("sessionId")
		return result

	async def prompt(self, text: str) -> str:
		"""Send a text prompt and return the concatenated response text."""
		if self._session_id is None:
			raise NoActiveSessionError()
		if self._transport is None:
			raise ClientNotStartedError()

		self._response_chunks.clear()
		result = await self._transport.call(
			METHOD_SESSION_PROMPT,
			{"sessionId": self._session_id, "prompt": make_text_prompt(text)},
			timeout=self.timeout,
		)

		# The final result may contain a stopReason; real response text is in
		# the agent_message_chunk notifications collected above.
		LOGGER.debug("session/prompt final result: %s", result)
		return "".join(self._response_chunks).strip()

	async def delete_session(self) -> dict[str, Any]:
		"""Call ``session/delete`` and clear local session state."""
		if self._transport is None or self._session_id is None:
			return {}
		try:
			result = await self._transport.call(
				METHOD_SESSION_DELETE,
				{"sessionId": self._session_id},
				timeout=self.timeout,
			)
		except AcpTransportClosed:
			result = {}
		self._session_id = None
		return result

	async def close(self) -> None:
		"""Send ``exit`` and terminate/kill the subprocess if needed."""
		if self._transport is not None:
			try:
				await self._transport.notify(METHOD_EXIT, {})
			except Exception as exc:  # noqa: BLE001
				LOGGER.debug("exit notification failed: %s", exc)
			await self._transport.close()
			self._transport = None

		if self._launcher is not None and self._process is not None:
			try:
				await self._launcher.reap(self._process)
			except Exception as exc:  # noqa: BLE001
				LOGGER.warning("ACP subprocess reap failed: %s", exc)
			self._launcher = None
			self._process = None
		elif self._process is not None and self._process.returncode is None:
			# Fallback for processes created without the launcher (legacy / tests).
			try:
				self._process.terminate()
				await asyncio.wait_for(self._process.wait(), timeout=5.0)
			except asyncio.TimeoutError:
				LOGGER.warning("ACP subprocess did not terminate; killing")
				self._process.kill()
				await self._process.wait()
			except ProcessLookupError:
				pass
			self._process = None

	def _on_notification(self, notification) -> None:
		params = notification.params
		update = params.get("update", {})
		if update.get("sessionUpdate") == "agent_message_chunk":
			content = update.get("content", {})
			if content.get("type") == CONTENT_TYPE_TEXT:
				self._response_chunks.append(str(content.get("text", "")))
		self._notifications.append({"method": notification.method, "params": params})

	def _build_env(self) -> dict[str, str]:
		"""Return a scrubbed environment for the subprocess.

		By default only a pinned ``PATH`` is inherited. Callers may supply
		additional safe env vars through ``self.env``.
		"""
		env: dict[str, str] = {}

		# Preserve a minimal PATH so the target binary is discoverable.
		path = shutil.which(self.command[0])
		if path:
			env["PATH"] = os.path.dirname(path)
		else:
			env["PATH"] = "/usr/local/bin:/usr/bin:/bin"

		if self.env:
			# Only allow explicitly listed keys; never merge the worker's full env.
			for key, value in self.env.items():
				if key in _SAFE_ENV_KEYS or key.startswith("HUF_ACP_"):
					env[key] = value

		return env


_SAFE_ENV_KEYS: frozenset[str] = frozenset(
	{
		"PATH",
		"HOME",
		"USER",
		"SHELL",
		"LANG",
		"LC_ALL",
		"TERM",
	}
)


async def run_acp_prompt(
	command: list[str],
	prompt_text: str,
	*,
	cwd: str | None = None,
	env: dict[str, str] | None = None,
	timeout: float = DEFAULT_COMMAND_TIMEOUT_SECONDS,
) -> str:
	"""One-shot helper: spawn, handshake, prompt, return text, cleanup."""
	async with AcpClient(command, cwd=cwd, env=env, timeout=timeout) as client:
		await client.new_session()
		return await client.prompt(prompt_text)
