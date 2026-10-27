# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""EXPERIMENTAL greeting-answer flow for WhatsApp Business Calling (default OFF).

Answers an inbound call from an approved caller, plays pre-recorded audio clips and hangs up.
NO RECORDING: caller audio goes only to an in-memory sink; only metadata is ever persisted.

Pluggable audio (so a realtime provider such as Gemini Live can replace file playback later):

* :class:`CallAudioSource`  - decides which bot audio to play next (``next_clip``).
* :class:`CallAudioSink`    - receives caller audio (``write``).
* :class:`MediaSession`     - the transport (aiortc peer connection, or an in-process fake).

aiortc is optional and imported lazily; without it :func:`get_media_backend` reports
``not_installed`` and the job rejects the call cleanly.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# States of one call, in order (FAILED / REJECTED can occur from any earlier state).
RECEIVED, ANSWERING, PRE_ACCEPTED, CONNECTED, ACCEPTED, PLAYING, TERMINATING, COMPLETED, FAILED, REJECTED = (
	"received", "answering", "pre_accepted", "connected", "accepted", "playing", "terminating", "completed",
	"failed", "rejected",
)
DEFAULT_MAX_SECONDS = 60
DEFAULT_CONNECT_TIMEOUT = 20.0
MAX_CLIPS = 6


# --------------------------------------------------------------------- audio interfaces
@dataclass(frozen=True)
class AudioClip:
	"""One pre-recorded audio file. ``data`` is optional (sim/in-memory); real playback uses ``path``."""

	name: str
	path: str = ""
	data: bytes = field(default=b"", repr=False)
	mime_type: str = "audio/ogg"

	def digest(self) -> str:
		if self.data:
			return hashlib.sha256(self.data).hexdigest()[:16]
		return ""

	def summary(self) -> dict[str, Any]:
		return {"name": self.name, "bytes": len(self.data), "sha256": self.digest()}


class CallAudioSource(ABC):
	"""Produces the bot side of the conversation, one clip at a time."""

	#: When True the flow listens for the caller after each clip and passes it to ``next_clip``.
	wants_caller_audio: bool = False

	@abstractmethod
	def next_clip(self, heard: AudioClip | None) -> AudioClip | None:
		"""Next clip to play (``None`` = end the call). ``heard`` is the caller's last utterance, if any."""


class CallAudioSink(ABC):
	"""Receives caller audio. Implementations must NOT persist it (no-recording policy)."""

	@abstractmethod
	def write(self, clip: AudioClip) -> None: ...


class FilePlayback(CallAudioSource):
	"""Plays a fixed list of pre-recorded files in order (greeting, reply, closing)."""

	def __init__(self, clips: list[AudioClip], *, listen_between: bool = False):
		self._clips = list(clips)[:MAX_CLIPS]
		self._i = 0
		self.wants_caller_audio = listen_between

	def next_clip(self, heard: AudioClip | None) -> AudioClip | None:
		if self._i >= len(self._clips):
			return None
		clip = self._clips[self._i]
		self._i += 1
		return clip


class InMemoryAudioSink(CallAudioSink):
	"""Keeps only metadata (name/bytes/hash). ``retain`` keeps bytes in memory for simulator assertions."""

	def __init__(self, retain: bool = False):
		self._retain = retain
		self.received: list[dict[str, Any]] = []
		self.clips: list[AudioClip] = []

	def write(self, clip: AudioClip) -> None:
		self.received.append(clip.summary())
		if self._retain:
			self.clips.append(clip)


# --------------------------------------------------------------------- media transport
class MediaSession(ABC):
	"""Transport for one call. The gate keeps outbound audio silent until ``open_gate()``."""

	@abstractmethod
	async def create_answer(self, offer_sdp: str) -> str: ...

	@abstractmethod
	async def wait_connected(self, timeout: float) -> bool: ...

	@abstractmethod
	def open_gate(self) -> None: ...

	@abstractmethod
	async def play(self, clip: AudioClip) -> None: ...

	@abstractmethod
	async def listen(self, timeout: float) -> AudioClip | None: ...

	@abstractmethod
	async def close(self) -> None: ...


