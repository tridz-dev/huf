"""Pairing, admission, STOP/START and per-sender limit hardening (T2)."""

import secrets
import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime

from huf.ai import gateway_service as gsvc
from huf.ai.tools import gateway_pairing_tools as tools


class FakeCache:
	"""Minimal in-memory stand-in for the redis wrapper used by the counters."""

	def __init__(self):
		self.data = {}

	def make_key(self, key):
		return key

	def incrby(self, key, amount):
		self.data[key] = int(self.data.get(key, 0)) + amount
		return self.data[key]

	def expire(self, key, ttl):
		return True

	def get(self, key):
		return self.data.get(key)


class TestPairingCodeFormat(unittest.TestCase):
	def test_generated_codes_use_the_unambiguous_alphabet_and_length(self):
		for _i in range(200):
			code = gsvc._generate_pairing_code()
			self.assertRegex(code, r"^PAIR-[A-Z2-9]{8}$")
			suffix = code[len("PAIR-"):]
			self.assertFalse(set(suffix) & set("01OIL"), code)
		self.assertEqual(len(set(gsvc.PAIRING_ALPHABET)), len(gsvc.PAIRING_ALPHABET))
		self.assertFalse(set(gsvc.PAIRING_ALPHABET) & set("01OIL"))

	def test_codes_are_not_repeated_in_a_sample(self):
		self.assertEqual(len({gsvc._generate_pairing_code() for _i in range(500)}), 500)

	def test_normalize_accepts_case_whitespace_and_optional_dash(self):
		expected = "PAIR-ABCD2345"
		for value in ("PAIR-ABCD2345", "pair-abcd2345", " Pair-ABCD2345 ", "PAIRABCD2345", "pair abcd2345", "ABCD2345", "abcd2345"):
			self.assertEqual(gsvc.normalize_pairing_code(value), expected, value)

	def test_normalize_rejects_malformed_codes(self):
		for value in ("", None, "PAIR-ABCD", "PAIR-ABCD23456", "PAIR-ABCD234O", "PAIR-ABCD2341", "PAIR-7A9K", "ACCESS-0001"):
			self.assertEqual(gsvc.normalize_pairing_code(value), "", value)

	@patch.object(gsvc, "_code_in_use")
	@patch.object(gsvc, "_generate_pairing_code")
	def test_collision_retries_until_a_free_code(self, mock_gen, mock_in_use):
		mock_gen.side_effect = ["PAIR-AAAAAAAA", "PAIR-BBBBBBBB", "PAIR-CCCCCCCC"]
		mock_in_use.side_effect = [True, True, False]
		self.assertEqual(gsvc._new_unique_pairing_code("GW"), "PAIR-CCCCCCCC")
		self.assertEqual(mock_gen.call_count, 3)

	@patch.object(gsvc, "_code_in_use", return_value=True)
	def test_exhausted_retries_raise(self, _mock):
		with patch.object(gsvc.frappe, "throw", side_effect=RuntimeError("no code")):
			with self.assertRaises(RuntimeError):
				gsvc._new_unique_pairing_code("GW")


