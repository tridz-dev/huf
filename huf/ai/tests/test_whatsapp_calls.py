# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Mock-based tests for WhatsApp Calling (experimental, default OFF). No network, no Meta."""

import asyncio
import importlib.util
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe

if isinstance(frappe, MagicMock):
	frappe.whitelist = lambda *args, **kwargs: (lambda fn: fn)
	frappe.PermissionError = PermissionError

from huf.ai import whatsapp_management as mgmt  # noqa: E402
from huf.ai.gateway_adapters import whatsapp_call_flow as flow  # noqa: E402
from huf.ai.gateway_adapters import whatsapp_calls as wc  # noqa: E402
from huf.ai.gateway_adapters.whatsapp_bridge import BridgeError  # noqa: E402

SDP = "v=0\r\ns=secret-offer-with-ips 10.1.2.3\r\n"
SIM_PATH = Path(__file__).resolve().parent / "wa_call_sim.py"


def _spec():
	spec = importlib.util.spec_from_file_location("wa_call_sim", SIM_PATH)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


def connect_value(caller="15550001111", sdp=SDP):
	return {
		"metadata": {"phone_number_id": "111"},
		"contacts": [{"profile": {"name": "Ann"}, "wa_id": caller}],
		"calls": [{"id": "wacid.1", "from": caller, "to": "15550751406", "event": "connect",
			"direction": "USER_INITIATED", "timestamp": "1", "session": {"sdp_type": "offer", "sdp": sdp}}],
	}


class FakeResp:
	def __init__(self, status=200, body=None):
		self.status_code, self._body = status, body if body is not None else {"success": True}

	def json(self):
		return self._body


class RecGraph:
	def __init__(self, fail_on=None):
		self.actions, self.fail_on = [], fail_on

	def _do(self, name, call_id):
		if name == self.fail_on:
			raise RuntimeError("boom")
		self.actions.append(name)

	def pre_accept(self, call_id, sdp):
		self._do("pre_accept", call_id)

	def accept(self, call_id, sdp):
		self._do("accept", call_id)

	def reject(self, call_id):
		self._do("reject", call_id)

	def terminate(self, call_id):
		self._do("terminate", call_id)


class TestNormalise(unittest.TestCase):
	def test_connect_normalised_and_public_has_no_sdp(self):
		(call,) = wc.normalize_calls(connect_value())
		self.assertEqual((call.call_id, call.event, call.caller, call.direction), ("wacid.1", "connect", "15550001111", "USER_INITIATED"))
		self.assertEqual(call.sdp_offer, SDP)
		self.assertEqual(call.display_name, "Ann")
		self.assertNotIn("sdp", json.dumps(call.public()).lower())
		self.assertNotIn("10.1.2.3", json.dumps(call.public()))
		self.assertNotIn(SDP, repr(call))

	def test_terminate_and_call_status(self):
		value = {
			"metadata": {"phone_number_id": "111"},
			"calls": [{"id": "c2", "from": "15550001111", "event": "terminate", "direction": "USER_INITIATED",
				"status": "FAILED", "duration": "12", "errors": [{"code": 1, "message": "x"}]}],
			"statuses": [{"id": "c3", "type": "call", "status": "RINGING", "recipient_id": "15550002222"}],
		}
		term, status = wc.normalize_calls(value)
		self.assertEqual((term.event, term.status, term.duration), ("terminate", "FAILED", 12))
		self.assertEqual(term.public()["errors"][0]["code"], 1)
		self.assertEqual((status.event, status.status, status.caller), ("status", "RINGING", "15550002222"))

	def test_malformed_items_skipped(self):
		self.assertEqual(wc.normalize_calls({"calls": ["x", {"event": "connect"}, {"id": "a", "event": "weird"}]}), [])


