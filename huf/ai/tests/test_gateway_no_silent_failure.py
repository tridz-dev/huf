"""WP-4b: a sender is never left with silence when processing fails (C-010, B-001)."""

import unittest
from types import SimpleNamespace
from unittest import mock
from unittest.mock import MagicMock, patch

from huf.ai import gateway_service as gs


def setUpModule():
	# No site in unit runs: whitelisted wrappers consult frappe.local.flags.
	import frappe

	if not getattr(frappe.local, "flags", None):
		frappe.local.flags = frappe._dict()


def _gw(**kw):
	values = dict(
		name="GW",
		provider="WhatsApp",
		error_reply_text="",
		integration_settings="",
		fallback_template_language="en_US",
	)
	values.update(kw)
	return SimpleNamespace(**values)


def _event(**kw):
	values = dict(
		name="GEV-1",
		sender_id="1555",
		conversation_id="1555",
		reply_message_id="",
		raw_payload={"message": {"type": "text"}},
	)
	values.update(kw)
	ev = MagicMock()
	for k, v in values.items():
		setattr(ev, k, v)
	return ev


class TestFallbackText(unittest.TestCase):
	def test_english_default(self):
		text = gs._default_fallback_text(_gw(fallback_template_language=""), _event(), "error")
		self.assertIn("Sorry", text)
		self.assertNotIn("Traceback", text)

	def test_contact_language_beats_gateway_default(self):
		ev = _event(raw_payload={"message": {"type": "text"}, "language": "es"})
		text = gs._default_fallback_text(_gw(fallback_template_language="fr_FR"), ev, "error")
		self.assertEqual(text, gs._FALLBACK_TEXTS["es"]["error"])

	def test_gateway_default_language_used(self):
		text = gs._default_fallback_text(_gw(fallback_template_language="fr_FR"), _event(), "error")
		self.assertEqual(text, gs._FALLBACK_TEXTS["fr"]["error"])

	def test_unknown_language_falls_back_to_english(self):
		ev = _event(raw_payload={"language": "xx"})
		text = gs._default_fallback_text(_gw(fallback_template_language="zz"), ev, "attachment")
		self.assertEqual(text, gs._FALLBACK_TEXTS["en"]["attachment"])

	def test_configured_text_wins_for_error_kind(self):
		text = gs._default_fallback_text(_gw(error_reply_text="Custom"), _event(), "error")
		self.assertEqual(text, "Custom")


class TestSendFallback(unittest.TestCase):
	def _send(self, event=None, gateway=None, opted_out=False, first=True):
		cache = MagicMock()
		cache.set.return_value = first
		with (
			patch.object(gs.frappe, "cache", return_value=cache),
			patch.object(gs, "is_opted_out", return_value=opted_out),
			patch("huf.ai.gateway_webhook.send_gateway_reply", return_value=SimpleNamespace(provider_message_id="w1")) as send,
			patch.object(gs, "_record_reply_sent"),
		):
			ok = gs._send_fallback_once(event or _event(), gateway or _gw(), "error")
		return ok, send

	def test_sends_through_reply_pipeline(self):
		ok, send = self._send()
		self.assertTrue(ok)
		send.assert_called_once()

	def test_opt_out_respected(self):
		ok, send = self._send(opted_out=True)
		self.assertFalse(ok)
		send.assert_not_called()

	def test_never_twice_for_same_event(self):
		ok, send = self._send(first=False)
		self.assertFalse(ok)
		send.assert_not_called()

	def test_never_raises(self):
		with patch("huf.ai.gateway_webhook.send_gateway_reply", side_effect=RuntimeError("x")), patch.object(
			gs, "is_opted_out", return_value=False
		), patch.object(gs.frappe, "cache", return_value=MagicMock(set=MagicMock(return_value=True))):
			self.assertFalse(gs._send_fallback_once(_event(), _gw(), "error"))