class TestConsentTextNormalisation(unittest.TestCase):
	def gw(self, **kw):
		return SimpleNamespace(provider="WhatsApp", name="GW", **kw)

	def matches_stop(self, text):
		return gsvc._text_matches_keywords(self.gw(), text, "opt_out_keywords", gsvc.DEFAULT_OPT_OUT_KEYWORDS)

	def test_whole_message_matches_ignoring_case_punctuation_and_emoji(self):
		for text in ("STOP", "stop", "  Stop  ", "Stop!", "stop.", "STOP!!!", "¡stop!", "stop 🛑", "🛑 STOP", "Unsubscribe", "cancel", "END", "Quit?", "\nstop\n", "s-t-o-p".replace("-", "")):
			self.assertTrue(self.matches_stop(text), text)

	def test_embedded_keywords_do_not_match(self):
		for text in ("please stop sending jokes", "don't stop", "stop it now", "I want to cancel my order", "stopping", "nonstop", "the end", "hi", "", None):
			self.assertFalse(self.matches_stop(text), text)

	def test_start_keywords(self):
		gw = self.gw()
		for text in ("START", "start!", "Unstop", "subscribe"):
			self.assertTrue(gsvc._text_matches_keywords(gw, text, "opt_in_keywords", gsvc.DEFAULT_OPT_IN_KEYWORDS), text)
		self.assertFalse(gsvc._text_matches_keywords(gw, "STOP", "opt_in_keywords", gsvc.DEFAULT_OPT_IN_KEYWORDS))

	def test_custom_keywords_and_multi_word(self):
		gw = self.gw(opt_out_keywords="BASTA\nstop all, no more")
		self.assertTrue(gsvc._text_matches_keywords(gw, "basta!", "opt_out_keywords", ""))
		self.assertTrue(gsvc._text_matches_keywords(gw, "Stop   ALL", "opt_out_keywords", ""))
		self.assertTrue(gsvc._text_matches_keywords(gw, "no more", "opt_out_keywords", ""))
		self.assertFalse(gsvc._text_matches_keywords(gw, "STOP", "opt_out_keywords", ""))


class TestCounters(unittest.TestCase):
	def setUp(self):
		self.cache = FakeCache()
		patcher = patch.object(gsvc.frappe, "cache", return_value=self.cache)
		patcher.start()
		self.addCleanup(patcher.stop)

	def test_sender_limit_boundary_20_then_21(self):
		gw = SimpleNamespace(provider="WhatsApp", name="GW", inbound_sender_limit=20)
		reasons = [gsvc._sender_rate_limit_reason(gw, {"sender_id": "15550001"}) for _i in range(21)]
		self.assertEqual(reasons[:20], [""] * 20)
		self.assertTrue(reasons[20].startswith("sender_rate_limited"))

	def test_limit_zero_is_off_and_unset_defaults_to_20(self):
		off = SimpleNamespace(provider="WhatsApp", name="GW", inbound_sender_limit=0)
		for _i in range(50):
			self.assertEqual(gsvc._sender_rate_limit_reason(off, {"sender_id": "1"}), "")
		default = SimpleNamespace(provider="WhatsApp", name="GW2", inbound_sender_limit=None)
		reasons = [gsvc._sender_rate_limit_reason(default, {"sender_id": "1"}) for _i in range(21)]
		self.assertTrue(reasons[20])

	def test_limit_is_per_sender_and_per_gateway_and_whatsapp_only(self):
		gw = SimpleNamespace(provider="WhatsApp", name="GW", inbound_sender_limit=1)
		self.assertEqual(gsvc._sender_rate_limit_reason(gw, {"sender_id": "1"}), "")
		self.assertTrue(gsvc._sender_rate_limit_reason(gw, {"sender_id": "1"}))
		self.assertEqual(gsvc._sender_rate_limit_reason(gw, {"sender_id": "2"}), "")
		other = SimpleNamespace(provider="WhatsApp", name="GW-B", inbound_sender_limit=1)
		self.assertEqual(gsvc._sender_rate_limit_reason(other, {"sender_id": "1"}), "")
		tg = SimpleNamespace(provider="Telegram", name="TG", inbound_sender_limit=1)
		for _i in range(5):
			self.assertEqual(gsvc._sender_rate_limit_reason(tg, {"sender_id": "1"}), "")

	def test_limit_resets_in_the_next_window(self):
		gw = SimpleNamespace(provider="WhatsApp", name="GW", inbound_sender_limit=1)
		now = time.time()
		with patch.object(gsvc, "time", SimpleNamespace(time=lambda: now)):
			self.assertEqual(gsvc._sender_rate_limit_reason(gw, {"sender_id": "1"}), "")
			self.assertTrue(gsvc._sender_rate_limit_reason(gw, {"sender_id": "1"}))
		with patch.object(gsvc, "time", SimpleNamespace(time=lambda: now + 2 * gsvc.INBOUND_SENDER_WINDOW_SECONDS)):
			self.assertEqual(gsvc._sender_rate_limit_reason(gw, {"sender_id": "1"}), "")