class TestPayloads(unittest.TestCase):
	def test_action_payload_shapes(self):
		pre = wc.call_action_payload("c1", "pre_accept", "SDP")
		self.assertEqual(pre, {"messaging_product": "whatsapp", "call_id": "c1", "action": "pre_accept",
			"session": {"sdp_type": "answer", "sdp": "SDP"}})
		self.assertNotIn("session", wc.call_action_payload("c1", "reject"))
		self.assertNotIn("session", wc.call_action_payload("c1", "terminate"))
		self.assertEqual(len(wc.call_action_payload("c1", "accept", "S", "x" * 900)["biz_opaque_callback_data"]), 512)

	def test_action_payload_validation(self):
		for args in (("c1", "accept"), ("c1", "reject", "SDP"), ("c1", "hangup"), ("", "reject")):
			with self.assertRaises(ValueError):
				wc.call_action_payload(*args)

	def test_settings_payload(self):
		self.assertEqual(wc.calling_settings_payload("enabled", "disable_all"),
			{"calling": {"status": "ENABLED", "call_icon_visibility": "DISABLE_ALL"}})
		greeting = wc.calling_settings_payload(greeting_media_id="m1")["calling"]["voicemail"]
		self.assertEqual(greeting["audio"]["default"]["announcement_media_id"], "m1")
		for kwargs in ({}, {"calls_status": "ON"}, {"call_icon_visibility": "x"}):
			with self.assertRaises(ValueError):
				wc.calling_settings_payload(**kwargs)

	def test_permission_request_payload(self):
		body = wc.permission_request_payload("+1 555-000-1111", "May we call you?")
		self.assertEqual(body["to"], "15550001111")
		self.assertEqual(body["interactive"], {"type": "call_permission_request",
			"action": {"name": "call_permission_request"}, "body": {"text": "May we call you?"}})
		for args in (("", "x"), ("15550001111", " "), ("15550001111", "x" * 2000)):
			with self.assertRaises(ValueError):
				wc.permission_request_payload(*args)


class TestCallsGraph(unittest.TestCase):
	acct = {"url": "https://graph.test", "version": "v25.0", "phone_id": "111", "token": "TOK"}

	def test_action_request(self):
		post = MagicMock(return_value=FakeResp())
		wc.CallsGraph(self.acct, http_post=post).pre_accept("c1", "SDP")
		url = post.call_args.args[0]
		self.assertEqual(url, "https://graph.test/v25.0/111/calls")
		self.assertEqual(post.call_args.kwargs["json"]["action"], "pre_accept")
		self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer TOK")

	def test_settings_get_set(self):
		get, post = MagicMock(return_value=FakeResp(body={"calling": {}})), MagicMock(return_value=FakeResp())
		graph = wc.CallsGraph(self.acct, http_post=post, http_get=get)
		graph.get_settings()
		self.assertTrue(get.call_args.args[0].endswith("/111/settings"))
		graph.set_settings({"calling": {"status": "ENABLED"}})
		self.assertEqual(post.call_args.kwargs["json"], {"calling": {"status": "ENABLED"}})

	def test_http_error_becomes_bridge_error_without_token(self):
		post = MagicMock(return_value=FakeResp(400, {"error": {"message": "bad", "code": 138006}}))
		with self.assertRaises(BridgeError) as ctx:
			wc.CallsGraph(self.acct, http_post=post).reject("c1")
		self.assertNotIn("TOK", json.dumps(ctx.exception.payload, default=str))

	def test_transport_exception_wrapped(self):
		with self.assertRaises(BridgeError):
			wc.CallsGraph(self.acct, http_post=MagicMock(side_effect=OSError("down"))).terminate("c1")