class TestPaths(unittest.TestCase):
	def test_agent_run_failure_sends_default_fallback(self):
		with patch.object(gs, "_send_fallback_once", return_value=True) as fb, patch.object(gs.frappe, "log_error"):
			out = gs._fail_event_for_agent_run(_event(), _gw(), {"success": False}, "agent_run_failed", "boom")
		fb.assert_called_once()
		self.assertTrue(out["fallback_sent"])

	def test_busy_exhausted_sends_fallback(self):
		event = _event()
		with (
			patch.object(gs.frappe, "cache", MagicMock(get_value=MagicMock(return_value=gs._REQUEUE_MAX)), create=True),
			patch.object(gs.frappe, "db", MagicMock(), create=True),
			patch.object(gs, "_commit_unless_testing"),
			patch.object(gs, "_send_fallback_once") as fb,
			patch.object(gs.frappe, "get_doc", return_value=_gw()),
		):
			out = gs._requeue_busy_event(event, "busy")
		self.assertEqual(out["status"], "Failed")
		fb.assert_called_once()

	def test_exception_path_sends_fallback_and_reraises(self):
		event = _event(status="Queued", gateway="GW", target_type="Agent", target_agent="A", message_text="hi", thread_id="")
		gw = _gw(is_enabled=1, execution_user="bot")
		docs = {"Gateway Event": event, "Gateway": gw, "Agent": MagicMock(owner="bot")}
		with (
			patch.object(gs.frappe, "get_doc", side_effect=lambda dt, *a, **k: docs[dt]),
			patch.object(gs, "_process_time_block_reason", return_value=""),
			patch.object(gs, "_is_reaction_event", return_value=False),
			patch("huf.ai.agent_access.resolve_run_identity_and_authorize", return_value=SimpleNamespace(authorized=True)),
			patch.object(gs.frappe, "set_user"),
			patch.object(gs, "_describe_attachments", return_value=""),
			patch.object(gs, "_save_event_media", return_value=[]),
			patch.object(gs, "_maybe_mark_read_typing", side_effect=RuntimeError("kaboom")),
			patch.object(gs.frappe, "db", MagicMock(), create=True),
			patch.object(gs.frappe, "log_error"),
			patch.object(gs, "_send_fallback_once") as fb,
		):
			with self.assertRaises(RuntimeError):
				gs._process_gateway_event("GEV-1")
		fb.assert_called_once()


class TestAttachmentUnavailable(unittest.TestCase):
	def test_media_id_detected(self):
		ev = _event(raw_payload={"message": {"type": "image", "image": {"id": "m1"}}})
		self.assertEqual(gs._inbound_media_type(ev), "image")
		self.assertIsNone(gs._inbound_media_type(_event()))

	def test_prompt_note_text(self):
		self.assertIn("attachment unavailable", gs.ATTACHMENT_UNAVAILABLE_NOTE.lower())


class TestBusyArithmetic(unittest.TestCase):
	def test_lock_wait_plus_backoff_below_job_timeout(self):
		worst_backoff = sum(
			min(gs._BUSY_BASE_DELAY * (2 ** (a - 1)), gs._BUSY_MAX_DELAY) * 1.25
			for a in range(1, gs._BUSY_ATTEMPTS)
		)
		self.assertLess(gs._CONVERSATION_LOCK_WAIT + worst_backoff, gs._PROCESS_JOB_TIMEOUT)
		self.assertGreaterEqual(gs._CONVERSATION_LOCK_TTL, gs._PROCESS_JOB_TIMEOUT)

	def test_requeue_cap_covers_long_run(self):
		# A second message must survive a 30-minute run before being failed.
		self.assertGreaterEqual(gs._REQUEUE_MAX * gs._CONVERSATION_LOCK_WAIT, 30 * 60)
		self.assertGreaterEqual(gs._REQUEUE_TTL, gs._REQUEUE_MAX * (gs._CONVERSATION_LOCK_WAIT + 10))


class TestEmptyReplyAfterToolDelivery(unittest.TestCase):
	def test_empty_text_after_delivering_tool_is_not_a_failure(self):
		self.assertIsNone(gs._agent_run_failure({"success": True, "response": "", "tool_calls_made": 1, "delivered_reply": True}))

	def test_empty_text_after_read_only_tool_is_a_failure(self):
		self.assertIsNotNone(gs._agent_run_failure({"success": True, "response": "", "tool_calls_made": 2}))
		self.assertIsNotNone(gs._agent_run_failure(
			{"success": True, "response": "", "tool_calls_made": 2, "delivered_reply": False}))

	def test_empty_text_without_tool_calls_is_still_a_failure(self):
		self.assertIsNotNone(gs._agent_run_failure({"success": True, "response": "", "tool_calls_made": 0}))
		self.assertIsNotNone(gs._agent_run_failure({"success": True, "response": "  "}))


class TestRunDeliveryFlag(unittest.TestCase):
	def test_flag_roundtrip_and_isolation(self):
		from huf.ai import run_delivery as rd

		store = {}
		cache = mock.Mock(set_value=lambda k, v, expires_in_sec=None: store.__setitem__(k, v),
			get_value=lambda k: store.get(k))
		with mock.patch.object(rd.frappe, "cache", return_value=cache):
			self.assertFalse(rd.delivered("RUN-1"))
			rd.mark("RUN-1")
			self.assertTrue(rd.delivered("RUN-1"))
			self.assertFalse(rd.delivered("RUN-2"))
			self.assertFalse(rd.delivered(""))
