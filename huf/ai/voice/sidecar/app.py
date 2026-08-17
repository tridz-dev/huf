"""Standalone ASGI sidecar that bridges a browser to a realtime voice provider.

Why this is a separate process
------------------------------
HUF's Frappe backend is served by gunicorn (WSGI). WSGI cannot hold a
long-lived duplex WebSocket, which is exactly what OpenAI-style Realtime APIs
require. So the duplex leg lives here, in a small standalone ASGI process
(uvicorn + FastAPI) that is started separately from the bench web workers and
speaks to the same site database/Redis via a normal frappe context.

Install with the optional dependency group::

    pip install -e ".[realtime]"

Run with::

    FRAPPE_SITE=<site> REALTIME_SIDECAR_PORT=8091 \\
        python -m huf.ai.voice.sidecar.app

``FRAPPE_SITE`` is required - it names the Frappe site whose database, Redis
cache and encryption key this sidecar uses. It must be the same site the
browser minted its voice session against, because the session lookup below
goes through ``frappe.cache()``, which namespaces keys per site.

The session handoff contract
----------------------------
The sidecar never accepts provider credentials, model ids or agent names from
the browser. All the browser supplies is an opaque ``session_id`` in the URL.
Everything else is read from a Redis stash written server-side by
``huf.ai.voice.engines.litellm_realtime.LitellmRealtimeEngine.start_session``.

That stash IS the contract between the engine and this sidecar:

- Key: ``huf:voice:realtime:session:{session_id}``, written and read via
  ``frappe.cache().set_value`` / ``get_value`` (both run the key through
  Frappe's ``make_key``, so the site prefix is applied consistently on both
  sides - do not mix these with raw redis-py calls, see the caveat documented
  in ``huf/ai/client_side_tool.py``).
- Value: a dict shaped::

      {
          "agent": <Agent docname>,
          "model": <AI Model docname>,
          "api_key_provider": <AI Provider docname>,
          "conversation_id": <Agent Conversation docname or None>,
      }

  ``conversation_id`` is optional: when present the sidecar joins that
  existing Agent Conversation for transcript persistence, otherwise it
  starts a fresh one at connect time.

- TTL: short (the engine uses 300s). An expired or missing stash means the
  session was never minted, already ended, or timed out - the WebSocket is
  closed with code ``4404``.

Providers
---------
Only OpenAI's Realtime API is implemented today. A second provider (e.g.
Gemini Live) should be added as a sibling ``_connect_*`` handler selected off
the resolved AI Provider, not by branching inside the proxy pump.
"""

from __future__ import annotations

import asyncio
import os

import aiohttp
import frappe
from fastapi import FastAPI, WebSocket
from fastapi.websockets import WebSocketDisconnect

from huf.ai.voice.persistence import get_or_create_voice_conversation, record_voice_turn

app = FastAPI(title="HUF Realtime Voice Sidecar")

SESSION_CACHE_KEY_PREFIX = "huf:voice:realtime:session:"

OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime"

# Close codes used towards the browser leg.
CLOSE_MISCONFIGURED = 4500  # sidecar itself is not configured (no FRAPPE_SITE)
CLOSE_SESSION_NOT_FOUND = 4404  # unknown/expired session_id
CLOSE_UPSTREAM_FAILED = 4502  # could not reach or authenticate with the provider


def _site() -> str:
	"""Return the Frappe site this sidecar is bound to.

	Raises ``KeyError`` if ``FRAPPE_SITE`` is unset - the caller turns that
	into an explicit close code rather than letting the connection hang.
	"""
	return os.environ["FRAPPE_SITE"]


def _load_session(session_id: str) -> dict | None:
	"""Read the session stash written by the engine's ``start_session``.

	Runs inside an established frappe context (see ``_realtime_bridge``).
	"""
	return frappe.cache().get_value(f"{SESSION_CACHE_KEY_PREFIX}{session_id}")


def _resolve_provider_credentials(session: dict) -> tuple[str | None, str | None]:
	"""Return ``(api_key, model_id)`` for a stashed session.

	The API key is read from the linked ``AI Provider`` with
	``get_password("api_key")`` - the same accessor used by
	``huf.ai.voice.engines.elevenlabs.ElevenLabsConvaiEngine._get_api_key`` and
	``huf.ai.providers.elevenlabs_convai_api._get_settings``. It is never
	logged and never sent to the browser.

	``session["model"]`` is an ``AI Model`` docname; the wire-level model id
	lives in its ``model_name`` field. Any LiteLLM-style ``provider/`` prefix
	is stripped, since the OpenAI Realtime endpoint wants the bare model id.
	"""
	provider_name = session.get("api_key_provider")
	model_docname = session.get("model")
	if not provider_name or not model_docname:
		return None, None

	api_key = frappe.get_doc("AI Provider", provider_name).get_password("api_key")

	model_id = frappe.db.get_value("AI Model", model_docname, "model_name") or model_docname
	if "/" in model_id:
		model_id = model_id.split("/", 1)[1]

	return api_key, model_id


async def _pump_browser_to_provider(browser: WebSocket, provider: aiohttp.ClientWebSocketResponse) -> None:
	"""Forward every frame the browser sends straight through to the provider.

	Frames are relayed verbatim - the sidecar deliberately does not parse or
	rewrite the realtime event protocol on this leg.
	"""
	while True:
		message = await browser.receive()
		if message["type"] == "websocket.disconnect":
			return
		if message.get("text") is not None:
			await provider.send_str(message["text"])
		elif message.get("bytes") is not None:
			await provider.send_bytes(message["bytes"])