class TestHandleCall(unittest.TestCase):
	def gateway(self, enabled):
		return SimpleNamespace(name="GW", calling_enabled=1 if enabled else 0)

	def call(self, **kw):
		(c,) = wc.normalize_calls(connect_value(**kw))
		return c

	def test_disabled_by_default_no_graph_no_enqueue(self):
		graph, enqueue = MagicMock(), MagicMock()
		with patch.object(wc, "record_call_event", return_value={"event_name": "E1"}) as rec:
			out = wc.handle_call(self.gateway(False), self.call(), graph=graph, enqueue=enqueue)
		self.assertEqual(out["outcome"], "disabled")
		graph.reject.assert_not_called()
		enqueue.assert_not_called()
		self.assertEqual(rec.call_args.args[2], "Rejected")
		self.assertFalse(wc.calling_enabled(SimpleNamespace()))

	def test_unknown_caller_rejected_and_action_recorded(self):
		graph, enqueue = MagicMock(), MagicMock()
		with (
			patch.object(wc, "call_admission", return_value=(False, "Caller is not on the allow list")),
			patch.object(wc, "record_call_event", return_value={"event_name": "E1"}) as rec,
		):
			out = wc.handle_call(self.gateway(True), self.call(), graph=graph, enqueue=enqueue)
		graph.reject.assert_called_once_with("wacid.1")
		enqueue.assert_not_called()
		self.assertEqual(out["outcome"], "rejected")
		self.assertEqual(rec.call_args.args[2], "Rejected")
		self.assertEqual(rec.call_args.args[4][0]["action"], "reject")
		self.assertTrue(rec.call_args.args[4][0]["ok"])

	def test_reject_failure_is_recorded_not_raised(self):
		graph = MagicMock()
		graph.reject.side_effect = RuntimeError("graph down")
		with (
			patch.object(wc, "call_admission", return_value=(False, "no")),
			patch.object(wc, "record_call_event", return_value={}) as rec,
		):
			out = wc.handle_call(self.gateway(True), self.call(), graph=graph)
		self.assertFalse(out["reject_action"]["ok"])
		self.assertIn("error", rec.call_args.args[4][0])

	def test_approved_caller_queued_without_agent_run(self):
		graph, enqueue = MagicMock(), MagicMock()
		with (
			patch.object(wc, "call_admission", return_value=(True, "")),
			patch.object(wc, "record_call_event", return_value={"event_name": "E1"}) as rec,
		):
			out = wc.handle_call(self.gateway(True), self.call(), graph=graph, enqueue=enqueue)
		self.assertEqual(out["outcome"], "queued")
		self.assertEqual(rec.call_args.args[2], "Received")
		self.assertEqual(enqueue.call_args.args[0], "huf.ai.gateway_adapters.whatsapp_call_flow.answer_inbound_call_job")
		graph.reject.assert_not_called()

	def test_sdp_is_not_in_job_kwargs(self):
		enqueue = MagicMock()
		with (
			patch.object(wc, "call_admission", return_value=(True, "")),
			patch.object(wc, "record_call_event", return_value={"event_name": "E1"}),
			patch.object(wc, "stash_sdp_offer", return_value="huf_call_sdp:GW:c1") as stash,
		):
			wc.handle_call(self.gateway(True), self.call(), enqueue=enqueue)
		stash.assert_called_once()
		kwargs = enqueue.call_args.kwargs
		self.assertEqual(kwargs["sdp_key"], "huf_call_sdp:GW:c1")
		self.assertNotIn("sdp_offer", kwargs)
		self.assertNotIn(SDP, [str(v) for v in kwargs.values()])

	def test_retry_for_unadmitted_caller_does_not_resend_reject(self):
		graph = MagicMock()
		with (
			patch.object(wc, "call_admission", return_value=(False, "no")),
			patch.object(wc, "_call_event_exists", return_value=True),
			patch.object(wc, "record_call_event", return_value={"duplicate": True, "event_name": "E1"}),
		):
			out = wc.handle_call(self.gateway(True), self.call(), graph=graph)
		graph.reject.assert_not_called()
		self.assertEqual(out["outcome"], "duplicate")

	def test_duplicate_connect_not_answered_twice(self):
		enqueue = MagicMock()
		with (
			patch.object(wc, "call_admission", return_value=(True, "")),
			patch.object(wc, "record_call_event", return_value={"duplicate": True, "event_name": "E1"}),
		):
			out = wc.handle_call(self.gateway(True), self.call(), enqueue=enqueue)
		self.assertEqual(out["outcome"], "duplicate")
		enqueue.assert_not_called()

	def test_terminate_updates_event(self):
		(term,) = wc.normalize_calls({"calls": [{"id": "c9", "from": "15550001111", "event": "terminate",
			"direction": "USER_INITIATED", "status": "COMPLETED"}]})
		with patch.object(wc, "update_call_event", return_value="E1") as upd:
			wc.handle_call(self.gateway(True), term)
		self.assertEqual(upd.call_args.args[2], "Succeeded")

	def test_admission_requires_approved_entry_open_policy_not_enough(self):
		from huf.ai import gateway_service as gs

		gw = SimpleNamespace(name="GW", provider="WhatsApp", direct_policy="Open")
		with patch.object(gs, "_sender_negative_state", return_value=None), patch.object(gs, "_has_access_entry", return_value=False):
			self.assertFalse(wc.call_admission(gw, "15550001111")[0])
		with patch.object(gs, "_sender_negative_state", return_value=None), patch.object(gs, "_has_access_entry", return_value=True):
			self.assertTrue(wc.call_admission(gw, "15550001111")[0])
		with patch.object(gs, "_sender_negative_state", return_value="Blocked"), patch.object(gs, "_has_access_entry", return_value=True):
			self.assertFalse(wc.call_admission(gw, "15550001111")[0])
		self.assertFalse(wc.call_admission(gw, "")[0])