class FakeMediaSession(MediaSession):
	"""In-process loopback used by the simulator and tests (no aiortc, no network).

	``caller_clips`` are what the simulated caller "says" after each bot clip.
	"""

	def __init__(self, caller_clips: list[AudioClip] | None = None, *, connect: bool = True, answer_sdp: str = "v=0 fake-answer"):
		self._caller = list(caller_clips or [])
		self._connect = connect
		self._answer = answer_sdp
		self._gate = False
		self.played: list[str] = []
		self.gate_violations = 0
		self.closed = False

	async def create_answer(self, offer_sdp: str) -> str:
		if not offer_sdp:
			raise ValueError("empty SDP offer")
		return self._answer

	async def wait_connected(self, timeout: float) -> bool:
		return self._connect

	def open_gate(self) -> None:
		self._gate = True

	async def play(self, clip: AudioClip) -> None:
		if not self._gate:
			self.gate_violations += 1
			raise RuntimeError("audio sent before accept")
		self.played.append(clip.name)

	async def listen(self, timeout: float) -> AudioClip | None:
		return self._caller.pop(0) if self._caller else None

	async def close(self) -> None:
		self.closed = True


# --------------------------------------------------------------------- ICE configuration
DEFAULT_STUN_URLS = ("stun:stun.l.google.com:19302", "stun:stun.cloudflare.com:3478")
_ENV_PREFIX = "HUF_WA_CALL_"
_TRUE = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class IceConfig:
	"""ICE server settings for the media session. The TURN credential never leaves this object.

	Default = direct UDP with public STUN only. ``relay_only`` forces every candidate through TURN
	(the NAT fallback: use ``turns:`` or ``?transport=tcp`` when no UDP can get in or out).
	"""

	stun_urls: tuple[str, ...] = DEFAULT_STUN_URLS
	turn_urls: tuple[str, ...] = ()
	turn_username: str = field(default="", repr=False)
	turn_credential: str = field(default="", repr=False)
	relay_only: bool = False

	def __repr__(self) -> str:  # never include the secret
		return (
			f"IceConfig(stun={list(self.stun_urls)}, turn={list(self.turn_urls)}, "
			f"turn_credential={'<set>' if self.turn_credential else '<unset>'}, relay_only={self.relay_only})"
		)

	__str__ = __repr__

	def safe_summary(self) -> dict[str, Any]:
		"""Loggable view (no username, no credential)."""
		return {
			"stun": list(self.stun_urls),
			"turn": list(self.turn_urls),
			"turn_auth": bool(self.turn_credential),
			"relay_only": self.relay_only,
		}

	def validate(self) -> None:
		if self.relay_only and not (self.turn_urls and self.turn_credential):
			raise ValueError("relay_only needs a TURN url and credential")
		for url in self.turn_urls:
			if not url.startswith(("turn:", "turns:")):
				raise ValueError("TURN url must start with turn: or turns:")
		for url in self.stun_urls:
			if not url.startswith("stun:"):
				raise ValueError("STUN url must start with stun:")


def _as_list(value: Any) -> list[str]:
	if not value:
		return []
	if isinstance(value, str):
		value = value.replace(";", ",").split(",")
	return [str(v).strip() for v in value if str(v).strip()]


def build_ice_config(site_conf: dict[str, Any] | None = None, env: dict[str, str] | None = None) -> IceConfig:
	"""Build the ICE config. Env ``HUF_WA_CALL_<KEY>`` overrides site config ``huf_wa_call_<key>``.

	Keys: ``stun_urls`` (comma list), ``turn_urls`` (comma list), ``turn_username``, ``turn_credential``,
	``relay_only``. The credential is read from site config / env only, never from a DocType field.
	"""
	import os

	site_conf = site_conf or {}
	env = os.environ if env is None else env

	def get(key: str) -> Any:
		return env.get(_ENV_PREFIX + key.upper()) or site_conf.get("huf_wa_call_" + key)

	stun = _as_list(get("stun_urls"))
	cfg = IceConfig(
		stun_urls=tuple(stun) if stun else DEFAULT_STUN_URLS,
		turn_urls=tuple(_as_list(get("turn_urls"))),
		turn_username=str(get("turn_username") or ""),
		turn_credential=str(get("turn_credential") or ""),
		relay_only=str(get("relay_only") or "").strip().lower() in _TRUE,
	)
	cfg.validate()
	return cfg


def site_ice_config() -> IceConfig:
	import frappe

	return build_ice_config(dict(frappe.conf or {}))


