# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Entry selection and dispatch safety for gateway-triggered flows. Frappe is patched out; runs without a bench."""

import json
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from huf.ai.flow.gateways import dispatch
from huf.ai.flow.gateways.dispatch import pick_gateway_entry

GW = SimpleNamespace(name="Support", provider="whatsapp", default_target_type="Agent", default_agent="helper")


def node(node_id, node_type="trigger.gateway", gateway="Support", **params):
	cfg = {"gateway": gateway, "params": [{"key": k, "value": v} for k, v in params.items()]}
	return {"id": node_id, "type": node_type, "config": cfg}


def defn(*nodes, entry=None):
	return {"entry": entry or [n["id"] for n in nodes], "nodes": list(nodes)}


def payload(**over):
	base = {
		"gateway_event": "GWE-1", "gateway": "Support", "provider": "whatsapp", "sender_id": "1", "conversation_id": "c1",
		"text": "refund please", "message_type": "text", "kind": "message", "attachments": [],
	}
	base.update(over)
	return base


def pick(d, p):
	entries = d["entry"]
	return pick_gateway_entry(d, entries, {n["id"]: n["type"] for n in d["nodes"]}, p)


class TestEntrySelection(unittest.TestCase):
	def test_no_gateway_trigger_keeps_first_entry(self):
		d = defn({"id": "t_web", "type": "trigger.webhook", "config": {}}, {"id": "t_cron", "type": "trigger.schedule", "config": {}})
		self.assertEqual(pick(d, payload()), "t_web")
		self.assertEqual(pick(d, None), "t_web")

	def test_first_matching_trigger_wins(self):
		d = defn(node("a", keywords=["order"]), node("b", keywords=["refund"]), node("c"))
		self.assertEqual(pick(d, payload()), "b")

	def test_mixed_triggers_prefer_gateway_over_first_entry(self):
		d = defn({"id": "t_web", "type": "trigger.webhook", "config": {}}, node("g"))
		self.assertEqual(pick(d, payload()), "g")

	def test_other_channel_does_not_match(self):
		d = defn(node("a", gateway="Other"), node("b"))
		self.assertEqual(pick(d, payload()), "b")

	def test_gateway_triggers_but_none_match_raises(self):
		with self.assertRaises(ValueError):
			pick(defn(node("a", keywords=["order"])), payload())

	def test_dedicated_node_checks_provider(self):
		d = defn(node("w", "trigger.whatsapp"))
		self.assertEqual(pick(d, payload()), "w")
		with self.assertRaises(ValueError):
			pick(d, payload(provider="telegram"))

	def test_test_run_without_event_ignores_filters(self):
		d = defn(node("a", gateway="Other", keywords=["x"]), node("b", keywords=["never"]))
		self.assertEqual(pick(d, {"gateway": "Support"}), "b")
		self.assertEqual(pick(d, {}), "a")
		self.assertEqual(pick(d, None), "a")


def run_gate(d, *, status="Active", owner_problem=None, busy=False, requeues=0, over_cap=False, pl=None):
	event = SimpleNamespace(name="GWE-1", target_flow="F1", conversation_id="c1")
	row = {"status": status, "owner": "o@x.com", "definition_json": json.dumps(d)}
	busy_mod = types.ModuleType("huf.ai.gateway_service")
	busy_mod.ConversationBusy = type("ConversationBusy", (Exception,), {})
	fake_cache = SimpleNamespace(get_value=lambda key: requeues if key == "huf_gw_requeue:GWE-1" else 0)
	with patch.object(dispatch, "_flow_row", return_value=row), patch.object(
		dispatch, "owner_problem", return_value=owner_problem
	), patch.object(dispatch, "conversation_is_busy", return_value=busy), patch(
		"frappe.cache", lambda: fake_cache
	), patch.object(dispatch, "over_rate_cap", return_value=over_cap) as cap, patch.dict(
		sys.modules, {"huf.ai.gateway_service": busy_mod}
	):
		try:
			return dispatch.gate_flow_start(event, GW, pl or payload()), cap, busy_mod
		except busy_mod.ConversationBusy as exc:
			return ("BUSY", exc.retry_delay), cap, busy_mod