class TestAdapterParsing(unittest.TestCase):
	def test_calls_field_parsed_into_calls_not_messages_or_statuses(self):
		sim = _spec()
		req = sim.webhook({"id": "c1", "from": "15550001111", "to": "1", "event": "connect",
			"direction": "USER_INITIATED", "session": {"sdp_type": "offer", "sdp": SDP}})
		adapter = sim.make_adapter()
		self.assertTrue(adapter.verify_inbound(req))
		parsed = adapter.parse_payload(req)
		self.assertEqual((len(parsed.calls), len(parsed.messages), len(parsed.statuses)), (1, 0, 0))
		with self.assertRaises(ValueError):
			adapter.normalize_inbound(req)  # only call events: not an agent message

	def test_unknown_phone_id_ignored(self):
		sim = _spec()
		body = json.loads(sim.webhook({"id": "c1", "from": "1", "event": "connect", "direction": "USER_INITIATED"}).body)
		body["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"] = "other"
		req = SimpleNamespace(body=json.dumps(body).encode(), headers={}, query={}, method="POST")
		self.assertEqual(sim.make_adapter().parse_payload(req).calls, ())


class TestFlow(unittest.TestCase):
	def run_flow(self, graph=None, media=None, source=None, **kw):
		graph = graph or RecGraph()
		media = media or flow.FakeMediaSession()
		source = source or flow.FilePlayback([flow.AudioClip("greeting", data=b"g")])
		sink = flow.InMemoryAudioSink()
		trace = asyncio.run(flow.run_call("c1", SDP, graph=graph, media=media, source=source, sink=sink, **kw))
		return trace, graph, media, sink

	def test_greeting_only_order_and_states(self):
		trace, graph, media, _ = self.run_flow()
		self.assertEqual(graph.actions, ["pre_accept", "accept", "terminate"])
		self.assertEqual(trace.transitions, [flow.RECEIVED, flow.ANSWERING, flow.PRE_ACCEPTED, flow.CONNECTED,
			flow.ACCEPTED, flow.PLAYING, flow.TERMINATING, flow.COMPLETED])
		self.assertEqual(media.played, ["greeting"])
		self.assertEqual(media.gate_violations, 0)
		self.assertTrue(media.closed)
		self.assertEqual(trace.terminate_reason, "eof")

	def test_ice_failure_terminates_and_fails(self):
		trace, graph, media, _ = self.run_flow(media=flow.FakeMediaSession(connect=False))
		self.assertEqual(graph.actions, ["pre_accept", "terminate"])
		self.assertEqual((trace.state, trace.terminate_reason), (flow.FAILED, "ice_failed"))
		self.assertEqual(media.played, [])

	def test_accept_failure_terminates_and_never_plays(self):
		trace, graph, media, _ = self.run_flow(graph=RecGraph(fail_on="accept"))
		self.assertEqual(trace.state, flow.FAILED)
		self.assertEqual(media.played, [])
		self.assertEqual(graph.actions, ["pre_accept", "terminate"])

	def test_max_duration_caps_playback(self):
		class Slow(flow.FakeMediaSession):
			async def play(self, clip):
				await asyncio.sleep(5)

		trace, graph, _, _ = self.run_flow(media=Slow(), max_seconds=1)
		self.assertEqual((trace.state, trace.terminate_reason), (flow.COMPLETED, "max_duration"))
		self.assertEqual(graph.actions[-1], "terminate")

	def test_no_recording_invariant(self):
		caller = [flow.AudioClip("c1", data=b"SECRET-CALLER-AUDIO")]
		media = flow.FakeMediaSession(caller)
		src = flow.FilePlayback([flow.AudioClip("g", data=b"g"), flow.AudioClip("r", data=b"r")], listen_between=True)
		with patch("builtins.open", side_effect=AssertionError("no file IO allowed during a call")):
			trace, _, _, sink = self.run_flow(media=media, source=src)
		dumped = json.dumps(trace.public()) + json.dumps(sink.received)
		self.assertNotIn("SECRET-CALLER-AUDIO", dumped)
		self.assertEqual(sink.clips, [])  # default sink retains nothing, not even in memory
		self.assertEqual(sink.received[0]["bytes"], len(b"SECRET-CALLER-AUDIO"))

	def test_trace_has_no_sdp(self):
		trace, *_ = self.run_flow()
		self.assertNotIn("secret-offer", json.dumps(trace.public()))

	def test_clip_limit(self):
		clips = [flow.AudioClip(f"c{i}", data=b"x") for i in range(20)]
		trace, _, media, _ = self.run_flow(source=flow.FilePlayback(clips))
		self.assertEqual(len(media.played), flow.MAX_CLIPS)