def to_rtc_configuration(cfg: IceConfig) -> Any:
	"""aiortc RTCConfiguration. aiortc uses ONE STUN and ONE TURN server (the first of each)."""
	from aiortc import RTCConfiguration, RTCIceServer

	servers = []
	if cfg.stun_urls:
		servers.append(RTCIceServer(urls=cfg.stun_urls[0]))
	if cfg.turn_urls:
		servers.append(
			RTCIceServer(urls=cfg.turn_urls[0], username=cfg.turn_username, credential=cfg.turn_credential)
		)
	return RTCConfiguration(iceServers=servers)


def _force_relay_policy(pc: Any) -> None:
	"""aiortc has no iceTransportPolicy option; set aioice's RELAY policy on every gatherer.

	Uses private attributes, so it fails closed: if it cannot be applied we raise instead of
	silently leaking host/srflx candidates.
	"""
	from aioice import TransportPolicy

	n = 0
	for tr in pc.getTransceivers():
		gatherer = tr.sender.transport.transport.iceGatherer
		gatherer._connection._transport_policy = TransportPolicy.RELAY
		n += 1
	if not n:
		raise RuntimeError("could not apply relay-only ICE policy")


def aiortc_available() -> bool:
	try:
		import aiortc  # noqa: F401
	except Exception:
		return False
	return True


class AiortcMediaSession(MediaSession):
	"""aiortc peer connection (loopback-tested; not yet exercised against Meta). ICE servers come from :class:`IceConfig`.

	Imported lazily: constructing it without aiortc raises ``RuntimeError("aiortc not installed")``.
	Inbound caller audio is drained and discarded (never stored) - ``listen`` returns ``None``.
	"""

	def __init__(self, ice: IceConfig | None = None) -> None:
		if not aiortc_available():
			raise RuntimeError("aiortc not installed")
		from aiortc import RTCPeerConnection

		self._ice = ice or IceConfig()
		self._ice.validate()
		self._pc = RTCPeerConnection(to_rtc_configuration(self._ice))
		self._connected = asyncio.Event()
		self._gate = asyncio.Event()
		self._players: list[Any] = []

		@self._pc.on("connectionstatechange")
		async def _on_state() -> None:
			if self._pc.connectionState == "connected":
				self._connected.set()

		@self._pc.on("track")
		def _on_track(track: Any) -> None:
			async def _drain() -> None:
				try:
					while True:
						await track.recv()  # discarded: no recording
				except Exception:
					pass

			asyncio.ensure_future(_drain())

	async def create_answer(self, offer_sdp: str) -> str:
		from aiortc import RTCSessionDescription

		await self._pc.setRemoteDescription(RTCSessionDescription(sdp=offer_sdp, type="offer"))
		self._track = _build_gated_track(self._gate)
		self._pc.addTrack(self._track)
		if self._ice.relay_only:
			_force_relay_policy(self._pc)
		await self._pc.setLocalDescription(await self._pc.createAnswer())
		return self._pc.localDescription.sdp

	async def wait_connected(self, timeout: float) -> bool:
		try:
			await asyncio.wait_for(self._connected.wait(), timeout)
			return True
		except asyncio.TimeoutError:
			return False

	def open_gate(self) -> None:
		self._gate.set()

	async def play(self, clip: AudioClip) -> None:
		if not clip.path:
			raise ValueError("aiortc playback needs a file path")
		from aiortc.contrib.media import MediaPlayer

		player = MediaPlayer(clip.path)
		self._players.append(player)
		await self._track.play(player)

	async def listen(self, timeout: float) -> AudioClip | None:
		return None

	async def close(self) -> None:
		try:
			await self._pc.close()
		except Exception:
			pass


def _build_gated_track(gate: asyncio.Event) -> Any:  # pragma: no cover - needs aiortc
	import fractions

	from aiortc.mediastreams import MediaStreamError, MediaStreamTrack
	from av import AudioFrame

	class _Track(MediaStreamTrack):
		kind = "audio"

		def __init__(self) -> None:
			super().__init__()
			self._player: Any = None
			self._done = asyncio.Event()
			self._pts = 0

		async def play(self, player: Any) -> None:
			self._done.clear()
			self._player = player
			await self._done.wait()

		async def recv(self) -> Any:
			if self.readyState != "live":
				raise MediaStreamError
			if not gate.is_set() or self._player is None:
				await asyncio.sleep(0.02)
				frame = AudioFrame(format="s16", layout="stereo", samples=960)
				for plane in frame.planes:
					plane.update(bytes(plane.buffer_size))
				frame.sample_rate = 48000
			else:
				try:
					frame = await self._player.audio.recv()
				except MediaStreamError:
					self._player = None
					self._done.set()
					frame = AudioFrame(format="s16", layout="stereo", samples=960)
					for plane in frame.planes:
						plane.update(bytes(plane.buffer_size))
					frame.sample_rate = 48000
			frame.pts = self._pts
			self._pts += frame.samples
			frame.time_base = fractions.Fraction(1, 48000)
			return frame

	return _Track()


