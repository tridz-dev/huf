"""BE-LMS: LMS adapter + WhatsApp LMS tools (frappe patched) and integration when the lms app is installed."""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.channels import adapters
from huf.ai.channels.adapters import lms
from huf.ai.tools import _registry
from huf.ai.channels import tools_lms

LMS_MISSING = {"success": False, "error": "lms_not_installed", "message": "LMS is not installed"}


def _conv(**overrides):
	data = {"name": "CC-1", "gateway": "gw-1", "contact_handle": "15550102030", "contact": None}
	data.update(overrides)
	return frappe._dict(data)


def _loads(raw):
	return json.loads(raw)


class TestLmsAdapterLogic(unittest.TestCase):
	def test_registered(self):
		self.assertEqual(adapters.ADAPTER_MODULES["lms"], "huf.ai.channels.adapters.lms")
		self.assertEqual(adapters.TARGET_APPS["lms"], "lms")
		self.assertEqual(lms.Adapter().name, "lms")
		self.assertFalse(lms.Adapter().on_human_reply(None, None))

	def test_normalize_phone(self):
		self.assertEqual(lms.normalize_phone("+1 (555) 010-2030"), "15550102030")
		self.assertEqual(lms.normalize_phone(None), "")

	def test_find_member_matches_digits_on_user(self):
		with patch.object(lms, "_contact_user", return_value=None), patch.object(lms, "_usable", return_value=True), patch.object(
			lms.frappe, "get_all", return_value=[{"name": "ana@example.com", "mobile_no": "+1 555 010 2030"}]
		):
			self.assertEqual(lms.find_member("15550102030"), "ana@example.com")

	def test_find_member_no_match_and_empty(self):
		with patch.object(lms, "_contact_user", return_value=None), patch.object(lms.frappe, "get_all", return_value=[]):
			self.assertIsNone(lms.find_member("15550102030"))
		self.assertIsNone(lms.find_member(""))

	def test_find_member_never_matches_guest_or_administrator(self):
		with patch.object(lms, "_contact_user", return_value="Administrator"), patch.object(lms.frappe, "get_all", return_value=[]):
			self.assertIsNone(lms.find_member("15550102030"))

	def test_lookup_customer_returns_user_doc_ref(self):
		with patch.object(lms, "find_member", return_value="ana@example.com"):
			self.assertEqual(lms.Adapter().lookup_customer("15550102030"), {"doctype": "User", "name": "ana@example.com"})
		with patch.object(lms, "find_member", return_value=None):
			self.assertIsNone(lms.Adapter().lookup_customer("15550102030"))


class TestLmsToolsNotInstalled(unittest.TestCase):
	def _run(self, fn, **kwargs):
		with patch.object(tools_lms.frappe, "get_installed_apps", return_value=["frappe", "huf"]):
			return _loads(fn(**kwargs))

	def test_every_tool_reports_lms_not_installed(self):
		for fn, kwargs in (
			(tools_lms.lms_list_courses, {}),
			(tools_lms.lms_enroll, {"course": "Python"}),
			(tools_lms.lms_my_progress, {}),
			(tools_lms.lms_send_certificate, {"course": "Python"}),
		):
			self.assertEqual(self._run(fn, **kwargs), LMS_MISSING, fn.__name__)

	def test_reminders_noop_when_not_installed(self):
		with patch.object(tools_lms.frappe, "get_installed_apps", return_value=["frappe"]), patch.object(
			tools_lms.frappe, "get_all"
		) as get_all:
			self.assertEqual(tools_lms.send_lesson_reminders(), 0)
			get_all.assert_not_called()