class TestMediaBackend(unittest.TestCase):
	def test_not_installed_is_graceful(self):
		with patch.object(flow, "aiortc_available", return_value=False):
			self.assertEqual(flow.get_media_backend(), {"available": False, "backend": "aiortc", "reason": "not_installed"})
			with self.assertRaises(RuntimeError):
				flow.AiortcMediaSession()

	def test_job_rejects_call_when_backend_missing(self):
		gateway = SimpleNamespace(name="GW", calling_enabled=1, call_max_seconds=30)
		graph_cls = MagicMock()
		with (
			patch("frappe.get_doc", return_value=gateway),
			patch.object(flow, "get_media_backend", return_value={"available": False, "backend": "aiortc", "reason": "not_installed"}),
			patch.object(wc, "CallsGraph", graph_cls),
			patch.object(wc, "update_call_event") as upd,
			patch.object(wc, "call_admission", return_value=(True, "")),
			patch.object(wc, "take_sdp_offer", return_value=SDP),
			patch("huf.ai.gateway_adapters.whatsapp_bridge.resolve_account", return_value={}),
			patch("huf.ai.gateway_adapters.whatsapp_bridge.gateway_account", return_value="ACC"),
		):
			out = flow.answer_inbound_call_job("GW", "c1", "15550001111", "k")
		self.assertEqual(out["outcome"], "media_unavailable")
		graph_cls.return_value.reject.assert_called_once_with("c1")
		self.assertEqual(upd.call_args.args[2], "Failed")

	def _job_patches(self, graph_cls, **over):
		gateway = SimpleNamespace(name="GW", calling_enabled=1, call_max_seconds=30)
		return (
			patch("frappe.get_doc", return_value=gateway),
			patch.object(wc, "CallsGraph", graph_cls),
			patch.object(wc, "update_call_event"),
			patch.object(wc, "call_admission", return_value=over.get("admission", (True, ""))),
			patch.object(wc, "take_sdp_offer", return_value=over.get("sdp", SDP)),
			patch.object(flow, "get_media_backend", return_value={"available": True}),
			patch.object(flow, "load_gateway_clips", return_value=over.get("clips", [])),
			patch("huf.ai.gateway_adapters.whatsapp_bridge.resolve_account", return_value={}),
			patch("huf.ai.gateway_adapters.whatsapp_bridge.gateway_account", return_value="ACC"),
		)

	def _run_job(self, **over):
		from contextlib import ExitStack

		graph_cls = MagicMock()
		with ExitStack() as stack:
			mocks = [stack.enter_context(p) for p in self._job_patches(graph_cls, **over)]
			out = flow.answer_inbound_call_job("GW", "c1", "15550001111", "k")
		return out, graph_cls, mocks

	def test_job_rejects_caller_no_longer_admitted(self):
		out, graph_cls, mocks = self._run_job(admission=(False, "Caller is blocked (Revoked)"))
		self.assertEqual(out["outcome"], "rejected")
		graph_cls.return_value.reject.assert_called_once_with("c1")
		self.assertEqual(mocks[2].call_args.args[2], "Rejected")

	def test_job_no_greeting_reject_failure_still_marks_failed(self):
		graph_cls = MagicMock()
		graph_cls.return_value.reject.side_effect = RuntimeError("graph down")
		from contextlib import ExitStack

		with ExitStack() as stack:
			mocks = [stack.enter_context(p) for p in self._job_patches(graph_cls, clips=[])]
			out = flow.answer_inbound_call_job("GW", "c1", "15550001111", "k")
		self.assertEqual(out["outcome"], "no_greeting")
		self.assertEqual(mocks[2].call_args.args[2], "Failed")

	def test_job_expired_offer_is_rejected(self):
		out, graph_cls, mocks = self._run_job(sdp="")
		self.assertEqual(out["outcome"], "offer_expired")
		graph_cls.return_value.reject.assert_called_once_with("c1")

	def test_job_skips_when_disabled(self):
		with patch("frappe.get_doc", return_value=SimpleNamespace(name="GW", calling_enabled=0)):
			self.assertEqual(flow.answer_inbound_call_job("GW", "c1", "1", "k"), {"call_id": "c1", "skipped": "calling disabled"})


