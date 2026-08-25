"""ACP server implementation: "Huf as an ACP agent".

The server is a thin JSON-RPC stdio proxy that translates ACP session
lifecycle messages into calls against a running Huf site's REST API. It is
intentionally importable without a Frappe site context so it can be launched
as a standalone CLI (``huf-acp``).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from huf.ai.acp.protocol import (
	ACP_PROTOCOL_VERSION,
	ERROR_INTERNAL_ERROR,
	ERROR_INVALID_PARAMS,
	ERROR_INVALID_REQUEST,
	ERROR_METHOD_NOT_FOUND,
	METHOD_EXIT,
	METHOD_INITIALIZE,
	METHOD_INITIALIZED,
	METHOD_SESSION_CANCEL,
	METHOD_SESSION_DELETE,
	METHOD_SESSION_NEW,
	METHOD_SESSION_PROMPT,
	METHOD_SESSION_UPDATE,
	JsonRpcError,
	JsonRpcNotification,
	JsonRpcRequest,
	JsonRpcResponse,
	make_server_capabilities,
)
from huf.ai.acp.transport import AcpTransport

logger = logging.getLogger(__name__)

DEFAULT_RUN_TIMEOUT_SECONDS = 120
"""Default wall-clock time to wait for a Huf run to complete."""

POLL_INTERVAL_SECONDS = 0.5
"""Interval between polls when waiting for a Huf run result."""


# -----------------------------------------------------------------------------
# Session state
# -----------------------------------------------------------------------------

@dataclass
class AcpSession:
	"""In-memory state for one ACP session."""

	session_id: str
	agent_name: str
	conversation_id: str | None = None
	status: str = "active"  # active, cancelled, deleted
	created_at: float = field(default_factory=time.time)


# -----------------------------------------------------------------------------
# Server
# -----------------------------------------------------------------------------

class AcpServer:
	"""ACP server translating stdio JSON-RPC to Huf REST calls."""

	def __init__(
		self,
		transport: AcpTransport,
		*,
		site: str,
		api_key: str,
		api_secret: str,
		default_agent: str,
		request_timeout: float = DEFAULT_RUN_TIMEOUT_SECONDS,
		poll_interval: float = POLL_INTERVAL_SECONDS,
	) -> None:
		self.transport = transport
		self.site = site.rstrip("/")
		self.api_key = api_key
		self.api_secret = api_secret
		self.default_agent = default_agent
		self.request_timeout = request_timeout
		self.poll_interval = poll_interval
		self._sessions: dict[str, AcpSession] = {}
		self._initialized = False

		# Wire ourselves into the transport so incoming requests dispatch here.
		self.transport.request_handler = self.handle_request
		self.transport.notification_handler = self.handle_notification

	async def serve(self) -> None:
		"""Start the transport and wait until it closes."""
		read_task = self.transport.start()
		try:
			await read_task
		except asyncio.CancelledError:
			pass
		finally:
			await self.transport.close()

	async def handle_request(self, request: JsonRpcRequest) -> JsonRpcResponse | None:
		"""Dispatch an incoming JSON-RPC request to the appropriate handler."""
		method = request.method
		params = request.params or {}

		if method == METHOD_INITIALIZE:
			return await self._handle_initialize(request.id, params)

		if method == METHOD_SESSION_NEW:
			return await self._handle_session_new(request.id, params)

		if method == METHOD_SESSION_PROMPT:
			return await self._handle_session_prompt(request.id, params)

		if method == METHOD_SESSION_CANCEL:
			return await self._handle_session_cancel(request.id, params)

		if method == METHOD_SESSION_DELETE:
			return await self._handle_session_delete(request.id, params)

		return JsonRpcResponse(
			id=request.id,
			error=JsonRpcError(
				code=ERROR_METHOD_NOT_FOUND,
				message=f"Method not found: {method}",
			),
		)

	async def handle_notification(self, notification: JsonRpcNotification) -> None:
		"""Handle client-to-server notifications."""
		method = notification.method
		if method == METHOD_INITIALIZED:
			logger.debug("Client initialized notification received")
			return
		if method == METHOD_EXIT:
			logger.info("Received exit notification; closing server")
			await self.transport.close()
			return
		logger.debug("Ignoring notification: %s", method)

	# -------------------------------------------------------------------------
	# Handshake
	# -------------------------------------------------------------------------
	async def _handle_initialize(
		self,
		request_id: int | str,
		params: dict[str, Any],
	) -> JsonRpcResponse:
		client_version = params.get("protocolVersion")
		if not isinstance(client_version, int) or isinstance(client_version, bool):
			return JsonRpcResponse(
				id=request_id,
				error=JsonRpcError(
					code=ERROR_INVALID_PARAMS,
					message="Invalid params",
					data={"protocolVersion": {"_errors": ["Invalid input: expected number, received string"]}},
				),
			)

		# V1 accepts the negotiated protocol version if it matches ours.
		if client_version != ACP_PROTOCOL_VERSION:
			return JsonRpcResponse(
				id=request_id,
				error=JsonRpcError(
					code=ERROR_INVALID_PARAMS,
					message="Invalid params",
					data={"protocolVersion": {"_errors": [f"Unsupported protocol version: {client_version}"]}},
				),
			)

		self._initialized = True
		return JsonRpcResponse(
			id=request_id,
			result=make_server_capabilities(
				agent_name="Huf",
				agent_version="1.0.0",
			),
		)

	# -------------------------------------------------------------------------
	# Session lifecycle
	# -------------------------------------------------------------------------
	async def _handle_session_new(
		self,
		request_id: int | str,
		params: dict[str, Any],
	) -> JsonRpcResponse:
		if not self._initialized:
			return self._not_initialized(request_id)

		cwd = params.get("cwd")
		mcp_servers = params.get("mcpServers")
		if not isinstance(cwd, str):
			return JsonRpcResponse(
				id=request_id,
				error=JsonRpcError(
					code=ERROR_INVALID_PARAMS,
					message="Invalid params",
					data={"cwd": {"_errors": ["Invalid input: expected string, received undefined"]}},
				),
			)
		if mcp_servers is None:
			return JsonRpcResponse(
				id=request_id,
				error=JsonRpcError(
					code=ERROR_INVALID_PARAMS,
					message="Invalid params",
					data={"mcpServers": {"_errors": ["Required value is missing"]}},
				),
			)

		# Resolve which agent this API key is allowed to drive. For V1 the server
		# is launched with a single default agent in env; policy resolution tells
		# us whether that default agent is actually admitted for this caller.
		try:
			policy = await self._huf_resolve_policy(self.default_agent)
		except Exception as exc:  # noqa: BLE001
			logger.warning("Policy resolution failed: %s", exc)
			return JsonRpcResponse(
				id=request_id,
				error=JsonRpcError(
					code=ERROR_INVALID_REQUEST,
					message=f"Policy resolution failed: {exc}",
				),
			)

		resolved_agent = policy.get("resolved_agent") or self.default_agent
		session_id = f"session_{uuid.uuid4()}"

		# Create a fresh Huf conversation for this ACP session.
		result = await self._huf_chat(
			prompt="",
			create_new=True,
			agent_name=resolved_agent,
		)
		conversation_id = result.get("conversation_id") if isinstance(result, dict) else None

		session = AcpSession(
			session_id=session_id,
			agent_name=resolved_agent,
			conversation_id=conversation_id,
		)
		self._sessions[session_id] = session

		return JsonRpcResponse(
			id=request_id,
			result={
				"sessionId": session_id,
				"configOptions": [],
				"modes": {
					"currentModeId": "default",
					"availableModes": [{"id": "default", "name": "Default"}],
				},
			},
		)

	async def _handle_session_prompt(
		self,
		request_id: int | str,
		params: dict[str, Any],
	) -> JsonRpcResponse | None:
		if not self._initialized:
			return self._not_initialized(request_id)

		session_id = params.get("sessionId")
		prompt_blocks = params.get("prompt")

		if not isinstance(session_id, str):
			return self._invalid_params(request_id, "sessionId", "expected string")
		if not isinstance(prompt_blocks, list) or not prompt_blocks:
			return self._invalid_params(request_id, "prompt", "expected array of content blocks")

		session = self._sessions.get(session_id)
		if session is None or session.status == "deleted":
			return JsonRpcResponse(
				id=request_id,
				error=JsonRpcError(
					code=ERROR_INVALID_PARAMS,
					message="Invalid params",
					data={"sessionId": {"_errors": ["Session not found"]}},
				),
			)

		if session.status == "cancelled":
			return JsonRpcResponse(id=request_id, result={"stopReason": "cancelled"})

		# Extract plain text from the first text block for V1.
		text_parts = [
			str(block.get("text", ""))
			for block in prompt_blocks
			if isinstance(block, dict) and block.get("type") == "text"
		]
		prompt_text = "\n".join(text_parts)

		try:
			run_result = await self._huf_chat(
				prompt=prompt_text,
				conversation_id=session.conversation_id,
				create_new=False,
				agent_name=session.agent_name,
				session_id=session_id,
			)
		except Exception as exc:
			logger.exception("Huf run failed for session %s", session_id)
			return JsonRpcResponse(
				id=request_id,
				error=JsonRpcError(
					code=ERROR_INTERNAL_ERROR,
					message=f"Huf run failed: {exc}",
				),
			)

		response_text = ""
		if isinstance(run_result, dict):
			if run_result.get("error"):
				return JsonRpcResponse(
					id=request_id,
					error=JsonRpcError(
						code=ERROR_INTERNAL_ERROR,
						message=str(run_result["error"]),
					),
				)
			response_text = run_result.get("response") or ""

		# Stream the response back as session/update notifications.
		await self._stream_text_response(session_id, response_text)

		return JsonRpcResponse(id=request_id, result={"stopReason": "end_turn"})

	async def _handle_session_cancel(
		self,
		request_id: int | str,
		params: dict[str, Any],
	) -> JsonRpcResponse:
		if not self._initialized:
			return self._not_initialized(request_id)

		session_id = params.get("sessionId")
		session = self._sessions.get(session_id)
		if session is None:
			return self._session_not_found(request_id)

		session.status = "cancelled"
		return JsonRpcResponse(id=request_id, result={"cancelled": True})

	async def _handle_session_delete(
		self,
		request_id: int | str,
		params: dict[str, Any],
	) -> JsonRpcResponse:
		if not self._initialized:
			return self._not_initialized(request_id)

		session_id = params.get("sessionId")
		session = self._sessions.get(session_id)
		if session is None:
			return self._session_not_found(request_id)

		session.status = "deleted"
		self._sessions.pop(session_id, None)
		return JsonRpcResponse(id=request_id, result={"deleted": True})

	# -------------------------------------------------------------------------
	# Huf REST integration
	# -------------------------------------------------------------------------
	async def _huf_chat(
		self,
		prompt: str,
		*,
		conversation_id: str | None = None,
		create_new: bool = False,
		agent_name: str | None = None,
		session_id: str | None = None,
	) -> Any:
		"""Call Huf's chat/run endpoint via REST and wait for the result.

		Huf's run API is queue-first by default. This method submits the run,
		then polls ``get_agent_run_status`` until it completes or the configured
		request timeout expires. Running the poll loop here (rather than inside
		``_huf_chat_sync``) lets us emit ACP progress notifications and avoids
		blocking a Frappe worker/gunicorn request for the full duration of the
		LLM run.
		"""
		agent_name = agent_name or self.default_agent
		enqueue_result = await self._huf_chat_enqueue(
			prompt, conversation_id, create_new, agent_name
		)

		run_id = enqueue_result.get("agent_run_id") or enqueue_result.get("run_id")
		final_conversation_id = enqueue_result.get(
			"conversation_id"
		) or conversation_id

		# If the site executed inline (now=1 / run_immediately) or otherwise
		# returned a final response immediately, short-circuit.
		if enqueue_result.get("response") is not None or not run_id:
			return {
				"conversation_id": final_conversation_id,
				"run_id": run_id,
				"response": enqueue_result.get("response"),
				"error": enqueue_result.get("error"),
			}

		# Poll until the run finishes or we time out.
		start = time.monotonic()
		last_progress_notify = 0.0
		progress_interval = 2.0
		while time.monotonic() - start < self.request_timeout:
			status = await self._huf_get_run_status(run_id)
			run_status = status.get("status")

			if run_status == "Success":
				return {
					"conversation_id": final_conversation_id,
					"run_id": run_id,
					"response": status.get("response"),
					"error": None,
				}
			if run_status == "Failed":
				return {
					"conversation_id": final_conversation_id,
					"run_id": run_id,
					"response": None,
					"error": status.get("error") or "Agent run failed",
				}

			if session_id and time.monotonic() - last_progress_notify > progress_interval:
				await self._notify_progress(session_id, run_status or "running")
				last_progress_notify = time.monotonic()

			await asyncio.sleep(self.poll_interval)

		return {
			"conversation_id": final_conversation_id,
			"run_id": run_id,
			"response": None,
			"error": f"Agent run did not complete within {self.request_timeout}s",
		}

	async def _huf_chat_enqueue(
		self,
		prompt: str,
		conversation_id: str | None,
		create_new: bool,
		agent_name: str,
	) -> Any:
		"""Submit a run to Huf and return the queued/enqueued payload."""
		loop = asyncio.get_running_loop()
		return await loop.run_in_executor(
			None,
			self._huf_chat_enqueue_sync,
			prompt,
			conversation_id,
			create_new,
			agent_name,
		)

	def _huf_chat_enqueue_sync(
		self,
		prompt: str,
		conversation_id: str | None,
		create_new: bool,
		agent_name: str,
	) -> Any:
		import requests

		url = f"{self.site}/api/method/huf.ai.chat_api.run_agent_sync_chat"
		payload: dict[str, Any] = {
			"agent_name": agent_name,
			"prompt": prompt,
			"create_new": create_new,
		}
		if conversation_id:
			payload["conversation_id"] = conversation_id

		headers = {
			"Content-Type": "application/json",
			"Accept": "application/json",
			"Authorization": f"token {self.api_key}:{self.api_secret}",
		}

		logger.debug("Huf chat enqueue request to %s (create_new=%s)", url, create_new)
		resp = requests.post(
			url,
			json=payload,
			headers=headers,
			timeout=30,
		)
		resp.raise_for_status()
		data = resp.json()
		# Frappe wraps whitelisted method results under "message".
		return data.get("message", data)

	async def _huf_get_run_status(self, run_id: str) -> dict[str, Any]:
		loop = asyncio.get_running_loop()
		return await loop.run_in_executor(None, self._huf_get_run_status_sync, run_id)

	def _huf_get_run_status_sync(self, run_id: str) -> dict[str, Any]:
		import requests

		url = f"{self.site}/api/method/huf.ai.agent_integration.get_agent_run_status"
		headers = {
			"Content-Type": "application/json",
			"Accept": "application/json",
			"Authorization": f"token {self.api_key}:{self.api_secret}",
		}

		logger.debug("Huf run status request for %s", run_id)
		resp = requests.post(
			url,
			json={"agent_run_id": run_id},
			headers=headers,
			timeout=30,
		)
		resp.raise_for_status()
		data = resp.json()
		return data.get("message", data)

	async def _huf_resolve_policy(self, requested_agent: str) -> dict[str, Any]:
		"""Ask the Huf site which agent this API key may drive."""
		loop = asyncio.get_running_loop()
		return await loop.run_in_executor(
			None,
			self._huf_resolve_policy_sync,
			requested_agent,
		)

	def _huf_resolve_policy_sync(self, requested_agent: str) -> dict[str, Any]:
		import requests

		url = f"{self.site}/api/method/huf.ai.remote_agents.api.resolve_agent_policy"
		headers = {
			"Content-Type": "application/json",
			"Accept": "application/json",
			"Authorization": f"token {self.api_key}:{self.api_secret}",
		}
		payload = {
			"caller_type": "user",
			"caller_reference": "",
			"requested_agent": requested_agent,
		}

		logger.debug("Huf policy resolution request to %s", url)
		resp = requests.post(
			url,
			json=payload,
			headers=headers,
			timeout=30,
		)
		resp.raise_for_status()
		data = resp.json()
		return data.get("message", data)

	# -------------------------------------------------------------------------
	# Streaming helpers
	# -------------------------------------------------------------------------
	async def _notify_progress(self, session_id: str, status: str) -> None:
		"""Emit a lightweight progress notification while polling a Huf run."""
		try:
			await self.transport.notify(
				METHOD_SESSION_UPDATE,
				{
					"sessionId": session_id,
					"update": {
						"sessionUpdate": "status",
						"status": status,
					},
				},
			)
		except (RuntimeError, TypeError, ValueError, AttributeError, OSError) as exc:
			logger.debug("Progress notification failed: %s", exc)

	async def _stream_text_response(self, session_id: str, text: str) -> None:
		"""Emit the Huf response as a sequence of session/update chunks.

		V1 streams the complete response word-by-word so the wire shape matches
		a real ACP agent, even though Huf's run API currently returns a final
		string rather than structured run events.
		"""
		if not text:
			return

		words = text.split(" ")
		for word in words:
			if not word:
				continue
			await self.transport.notify(
				METHOD_SESSION_UPDATE,
				{
					"sessionId": session_id,
					"update": {
						"sessionUpdate": "agent_message_chunk",
						"content": {"type": "text", "text": word + " "},
					},
				},
			)
			# Tiny artificial delay keeps the stream visible without adding
			# meaningful latency for human-conversation speeds.
			await asyncio.sleep(0)

	# -------------------------------------------------------------------------
	# Error helpers
	# -------------------------------------------------------------------------
	def _not_initialized(self, request_id: int | str) -> JsonRpcResponse:
		return JsonRpcResponse(
			id=request_id,
			error=JsonRpcError(
				code=ERROR_INVALID_REQUEST,
				message="Server not initialized",
			),
		)

	def _invalid_params(
		self,
		request_id: int | str,
		field: str,
		detail: str,
	) -> JsonRpcResponse:
		return JsonRpcResponse(
			id=request_id,
			error=JsonRpcError(
				code=ERROR_INVALID_PARAMS,
				message="Invalid params",
				data={field: {"_errors": [f"Invalid input: {detail}"]}},
			),
		)

	def _session_not_found(self, request_id: int | str) -> JsonRpcResponse:
		return JsonRpcResponse(
			id=request_id,
			error=JsonRpcError(
				code=ERROR_INVALID_PARAMS,
				message="Invalid params",
				data={"sessionId": {"_errors": ["Session not found"]}},
			),
		)


# -----------------------------------------------------------------------------
# Factory
# -----------------------------------------------------------------------------

def build_acp_server(
	transport: AcpTransport,
	*,
	site: str | None = None,
	api_key: str | None = None,
	api_secret: str | None = None,
	default_agent: str | None = None,
) -> AcpServer:
	"""Build an :class:`AcpServer` from explicit values or environment."""
	site = site or os.environ.get("HUF_ACP_SITE", "")
	api_key = api_key or os.environ.get("HUF_ACP_API_KEY", "")
	api_secret = api_secret or os.environ.get("HUF_ACP_API_SECRET", "")
	default_agent = default_agent or os.environ.get("HUF_ACP_DEFAULT_AGENT", "")

	if not site or not api_key or not api_secret:
		raise ValueError("HUF_ACP_SITE, HUF_ACP_API_KEY, and HUF_ACP_API_SECRET are required")
	if not default_agent:
		raise ValueError("HUF_ACP_DEFAULT_AGENT is required (or pass default_agent=)")

	return AcpServer(
		transport=transport,
		site=site,
		api_key=api_key,
		api_secret=api_secret,
		default_agent=default_agent,
	)
