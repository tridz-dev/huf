"""WP-5: no lost messages (reaper v2, ingest dead letters + replay, explicit >100 messages policy)."""

import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe

from huf.ai import gateway_service, gateway_webhook
from huf.ai.gateway_adapters.types import GatewayInboundRequest

NOW = datetime(2026, 10, 22, 12, 0, 0)


class FakeStore:
	"""Tiny in-memory Gateway Event table for the reaper (patches frappe.get_all / db.set_value / enqueue)."""

	def __init__(self, rows):
		self.rows = {r["name"]: dict(r) for r in rows}
		self.enqueued = []

	def get_all(self, doctype, filters=None, fields=None, pluck=None, limit_page_length=None, **kw):
		out = []
		for row in self.rows.values():
			ok = True
			for key, cond in (filters or {}).items():
				val = row.get(key)
				if isinstance(cond, list) and cond[0] == "<":
					ok = ok and val is not None and val < cond[1]
				elif isinstance(cond, list) and cond[0] == "!=":
					ok = ok and val != cond[1]
				elif isinstance(cond, list) and cond[0] == "in":
					ok = ok and val in cond[1]
				else:
					ok = ok and val == cond
			if ok:
				out.append(row["name"] if pluck else dict(row))
		return out

	def get_value(self, doctype, name, fieldname=None, as_dict=False, for_update=False, **kw):
		row = self.rows.get(name) if isinstance(name, str) else None
		if row is None:
			return None
		if isinstance(fieldname, (list, tuple)):
			return {f: row.get(f) for f in fieldname}
		return row.get(fieldname)

	def set_value(self, doctype, name, values, *a, **kw):
		self.rows[name].update(values)

	def enqueue(self, method, **kw):
		self.enqueued.append((method, kw))

	def patches(self):
		return (
			patch.object(gateway_service.frappe, "get_all", side_effect=self.get_all),
			patch.object(gateway_service.frappe.db, "get_value", side_effect=self.get_value),
			patch.object(gateway_service.frappe.db, "set_value", side_effect=self.set_value),
			patch.object(gateway_service.frappe.db, "commit"),
			patch.object(gateway_service.frappe, "enqueue", side_effect=self.enqueue),
			patch.object(gateway_service, "now_datetime", return_value=NOW),
		)


def _row(name, status, age_min, **extra):
	base = {
		"name": name,
		"status": status,
		"modified": NOW - timedelta(minutes=age_min),
		"received_at": NOW - timedelta(minutes=age_min),
		"reply_status": "",
		"reply_message_id": "",
		"agent_run": "",
		"recovery_attempts": 0,
		"retry_deadline": None,
		"error_message": "",
	}
	base.update(extra)
	return base


def _run_reaper(store):
	from contextlib import ExitStack

	with ExitStack() as stack:
		for p in store.patches():
			stack.enter_context(p)
		return gateway_service.reap_stuck_gateway_events()