class TestSimulator(unittest.TestCase):
	def test_end_to_end_both_directions(self):
		report = _spec().simulate(bot_files=3, caller_files=2)
		self.assertEqual(report["state"], flow.COMPLETED)
		self.assertEqual(report["played"], ["greeting", "reply", "closing"])
		self.assertEqual([h["name"] for h in report["heard"]], ["caller-1", "caller-2"])
		self.assertEqual(report["actions"], [("pre_accept", "wacid.SIM1"), ("accept", "wacid.SIM1"), ("terminate", "wacid.SIM1")])
		self.assertEqual(report["transitions"][-3:], [flow.PLAYING, flow.TERMINATING, flow.COMPLETED])
		self.assertEqual([e["event"] for e in report["events"]], ["connect", "terminate"])
		self.assertEqual(report["gate_violations"], 0)
		self.assertNotIn("caller-audio", json.dumps(report["heard"]))

	def test_unknown_caller_rejected_never_answered(self):
		report = _spec().simulate(allowed=())
		self.assertEqual((report["outcome"], report["state"]), ("rejected", flow.REJECTED))
		self.assertEqual(report["actions"], [("reject", "wacid.SIM1")])

	def test_ice_failure_simulated(self):
		report = _spec().simulate(connect=False)
		self.assertEqual((report["state"], report["terminate_reason"]), (flow.FAILED, "ice_failed"))


