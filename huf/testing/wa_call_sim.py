#!/usr/bin/env python3
"""Offline simulation of a WhatsApp inbound call (no Meta, no Graph, no DB, no recording).

Feeds a simulated `calls` webhook (connect, then terminate) through the real adapter parser
(``WhatsAppGatewayAdapter.parse_payload``) and the real answer flow (``run_call``) using an
in-process fake media session:

    greeting -> caller file(s) heard (in memory only) -> bot reply file(s) -> terminate

Run inside the bench python (needs frappe importable, no site):
    python huf/testing/wa_call_sim.py [--caller 15550001111] [--unknown]
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import sys
from typing import Any

from huf.ai.gateway_adapters import whatsapp_call_flow as flow
from huf.ai.gateway_adapters.types import GatewayInboundRequest
from huf.ai.gateway_adapters.whatsapp import WhatsAppGatewayAdapter

PHONE_ID = "111222333"
APP_SECRET = "sim-secret"
FAKE_OFFER = "v=0\r\no=- 1 1 IN IP4 0.0.0.0\r\ns=sim-offer\r\n"


class FakeGraph:
	"""Records Calling API actions instead of calling Meta."""

	def __init__(self) -> None:
		self.actions: list[tuple[str, str]] = []

	def pre_accept(self, call_id: str, sdp: str) -> dict:
		self.actions.append(("pre_accept", call_id))
		return {"success": True}

	def accept(self, call_id: str, sdp: str) -> dict:
		self.actions.append(("accept", call_id))
		return {"success": True}

	def reject(self, call_id: str) -> dict:
		self.actions.append(("reject", call_id))
		return {"success": True}

	def terminate(self, call_id: str) -> dict:
		self.actions.append(("terminate", call_id))
		return {"success": True}


def webhook(call: dict[str, Any]) -> GatewayInboundRequest:
	"""A signed `calls` webhook delivery carrying one call item."""
	body = json.dumps(
		{
			"object": "whatsapp_business_account",
			"entry": [{"id": "WABA", "changes": [{"field": "calls", "value": {
				"messaging_product": "whatsapp",
				"metadata": {"display_phone_number": "15550751406", "phone_number_id": PHONE_ID},
				"contacts": [{"profile": {"name": "Sim Caller"}, "wa_id": call.get("from", "")}],
				"calls": [call],
			}}]}],
		}
	).encode()
	sig = "sha256=" + hmac.new(APP_SECRET.encode(), body, "sha256").hexdigest()
	return GatewayInboundRequest(body=body, headers={"X-Hub-Signature-256": sig})


def make_adapter() -> WhatsAppGatewayAdapter:
	return WhatsAppGatewayAdapter(
		{"phone_number_id": PHONE_ID, "access_token": "x", "webhook_verify_token": "v", "app_secret": APP_SECRET}
	)


def clip(name: str, text: str) -> flow.AudioClip:
	"""A stand-in 'audio file' (bytes are text; only their hash/size are ever reported)."""
	return flow.AudioClip(name=name, data=text.encode())


def simulate(
	caller: str = "15550001111",
	allowed: tuple[str, ...] = ("15550001111",),
	bot_files: int = 3,
	caller_files: int = 2,
	max_seconds: int = 30,
	connect: bool = True,
) -> dict[str, Any]:
	"""Run one simulated call end to end and return a metadata-only report."""
	adapter = make_adapter()
	graph = FakeGraph()
	report: dict[str, Any] = {"caller": caller, "events": []}

	connect_req = webhook({"id": "wacid.SIM1", "from": caller, "to": "15550751406", "event": "connect",
		"direction": "USER_INITIATED", "timestamp": "1", "session": {"sdp_type": "offer", "sdp": FAKE_OFFER}})
	if not adapter.verify_inbound(connect_req):
		raise RuntimeError("simulated webhook signature failed")
	call = adapter.parse_payload(connect_req).calls[0]
	report["events"].append({"event": "connect", **call.public()})

	if call.caller not in allowed:
		graph.reject(call.call_id)
		report.update(outcome="rejected", state=flow.REJECTED, actions=graph.actions)
		return report

	bot = [clip(n, f"bot-{n}") for n in ("greeting", "reply", "closing")[:bot_files]]
	spoken = [clip(f"caller-{i + 1}", f"caller-audio-{i + 1}") for i in range(caller_files)]
	media = flow.FakeMediaSession(spoken, connect=connect)
	sink = flow.InMemoryAudioSink(retain=True)
	source = flow.FilePlayback(bot, listen_between=True)
	trace = asyncio.run(flow.run_call(call.call_id, call.sdp_offer, graph=graph, media=media, source=source,
		sink=sink, max_seconds=max_seconds))

	term_req = webhook({"id": call.call_id, "from": caller, "to": "15550751406", "event": "terminate",
		"direction": "USER_INITIATED", "status": "COMPLETED", "duration": 7})
	term = adapter.parse_payload(term_req).calls[0]
	report["events"].append({"event": "terminate", **term.public()})
	report.update(
		outcome=trace.state, state=trace.state, transitions=trace.transitions, actions=graph.actions,
		played=media.played, heard=sink.received, gate_violations=media.gate_violations,
		terminate_reason=trace.terminate_reason, retained_in_memory_only=len(sink.clips),
	)
	return report


def main(argv: list[str] | None = None) -> int:
	ap = argparse.ArgumentParser(description=__doc__)
	ap.add_argument("--caller", default="15550001111")
	ap.add_argument("--unknown", action="store_true", help="caller is not on the allow list")
	args = ap.parse_args(argv)
	allowed = () if args.unknown else (args.caller,)
	print(json.dumps(simulate(args.caller, allowed), indent=2))
	return 0


if __name__ == "__main__":
	sys.exit(main())