class TestLmsToolsLogic(unittest.TestCase):
	def setUp(self):
		for patcher in (
			patch.object(tools_lms.frappe, "get_installed_apps", return_value=["frappe", "lms"]),
			patch.object(tools_lms, "_schema_ready", return_value=True),
		):
			patcher.start()
			self.addCleanup(patcher.stop)

	def test_enroll_refuses_without_matching_user_and_never_creates_user(self):
		with patch.object(tools_lms, "_conversation", return_value=_conv()), patch.object(
			tools_lms, "_member_for_conversation", return_value=None
		), patch.object(tools_lms.frappe, "get_doc") as get_doc:
			res = _loads(tools_lms.lms_enroll(course="Python"))
		self.assertFalse(res["success"])
		self.assertEqual(res["error"], "member_not_found")
		get_doc.assert_not_called()

	def test_enroll_creates_enrollment_for_member_only(self):
		created = MagicMock()
		created.name = "ENR-1"
		with patch.object(tools_lms, "_conversation", return_value=_conv()), patch.object(
			tools_lms, "_member_for_conversation", return_value="ana@example.com"
		), patch.object(tools_lms, "_published_course", return_value="Python 101"), patch.object(
			tools_lms.frappe, "get_all", return_value=[]
		), patch.object(tools_lms.frappe, "get_doc", return_value=created) as get_doc:
			res = _loads(tools_lms.lms_enroll(course="Python 101"))
		self.assertTrue(res["success"])
		self.assertEqual(res["enrollment"], "ENR-1")
		values = get_doc.call_args.args[0]
		self.assertEqual(values["doctype"], "LMS Enrollment")
		self.assertEqual(values["course"], "Python 101")
		self.assertEqual(values["member"], "ana@example.com")
		self.assertNotIn("User", [c.args[0].get("doctype") for c in get_doc.call_args_list if c.args and isinstance(c.args[0], dict)])
		created.insert.assert_called_once()

	def test_enroll_unpublished_or_unknown_course_refused(self):
		with patch.object(tools_lms, "_conversation", return_value=_conv()), patch.object(
			tools_lms, "_member_for_conversation", return_value="ana@example.com"
		), patch.object(tools_lms, "_published_course", return_value=None), patch.object(tools_lms.frappe, "get_doc") as get_doc:
			res = _loads(tools_lms.lms_enroll(course="Secret draft"))
		self.assertEqual(res["error"], "course_not_found")
		get_doc.assert_not_called()

	def test_send_certificate_refuses_without_certificate(self):
		with patch.object(tools_lms, "_conversation", return_value=_conv()), patch.object(
			tools_lms, "_member_for_conversation", return_value="ana@example.com"
		), patch.object(tools_lms, "_published_course", return_value="Python 101"), patch.object(
			tools_lms, "_certificate_file", return_value=None
		), patch.object(tools_lms.frappe, "get_doc") as get_doc:
			res = _loads(tools_lms.lms_send_certificate(course="Python 101"))
		self.assertEqual(res["error"], "certificate_not_found")
		get_doc.assert_not_called()

	def test_send_certificate_goes_through_send_file_and_gates(self):
		resolved = {"row": {"name": "F-1"}, "filename": "cert.pdf", "mime": "application/pdf", "size": 10}
		prepared = {"content": b"%PDF", "mime": "application/pdf", "filename": "cert.pdf", "kind": "document", "voice": False}
		with patch.object(tools_lms, "_conversation", return_value=_conv()), patch.object(
			tools_lms, "_member_for_conversation", return_value="ana@example.com"
		), patch.object(tools_lms, "_published_course", return_value="Python 101"), patch.object(
			tools_lms, "_certificate_file", return_value={"name": "F-1"}
		), patch.object(tools_lms, "_certificate_resolved", return_value=resolved), patch.object(
			tools_lms.send_file, "prepare_upload", return_value=prepared
		) as prep, patch.object(tools_lms, "_free_form_refusal", return_value=None), patch.object(
			tools_lms, "_account_for_gateway", return_value="acct-1"
		), patch.object(tools_lms.bridge, "upload_media", return_value={"media_id": "M1"}) as up, patch.object(
			tools_lms.bridge, "send_media", return_value={"success": True}
		) as send:
			res = _loads(tools_lms.lms_send_certificate(course="Python 101"))
		self.assertTrue(res["success"])
		prep.assert_called_once_with(resolved, "document", False)
		up.assert_called_once()
		self.assertEqual(send.call_args.args[2], "document")
		self.assertEqual(send.call_args.kwargs["media_id"], "M1")

	def test_send_certificate_refused_by_send_gate(self):
		with patch.object(tools_lms, "_conversation", return_value=_conv()), patch.object(
			tools_lms, "_member_for_conversation", return_value="ana@example.com"
		), patch.object(tools_lms, "_published_course", return_value="Python 101"), patch.object(
			tools_lms, "_certificate_file", return_value={"name": "F-1"}
		), patch.object(tools_lms, "_certificate_resolved", return_value={"row": {}, "filename": "c.pdf", "mime": "application/pdf", "size": 1}), patch.object(
			tools_lms.send_file, "prepare_upload", return_value={"content": b"", "mime": "application/pdf", "filename": "c.pdf", "kind": "document", "voice": False}
		), patch.object(tools_lms, "_free_form_refusal", return_value=json.dumps({"success": False, "error": "opted_out"})), patch.object(
			tools_lms.bridge, "send_media"
		) as send:
			res = _loads(tools_lms.lms_send_certificate(course="Python 101"))
		self.assertEqual(res["error"], "opted_out")
		send.assert_not_called()

	def test_my_progress_lists_only_member_enrollments(self):
		rows = [{"course": "Python 101", "progress": 40}]
		with patch.object(tools_lms, "_conversation", return_value=_conv()), patch.object(
			tools_lms, "_member_for_conversation", return_value="ana@example.com"
		), patch.object(tools_lms.frappe, "get_all", return_value=rows) as get_all:
			res = _loads(tools_lms.lms_my_progress())
		self.assertTrue(res["success"])
		self.assertEqual(res["courses"], rows)
		self.assertEqual(get_all.call_args.kwargs["filters"], {"member": "ana@example.com"})

	def test_list_courses_published_only(self):
		rows = [{"name": "Python 101", "title": "Python 101"}]
		with patch.object(tools_lms.frappe, "get_all", return_value=rows) as get_all:
			res = _loads(tools_lms.lms_list_courses())
		self.assertEqual(res["courses"], rows)
		self.assertEqual(get_all.call_args.kwargs["filters"], {"published": 1})