class TestManagementApi(unittest.TestCase):
	def setUp(self):
		patcher = patch("huf.ai.whatsapp_management.frappe")
		self.frappe = patcher.start()
		self.addCleanup(patcher.stop)
		self.frappe.PermissionError = PermissionError
		self.frappe.db.exists.return_value = True
		self.frappe.db.get_value.return_value = "ACC-1"
		self.frappe.has_permission.return_value = True
		self.frappe.get_roles.return_value = ["System Manager"]
		self.graph = MagicMock()
		for p in (
			patch.object(mgmt.bridge, "is_available", return_value=True),
			patch.object(mgmt.bridge, "resolve_account", return_value={"name": "ACC-1", "phone_id": "1", "url": "u", "version": "v", "token": "t"}),
			patch.object(mgmt.wcalls, "CallsGraph", return_value=self.graph),
			patch.object(mgmt, "_opted_out", return_value=False),
			patch.object(mgmt.bridge, "window_state", return_value={"open": True}),
		):
			p.start()
			self.addCleanup(p.stop)

	def test_get_settings(self):
		self.graph.get_settings.return_value = {"calling": {"status": "DISABLED"}}
		out = mgmt.get_calling_settings("GW")
		self.assertEqual(out["settings"]["calling"]["status"], "DISABLED")

	def test_set_settings_payload_and_validation(self):
		out = mgmt.set_calling_settings("GW", calls_status="ENABLED", call_icon_visibility="DEFAULT")
		self.assertTrue(out["success"])
		self.graph.set_settings.assert_called_once_with({"calling": {"status": "ENABLED", "call_icon_visibility": "DEFAULT"}})
		bad = mgmt.set_calling_settings("GW", calls_status="MAYBE")
		self.assertEqual(bad["error"], "invalid_request")

	def _calling_off(self):
		self.frappe.db.get_value.side_effect = lambda dt, name, field=None, *a, **k: (
			0 if field == "calling_enabled" else "ACC-1"
		)

	def test_enabling_calling_refused_when_gateway_calling_off(self):
		self._calling_off()
		out = mgmt.set_calling_settings("GW", calls_status="ENABLED")
		self.assertEqual(out["error"], "calling_disabled")
		self.graph.set_settings.assert_not_called()
		# turning it off is always allowed
		self.assertTrue(mgmt.set_calling_settings("GW", calls_status="DISABLED")["success"])

	def test_call_action_refused_when_gateway_calling_off(self):
		self._calling_off()
		self.assertEqual(mgmt.call_action("GW", "c1", "reject")["error"], "calling_disabled")
		self.graph.action.assert_not_called()

	def test_call_action_validates_before_graph(self):
		self.graph.action.side_effect = ValueError("Unknown call action: x")
		self.assertEqual(mgmt.call_action("GW", "c1", "x")["error"], "invalid_request")

	def test_permission_request_gated_by_window_and_optout(self):
		out = mgmt.send_call_permission_request("GW", "15550001111", "May we call?")
		self.assertTrue(out["success"])
		self.graph.send_permission_request.assert_called_once_with("15550001111", "May we call?")
		with patch.object(mgmt.bridge, "window_state", return_value={"open": False}):
			self.assertEqual(mgmt.send_call_permission_request("GW", "15550001111", "hi")["error"], "window_closed")
		with patch.object(mgmt, "_opted_out", return_value=True):
			self.assertEqual(mgmt.send_call_permission_request("GW", "15550001111", "hi")["error"], "opted_out")

	def test_non_admin_refused(self):
		self.frappe.get_roles.return_value = ["Guest"]
		with patch.object(mgmt, "_is_admin", return_value=False), patch.object(mgmt, "_can_manage_integrations", return_value=False):
			with self.assertRaises(PermissionError):
				mgmt.get_calling_settings("GW")