class TestGate(unittest.TestCase):
	D = defn(node("g"))

	def test_start_when_everything_is_fine(self):
		(note, voice), cap, _ = run_gate(self.D)
		self.assertEqual((note, voice), (None, False))
		cap.assert_called_once()

	def test_not_active_fails_closed(self):
		self.assertEqual(run_gate(self.D, status="Draft")[0], (dispatch.NOTE_NOT_LIVE, False))

	def test_owner_checks_fail_closed(self):
		note, _ = run_gate(self.D, owner_problem="owner lost the publish capability")[0]
		self.assertTrue(note.startswith(dispatch.NOTE_OWNER))

	def test_filter_mismatch_skips(self):
		d = defn(node("g", keywords=["order"]))
		self.assertEqual(run_gate(d)[0], (dispatch.NOTE_NO_MATCH, False))

	def test_rate_cap_skips(self):
		self.assertEqual(run_gate(self.D, over_cap=True)[0], (dispatch.NOTE_RATE, False))

	def test_plain_route_bound_flow_is_untouched(self):
		d = defn({"id": "t", "type": "trigger.webhook", "config": {}})
		(note, _), cap, _ = run_gate(d, owner_problem="should not matter", busy=True, over_cap=True)
		self.assertIsNone(note)
		cap.assert_not_called()

	def test_busy_conversation_requeues_with_a_delay_and_never_sleeps(self):
		self.assertFalse(hasattr(dispatch, "time"))  # no time.sleep in the gate: the worker is never held
		got = run_gate(self.D, busy=True, requeues=dispatch.BUSY_REQUEUE_LIMIT - 1)[0]
		self.assertEqual(got, ("BUSY", dispatch.BUSY_RETRY_DELAY_SECONDS))

	def test_busy_at_the_requeue_limit_falls_through_instead_of_a_parallel_run(self):
		got, cap, _ = run_gate(self.D, busy=True, requeues=dispatch.BUSY_REQUEUE_LIMIT)
		self.assertEqual(got, (dispatch.NOTE_BUSY, False))
		self.assertEqual(dispatch.NOTE_BUSY, "Skipped: conversation busy")
		cap.assert_not_called()

	def test_busy_does_not_count_the_rate_cap(self):
		_, cap, _ = run_gate(self.D, busy=True)
		cap.assert_not_called()

	def test_allow_parallel_skips_serialization(self):
		(note, _), _, _ = run_gate(defn(node("g", allow_parallel=True)), busy=True)
		self.assertIsNone(note)

	def test_voice_trigger_asks_for_transcript(self):
		(note, voice), _, _ = run_gate(defn(node("g", message_kinds=["voice"])), pl=payload(message_type="voice"))
		self.assertEqual((note, voice), (None, True))


class TestBusyQuery(unittest.TestCase):
	def test_running_earlier_run_counts_waiting_does_not(self):
		fr = MagicMock()
		fr.get_all.return_value = ["FR-1"]
		fr.db.exists.return_value = False  # nothing Running among them (Waiting User / Success only)
		with patch("frappe.get_all", fr.get_all), patch("frappe.db.exists", fr.db.exists):
			self.assertFalse(dispatch.conversation_is_busy("Support", "c1", "GWE-2"))
			args = fr.db.exists.call_args[0]
			self.assertEqual(args[1], {"name": ["in", ["FR-1"]], "status": "Running"})
			fr.db.exists.return_value = "FR-1"
			self.assertTrue(dispatch.conversation_is_busy("Support", "c1", "GWE-2"))
			self.assertFalse(dispatch.conversation_is_busy("Support", "", "GWE-2"))