class TestApprovalBruteForce(unittest.TestCase):
	def setUp(self):
		self.cache = FakeCache()
		for patcher in (
			patch.object(gsvc.frappe, "cache", return_value=self.cache),
			patch.object(gsvc, "_is_gateway_admin", return_value=True),
			patch.object(gsvc.frappe.db, "exists", return_value=False),
			patch.object(gsvc, "_find_pending_entry_by_code", return_value=None),
		):
			patcher.start()
			self.addCleanup(patcher.stop)

	def test_sixth_attempt_in_a_minute_is_refused_even_if_valid(self):
		for _i in range(5):
			with self.assertRaises(frappe.ValidationError) as ctx:
				gsvc.approve_gateway_pairing("PAIR-ABCD2345", gateway="GW")
			self.assertNotIsInstance(ctx.exception, frappe.TooManyRequestsError)
		with patch.object(gsvc, "_find_pending_entry_by_code", return_value="ENTRY"):
			with self.assertRaises(frappe.TooManyRequestsError):
				gsvc.approve_gateway_pairing("PAIR-ABCD2345", gateway="GW")

	def test_counter_is_per_admin_and_per_minute(self):
		for _i in range(5):
			with self.assertRaises(frappe.ValidationError):
				gsvc.approve_gateway_pairing("PAIR-ABCD2345", gateway="GW")
		original_user = frappe.session.user
		frappe.session.user = "other.admin@example.com"
		try:
			with self.assertRaises(frappe.ValidationError) as ctx:
				gsvc.approve_gateway_pairing("PAIR-ABCD2345", gateway="GW")
			self.assertNotIsInstance(ctx.exception, frappe.TooManyRequestsError)
		finally:
			frappe.session.user = original_user
		later = time.time() + 61
		with patch.object(gsvc, "time", SimpleNamespace(time=lambda: later)):
			with self.assertRaises(frappe.ValidationError) as ctx:
				gsvc.approve_gateway_pairing("PAIR-ABCD2345", gateway="GW")
			self.assertNotIsInstance(ctx.exception, frappe.TooManyRequestsError)


class _GatewayFixture:
	def setUp(self):
		frappe.set_user("Administrator")
		cache = frappe.cache()
		cache.delete(cache.make_key(gsvc._approval_failure_key()))
		self.suffix = secrets.token_hex(3)
		self.gateways: list[str] = []
		self.adapter = MagicMock()
		patcher = patch("huf.ai.gateway_webhook.get_gateway_adapter", return_value=self.adapter)
		patcher.start()
		self.addCleanup(patcher.stop)
		enqueue = patch.object(gsvc.frappe, "enqueue")
		self.enqueue = enqueue.start()
		self.addCleanup(enqueue.stop)
		route = patch.object(
			gsvc,
			"resolve_gateway_route",
			return_value={"status": "Queued", "target_type": "Agent", "agent": "Hardening Agent", "binding": None},
		)
		route.start()
		self.addCleanup(route.stop)
		self.counter = 0

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in self.gateways:
			frappe.db.delete("Gateway Event", {"gateway": name})
			frappe.db.delete("Gateway Access Entry", {"gateway": name})
			frappe.db.delete("Gateway", {"name": name})
		frappe.db.commit()

	def make_gateway(self, label, *, provider="WhatsApp", policy="Pairing", **extra):
		name = f"T2 {label} {self.suffix}"
		frappe.get_doc(
			{"doctype": "Gateway", "gateway_name": name, "provider": provider, "is_enabled": 0, "direct_policy": policy}
		).insert(ignore_permissions=True)
		values = {
			"is_enabled": 1, "execution_user": "Administrator", "integration_settings": "x",
			"direct_policy": policy, "pairing_reply_enabled": 1,  # reply default is OFF; these tests exercise the reply path
		}
		values.update(extra)
		frappe.db.set_value("Gateway", name, values)
		self.gateways.append(name)
		return name

	def gw(self, name):
		return frappe.get_doc("Gateway", name)

	def make_entry(self, gateway, external_id="15551230001", *, state="Pending", code=None, expires_at=None, **extra):
		doc = frappe.get_doc(
			{
				"doctype": "Gateway Access Entry",
				"gateway": gateway,
				"entry_type": "Sender",
				"provider": frappe.db.get_value("Gateway", gateway, "provider"),
				"external_id": external_id,
				"pairing_code": code,
				"state": state,
				"expires_at": expires_at,
				**extra,
			}
		).insert(ignore_permissions=True)
		return doc.name

	def ingest(self, gateway, sender, text, **ctx):
		self.counter += 1
		context = {"sender_id": sender, "conversation_id": sender, "message_text": text, **ctx}
		return gsvc.ingest_gateway_event(
			gateway, f"wamid.{self.suffix}.{self.counter}", context, verified_sender=True, raw_payload={}
		)

	def event_error(self, result):
		return frappe.db.get_value("Gateway Event", result["event_name"], ["status", "error_message"], as_dict=True)

	def entry_state(self, name):
		return frappe.db.get_value("Gateway Access Entry", name, "state")

	def sent_texts(self):
		return [call.args[0].text for call in self.adapter.send_reply.call_args_list]


