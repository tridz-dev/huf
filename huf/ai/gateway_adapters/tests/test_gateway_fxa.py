"""FX-A: reaper vs Flow runs, atomic recovery, flow-reply compare-and-set, linked opt-out ids."""

import json
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from huf.ai import gateway_service as gs

NOW = datetime(2026, 10, 22, 12, 0, 0)
BSUID = "IN.460812345678901234"
PHONE = "919876543210"


class Store:
	"""In-memory Gateway Event / Flow Run / Access Entry tables behind the frappe calls gateway_service makes."""

	def __init__(self, events=(), flow_runs=None, entries=()):
		self.events = {e["name"]: dict(e) for e in events}
		self.flow_runs = dict(flow_runs or {})
		self.entries = [dict(e) for e in entries]
		self.enqueued = []
		self.locked = []
		self.cache_keys = {}
		self.clock = NOW

	def _match(self, row, filters):
		for key, cond in (filters or {}).items():
			val = row.get(key)
			if isinstance(cond, list):
				op, arg = cond[0], cond[1]
				if op == "<":
					ok = val is not None and val < arg
				elif op == "!=":
					ok = val != arg
				elif op == "in":
					ok = val in arg
				elif op == "like":
					ok = arg.strip("%") in str(val or "")
				else:
					raise AssertionError(op)
			else:
				ok = val == cond
			if not ok:
				return False
		return True

	def get_all(self, doctype, filters=None, fields=None, pluck=None, limit_page_length=None, **kw):
		table = {"Gateway Event": list(self.events.values()), "Gateway Access Entry": self.entries}[doctype]
		rows = [r for r in table if self._match(r, filters)]
		return [r["name"] for r in rows] if pluck else [dict(r) for r in rows]

	def get_value(self, doctype, name, fieldname=None, as_dict=False, for_update=False, **kw):
		if doctype == "Flow Run":
			return self.flow_runs.get(name)
		assert doctype == "Gateway Event"
		if isinstance(name, dict):
			rows = [r for r in self.events.values() if self._match(r, name)]
			row = rows[0] if rows else None
		else:
			row = self.events.get(name)
		if for_update and row:
			self.locked.append(row["name"])
		if row is None:
			return None
		if isinstance(fieldname, (list, tuple)):
			out = {f: row.get(f) for f in fieldname}
			return out if as_dict else tuple(out.values())
		return row.get(fieldname)

	def set_value(self, doctype, name, values, value=None, *a, **kw):
		if not isinstance(values, dict):
			values = {values: value}
		if isinstance(name, dict):
			targets = [r for r in self.events.values() if self._match(r, name)]
		else:
			targets = [self.events[name]]
		for row in targets:
			row.update(values)
			if kw.get("update_modified", True):
				self.clock += timedelta(seconds=1)
				row["modified"] = self.clock

	def enqueue(self, method, **kw):
		self.enqueued.append((method, kw))

	def cache_set(self, key, value, ex=None, nx=False):
		if nx and key in self.cache_keys:
			return False
		self.cache_keys[key] = value
		return True

	def patch(self):
		from contextlib import ExitStack

		stack = ExitStack()
		f = gs.frappe
		stack.enter_context(patch.object(f, "get_all", side_effect=self.get_all))
		stack.enter_context(patch.object(f.db, "get_value", side_effect=self.get_value))
		stack.enter_context(patch.object(f.db, "set_value", side_effect=self.set_value))
		stack.enter_context(patch.object(f.db, "commit"))
		stack.enter_context(patch.object(f, "enqueue", side_effect=self.enqueue))
		stack.enter_context(patch.object(gs, "now_datetime", return_value=NOW))
		cache = SimpleNamespace(set=self.cache_set, delete=lambda key: self.cache_keys.pop(key, None))
		stack.enter_context(patch.object(f, "cache", return_value=cache))
		return stack