class TestFallThrough(unittest.TestCase):
	def event(self):
		ev = MagicMock()
		ev.name = "GWE-1"
		return ev

	def test_goes_to_default_agent_and_not_back_to_the_flow(self):
		svc = MagicMock()
		svc._process_gateway_event.return_value = {"status": "Succeeded"}
		ev = self.event()
		out = dispatch.fall_through(ev, GW, dispatch.NOTE_NO_MATCH, svc=svc)
		values = ev.db_set.call_args[0][0]
		self.assertEqual((values["target_type"], values["target_agent"], values["target_flow"]), ("Agent", "helper", None))
		self.assertEqual(values["status"], "Queued")
		svc._process_gateway_event.assert_called_once_with("GWE-1")
		self.assertTrue(out["skipped"])

	def test_default_flow_or_none_is_unrouted(self):
		for gw in (
			SimpleNamespace(name="S", default_target_type="Flow", default_agent=None, default_flow="F1"),
			SimpleNamespace(name="S", default_target_type=None, default_agent=None),
		):
			svc = MagicMock()
			out = dispatch.fall_through(self.event(), gw, dispatch.NOTE_NOT_LIVE, svc=svc)
			svc._process_gateway_event.assert_not_called()
			svc._reject_gateway_event.assert_called_once()
			self.assertEqual(svc._reject_gateway_event.call_args[0][2:], ("Unrouted", dispatch.NOTE_NOT_LIVE))
			self.assertEqual(out["status"], "Unrouted")


class TestOwnerProblem(unittest.TestCase):
	def test_each_loss_is_reported(self):
		with patch("frappe.db.get_value", return_value=0):
			self.assertEqual(dispatch.owner_problem("o@x.com", "Support"), "owner is disabled")
		with patch("frappe.db.get_value", return_value=1), patch("huf.permissions.has_capability", return_value=False):
			self.assertEqual(dispatch.owner_problem("o@x.com", "Support"), "owner lost the publish capability")
		with patch("frappe.db.get_value", return_value=1), patch("huf.permissions.has_capability", return_value=True), patch(
			"frappe.has_permission", return_value=False
		):
			self.assertEqual(dispatch.owner_problem("o@x.com", "Support"), "owner cannot write to the gateway")
		with patch("frappe.db.get_value", return_value=1), patch("huf.permissions.has_capability", return_value=True), patch(
			"frappe.has_permission", return_value=True
		):
			self.assertIsNone(dispatch.owner_problem("o@x.com", "Support"))


class TestTranscript(unittest.TestCase):
	def test_voice_only_and_wrapped_untrusted(self):
		out = types.ModuleType("huf.ai.audio_service")
		out.transcribe_audio_file = lambda **kw: {"success": True, "transcript": "call me <b>now</b>"}
		p = payload(message_type="voice", attachments=["/files/v.ogg"])
		with patch.dict(sys.modules, {"huf.ai.audio_service": out}), patch("frappe.db.get_value", return_value="FILE-1"):
			dispatch.add_transcript(p, GW)
		self.assertIn("&lt;b&gt;now&lt;/b&gt;", p["transcript"])
		self.assertIn("voice note", p["transcript"])
		text = payload(attachments=["/files/a.png"])
		dispatch.add_transcript(text, GW)
		self.assertNotIn("transcript", text)


class TestMergeExtras(unittest.TestCase):
	def test_provider_value_wins_only_when_non_empty(self):
		from huf.ai.flow.gateways.gateway_payload import merge_extras

		p = {"display_name": "Asha", "language": "en", "is_room": True, "kind": "message", "new": None}
		merge_extras(p, {"display_name": "", "language": None, "is_room": False, "kind": "callback", "new": "x", "tags": []})
		self.assertEqual(p["display_name"], "Asha")
		self.assertEqual(p["language"], "en")
		self.assertFalse(p["is_room"])  # False is a real provider value
		self.assertEqual(p["kind"], "callback")
		self.assertEqual(p["new"], "x")


if __name__ == "__main__":
	unittest.main()


class TestEngineSelectEntryNode(unittest.TestCase):
	"""The engine rule, including the regression for a route-bound flow with no gateway trigger."""

	def setUp(self):
		try:
			from huf.ai.flow import engine
		except Exception:  # pragma: no cover
			self.skipTest("needs the app's imports (bench)")
		self.engine = engine

	def test_gateway_tuple_registered(self):
		self.assertEqual(
			self.engine.TRIGGER_NODE_TYPES["Gateway"], ("trigger.gateway", "trigger.whatsapp", "trigger.telegram")
		)

	def test_no_gateway_trigger_keeps_entries_zero_and_never_raises(self):
		d = defn({"id": "t_web", "type": "trigger.webhook", "config": {}}, {"id": "t_doc", "type": "trigger.doc-event", "config": {}})
		self.assertEqual(self.engine.select_entry_node(d, "Gateway"), "t_web")
		self.assertEqual(self.engine.select_entry_node(d, "Gateway", payload()), "t_web")
		self.assertEqual(self.engine.select_entry_node({"entry": "a", "nodes": [{"id": "a", "type": "end"}]}, "Gateway", payload()), "a")

	def test_matching_and_no_match(self):
		d = defn(node("a", keywords=["order"]), node("b", keywords=["refund"]))
		self.assertEqual(self.engine.select_entry_node(d, "Gateway", payload()), "b")
		with self.assertRaises(ValueError):
			self.engine.select_entry_node(d, "Gateway", payload(text="hello"))

	def test_other_trigger_types_unchanged(self):
		d = defn({"id": "t_web", "type": "trigger.webhook", "config": {}}, {"id": "t_cron", "type": "trigger.schedule", "config": {}})
		self.assertEqual(self.engine.select_entry_node(d, "Schedule"), "t_cron")
		self.assertEqual(self.engine.select_entry_node(d, "Manual"), "t_web")