async def _pump_provider_to_browser(
	browser: WebSocket,
	provider: aiohttp.ClientWebSocketResponse,
	*,
	agent_name: str | None = None,
	cm=None,
	conversation=None,
) -> None:
	"""Forward every provider frame back to the browser.

	Tool-call events (``response.function_call_arguments.done`` and friends)
	pass through untouched along with everything else: bridging them to the
	existing Redis handoff in ``huf/ai/client_side_tool.py`` is a follow-up and
	is explicitly not attempted here. Unrecognized event types are therefore a
	non-event for the sidecar - it never inspects the payload, so no event type
	can crash this pump.
	"""
	async for frame in provider:
		if frame.type == aiohttp.WSMsgType.TEXT:
			await browser.send_text(frame.data)
			if cm and conversation and agent_name:
				_try_persist_agent_turn(frame.data, cm, conversation, agent_name)
		elif frame.type == aiohttp.WSMsgType.BINARY:
			await browser.send_bytes(frame.data)
		elif frame.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
			return


@app.websocket("/voice/realtime/{session_id}")
async def realtime_bridge(websocket: WebSocket, session_id: str) -> None:
	"""Bridge one browser WebSocket to one provider realtime WebSocket.

	Lifecycle: accept -> establish frappe context -> resolve the session stash,
	the Agent Conversation to persist into, and credentials -> dial the
	provider -> pump both directions until either side closes -> tear the
	frappe context down.
	"""
	await websocket.accept()

	try:
		site = _site()
	except KeyError:
		await websocket.close(code=CLOSE_MISCONFIGURED, reason="FRAPPE_SITE is not set")
		return

	# Establish a frappe context on this (non-request) thread, same pattern as
	# the code-execution broker thread in huf/ai/tools/code_execution.py.
	# These frappe.* calls are synchronous and block the event loop briefly;
	# they only run once per connection, at connect time, before any audio
	# flows - the steady-state proxy below touches frappe not at all.
	#
	# frappe.init() and frappe.connect() are INSIDE the try: if connect()
	# raises (DB unreachable, bad site), frappe.init() has already set up
	# thread-local state that must still be torn down via frappe.destroy(),
	# or every failed connection attempt leaks a thread-local context.
	try:
		frappe.init(site=site)
		frappe.connect()
		session = _load_session(session_id)
		if not session:
			await websocket.close(code=CLOSE_SESSION_NOT_FOUND, reason="Unknown or expired voice session")
			return

		agent_name = session.get("agent")
		conversation_id = session.get("conversation_id")
		cm, conversation = None, None
		if agent_name:
			try:
				cm, conversation = get_or_create_voice_conversation(agent_name, conversation_id)
			except Exception:
				# Persistence is best-effort: a broken/inaccessible conversation_id
				# must never block the call itself from connecting.
				cm, conversation = None, None

		api_key, model_id = _resolve_provider_credentials(session)
		if not api_key or not model_id:
			await websocket.close(code=CLOSE_UPSTREAM_FAILED, reason="Voice session is missing provider credentials")
			return

		await _proxy_openai_realtime(
			websocket,
			api_key=api_key,
			model_id=model_id,
			agent_name=agent_name,
			cm=cm,
			conversation=conversation,
		)
	finally:
		frappe.destroy()


async def _proxy_openai_realtime(
	websocket: WebSocket,
	*,
	api_key: str,
	model_id: str,
	agent_name: str | None = None,
	cm=None,
	conversation=None,
) -> None:
	"""Dial OpenAI's Realtime API and pump frames both ways until either closes.

	``aiohttp`` is used for the upstream leg because it is already a declared
	huf dependency; no extra websocket client library is introduced.
	"""
	headers = {
		"Authorization": f"Bearer {api_key}",
		"OpenAI-Beta": "realtime=v1",
	}

	try:
		async with aiohttp.ClientSession() as http:
			async with http.ws_connect(
				f"{OPENAI_REALTIME_URL}?model={model_id}",
				headers=headers,
				heartbeat=30,
			) as provider:
				pumps = [
					asyncio.create_task(_pump_browser_to_provider(websocket, provider)),
					asyncio.create_task(
						_pump_provider_to_browser(
							websocket,
							provider,
							agent_name=agent_name,
							cm=cm,
							conversation=conversation,
						)
					),
				]
				try:
					# Either direction finishing means the call is over; cancel
					# the other pump rather than leaving it parked on a read.
					await asyncio.wait(pumps, return_when=asyncio.FIRST_COMPLETED)
				finally:
					for pump in pumps:
						pump.cancel()
					await asyncio.gather(*pumps, return_exceptions=True)
	except WebSocketDisconnect:
		return
	except aiohttp.ClientError as e:
		# Upstream refused/dropped us (bad key, bad model, network). Report it
		# on the browser leg instead of dying silently.
		await _safe_close(websocket, CLOSE_UPSTREAM_FAILED, f"Realtime provider unavailable: {type(e).__name__}")
		return

	await _safe_close(websocket, 1000, "Session ended")


async def _safe_close(websocket: WebSocket, code: int, reason: str) -> None:
	"""Close the browser leg, tolerating a browser that already went away."""
	try:
		await websocket.close(code=code, reason=reason)
	except RuntimeError:
		pass


def _try_persist_agent_turn(raw_frame: str, cm, conversation, agent_name: str) -> None:
	"""Best-effort: persist an agent-spoken turn if this frame is a completed transcript event.

	Never raises - a parse failure or persistence error here must never affect
	the live audio relay, which has already happened by the time this runs
	(see the call site in _pump_provider_to_browser).
	"""
	import json as _json

	try:
		event = _json.loads(raw_frame)
		if event.get("type") == "response.audio_transcript.done":
			record_voice_turn(cm, conversation, agent_name, role="agent", content=event.get("transcript", ""))
	except Exception:
		pass


if __name__ == "__main__":
	import uvicorn

	uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("REALTIME_SIDECAR_PORT", 8091)))