class TestReaperV2(unittest.TestCase):
	def test_queued_orphan_is_reenqueued_and_attempt_persisted(self):
		store = FakeStore([_row("E1", "Queued", 30)])
		self.assertEqual(_run_reaper(store), 1)
		self.assertEqual(store.rows["E1"]["status"], "Queued")
		self.assertEqual(store.rows["E1"]["recovery_attempts"], 1)
		self.assertGreater(store.rows["E1"]["retry_deadline"], NOW)
		self.assertEqual(store.enqueued[0][0], "huf.ai.gateway_service.process_gateway_event")
		self.assertEqual(store.enqueued[0][1]["event_name"], "E1")

	def test_fresh_queued_event_is_left_alone(self):
		store = FakeStore([_row("E1", "Queued", 1)])
		self.assertEqual(_run_reaper(store), 0)
		self.assertEqual(store.enqueued, [])

	def test_queued_attempt_budget_exhausted_ends_failed_with_reason(self):
		store = FakeStore([_row("E1", "Queued", 30, recovery_attempts=gateway_service.RECOVERY_MAX_ATTEMPTS)])
		_run_reaper(store)
		self.assertEqual(store.rows["E1"]["status"], "Failed")
		self.assertIn("recovery", store.rows["E1"]["error_message"].lower())
		self.assertEqual(store.enqueued, [])

	def test_queued_past_retry_deadline_ends_failed(self):
		store = FakeStore([_row("E1", "Queued", 30, recovery_attempts=1, retry_deadline=NOW - timedelta(minutes=1))])
		_run_reaper(store)
		self.assertEqual(store.rows["E1"]["status"], "Failed")
		self.assertIn("deadline", store.rows["E1"]["error_message"].lower())

	def test_counter_is_persisted_on_the_event_not_the_cache(self):
		store = FakeStore([_row("E1", "Queued", 30)])
		with patch.object(gateway_service.frappe, "cache") as cache:
			_run_reaper(store)
		cache.assert_not_called()
		cache.return_value.get_value.assert_not_called()

	def test_failed_after_budget_runs_sender_notice_hooks(self):
		store = FakeStore([_row("E1", "Queued", 30, recovery_attempts=99)])
		seen = []
		hook = lambda name, reason: seen.append((name, reason))  # noqa: E731
		with patch.object(gateway_service, "REAP_FAILURE_HOOKS", [hook]):
			_run_reaper(store)
		self.assertEqual(seen[0][0], "E1")
		self.assertTrue(seen[0][1])

	def test_hook_errors_never_break_the_reaper(self):
		store = FakeStore([_row("E1", "Queued", 30, recovery_attempts=99), _row("E2", "Running", 60)])
		with patch.object(gateway_service, "REAP_FAILURE_HOOKS", [MagicMock(side_effect=RuntimeError("x"))]):
			self.assertEqual(_run_reaper(store), 2)
		self.assertEqual(store.rows["E2"]["status"], "Failed")

	def test_received_orphan_is_replayed_through_ingest(self):
		store = FakeStore([_row("E1", "Received", 30)])
		with patch.object(gateway_service, "_replay_event_ingest") as replay:
			_run_reaper(store)
		replay.assert_called_once_with("E1")
		self.assertEqual(store.rows["E1"]["recovery_attempts"], 1)

	def test_received_replay_failure_ends_failed_and_dead_lettered(self):
		store = FakeStore([_row("E1", "Received", 30)])
		with patch.object(gateway_service, "_replay_event_ingest", side_effect=ValueError("bad")):
			_run_reaper(store)
		self.assertEqual(store.rows["E1"]["status"], "Failed")
		self.assertTrue(store.rows["E1"]["error_message"].startswith(gateway_service.DEAD_LETTER_PREFIX))

	def test_running_stuck_still_failed_and_retrying_running_not_failed_as_running(self):
		store = FakeStore(
			[
				_row("E1", "Running", 60),
				_row("E2", "Running", 5),
				_row("E3", "Running", 60, reply_status="retrying", reply_message_id="wamid.1"),
			]
		)
		_run_reaper(store)
		self.assertEqual(store.rows["E1"]["status"], "Failed")
		self.assertEqual(store.rows["E2"]["status"], "Running")
		# E3: a part was already delivered and the rest is unknown -> failed with a reason, not retried blind
		self.assertEqual(store.rows["E3"]["status"], "Failed")
		self.assertIn("retry", store.rows["E3"]["error_message"].lower())

	def test_retrying_with_gone_job_is_resent_from_the_agent_run_response(self):
		store = FakeStore([_row("E1", "Running", 60, reply_status="retrying", agent_run="AR-1")])
		with patch.object(gateway_service, "_reply_parts_for_run", return_value=["hello"]):
			_run_reaper(store)
		self.assertEqual(store.rows["E1"]["recovery_attempts"], 1)
		method, kw = store.enqueued[0]
		self.assertEqual(method, "huf.ai.gateway_service.retry_gateway_reply")
		self.assertEqual(kw["parts_remaining"], ["hello"])
		self.assertGreater(kw["attempt"], 1)

	def test_retrying_with_no_recoverable_reply_fails(self):
		store = FakeStore([_row("E1", "Running", 60, reply_status="retrying", agent_run="AR-1")])
		with patch.object(gateway_service, "_reply_parts_for_run", return_value=[]):
			_run_reaper(store)
		self.assertEqual(store.rows["E1"]["status"], "Failed")

	def test_reaper_is_registered_exactly_once(self):
		from huf import hooks

		count = sum(
			jobs.count("huf.ai.gateway_service.reap_stuck_gateway_events")
			for jobs in hooks.scheduler_events["cron"].values()
		)
		for key, jobs in hooks.scheduler_events.items():
			if isinstance(jobs, list):
				count += jobs.count("huf.ai.gateway_service.reap_stuck_gateway_events")
		self.assertEqual(count, 1)
		self.assertIn(
			"huf.ai.gateway_service.reap_stuck_gateway_events", hooks.scheduler_events["cron"]["*/10 * * * *"]
		)