class TestGatewayDoctypeDefaults(unittest.TestCase):
	def test_calling_field_default_off(self):
		path = Path(__file__).resolve().parents[2] / "huf" / "doctype" / "gateway" / "gateway.json"
		fields = {f["fieldname"]: f for f in json.loads(path.read_text())["fields"]}
		self.assertEqual(fields["calling_enabled"]["default"], "0")
		self.assertEqual(fields["calling_enabled"]["fieldtype"], "Check")


class TestIceConfig(unittest.TestCase):
	SECRET = "s3cr3t-turn-credential"

	def test_default_is_stun_only_direct(self):
		cfg = flow.build_ice_config({}, env={})
		self.assertEqual(cfg.stun_urls, flow.DEFAULT_STUN_URLS)
		self.assertEqual(cfg.turn_urls, ())
		self.assertFalse(cfg.relay_only)

	def test_site_config_and_env_override(self):
		site = {"huf_wa_call_stun_urls": "stun:a:1, stun:b:2", "huf_wa_call_turn_urls": ["turn:t:443?transport=tcp"],
			"huf_wa_call_turn_username": "u", "huf_wa_call_turn_credential": self.SECRET}
		cfg = flow.build_ice_config(site, env={})
		self.assertEqual(cfg.stun_urls, ("stun:a:1", "stun:b:2"))
		self.assertEqual(cfg.turn_urls, ("turn:t:443?transport=tcp",))
		cfg = flow.build_ice_config(site, env={"HUF_WA_CALL_TURN_URLS": "turns:x:443", "HUF_WA_CALL_RELAY_ONLY": "true"})
		self.assertEqual(cfg.turn_urls, ("turns:x:443",))
		self.assertTrue(cfg.relay_only)

	def test_validation(self):
		with self.assertRaises(ValueError):
			flow.build_ice_config({}, env={"HUF_WA_CALL_RELAY_ONLY": "1"})  # relay without TURN
		with self.assertRaises(ValueError):
			flow.build_ice_config({}, env={"HUF_WA_CALL_TURN_URLS": "http://nope"})
		with self.assertRaises(ValueError):
			flow.build_ice_config({}, env={"HUF_WA_CALL_STUN_URLS": "turn:nope"})

	def test_secret_never_in_repr_or_summary_or_logs(self):
		cfg = flow.build_ice_config({}, env={"HUF_WA_CALL_TURN_URLS": "turns:x:443", "HUF_WA_CALL_TURN_USERNAME": "user1",
			"HUF_WA_CALL_TURN_CREDENTIAL": self.SECRET})
		with self.assertLogs(level="DEBUG") as logs:
			import logging

			logging.getLogger("t").info("ice %s %r %s", cfg, cfg, cfg.safe_summary())
		blob = repr(cfg) + str(cfg) + json.dumps(cfg.safe_summary()) + "".join(logs.output)
		self.assertNotIn(self.SECRET, blob)
		self.assertNotIn("user1", blob)
		self.assertTrue(cfg.safe_summary()["turn_auth"])

	def test_rtc_configuration_uses_first_stun_and_turn(self):
		fake = MagicMock()
		fake.RTCIceServer = lambda **kw: SimpleNamespace(**kw)
		fake.RTCConfiguration = lambda iceServers: SimpleNamespace(iceServers=iceServers)
		cfg = flow.IceConfig(stun_urls=("stun:a:1", "stun:b:2"), turn_urls=("turns:t:443",), turn_username="u", turn_credential="c")
		with patch.dict("sys.modules", {"aiortc": fake}):
			rtc = flow.to_rtc_configuration(cfg)
		self.assertEqual([s.urls for s in rtc.iceServers], ["stun:a:1", "turns:t:443"])
		self.assertEqual(rtc.iceServers[1].credential, "c")

	def test_relay_policy_fails_closed(self):
		pc = SimpleNamespace(getTransceivers=lambda: [])
		with patch.dict("sys.modules", {"aioice": MagicMock()}):
			with self.assertRaises(RuntimeError):
				flow._force_relay_policy(pc)