def get_media_backend() -> dict[str, Any]:
	"""Status of the media backend: ``{"available": bool, "backend": str, "reason": str}``."""
	if aiortc_available():
		return {"available": True, "backend": "aiortc", "reason": ""}
	return {"available": False, "backend": "aiortc", "reason": "not_installed"}


# --------------------------------------------------------------------- the flow
@dataclass
class CallTrace:
	"""Metadata-only record of one call (safe to persist: no SDP, no audio)."""

	call_id: str
	state: str = RECEIVED
	transitions: list[str] = field(default_factory=lambda: [RECEIVED])
	actions: list[dict[str, Any]] = field(default_factory=list)
	played: list[str] = field(default_factory=list)
	heard: list[dict[str, Any]] = field(default_factory=list)
	terminate_reason: str = ""
	error: str = ""
	started: float = field(default_factory=time.monotonic)
	duration_s: float = 0.0

	def to(self, state: str) -> None:
		self.state = state
		self.transitions.append(state)

	def public(self) -> dict[str, Any]:
		return {
			"call_id": self.call_id,
			"state": self.state,
			"transitions": list(self.transitions),
			"actions": list(self.actions),
			"played": list(self.played),
			"heard": list(self.heard),
			"terminate_reason": self.terminate_reason,
			"error": self.error,
			"duration_s": round(self.duration_s, 2),
		}


async def run_call(
	call_id: str,
	offer_sdp: str,
	*,
	graph: Any,
	media: MediaSession,
	source: CallAudioSource,
	sink: CallAudioSink,
	max_seconds: int = DEFAULT_MAX_SECONDS,
	connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
	listen_timeout: float = 5.0,
) -> CallTrace:
	"""pre_accept -> wait media -> accept (same SDP) -> play/listen loop -> terminate.

	``graph`` needs pre_accept/accept/reject/terminate(call_id[, sdp]) (a CallsGraph or a fake).
	Audio only flows after accept succeeded. Never raises; failures end in FAILED with a terminate.
	"""
	trace = CallTrace(call_id)

	def act(name: str, fn: Callable[..., Any], *args: Any) -> None:
		try:
			fn(call_id, *args)
			trace.actions.append({"action": name, "ok": True})
		except Exception as exc:
			trace.actions.append({"action": name, "ok": False})
			raise exc

	try:
		trace.to(ANSWERING)
		answer = await media.create_answer(offer_sdp)
		act("pre_accept", graph.pre_accept, answer)
		trace.to(PRE_ACCEPTED)
		if not await media.wait_connected(connect_timeout):
			trace.terminate_reason = "ice_failed"
			trace.to(TERMINATING)
			act("terminate", graph.terminate)
			trace.to(FAILED)
			return trace
		trace.to(CONNECTED)
		act("accept", graph.accept, answer)  # SAME SDP as pre_accept
		trace.to(ACCEPTED)
		media.open_gate()  # media only after accept returned OK
		trace.to(PLAYING)
		reason = await _play_loop(media, source, sink, trace, max_seconds, listen_timeout)
		trace.terminate_reason = reason
		trace.to(TERMINATING)
		act("terminate", graph.terminate)
		trace.to(COMPLETED)
	except Exception as exc:  # noqa: BLE001 - flow must never raise into the worker
		trace.error = f"{type(exc).__name__}"
		trace.terminate_reason = trace.terminate_reason or "error"
		if trace.state in (ANSWERING, PRE_ACCEPTED, CONNECTED, ACCEPTED, PLAYING, TERMINATING):
			try:
				graph.terminate(call_id)
				trace.actions.append({"action": "terminate", "ok": True})
			except Exception:
				trace.actions.append({"action": "terminate", "ok": False})
		trace.to(FAILED)
	finally:
		trace.duration_s = time.monotonic() - trace.started
		try:
			await media.close()
		except Exception:
			pass
	return trace