class TestLessonReminders(unittest.TestCase):
	def setUp(self):
		for patcher in (patch.object(tools_lms, "_schema_ready", return_value=True),):
			patcher.start()
			self.addCleanup(patcher.stop)
		self.cache = {}

	def _cache_get(self, key):
		return self.cache.get(key)

	def _cache_set(self, key, value, *a, **kw):
		self.cache[key] = value

	def test_stale_enrollment_gets_one_reminder_per_three_days(self):
		stale = [{"name": "ENR-1", "member": "ana@example.com", "course": "Python 101", "creation": "2026-10-01 00:00:00", "last": None}]
		sent = []
		with patch.object(tools_lms, "_stale_enrollments", return_value=stale), patch.object(
			tools_lms, "_reminder_target", return_value=("gw-1", "15550102030")
		), patch.object(tools_lms, "_gateway_template", return_value="lesson_reminder"), patch.object(
			tools_lms, "_send_template", side_effect=lambda *a, **k: sent.append(a) or {"success": True}
		), patch.object(
			tools_lms, "_cache_get", side_effect=self._cache_get
		), patch.object(tools_lms, "_cache_set", side_effect=self._cache_set):
			self.assertEqual(tools_lms.send_lesson_reminders(), 1)
			self.assertEqual(tools_lms.send_lesson_reminders(), 0)
		self.assertEqual(len(sent), 1)

	def test_no_template_configured_skips(self):
		stale = [{"name": "ENR-1", "member": "ana@example.com", "course": "Python 101", "creation": "2026-10-01 00:00:00", "last": None}]
		with patch.object(tools_lms, "_stale_enrollments", return_value=stale), patch.object(
			tools_lms, "_reminder_target", return_value=("gw-1", "15550102030")
		), patch.object(tools_lms, "_gateway_template", return_value=""), patch.object(tools_lms, "_send_template") as send:
			self.assertEqual(tools_lms.send_lesson_reminders(), 0)
		send.assert_not_called()

	def test_refused_send_is_not_counted_and_not_cached(self):
		stale = [{"name": "ENR-1", "member": "ana@example.com", "course": "Python 101", "creation": "2026-10-01 00:00:00", "last": None}]
		with patch.object(tools_lms, "_stale_enrollments", return_value=stale), patch.object(
			tools_lms, "_reminder_target", return_value=("gw-1", "15550102030")
		), patch.object(tools_lms, "_gateway_template", return_value="lesson_reminder"), patch.object(
			tools_lms, "_send_template", return_value={"success": False, "error": "opted_out"}
		), patch.object(
			tools_lms, "_cache_get", side_effect=self._cache_get
		), patch.object(tools_lms, "_cache_set", side_effect=self._cache_set):
			self.assertEqual(tools_lms.send_lesson_reminders(), 0)
		self.assertEqual(self.cache, {})


class TestLmsToolRegistry(unittest.TestCase):
	def test_tools_registered_with_function_paths(self):
		names = {t["tool_name"]: t["function_path"] for t in _registry.LMS_TOOLS}
		self.assertEqual(
			names,
			{
				"lms_list_courses": "huf.ai.channels.tools_lms.lms_list_courses",
				"lms_enroll": "huf.ai.channels.tools_lms.lms_enroll",
				"lms_my_progress": "huf.ai.channels.tools_lms.lms_my_progress",
				"lms_send_certificate": "huf.ai.channels.tools_lms.lms_send_certificate",
			},
		)
		self.assertIn("lms_enroll", {t["tool_name"] for t in _registry.ALL_INTEGRATION_TOOLS})


@unittest.skipUnless("lms" in frappe.get_installed_apps(), "LMS app not installed on this site")
class TestLmsIntegration(IntegrationTestCase):
	def test_list_courses_runs_against_real_lms(self):
		res = _loads(tools_lms.lms_list_courses())
		self.assertTrue(res["success"])
		self.assertIsInstance(res["courses"], list)