def _event(i):
	return SimpleNamespace(
		provider_event_id=f"id{i}",
		sender_id="1",
		conversation_id="1",
		thread_id="",
		message_text="t",
		is_room=0,
		mentioned=0,
		kind="message",
		raw_payload={"message": {"id": f"id{i}"}},
	)


def _req(body: bytes) -> GatewayInboundRequest:
	return GatewayInboundRequest(body=body, headers={}, query={}, method="POST")


class FakeResponse:
	http_status_code = 200


def _handle(messages, ingest_side_effect=None, ignored=0):
	parsed = SimpleNamespace(
		messages=tuple(messages), statuses=(), template_updates=(), ignored=ignored, unknown_phone_ids=()
	)
	adapter = MagicMock()
	adapter.parse_payload.return_value = parsed
	gateway = SimpleNamespace(name="GW", whatsapp_account="")
	response = FakeResponse()
	headers = {}
	ingest = MagicMock(
		side_effect=ingest_side_effect, return_value={"event_name": "E", "status": "Rejected"}
	)
	with (
		patch.object(gateway_webhook, "_ingest_rate_gate"),
		patch.object(gateway_webhook, "touch_last_event"),
		patch.object(gateway_webhook, "_warn"),
		patch.object(gateway_webhook, "_record_unknown_phone_ids"),
		patch.object(gateway_webhook, "_set_gateway_error"),
		patch.object(gateway_webhook.frappe.local, "response", response, create=True),
		patch.object(gateway_webhook.frappe.local, "response_headers", headers, create=True),
		patch("huf.ai.gateway_service.ingest_gateway_event", ingest),
		patch("huf.ai.gateway_service.store_ingest_dead_letter", return_value="DL-1") as dead,
		patch.object(gateway_webhook, "_savepoint"),
		patch.object(gateway_webhook, "_rollback_to_savepoint"),
	):
		result = gateway_webhook._handle_batched_payload(gateway, adapter, _req(b"{}"))
	return result, ingest, dead, response, headers


class TestMessageCapPolicy(unittest.TestCase):
	def test_more_than_100_messages_are_all_processed(self):
		n = gateway_webhook.MAX_MESSAGES_PER_PAYLOAD + 20
		result, ingest, _dead, response, _h = _handle([_event(i) for i in range(n)])
		self.assertEqual(ingest.call_count, n)
		self.assertEqual(result["ignored"], 0)
		self.assertEqual(result["deferred"], 0)
		self.assertEqual(response.http_status_code, 200)

	def test_beyond_total_cap_webhook_returns_503_so_meta_retries(self):
		cap = gateway_webhook.MAX_INGEST_PER_REQUEST
		result, ingest, _dead, response, headers = _handle([_event(i) for i in range(cap + 7)], ignored=2)
		self.assertEqual(ingest.call_count, cap)
		self.assertEqual(response.http_status_code, 503)
		self.assertEqual(result["deferred"], 7)
		self.assertEqual(result["ignored"], 2)  # only what the parser dropped; deferred are NOT ignored
		self.assertFalse(result["success"])
		self.assertIn("Retry-After", headers)