async def _play_loop(
	media: MediaSession, source: CallAudioSource, sink: CallAudioSink, trace: CallTrace, max_seconds: int, listen_timeout: float
) -> str:
	async def loop() -> str:
		heard: AudioClip | None = None
		for _ in range(MAX_CLIPS):
			clip = source.next_clip(heard)
			if clip is None:
				return "eof"
			await media.play(clip)
			trace.played.append(clip.name)
			heard = None
			if source.wants_caller_audio:
				heard = await media.listen(listen_timeout)
				if heard is not None:
					sink.write(heard)
					trace.heard.append(heard.summary())
		return "eof"

	try:
		return await asyncio.wait_for(loop(), max(int(max_seconds), 1))
	except asyncio.TimeoutError:
		return "max_duration"


# --------------------------------------------------------------------- worker entry (Frappe)
def answer_inbound_call_job(gateway_name: str, call_id: str, caller: str, sdp_key: str) -> dict[str, Any]:
	"""RQ job: answer an admitted call with the Gateway's greeting. Experimental, flag-gated.

	Production should run this in the ``huf-media`` sidecar (design section 4); the job form is the
	minimal in-bench variant. Without aiortc the call is rejected and the event marked Failed.
	"""
	import frappe

	from huf.ai.gateway_adapters import whatsapp_bridge as bridge
	from huf.ai.gateway_adapters.whatsapp_calls import (
		CallsGraph,
		WhatsAppCall,
		call_admission,
		take_sdp_offer,
		update_call_event,
	)

	gateway = frappe.get_doc("Gateway", gateway_name)
	stub = WhatsAppCall(call_id=call_id, event="status", direction="USER_INITIATED", caller=caller)
	if not getattr(gateway, "calling_enabled", 0):
		return {"call_id": call_id, "skipped": "calling disabled"}
	graph = CallsGraph(bridge.resolve_account(bridge.gateway_account(gateway_name)) or {})
	admitted, reason = call_admission(gateway, caller)
	if not admitted:
		# the caller may have been revoked/blocked between the webhook and this job
		try:
			graph.reject(call_id)
		except Exception:
			pass
		update_call_event(gateway_name, stub, "Rejected", reason, {"action": "reject", "reason": reason})
		return {"call_id": call_id, "outcome": "rejected", "reason": reason}
	sdp_offer = take_sdp_offer(sdp_key)
	if not sdp_offer:
		try:
			graph.reject(call_id)
		except Exception:
			pass
		update_call_event(gateway_name, stub, "Failed", "Call offer expired before it could be answered",
			{"action": "reject", "reason": "offer_expired"})
		return {"call_id": call_id, "outcome": "offer_expired"}
	backend = get_media_backend()
	if not backend["available"]:
		try:
			graph.reject(call_id)
		except Exception:
			pass
		update_call_event(gateway_name, stub, "Failed", f"Media backend unavailable: {backend['reason']}",
			{"action": "reject", "reason": "media_unavailable"})
		return {"call_id": call_id, "outcome": "media_unavailable"}

	clips = load_gateway_clips(gateway)
	if not clips:
		try:
			graph.reject(call_id)
		except Exception:
			pass
		update_call_event(gateway_name, stub, "Failed", "No greeting audio configured", {"action": "reject", "reason": "no_greeting"})
		return {"call_id": call_id, "outcome": "no_greeting"}
	trace = asyncio.run(
		run_call(
			call_id, sdp_offer, graph=graph, media=AiortcMediaSession(site_ice_config()), source=FilePlayback(clips),
			sink=InMemoryAudioSink(), max_seconds=int(getattr(gateway, "call_max_seconds", 0) or DEFAULT_MAX_SECONDS),
		)
	)
	update_call_event(gateway_name, stub, "Succeeded" if trace.state == COMPLETED else "Failed", trace.error,
		{"action": "flow", **trace.public()})
	return trace.public()


def load_gateway_clips(gateway: Any) -> list[AudioClip]:
	"""Bot-side clips from the Gateway (greeting, reply, closing), as file paths of private Files."""
	import frappe

	clips: list[AudioClip] = []
	for fieldname in ("call_greeting_audio", "call_reply_audio", "call_closing_audio"):
		url = getattr(gateway, fieldname, "") or ""
		if not url:
			continue
		name = frappe.db.get_value("File", {"file_url": url}, "name")
		if name:
			clips.append(AudioClip(name=fieldname, path=frappe.get_doc("File", name).get_full_path()))
	return clips