def _event(name, status="Running", age=30, **extra):
	row = {
		"name": name, "status": status, "modified": NOW - timedelta(minutes=age),
		"received_at": NOW - timedelta(minutes=age), "reply_status": "", "reply_message_id": "",
		"agent_run": "", "recovery_attempts": 0, "retry_deadline": None, "error_message": "",
		"flow_run": "", "gateway": "GW", "sender_id": PHONE, "raw_payload": "{}",
	}
	row.update(extra)
	return row


class TestReaperFlowRuns(unittest.TestCase):
	def test_running_flow_run_is_not_reaped(self):
		for flow_status in ("Queued", "Running", "Waiting User", "Waiting Approval"):
			store = Store([_event("E1", flow_run="FR1")], {"FR1": flow_status})
			with store.patch():
				gs.reap_stuck_gateway_events()
			self.assertEqual(store.events["E1"]["status"], "Running", flow_status)

	def test_terminal_flow_run_event_is_still_reaped(self):
		store = Store([_event("E1", flow_run="FR1")], {"FR1": "Failed"})
		with store.patch():
			gs.reap_stuck_gateway_events()
		self.assertEqual(store.events["E1"]["status"], "Failed")


class TestFinishFlowEvent(unittest.TestCase):
	def _run(self, store, **kw):
		sent = []

		class Doc(SimpleNamespace):
			def db_set(self, values, value=None, **k):
				store.set_value("Gateway Event", self.name, values if isinstance(values, dict) else {values: value})
				self.__dict__.update(values if isinstance(values, dict) else {values: value})

		def get_doc(doctype, name=None):
			if doctype == "Gateway":
				return SimpleNamespace(name="GW", provider="WhatsApp")
			return Doc(**store.events[name])

		def send(event, gateway, run, text):
			sent.append((text, store.events[event.name]["status"]))
			store.set_value("Gateway Event", event.name, {"status": "Succeeded"})

		with store.patch(), patch.object(gs.frappe, "get_doc", side_effect=get_doc), patch.object(
			gs, "_send_whatsapp_reply", side_effect=send
		):
			gs.finish_flow_event("FR1", "Success", "hello", **kw)
		return sent

	def test_reaper_failed_event_still_delivers_the_flow_reply(self):
		reaped = f"Stuck in Running for over {gs.STUCK_RUNNING_MINUTES} minutes; the worker finished or died."
		store = Store([_event("E1", "Failed", flow_run="FR1", error_message=reaped)])
		sent = self._run(store)
		self.assertEqual(len(sent), 1)
		self.assertEqual(store.events["E1"]["status"], "Succeeded")
		self.assertEqual(store.events["E1"]["error_message"], "")

	def test_genuinely_failed_event_is_left_alone(self):
		store = Store([_event("E1", "Failed", flow_run="FR1", error_message="boom")])
		self.assertEqual(self._run(store), [])

	def test_status_is_claimed_under_row_lock_before_sending(self):
		store = Store([_event("E1", "Running", flow_run="FR1")])
		sent = self._run(store)
		self.assertEqual(sent, [("hello", "Replying")])
		self.assertIn("E1", store.locked)

	def test_second_completion_while_replying_does_not_send(self):
		store = Store([_event("E1", "Replying", flow_run="FR1")])
		self.assertEqual(self._run(store), [])