class TestIngestDeadLetter(unittest.TestCase):
	def test_deterministic_failure_is_dead_lettered_with_context(self):
		result, _ingest, dead, response, _h = _handle([_event(1)], ingest_side_effect=ValueError("bad row"))
		dead.assert_called_once()
		args = dead.call_args
		self.assertEqual(args.args[0], "GW")
		self.assertEqual(args.args[1], "id1")
		self.assertEqual(args.args[2]["sender_id"], "1")
		self.assertEqual(result["failed"], 1)
		self.assertEqual(result["dead_lettered"], 1)
		self.assertEqual(response.http_status_code, 200)

	def test_transient_failure_is_not_dead_lettered_and_reraises(self):
		with self.assertRaises(ConnectionError):
			_result = _handle([_event(1)], ingest_side_effect=ConnectionError("db down"))
		# dead letter helper must not have been used for a transient error
		# (checked via a second call capturing the mock)

	def test_transient_failure_does_not_dead_letter(self):
		parsed = SimpleNamespace(
			messages=(_event(1),), statuses=(), template_updates=(), ignored=0, unknown_phone_ids=()
		)
		adapter = MagicMock()
		adapter.parse_payload.return_value = parsed
		with (
			patch.object(gateway_webhook, "_ingest_rate_gate"),
			patch.object(gateway_webhook, "_warn"),
			patch.object(gateway_webhook, "_record_unknown_phone_ids"),
			patch.object(gateway_webhook, "_set_gateway_error"),
			patch.object(gateway_webhook, "_savepoint"),
			patch.object(gateway_webhook, "_rollback_to_savepoint"),
			patch("huf.ai.gateway_service.ingest_gateway_event", side_effect=ConnectionError("x")),
			patch("huf.ai.gateway_service.store_ingest_dead_letter") as dead,
		):
			with self.assertRaises(ConnectionError):
				gateway_webhook._handle_batched_payload(SimpleNamespace(name="GW", whatsapp_account=""), adapter, _req(b"{}"))
		dead.assert_not_called()

	def test_dead_letter_failure_never_breaks_the_ack(self):
		with patch("huf.ai.gateway_service.store_ingest_dead_letter", side_effect=RuntimeError("db")):
			pass
		parsed = SimpleNamespace(
			messages=(_event(1),), statuses=(), template_updates=(), ignored=0, unknown_phone_ids=()
		)
		adapter = MagicMock()
		adapter.parse_payload.return_value = parsed
		with (
			patch.object(gateway_webhook, "_ingest_rate_gate"),
			patch.object(gateway_webhook, "_warn"),
			patch.object(gateway_webhook, "_record_unknown_phone_ids"),
			patch.object(gateway_webhook, "_set_gateway_error"),
			patch.object(gateway_webhook, "_savepoint"),
			patch.object(gateway_webhook, "_rollback_to_savepoint"),
			patch("huf.ai.gateway_service.ingest_gateway_event", side_effect=ValueError("x")),
			patch("huf.ai.gateway_service.store_ingest_dead_letter", side_effect=RuntimeError("db")),
		):
			result = gateway_webhook._handle_batched_payload(
				SimpleNamespace(name="GW", whatsapp_account=""), adapter, _req(b"{}")
			)
		self.assertEqual(result["failed"], 1)
		self.assertEqual(result["dead_lettered"], 0)

	def test_store_dead_letter_inserts_failed_event_with_payload_and_replay_context(self):
		captured = {}
		doc = MagicMock()
		doc.name = "DL-1"

		def fake_get_doc(values):
			captured.update(values)
			return doc

		with (
			patch.object(gateway_service.frappe.db, "get_value", return_value=None),
			patch.object(gateway_service.frappe, "get_doc", side_effect=fake_get_doc),
		):
			name = gateway_service.store_ingest_dead_letter(
				"GW", "wamid.1", {"sender_id": "55", "kind": "message"}, {"message": {"id": "wamid.1"}}, ValueError("boom")
			)
		self.assertEqual(name, "DL-1")
		self.assertEqual(captured["status"], "Failed")
		self.assertEqual(captured["idempotency_key"], gateway_service._idempotency_key("GW", "wamid.1"))
		self.assertTrue(captured["error_message"].startswith(gateway_service.DEAD_LETTER_PREFIX))
		self.assertEqual(captured["raw_payload"]["message"]["id"], "wamid.1")
		self.assertEqual(captured["raw_payload"]["_replay_context"]["sender_id"], "55")

	def test_store_dead_letter_reuses_a_half_inserted_event(self):
		with (
			patch.object(
				gateway_service.frappe.db, "get_value", return_value={"name": "E9", "status": "Received"}
			),
			patch.object(gateway_service.frappe.db, "set_value") as set_value,
			patch.object(gateway_service.frappe, "get_doc") as get_doc,
		):
			name = gateway_service.store_ingest_dead_letter("GW", "wamid.1", {}, {"a": 1}, ValueError("boom"))
		self.assertEqual(name, "E9")
		get_doc.assert_not_called()
		values = set_value.call_args.args[2]
		self.assertEqual(values["status"], "Failed")

	def test_error_text_in_dead_letter_is_redacted(self):
		captured = {}
		doc = MagicMock()
		with (
			patch.object(gateway_service.frappe.db, "get_value", return_value=None),
			patch.object(gateway_service.frappe, "get_doc", side_effect=lambda v: captured.update(v) or doc),
		):
			gateway_service.store_ingest_dead_letter(
				"GW", "w", {}, {"access_token": "SECRET"}, ValueError("x")
			)
		self.assertEqual(captured["raw_payload"]["access_token"], "[redacted]")