class TestPairingScopeAndAuthority(_GatewayFixture, IntegrationTestCase):
	def test_cross_gateway_code_approval_fails_and_same_code_is_scoped(self):
		a = self.make_gateway("A")
		b = self.make_gateway("B")
		entry_a = self.make_entry(a, "111", code="PAIR-SAMEKEY2")
		entry_b = self.make_entry(b, "222", code="PAIR-SAMEKEY2")
		with self.assertRaises(frappe.ValidationError):
			gsvc.approve_gateway_pairing("PAIR-SAMEKEY2", gateway="Nonexistent Gateway")
		result = gsvc.approve_gateway_pairing("pair-samekey2", gateway=b)
		self.assertEqual(result["name"], entry_b)
		self.assertEqual(self.entry_state(entry_b), "Approved")
		self.assertEqual(self.entry_state(entry_a), "Pending")

	def test_code_needs_a_gateway_and_entry_name_must_match_given_gateway(self):
		a = self.make_gateway("A")
		b = self.make_gateway("B")
		entry_a = self.make_entry(a, "111", code="PAIR-ABCD2345")
		with self.assertRaises(frappe.ValidationError):
			gsvc.approve_gateway_pairing("PAIR-ABCD2345")
		with self.assertRaises(frappe.ValidationError):
			gsvc.approve_gateway_pairing(entry_a, gateway=b)
		self.assertEqual(self.entry_state(entry_a), "Pending")
		self.assertEqual(gsvc.approve_gateway_pairing(entry_a, gateway=a)["state"], "Approved")

	def test_pending_codes_are_unique_per_gateway(self):
		a = self.make_gateway("A")
		self.make_entry(a, "111", code="PAIR-ABCD2345")
		with self.assertRaises(frappe.ValidationError):
			self.make_entry(a, "222", code="PAIR-ABCD2345")
		self.make_entry(a, "222", state="Approved", code="PAIR-ABCD2345")  # not Pending: allowed

	def test_non_admin_cannot_approve_even_with_doctype_write(self):
		a = self.make_gateway("A")
		entry = self.make_entry(a, "111", code="PAIR-ABCD2345")
		with patch.object(gsvc.frappe, "has_permission", return_value=True):
			frappe.set_user("Guest")
			with self.assertRaises(frappe.PermissionError):
				gsvc.approve_gateway_pairing("PAIR-ABCD2345", gateway=a)
		frappe.set_user("Administrator")
		self.assertEqual(self.entry_state(entry), "Pending")

	def test_integrations_capability_counts_as_admin(self):
		frappe.set_user("Guest")
		with patch.object(gsvc.frappe, "get_roles", return_value=["Desk User"]), patch(
			"huf.permissions.has_capability", side_effect=lambda user, cap: cap == "system.integrations.manage"
		):
			self.assertTrue(gsvc._is_gateway_admin())
		with patch.object(gsvc.frappe, "get_roles", return_value=["Desk User"]), patch(
			"huf.permissions.has_capability", return_value=False
		):
			self.assertFalse(gsvc._is_gateway_admin())

	def test_pairing_tools_are_admin_only_and_gateway_scoped(self):
		a = self.make_gateway("A")
		b = self.make_gateway("B")
		self.make_entry(a, "111", code="PAIR-ABCD2345")
		self.assertTrue(any(r["pairing_code"] == "*" * 11 + "45" for r in tools.list_pairing_requests(a)))
		wrong = tools.approve_pairing_code("PAIR-ABCD2345", gateway_name=b)
		self.assertFalse(wrong["success"])
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			tools.list_pairing_requests(a)
		denied = tools.approve_pairing_code("PAIR-ABCD2345", gateway_name=a)
		self.assertFalse(denied["success"])
		frappe.set_user("Administrator")
		ok = tools.approve_pairing_code("pair-abcd2345", gateway_name=a)
		self.assertTrue(ok["success"])
		self.assertEqual(ok["state"], "Approved")

	def test_list_pairing_requests_hides_expired(self):
		a = self.make_gateway("A")
		self.make_entry(a, "111", code="PAIR-ABCD2345", expires_at=add_to_date(now_datetime(), minutes=-1))
		self.assertEqual(tools.list_pairing_requests(a), [])