class TestMediaSaveIdempotent(unittest.TestCase):
	"""Fall-through to the default agent asks for media twice (flow start, then agent path): download once.
	A retry after a partial save (no marker) downloads the rest."""

	def run_save(self, *, marker, existing, urls=("/private/files/new.ogg",)):
		from huf.ai import gateway_service as svc

		calls = []
		hook = lambda event, gateway: calls.append(1) or list(urls)  # noqa: E731
		cache = SimpleNamespace(get_value=lambda key: 1 if marker else None, set_value=MagicMock())
		with patch.object(svc.provider_hooks, "get", return_value=hook), patch("frappe.get_all", return_value=existing), patch(
			"frappe.cache", cache
		):
			out = svc._save_event_media(types.SimpleNamespace(name="GE-1"), types.SimpleNamespace(provider="WhatsApp"))
		return out, calls, cache

	def test_reuses_files_when_the_media_saved_marker_is_set(self):
		out, calls, _ = self.run_save(marker=True, existing=["/private/files/old.ogg"])
		self.assertEqual((out, calls), (["/private/files/old.ogg"], []))

	def test_partial_save_without_marker_downloads_the_rest(self):
		out, calls, cache = self.run_save(marker=False, existing=["/private/files/old.ogg"], urls=["/private/files/old.ogg", "/private/files/b.png"])
		self.assertEqual((out, calls), (["/private/files/old.ogg", "/private/files/b.png"], [1]))
		cache.set_value.assert_called_once()  # the marker is set once the hook has run

	def test_nothing_saved_yet_runs_the_hook(self):
		out, calls, _ = self.run_save(marker=False, existing=[])
		self.assertEqual((out, calls), (["/private/files/new.ogg"], [1]))


class TestDelayedRequeue(unittest.TestCase):
	"""The busy requeue is a delayed enqueue (``not_before``); an early job hops back instead of holding a worker."""

	def test_requeue_passes_the_delay_as_not_before(self):
		from huf.ai import gateway_service as svc

		event = MagicMock(name="event")
		event.name = "GWE-1"
		cache = MagicMock()
		cache.get_value.return_value = 0
		with patch("frappe.cache", cache), patch("frappe.db.rollback"), patch.object(svc, "_commit_unless_testing"), patch.object(
			svc, "_epoch", return_value=1000.0
		), patch("frappe.enqueue") as enqueue:
			svc._requeue_busy_event(event, "busy", 2.0)
			self.assertEqual(enqueue.call_args.kwargs["not_before"], 1002.0)
			svc._requeue_busy_event(event, "busy")
			self.assertIsNone(enqueue.call_args.kwargs["not_before"])

	def test_early_job_re_enqueues_without_processing(self):
		from huf.ai import gateway_service as svc

		with patch.object(svc, "_epoch", return_value=1000.0), patch.object(svc, "_sleep") as slept, patch(
			"frappe.enqueue"
		) as enqueue, patch.object(svc, "_process_gateway_event") as process:
			out = svc.process_gateway_event("GWE-1", not_before=1002.0)
		self.assertTrue(out["deferred"])
		process.assert_not_called()
		self.assertEqual(enqueue.call_args.kwargs["not_before"], 1002.0)
		self.assertLessEqual(slept.call_args.args[0], svc._RETRY_POLL_SECONDS)  # a short hop, never the whole delay