class TestRetryGatewayEvent(unittest.TestCase):
	def _dead(self, **over):
		raw = {"message": {"id": "w"}, "_replay_context": {"kind": "message", "sender_id": "5"}}
		row = {
			"name": "DL-1",
			"gateway": "GW",
			"status": "Failed",
			"error_message": gateway_service.DEAD_LETTER_PREFIX + " boom",
			"provider_event_id": "w",
			"raw_payload": raw,
			"sender_id": "5",
		}
		row.update(over)
		return row

	def test_requires_gateway_admin(self):
		with patch.object(gateway_service, "_is_gateway_admin", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				gateway_service.retry_gateway_event("DL-1")

	def test_is_whitelisted_post_only(self):
		self.assertIn(gateway_service.retry_gateway_event, frappe.whitelisted)
		self.assertEqual(list(frappe.allowed_http_methods_for_whitelisted_func[gateway_service.retry_gateway_event]), ["POST"])

	def test_replays_dead_letter_with_same_event_row(self):
		row = self._dead()
		with (
			patch.object(gateway_service, "_is_gateway_admin", return_value=True),
			patch.object(gateway_service.frappe.db, "get_value", return_value=row),
			patch.object(gateway_service.frappe.db, "set_value") as set_value,
			patch.object(gateway_service, "_replay_event_ingest", return_value={"status": "Queued"}) as replay,
		):
			out = gateway_service.retry_gateway_event("DL-1")
		replay.assert_called_once_with("DL-1")
		self.assertTrue(out["replayed"])
		first = set_value.call_args_list[0].args[2]
		self.assertEqual(first["status"], "Received")
		self.assertEqual(first["error_message"], "")

	def test_second_replay_is_a_noop(self):
		row = self._dead(status="Queued", error_message="")
		with (
			patch.object(gateway_service, "_is_gateway_admin", return_value=True),
			patch.object(gateway_service.frappe.db, "get_value", return_value=row),
			patch.object(gateway_service, "_replay_event_ingest") as replay,
		):
			out = gateway_service.retry_gateway_event("DL-1")
		replay.assert_not_called()
		self.assertFalse(out["replayed"])

	def test_non_dead_letter_failed_event_is_refused(self):
		row = self._dead(error_message="agent crashed")
		with (
			patch.object(gateway_service, "_is_gateway_admin", return_value=True),
			patch.object(gateway_service.frappe.db, "get_value", return_value=row),
			patch.object(gateway_service, "_replay_event_ingest") as replay,
		):
			with self.assertRaises(frappe.ValidationError):
				gateway_service.retry_gateway_event("DL-1")
		replay.assert_not_called()

	def test_replay_failure_restores_the_dead_letter(self):
		row = self._dead()
		with (
			patch.object(gateway_service, "_is_gateway_admin", return_value=True),
			patch.object(gateway_service.frappe.db, "get_value", return_value=row),
			patch.object(gateway_service.frappe.db, "set_value") as set_value,
			patch.object(gateway_service.frappe.db, "savepoint"),
			patch.object(gateway_service.frappe.db, "rollback"),
			patch.object(gateway_service, "_replay_event_ingest", side_effect=ValueError("still bad")),
		):
			out = gateway_service.retry_gateway_event("DL-1")
		self.assertFalse(out["replayed"])
		last = set_value.call_args_list[-1].args[2]
		self.assertEqual(last["status"], "Failed")
		self.assertTrue(last["error_message"].startswith(gateway_service.DEAD_LETTER_PREFIX))

	def test_unknown_event_raises_not_found(self):
		with (
			patch.object(gateway_service, "_is_gateway_admin", return_value=True),
			patch.object(gateway_service.frappe.db, "get_value", return_value=None),
		):
			with self.assertRaises(frappe.DoesNotExistError):
				gateway_service.retry_gateway_event("nope")