class TestPairingLifecycle(_GatewayFixture, IntegrationTestCase):
	def test_new_sender_gets_a_code_once_and_the_message_is_sent(self):
		a = self.make_gateway("A")
		gw = self.gw(a)
		code = gsvc._create_pairing_request(gw, "15551230001")
		self.assertRegex(code, r"^PAIR-[A-Z2-9]{8}$")
		self.assertEqual(len(self.sent_texts()), 1)
		self.assertIn(code, self.sent_texts()[0])
		self.assertEqual(gsvc._create_pairing_request(gw, "15551230001"), code)
		self.assertEqual(len(self.sent_texts()), 1)  # no spam on repeat messages

	def test_expired_entry_is_marked_expired_and_reissued_immediately(self):
		a = self.make_gateway("A", pairing_ttl_minutes=30)
		gw = self.gw(a)
		first = gsvc._create_pairing_request(gw, "15551230001")
		entry = frappe.db.get_value("Gateway Access Entry", {"gateway": a, "pairing_code": first}, "name")
		frappe.db.set_value("Gateway Access Entry", entry, "expires_at", add_to_date(now_datetime(), minutes=-1))

		# Expired inside the 10 minute cooldown: a NEW code is issued immediately and sent.
		second = gsvc._create_pairing_request(gw, "15551230001")
		self.assertRegex(second, r"^PAIR-[A-Z2-9]{8}$")
		self.assertNotEqual(first, second)
		self.assertEqual(self.entry_state(entry), "Expired")
		self.assertEqual(len(self.sent_texts()), 2)
		with self.assertRaises(frappe.ValidationError):
			gsvc.approve_gateway_pairing(first, gateway=a)
		self.assertIn(second, self.sent_texts()[1])
		self.assertEqual(gsvc.approve_gateway_pairing(second, gateway=a)["state"], "Approved")

	def test_admission_reason_reports_cooldown_without_a_code(self):
		a = self.make_gateway("A")
		gw = self.gw(a)
		ctx = {"sender_id": "15551230001", "conversation_id": "15551230001"}
		admitted, reason = gsvc._admission(gw, ctx)
		self.assertFalse(admitted)
		self.assertRegex(reason, r"Pairing code: \*+[A-Z0-9]{2}$")
		entry = frappe.db.get_value("Gateway Access Entry", {"gateway": a}, "name")
		frappe.db.set_value("Gateway Access Entry", entry, "expires_at", add_to_date(now_datetime(), minutes=-1))
		admitted, reason = gsvc._admission(gw, ctx)
		self.assertFalse(admitted)
		self.assertNotIn("PAIR-", reason)

	def test_revoked_sender_is_never_repaired_and_gets_no_reply(self):
		a = self.make_gateway("A")
		entry = self.make_entry(a, "15551230001", state="Approved")
		gsvc.revoke_gateway_access_entry(entry)
		for _i in range(3):
			result = self.ingest(a, "15551230001", "hello again")
			self.assertEqual(result["status"], "Rejected")
		self.assertEqual(frappe.db.count("Gateway Access Entry", {"gateway": a}), 1)
		self.assertEqual(self.entry_state(entry), "Revoked")
		self.adapter.send_reply.assert_not_called()
		self.enqueue.assert_not_called()

	def test_blocked_sender_is_never_repaired_and_gets_no_reply(self):
		a = self.make_gateway("A")
		entry = self.make_entry(a, "15551230001", state="Blocked")
		result = self.ingest(a, "+1 (555) 123-0001", "let me in")
		self.assertEqual(result["status"], "Rejected")
		self.assertIn("blocked", self.event_error(result)["error_message"].lower())
		self.assertEqual(frappe.db.count("Gateway Access Entry", {"gateway": a}), 1)
		self.assertEqual(self.entry_state(entry), "Blocked")
		self.adapter.send_reply.assert_not_called()

	def test_re_approved_sender_wins_over_old_revoked_row(self):
		a = self.make_gateway("A")
		self.make_entry(a, "15551230001", state="Revoked")
		self.make_entry(a, "15551230001", state="Approved")
		self.assertEqual(self.ingest(a, "15551230001", "hi")["status"], "Queued")

	def test_other_gateways_revocation_does_not_block(self):
		a = self.make_gateway("A")
		b = self.make_gateway("B")
		self.make_entry(a, "15551230001", state="Revoked")
		result = self.ingest(b, "15551230001", "hi")
		self.assertEqual(result["status"], "Rejected")
		self.assertRegex(self.event_error(result)["error_message"], r"Pairing code: \*+[A-Z0-9]{2}$")

	def test_process_time_recheck_rejects_sender_revoked_after_queueing(self):
		a = self.make_gateway("A", policy="Allow list")
		entry = self.make_entry(a, "15551230001", state="Approved")
		queued = self.ingest(a, "15551230001", "hi")
		self.assertEqual(queued["status"], "Queued")
		gsvc.revoke_gateway_access_entry(entry)
		run = MagicMock()
		with patch.dict("sys.modules", {"huf.ai.agent_integration": SimpleNamespace(run_agent_sync=run)}):
			result = gsvc.process_gateway_event(queued["event_name"])
		self.assertEqual(result["status"], "Rejected")
		run.assert_not_called()
		self.assertEqual(frappe.db.get_value("Gateway Event", queued["event_name"], "status"), "Rejected")

	def test_process_time_recheck_rejects_sender_who_opted_out_after_queueing(self):
		a = self.make_gateway("A", policy="Allow list")
		self.make_entry(a, "15551230001", state="Approved")
		queued = self.ingest(a, "15551230001", "hi")
		self.ingest(a, "15551230001", "STOP")
		run = MagicMock()
		with patch.dict("sys.modules", {"huf.ai.agent_integration": SimpleNamespace(run_agent_sync=run)}):
			result = gsvc.process_gateway_event(queued["event_name"])
		self.assertEqual(result["status"], "Rejected")
		run.assert_not_called()