class TestAtomicRecovery(unittest.TestCase):
	def test_two_workers_with_the_same_stale_snapshot_spend_one_attempt(self):
		store = Store([_event("E1", "Queued", age=30)])
		snapshot = dict(store.events["E1"])
		with store.patch():
			first = gs._spend_recovery_attempt(dict(snapshot), NOW)
			second = gs._spend_recovery_attempt(dict(snapshot), NOW)
		self.assertIsNone(first)
		self.assertEqual(second, gs.RECOVERY_RACED)
		self.assertEqual(store.events["E1"]["recovery_attempts"], 1)
		self.assertIn("E1", store.locked)

	def test_concurrent_reapers_enqueue_an_orphan_once(self):
		store = Store([_event("E1", "Queued", age=30)])
		with store.patch():
			rows = store.get_all("Gateway Event")
			# both workers listed the orphan before either spent an attempt
			with patch.object(gs.frappe, "get_all", side_effect=[rows, [], []] * 2):
				gs._recover_orphaned_events()
				gs._recover_orphaned_events()
		self.assertEqual(len(store.enqueued), 1)

	def test_retry_claim_is_per_event_so_an_overlapping_attempt_is_skipped(self):
		store = Store([_event("E1", "Running", reply_status="retrying")])
		event = SimpleNamespace(name="E1", reply_status="retrying", status="Running", gateway="GW", sender_id="", agent_run="")
		gateway = SimpleNamespace(execution_user="")
		inner = []

		def attempt(*a, **k):
			inner.append(gs.retry_gateway_reply("E1", ["p"], attempt=3, not_before=0))
			return {}

		with store.patch(), patch.object(
			gs.frappe, "get_doc", side_effect=lambda dt, n=None: gateway if dt == "Gateway" else event
		), patch.object(gs, "_attempt_reply_parts", side_effect=attempt
		), patch.object(gs, "is_opted_out", return_value=False):
			gs.retry_gateway_reply("E1", ["p"], attempt=2, not_before=0)
			self.assertEqual(inner, [{"event_name": "E1", "skipped": True}])
			self.assertEqual(store.cache_keys, {})  # released after the attempt

	def test_retry_hopping_back_to_the_queue_refreshes_modified(self):
		store = Store([_event("E1", "Running", age=9, reply_status="retrying")])
		before = store.events["E1"]["modified"]
		event = SimpleNamespace(name="E1", reply_status="retrying", status="Running", gateway="GW")
		with store.patch(), patch.object(gs.frappe, "get_doc", return_value=event), patch.object(
			gs, "_sleep"
		), patch.object(gs, "_epoch", return_value=1000.0):
			out = gs.retry_gateway_reply("E1", ["p"], attempt=2, not_before=1500.0)
		self.assertTrue(out.get("deferred"))
		self.assertGreater(store.events["E1"]["modified"], before)


class TestLinkedOptOut(unittest.TestCase):
	def _entry(self, external_id):
		return {"name": f"AE-{external_id}", "gateway": "GW", "entry_type": "Sender", "external_id": external_id, "state": "Opted out"}

	def _gw(self):
		return SimpleNamespace(name="GW", provider="WhatsApp")

	def test_bsuid_stop_blocks_later_sends_to_the_linked_phone(self):
		both = _event("E1", sender_id=PHONE, raw_payload=json.dumps({"bsuid": BSUID}))
		store = Store([both], entries=[self._entry(BSUID)])
		with store.patch():
			self.assertTrue(gs.is_opted_out(self._gw(), PHONE))

	def test_phone_stop_blocks_the_linked_bsuid(self):
		both = _event("E1", sender_id=PHONE, raw_payload=json.dumps({"bsuid": BSUID}))
		store = Store([both], entries=[self._entry(PHONE)])
		with store.patch():
			self.assertTrue(gs.is_opted_out(self._gw(), BSUID))

	def test_unlinked_phone_is_not_opted_out(self):
		store = Store([_event("E1", sender_id="911111111111")], entries=[self._entry(BSUID)])
		with store.patch():
			self.assertFalse(gs.is_opted_out(self._gw(), "911111111111"))

	def test_stop_with_both_ids_is_recorded_under_both(self):
		store = Store()
		recorded = []
		event = SimpleNamespace(raw_payload={"bsuid": BSUID})
		with store.patch(), patch.object(gs, "_record_opt_out", side_effect=lambda g, s, d=None: recorded.append(s)):
			gs._record_opt_out_linked(self._gw(), event, PHONE, None)
		self.assertEqual(recorded, [PHONE, BSUID])