class TestOptOut(_GatewayFixture, IntegrationTestCase):
	def test_stop_persists_opt_out_sends_one_confirmation_and_creates_no_run(self):
		a = self.make_gateway("A", policy="Allow list", opt_out_reply_text="Bye, unsubscribed.")
		entry = self.make_entry(a, "15551230001", state="Approved")
		result = self.ingest(a, "15551230001", "STOP")
		self.assertEqual(result["status"], "Rejected")
		self.enqueue.assert_not_called()
		self.assertEqual(self.entry_state(entry), "Opted out")
		self.assertEqual(self.sent_texts(), ["Bye, unsubscribed."])
		self.assertTrue(gsvc.is_opted_out(a, "15551230001"))
		self.assertTrue(gsvc.is_opted_out(self.gw(a), "+1 555 123 0001"))
		self.assertFalse(gsvc.is_opted_out(a, "15559999999"))

	def test_later_events_from_opted_out_sender_are_silently_rejected(self):
		a = self.make_gateway("A", policy="Allow list")
		self.make_entry(a, "15551230001", state="Approved")
		self.ingest(a, "15551230001", "stop")
		self.adapter.send_reply.reset_mock()
		for text in ("hello?", "STOP", "stop!"):
			result = self.ingest(a, "15551230001", text)
			self.assertEqual(result["status"], "Rejected")
		self.adapter.send_reply.assert_not_called()  # exactly one confirmation, ever
		self.enqueue.assert_not_called()

	def test_start_restores_previously_approved_sender(self):
		a = self.make_gateway("A", policy="Allow list")
		entry = self.make_entry(a, "15551230001", state="Approved")
		self.ingest(a, "15551230001", "STOP")
		self.adapter.send_reply.reset_mock()
		result = self.ingest(a, "15551230001", "START")
		self.assertEqual(result["status"], "Rejected")  # the START message itself runs nothing
		self.assertEqual(self.entry_state(entry), "Approved")
		self.assertFalse(gsvc.is_opted_out(a, "15551230001"))
		self.assertEqual(self.sent_texts(), [gsvc.DEFAULT_OPT_IN_REPLY])
		self.assertEqual(self.ingest(a, "15551230001", "hello")["status"], "Queued")

	def test_stranger_stop_and_start_create_no_state(self):
		# C-027: a sender that is not admitted gets no row and no reply from STOP/START.
		a = self.make_gateway("A")  # Pairing
		self.ingest(a, "15551230009", "UNSUBSCRIBE")
		self.assertFalse(gsvc.is_opted_out(a, "15551230009"))
		self.assertEqual(frappe.db.count("Gateway Access Entry", {"gateway": a}), 0)
		self.adapter.send_reply.assert_not_called()

	def test_keyword_must_be_the_whole_message(self):
		a = self.make_gateway("A", policy="Allow list")
		self.make_entry(a, "15551230001", state="Approved")
		for text in ("please stop sending jokes", "don't stop", "I want to cancel my order"):
			self.assertEqual(self.ingest(a, "15551230001", text)["status"], "Queued", text)
		self.assertFalse(gsvc.is_opted_out(a, "15551230001"))
		self.adapter.send_reply.assert_not_called()

	def test_punctuation_case_and_emoji_variants_opt_out(self):
		for i, text in enumerate(("Stop.", " QUIT!! ", "cancel 🛑", "End")):
			a = self.make_gateway(f"V{i}", policy="Allow list")
			self.make_entry(a, "15551230001", state="Approved")
			self.ingest(a, "15551230001", text)
			self.assertTrue(gsvc.is_opted_out(a, "15551230001"), text)

	def test_custom_keywords_are_honoured(self):
		a = self.make_gateway("A", policy="Allow list", opt_out_keywords="BASTA", opt_in_keywords="VOLVER")
		self.make_entry(a, "15551230001", state="Approved")
		self.assertEqual(self.ingest(a, "15551230001", "STOP")["status"], "Queued")
		self.ingest(a, "15551230001", "basta")
		self.assertTrue(gsvc.is_opted_out(a, "15551230001"))
		self.ingest(a, "15551230001", "volver")
		self.assertFalse(gsvc.is_opted_out(a, "15551230001"))

	def test_confirmation_is_not_blocked_by_the_outbound_gate_but_other_sends_are(self):
		a = self.make_gateway("A", policy="Allow list")
		self.make_entry(a, "15551230001", state="Approved")
		seen = []
		self.adapter.send_reply.side_effect = lambda reply: seen.append(gsvc.is_opted_out(a, "15551230001"))
		self.ingest(a, "15551230001", "STOP")
		self.assertEqual(seen, [False])  # inside the confirmation scope
		self.assertTrue(gsvc.is_opted_out(a, "15551230001"))  # and blocked again right after

	def test_blocked_sender_stop_is_silent_and_changes_nothing(self):
		a = self.make_gateway("A")
		entry = self.make_entry(a, "15551230001", state="Blocked")
		self.ingest(a, "15551230001", "STOP")
		self.assertEqual(self.entry_state(entry), "Blocked")
		self.adapter.send_reply.assert_not_called()

	def test_non_whatsapp_gateways_do_not_get_opt_out_handling(self):
		a = self.make_gateway("TG", provider="Telegram", policy="Allow list")
		self.make_entry(a, "42", state="Approved")
		self.assertEqual(self.ingest(a, "42", "STOP")["status"], "Queued")
		self.assertFalse(gsvc.is_opted_out(a, "42"))

	def test_keyword_overlap_between_lists_is_rejected_on_save(self):
		a = self.make_gateway("A", policy="Allow list")
		doc = frappe.get_doc("Gateway", a)
		doc.is_enabled = 0
		doc.opt_out_keywords = "STOP\nBACK"
		doc.opt_in_keywords = "back!\nSTART"
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)


class TestSenderLimitIngest(_GatewayFixture, IntegrationTestCase):
	def test_21st_message_in_ten_minutes_is_rejected_and_starts_no_run(self):
		a = self.make_gateway("A", policy="Allow list")
		self.make_entry(a, "15551230001", state="Approved")
		sender = "1555" + str(int(time.time()))[-7:]
		self.make_entry(a, sender, state="Approved")
		results = [self.ingest(a, sender, f"msg {i}") for i in range(21)]
		self.assertEqual([r["status"] for r in results[:20]], ["Queued"] * 20)
		self.assertEqual(results[20]["status"], "Rejected")
		self.assertTrue(self.event_error(results[20])["error_message"].startswith("sender_rate_limited"))
		self.assertEqual(self.enqueue.call_count, 20)
		self.adapter.send_reply.assert_not_called()  # silent by default

	def test_limit_zero_disables_it(self):
		a = self.make_gateway("A", policy="Allow list", inbound_sender_limit=0)
		sender = "1555" + str(int(time.time()) + 7)[-7:]
		self.make_entry(a, sender, state="Approved")
		self.assertTrue(all(self.ingest(a, sender, f"m{i}")["status"] == "Queued" for i in range(25)))


class TestStaleEntryCleanup(_GatewayFixture, IntegrationTestCase):
	def test_expired_pending_marked_and_old_expired_deleted(self):
		a = self.make_gateway("A")
		stale = self.make_entry(a, "111", code="PAIR-AAAAAAAA", expires_at=add_to_date(now_datetime(), minutes=-5))
		fresh = self.make_entry(a, "222", code="PAIR-BBBBBBBB", expires_at=add_to_date(now_datetime(), minutes=30))
		old_expired = self.make_entry(a, "333", state="Expired")
		frappe.db.set_value("Gateway Access Entry", old_expired, "modified", add_to_date(now_datetime(), days=-8), update_modified=False)
		approved = self.make_entry(a, "444", state="Approved")
		frappe.db.set_value("Gateway Access Entry", approved, "modified", add_to_date(now_datetime(), days=-30), update_modified=False)
		opted = self.make_entry(a, "555", state="Opted out")
		frappe.db.set_value("Gateway Access Entry", opted, "modified", add_to_date(now_datetime(), days=-30), update_modified=False)

		result = gsvc.cleanup_stale_access_entries()

		self.assertGreaterEqual(result["expired"], 1)
		self.assertGreaterEqual(result["deleted"], 1)
		self.assertEqual(self.entry_state(stale), "Expired")
		self.assertEqual(self.entry_state(fresh), "Pending")
		self.assertFalse(frappe.db.exists("Gateway Access Entry", old_expired))
		self.assertEqual(self.entry_state(approved), "Approved")
		self.assertEqual(self.entry_state(opted), "Opted out")

	def test_cleanup_is_registered_in_the_daily_scheduler(self):
		from huf import hooks

		self.assertIn("huf.ai.gateway_service.cleanup_stale_access_entries", hooks.scheduler_events["daily"])
