"""Unit tests for the optional frappe_whatsapp bridge (mock-based)."""

import json
import sys
import unittest
from datetime import datetime, timedelta
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe

from huf.ai.gateway_adapters import whatsapp_bridge as wb

NOW = datetime(2026, 1, 10, 12, 0, 0)
ACCT = {
	"name": "ACC",
	"phone_id": "111",
	"business_id": "BIZ",
	"app_id": "APP",
	"token": "tok",
	"url": "https://graph.facebook.com",
	"version": "v25.0",
	"webhook_verify_token": "v",
	"status": "Active",
}


class FakeResp:
	def __init__(self, json_data=None, content=b""):
		self._j = json_data or {}
		self.content = content

	def raise_for_status(self):
		pass

	def json(self):
		return self._j

	def iter_content(self, chunk_size=1):
		for i in range(0, len(self.content), 2):
			yield self.content[i : i + 2]

	def close(self):
		pass


class FakeDoc(SimpleNamespace):
	def get(self, key, default=None):
		return getattr(self, key, default)

	def get_password(self, field):
		return "secret"

	def insert(self, **kwargs):
		self.insert_kwargs = kwargs
		self.name = "WAM-1"
		self.message_id = "wamid.X"
		self.status = "Success"
		return self


def avail(value=True):
	return patch.object(wb, "is_available", return_value=value)


class TestBridge(unittest.TestCase):
	def test_constants_and_import_without_app(self):
		self.assertEqual(wb.GRAPH_DEFAULT_VERSION, "v25.0")
		# The bench may load frappe_whatsapp itself; the bridge must never import it at module level.
		import ast, inspect

		tree = ast.parse(inspect.getsource(wb))
		top_level = [
			(getattr(n, "module", None) or "") + "|" + ",".join(a.name for a in n.names)
			for n in tree.body
			if isinstance(n, (ast.Import, ast.ImportFrom))
		]
		self.assertFalse([i for i in top_level if "frappe_whatsapp" in i])

	def test_is_available(self):
		with patch.object(frappe.db, "exists", side_effect=[True, True, True]):
			self.assertTrue(wb.is_available())
		with patch.object(frappe.db, "exists", side_effect=[True, False, True]):
			self.assertFalse(wb.is_available())

	def test_normalize_phone_table(self):
		for raw, want in [
			("+1 (415) 555-2671", "14155552671"),
			("0044 20 7946 0958", "442079460958"),
			("91-98765 43210", "919876543210"),
			("", ""),
			(None, ""),
			("abc", ""),
			(14155552671, "14155552671"),
		]:
			self.assertEqual(wb.normalize_phone(raw), want)

	def test_resolve_account(self):
		doc = FakeDoc(name="ACC", phone_id="111", business_id="B", app_id="A", url="", version="", webhook_verify_token="v", status="Active")
		with avail(), patch.object(frappe.db, "get_value", return_value="ACC"), patch.object(
			frappe.db, "exists", return_value=True
		), patch.object(frappe, "get_doc", return_value=doc):
			acct = wb.resolve_account("ACC")
			default = wb.resolve_default_account()
		self.assertEqual(acct["token"], "secret")
		self.assertEqual(acct["version"], "v25.0")
		self.assertEqual(acct["url"], "https://graph.facebook.com")
		self.assertEqual(default["name"], "ACC")  # non-gateway tools only

	def test_resolve_account_has_no_default_fallback(self):
		"""Gateway/webhook/management paths never guess an account: an empty name is no_account."""
		with avail(), patch.object(frappe.db, "get_value", return_value="ACC") as gv, patch.object(
			frappe.db, "exists", return_value=True
		):
			self.assertEqual(wb.resolve_account(), {"error": "no_account"})
			self.assertEqual(wb.resolve_account(None), {"error": "no_account"})
			self.assertEqual(wb.resolve_account(""), {"error": "no_account"})
		gv.assert_not_called()

	def test_resolve_account_none_and_unavailable(self):
		with avail(), patch.object(frappe.db, "get_value", return_value=None):
			self.assertEqual(wb.resolve_account(), {"error": "no_account"})
		with avail(False):
			self.assertIsNone(wb.resolve_account())

	def test_account_matches_phone_id(self):
		with avail(), patch.object(frappe.db, "get_value", return_value="111"):
			self.assertTrue(wb.account_matches_phone_id("ACC", "111"))
			self.assertFalse(wb.account_matches_phone_id("ACC", "222"))
			self.assertFalse(wb.account_matches_phone_id("ACC", ""))
		with avail(False):
			self.assertFalse(wb.account_matches_phone_id("ACC", "111"))

	def _window(self, rows):
		with patch.object(frappe, "get_all", return_value=rows) as ga:
			res = wb.window_state("GW", "+1 415", now=NOW)
		return res, ga

	def test_window_boundaries(self):
		res, ga = self._window([{"received_at": NOW - timedelta(hours=23, minutes=59), "verified_sender": 1}])
		self.assertTrue(res["open"])
		self.assertEqual(ga.call_args.args[0], "Gateway Event")
		self.assertEqual(ga.call_args.kwargs["filters"]["sender_id"], "1415")
		res, _ = self._window([{"received_at": NOW - timedelta(hours=24, minutes=1), "verified_sender": 1}])
		self.assertFalse(res["open"])
		res, _ = self._window([{"received_at": NOW - timedelta(hours=1), "verified_sender": 0}])
		self.assertFalse(res["open"])
		self.assertIsNone(res["last_inbound_at"])
		res, _ = self._window([])
		self.assertFalse(res["open"])

	def _event_row(self, received_at, ts_epoch=None, verified=1):
		payload = {"message": {"id": "w", "timestamp": str(ts_epoch)}} if ts_epoch is not None else {}
		return {"received_at": received_at, "verified_sender": verified, "raw_payload": payload}

	def _epoch(self, naive_local, tz="Asia/Kolkata"):
		from zoneinfo import ZoneInfo

		return int(naive_local.replace(tzinfo=ZoneInfo(tz)).timestamp())

	def test_redelivered_old_message_does_not_open_window(self):
		# Meta redelivers a 30h-old message just now: received_at is fresh, the message is not.
		old = self._epoch(NOW - timedelta(hours=30))
		with patch("frappe.utils.data.get_system_timezone", return_value="Asia/Kolkata"):
			res, _ = self._window([self._event_row(NOW - timedelta(minutes=1), old)])
		self.assertFalse(res["open"])

	def test_fresh_message_opens_window_anchored_on_message_time(self):
		sent = NOW - timedelta(hours=23, minutes=30)  # received_at is later (delayed delivery)
		with patch("frappe.utils.data.get_system_timezone", return_value="Asia/Kolkata"):
			res, _ = self._window([self._event_row(NOW - timedelta(minutes=5), self._epoch(sent))])
		self.assertTrue(res["open"])
		self.assertEqual(res["last_inbound_at"], sent)
		self.assertEqual(res["expires_at"], sent + timedelta(hours=24))

	def test_window_timezone_boundary(self):
		# Same instant, different system zones: the naive conversion must follow the zone.
		sent_utc_naive = datetime(2026, 1, 9, 12, 30)  # 23.5h before NOW if NOW is also UTC
		epoch = int(sent_utc_naive.replace(tzinfo=__import__("datetime").timezone.utc).timestamp())
		with patch("frappe.utils.data.get_system_timezone", return_value="UTC"):
			res, _ = self._window([self._event_row(NOW, epoch)])
			self.assertTrue(res["open"])  # 23.5h old
			res, _ = self._window([self._event_row(NOW, epoch - 3600)])
			self.assertFalse(res["open"])  # 24.5h old
		# NOW is naive in Kolkata (UTC+5:30): the same epoch is 5.5h further back in that zone's wall clock.
		with patch("frappe.utils.data.get_system_timezone", return_value="Asia/Kolkata"):
			self.assertEqual(wb.message_time({"message": {"timestamp": str(epoch)}}), sent_utc_naive + timedelta(hours=5, minutes=30))

	def test_window_falls_back_to_received_at_without_timestamp(self):
		for payload in ({}, {"message": {"timestamp": "garbage"}}, "not json"):
			row = {"received_at": NOW - timedelta(hours=1), "verified_sender": 1, "raw_payload": payload}
			res, _ = self._window([row])
			self.assertTrue(res["open"])
			self.assertEqual(res["last_inbound_at"], NOW - timedelta(hours=1))

	def test_message_timestamp_never_extends_beyond_received_at(self):
		future = self._epoch(NOW + timedelta(hours=5))
		with patch("frappe.utils.data.get_system_timezone", return_value="Asia/Kolkata"):
			res, _ = self._window([self._event_row(NOW - timedelta(hours=23), future)])
		self.assertEqual(res["last_inbound_at"], NOW - timedelta(hours=23))

	def test_window_uses_newest_effective_anchor(self):
		old = self._epoch(NOW - timedelta(hours=40))
		fresh = self._epoch(NOW - timedelta(hours=2))
		with patch("frappe.utils.data.get_system_timezone", return_value="Asia/Kolkata"):
			res, _ = self._window(
				[self._event_row(NOW - timedelta(minutes=1), old), self._event_row(NOW - timedelta(minutes=3), fresh)]
			)
		self.assertTrue(res["open"])

	def test_record_incoming_idempotent(self):
		msg = {"id": "wamid.1", "from": "+1 415", "type": "text", "text": {"body": "hi"}}
		with avail(False):
			self.assertIsNone(wb.record_incoming("ACC", msg))
		with avail(), patch.object(frappe.db, "get_value", return_value="WAM-9"), patch.object(frappe, "get_doc") as gd:
			self.assertEqual(wb.record_incoming("ACC", msg), "WAM-9")
			gd.assert_not_called()
		doc = MagicMock()
		doc.name = "WAM-2"
		with avail(), patch.object(frappe.db, "get_value", return_value=None), patch.object(frappe, "get_doc", return_value=doc) as gd:
			self.assertEqual(wb.record_incoming("ACC", msg, "Bob"), "WAM-2")
			values = gd.call_args.args[0]
			self.assertEqual(values["type"], "Incoming")
			self.assertEqual(values["from"], "1415")
			self.assertEqual(values["message"], "hi")

	def test_send_text(self):
		doc = FakeDoc()
		with avail(), patch.object(wb, "resolve_account", return_value=ACCT), patch.object(frappe, "get_doc", return_value=doc) as gd:
			res = wb.send_text("ACC", "+1 415", "yo", reply_to="w1")
		self.assertEqual(res["message_id"], "wamid.X")
		self.assertEqual(doc.insert_kwargs, {"ignore_permissions": False})
		self.assertEqual(gd.call_args.args[0]["reply_to_message_id"], "w1")
		doc2 = FakeDoc()
		with avail(), patch.object(wb, "resolve_account", return_value=ACCT), patch.object(frappe, "get_doc", return_value=doc2):
			wb.send_text("ACC", "1", "x", trusted=True)
		self.assertEqual(doc2.insert_kwargs, {"ignore_permissions": True})

	def test_send_text_errors(self):
		with avail(False):
			with self.assertRaises(wb.BridgeError) as cm:
				wb.send_text("ACC", "1", "x")
			self.assertEqual(cm.exception.payload["error"], "bridge_unavailable")
		with avail(), patch.object(wb, "resolve_account", return_value={"error": "no_account"}):
			with self.assertRaises(wb.BridgeError) as cm:
				wb.send_text("ACC", "1", "x")
			self.assertEqual(cm.exception.payload["error"], "no_account")
		bad = FakeDoc()
		bad.insert = MagicMock(side_effect=RuntimeError("boom"))
		with avail(), patch.object(wb, "resolve_account", return_value=ACCT), patch.object(frappe, "get_doc", return_value=bad):
			with self.assertRaises(wb.BridgeError) as cm:
				wb.send_text("ACC", "1", "x")
			self.assertEqual(cm.exception.payload["error"], "send_failed")

	def test_send_template(self):
		doc = FakeDoc()
		with avail(), patch.object(wb, "resolve_account", return_value=ACCT), patch.object(frappe, "get_doc", return_value=doc) as gd, patch.object(
			wb, "_template_docname", return_value="hello_tpl-en_US"
		), patch.object(frappe.db, "commit") as commit:
			wb.send_template("ACC", "+1 415", "hello_tpl", ["a", "b"])
		v = gd.call_args.args[0]
		self.assertEqual(v["use_template"], 1)
		self.assertEqual(v["template"], "hello_tpl-en_US")
		self.assertEqual(v["template_parameters"], "a,b")
		self.assertEqual(doc.insert_kwargs, {"ignore_permissions": False})
		commit.assert_not_called()  # user-initiated path never commits

	def test_send_template_with_header_param_posts_to_graph_and_mirrors_without_resend(self):
		doc = FakeDoc()
		with avail(), patch.object(wb, "resolve_account", return_value=ACCT), patch.object(
			frappe, "get_doc", return_value=doc
		) as gd, patch.object(wb, "_template_docname", return_value="hello_tpl-en_US"), patch.object(
			wb, "_graph_post_message", return_value="wamid.G1"
		) as post, patch.object(frappe, "has_permission", return_value=True):
			res = wb.send_template("ACC", "+1 415", "hello_tpl", ["a", "b"], ["h"])
		self.assertEqual(res["message_id"], "wamid.G1")
		components = post.call_args.args[1]["template"]["components"]
		self.assertEqual(components[0], {"type": "header", "parameters": [{"type": "text", "text": "h"}]})
		v = gd.call_args.args[0]
		self.assertEqual(v["message_id"], "wamid.G1")  # preset message_id: frappe_whatsapp will not send again
		self.assertEqual(v["template_header_parameters"], "h")

	def test_trusted_sends_commit_right_after_insert(self):
		for send in (
			lambda: wb.send_text("ACC", "1", "x", trusted=True),
			lambda: wb.send_template("ACC", "1", "t", [], trusted=True),
		):
			doc = FakeDoc()
			order = []
			doc.insert = lambda **kw: order.append("insert") or FakeDoc.insert(doc, **kw)
			with avail(), patch.object(wb, "resolve_account", return_value=ACCT), patch.object(
				frappe, "get_doc", return_value=doc
			), patch.object(wb, "_template_docname", return_value="t"), patch.object(
				frappe.db, "commit", side_effect=lambda: order.append("commit")
			):
				send()
			self.assertEqual(order, ["insert", "commit"])

	def test_docname_accepts_record_name_and_requires_language_when_ambiguous(self):
		def get_value(dt, filters, field=None, *a, **k):
			if isinstance(filters, dict) and filters.get("name") == "wash-en" and filters.get("whatsapp_account") == "ACC":
				return "wash-en"
			if isinstance(filters, dict) and filters.get("actual_name") == "wash" and "language_code" not in filters:
				return "wash-en"
			return None

		rows = [{"name": "wash-en", "language_code": "en"}, {"name": "wash-hi", "language_code": "hi"}]
		with patch.object(frappe.db, "get_value", side_effect=get_value), patch.object(
			frappe, "get_all", return_value=rows
		):
			self.assertEqual(wb._template_docname("ACC", "wash-en"), "wash-en")
			with self.assertRaises(wb.BridgeError) as ctx:
				wb._template_docname("ACC", "wash")
			self.assertEqual(ctx.exception.payload["error"], "language_required")
			self.assertEqual(ctx.exception.payload["languages"], ["en", "hi"])
		with patch.object(frappe.db, "get_value", side_effect=get_value), patch.object(
			frappe, "get_all", return_value=rows[:1]
		):
			self.assertEqual(wb._template_docname("ACC", "wash"), "wash-en")

	def test_template_language_and_docname_by_language(self):
		def get_value(dt, filters, field=None, *a, **k):
			if isinstance(filters, dict) and filters.get("language_code") == "hi":
				return "reopen-hi" if field == "name" else "hi"
			if isinstance(filters, dict) and filters.get("actual_name") == "reopen":
				return "reopen-en_US" if field == "name" else "en_US"
			return None

		with avail(), patch.object(frappe.db, "exists", return_value=False), patch.object(
			frappe.db, "get_value", side_effect=get_value
		):
			self.assertEqual(wb.template_language("ACC", "reopen", "hi"), "hi")
			self.assertEqual(wb.template_language("ACC", "reopen"), "en_US")
			self.assertEqual(wb._template_docname("ACC", "reopen", "hi"), "reopen-hi")
			self.assertIsNone(wb.template_language("ACC", "nope"))
		with avail(False):
			self.assertIsNone(wb.template_language("ACC", "reopen"))

	def test_authentication_category_is_not_supported(self):
		self.assertEqual(wb.TEMPLATE_CATEGORIES, ("MARKETING", "UTILITY"))
		with avail(), patch.object(frappe, "has_permission", return_value=True):
			res = wb.create_template("ACC", {"template_name": "otp", "category": "AUTHENTICATION", "language_code": "en"})
		self.assertEqual(res["error"], "invalid_category")

	def test_list_templates(self):
		with avail(False):
			self.assertEqual(wb.list_templates(), [])
		with avail(), patch.object(wb, "_attach_state"), patch.object(wb, "_get_extra", return_value=None), patch.object(frappe, "get_list", return_value=[{"name": "t"}]) as gl:
			self.assertEqual(wb.list_templates("ACC", "APPROVED"), [{"name": "t", "header_format": ""}])
			self.assertEqual(gl.call_args.kwargs["filters"], {"whatsapp_account": "ACC", "status": "APPROVED"})

	def test_create_template(self):
		good = {"template_name": "promo_1", "category": "marketing", "language_code": "en_US", "template": "Hi {{1}}, welcome", "sample_values": "Ann"}
		with avail(False):
			self.assertEqual(wb.create_template("ACC", good)["error"], "bridge_unavailable")
		with avail(), patch.object(frappe, "has_permission", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				wb.create_template("ACC", good)
		with avail(), patch.object(frappe, "has_permission", return_value=True), patch.object(
			wb, "_docname_taken_by_other_account", return_value=None
		):
			self.assertEqual(wb.create_template("ACC", {**good, "template_name": "Bad Name"})["error"], "invalid_name")
			self.assertEqual(wb.create_template("ACC", {**good, "category": "X"})["error"], "invalid_category")
			too_long = wb.create_template("ACC", {**good, "template_name": "a" * 513})
			self.assertEqual(too_long["error"], "validation_failed")
			self.assertEqual(too_long["errors"][0]["code"], "too_long")
			self.assertEqual(wb.create_template("ACC", {**good, "language_code": ""})["error"], "invalid_language")
		calls = []

		def post(url, **kw):
			calls.append((url, kw))
			return SimpleNamespace(status_code=200, json=lambda: {"id": "900", "status": "PENDING", "category": "MARKETING"})

		with self._direct_create() as m:
			for tname in ("a" * 128, "promo_1"):
				res = wb.create_template("ACC", {**good, "template_name": tname}, http_post=post)
				self.assertTrue(res["success"], res)
				self.assertEqual(res["id"], "900")
			url, kw = calls[-1]
			self.assertEqual(url, "https://graph.facebook.com/v25.0/BIZ/message_templates")
			self.assertEqual(kw["json"]["category"], "MARKETING")
			self.assertEqual(kw["json"]["parameter_format"], "POSITIONAL")
			self.assertEqual(kw["json"]["components"][0], {"type": "BODY", "text": "Hi {{1}}, welcome", "example": {"body_text": [["Ann"]]}})
			self.assertEqual(m["insert"].call_count, 2)

	def _direct_create(self):
		import contextlib

		@contextlib.contextmanager
		def ctx():
			def new_doc(dt):
				doc = FakeDoc(flags=SimpleNamespace(), buttons=[])
				doc.update = lambda d: doc.__dict__.update(d)
				doc.set = lambda k, v: setattr(doc, k, v)
				doc.append = lambda k, v: doc.buttons.append(v)
				return doc

			with avail(), patch.object(frappe, "has_permission", return_value=True), patch.object(
				wb, "_docname_taken_by_other_account", return_value=None
			), patch.object(frappe.db, "exists", side_effect=lambda dt, *a, **k: dt == "Language"), patch.object(
				wb, "resolve_account", return_value=ACCT
			), patch.object(frappe, "new_doc", side_effect=new_doc), patch.object(
				wb, "_insert_mirror_row"
			) as insert, patch.object(wb, "_guard"), patch.object(wb, "record_template_state"):
				yield {"insert": insert}

		return ctx()

	def test_create_template_refuses_a_docname_owned_by_another_account(self):
		"""frappe_whatsapp names templates <name>-<language> site-wide: never overwrite another account's."""
		good = {"template_name": "promo_3", "category": "utility", "language_code": "en_US", "template": "Hi {{1}} there", "sample_values": "Ann"}
		with avail(), patch.object(frappe, "has_permission", return_value=True), patch.object(
			frappe.db, "exists", return_value=True
		), patch.object(frappe.db, "get_value", return_value="OTHER"), patch.object(frappe, "get_doc") as gd:
			res = wb.create_template("ACC", good)
		self.assertEqual(res["error"], "template_name_taken_by_other_account")
		gd.assert_not_called()

	def test_create_template_meta_rejection_writes_no_local_row(self):
		good = {"template_name": "promo_2", "category": "utility", "language_code": "en_US", "template": "Hi {{1}} there", "sample_values": "Ann"}

		def post(url, **kw):
			return SimpleNamespace(
				status_code=400, text="",
				json=lambda: {"error": {"code": 100, "message": "Invalid parameter access_token=SECRET123", "error_data": {"details": "bad body"}}},
			)

		with self._direct_create() as m, patch.object(frappe.db, "delete") as dele:
			res = wb.create_template("ACC", good, http_post=post)
		self.assertEqual(res["error"], "create_failed")
		self.assertIn("bad body", res["message"])
		self.assertNotIn("SECRET123", res["message"])
		m["insert"].assert_not_called()
		dele.assert_not_called()

	def test_direct_send_components_named_location_and_copy_code(self):
		comps, errors = wb.direct_send_components(
			{"first_name": "Ann", "order_id": "A1"},
			{"type": "location", "latitude": 1.5, "longitude": 2.5},
			[{"index": 1, "sub_type": "copy_code", "code": "SAVE"}, {"index": 0, "sub_type": "url", "text": "x"}],
		)
		self.assertEqual(errors, [])
		self.assertEqual(comps[0], {"type": "header", "parameters": [{"type": "location", "location": {"latitude": 1.5, "longitude": 2.5}}]})
		self.assertEqual(comps[1]["parameters"], [
			{"type": "text", "parameter_name": "first_name", "text": "Ann"},
			{"type": "text", "parameter_name": "order_id", "text": "A1"},
		])
		self.assertEqual([c.get("sub_type") for c in comps[2:]], ["url", "copy_code"])
		_, errors = wb.direct_send_components(["Ann"], [{"type": "", "link": "https://x.example/a.png"}], None)
		self.assertEqual(errors[0]["code"], "invalid_type")
		_, errors = wb.direct_send_components(None, None, [{"index": 0, "sub_type": "copy_code", "code": "x" * 16}])
		self.assertEqual(errors[0]["code"], "invalid_code")

	def test_send_template_named_params_use_the_stored_parameter_format(self):
		tpl = {
			"template": "Hi {{first_name}}, bye", "header_type": "", "header": "", "sample": "", "actual_name": "named_t",
			"template_name": "named_t", "language_code": "en_US", "status": "APPROVED", "whatsapp_account": "ACC",
			"buttons": [], "parameter_format": "NAMED", "header_format": "",
		}
		posted = []
		with avail(), patch.object(wb, "resolve_account", return_value=ACCT), patch.object(
			wb, "_template_docname", return_value="named_t-en_US"
		), patch.object(wb, "_template_row", return_value=tpl), patch.object(
			wb, "_mirror_template_send", side_effect=lambda *a, **k: {"success": True}
		), patch.object(frappe, "has_permission", return_value=True):
			post = lambda url, **kw: posted.append(kw["json"]) or SimpleNamespace(  # noqa: E731
				status_code=200, json=lambda: {"messages": [{"id": "wamid.1"}]}
			)
			self.assertTrue(wb.send_template("ACC", "15551234567", "named_t", {"first_name": "Zed"}, http_post=post)["success"])
			self.assertEqual(posted[0]["template"]["components"], [{"type": "body", "parameters": [{"type": "text", "parameter_name": "first_name", "text": "Zed"}]}])
			with self.assertRaises(wb.BridgeError) as ctx:
				wb.send_template("ACC", "15551234567", "named_t", {}, http_post=post)
			self.assertEqual(ctx.exception.payload["error"], "param_missing")
			with self.assertRaises(wb.BridgeError) as ctx:
				wb.send_template("ACC", "15551234567", "named_t", {"first_name": "Z", "nope": "x"}, http_post=post)
			self.assertEqual(ctx.exception.payload["error"], "param_unknown")
		self.assertEqual(len(posted), 1)

	def test_delete_template(self):
		with avail(False):
			self.assertEqual(wb.delete_template("T")["error"], "bridge_unavailable")
		with avail(), patch.object(frappe, "has_permission", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				wb.delete_template("T")

		def exists(doctype, *a, **k):
			return doctype != "WhatsApp Message"  # the template exists and has no sent messages

		with avail(), patch.object(frappe, "has_permission", return_value=True), patch.object(
			frappe.db, "exists", side_effect=exists
		), patch.object(frappe.db, "get_value", return_value="ACC"), patch.object(wb, "_guard"), patch.object(
			frappe, "delete_doc"
		) as dd:
			self.assertTrue(wb.delete_template("T")["success"])
			dd.assert_called_once_with("WhatsApp Templates", "T")
		with avail(), patch.object(frappe, "has_permission", return_value=True), patch.object(
			frappe.db, "exists", return_value=True
		), patch.object(frappe, "delete_doc") as dd:
			res = wb.delete_template("T")  # sent messages reference it: refuse before Meta is touched
			self.assertEqual(res["error"], "template_in_use")
			dd.assert_not_called()

	def test_sync_templates(self):
		calls = []

		def http_get(url, **kw):
			calls.append((url, kw))
			return FakeResp(
				{
					"data": [
						{"name": "promo", "language": "en_US", "status": "APPROVED", "category": "MARKETING", "id": "9"},
						{"name": "same", "language": "en_US", "status": "APPROVED", "category": "UTILITY", "id": "7"},
						{"name": "zz", "language": "en_US", "status": "X", "id": "8"},
					]
				}
			)

		def local(account, name, lang):
			return {"promo": "T1", "same": "T2"}.get(name)

		def get_value(dt, name, fields, as_dict=False):
			return {"T1": {"status": "PENDING", "category": "MARKETING", "id": "9"}, "T2": {"status": "APPROVED", "category": "UTILITY", "id": "7"}}[name]

		with avail(), patch.object(frappe, "has_permission", return_value=True), patch.object(
			wb, "resolve_account", return_value=ACCT
		), patch.object(frappe.db, "exists", return_value=False), patch.object(wb, "_local_template", side_effect=local), patch.object(
			frappe.db, "get_value", side_effect=get_value
		), patch.object(frappe.db, "set_value") as sv, patch.object(wb, "_import_template", return_value="zz-en_US") as imp:
			res = wb.sync_templates("ACC", http_get=http_get)
		self.assertEqual(
			res,
			{"success": True, "seen": 3, "imported": 1, "updated": 1, "unchanged": 1, "skipped": 0, "skipped_reasons": []},
		)
		self.assertEqual(calls[0][0], "https://graph.facebook.com/v25.0/BIZ/message_templates")
		self.assertEqual(calls[0][1]["headers"]["Authorization"], "Bearer tok")
		sv.assert_called_once_with("WhatsApp Templates", "T1", {"status": "APPROVED"})
		imp.assert_called_once()
		self.assertEqual(imp.call_args.args[1]["name"], "zz")
		with avail(False):
			self.assertEqual(wb.sync_templates("ACC")["error"], "bridge_unavailable")

	def test_sync_templates_isolates_overflowing_template(self):
		long_cdn = "https://scontent.xx.fbcdn.net/v/t39/sample.jpg?" + "oh=" + "a" * 180
		inserted = []

		class Doc:
			doctype = "WhatsApp Templates"

			def __init__(self):
				self.rows = []

			def append(self, field, row):
				self.rows.append(SimpleNamespace(db_insert=lambda: None, **row))

			def get(self, field):
				return self.rows

			def db_insert(self):
				inserted.append(self.template_name)

		def button_components(url, example):
			btn = {"type": "URL", "text": "Go", "url": url}
			if example:
				btn["example"] = [example]
			return [{"type": "BUTTONS", "buttons": [btn]}]

		def http_get(url, **kw):
			return FakeResp({"data": [
				# good: Meta sample link is too long for example_url, so it is dropped and the template imports
				{"name": "good", "language": "en_US", "status": "APPROVED", "category": "UTILITY", "id": "1",
				 "components": [{"type": "BODY", "text": "Hi"}] + button_components("https://x.io/static", long_cdn)},
				# bad: dynamic base URL overflows website_url, which is needed to send, so it is skipped
				{"name": "bad", "language": "en_US", "status": "APPROVED", "category": "UTILITY", "id": "2",
				 "components": [{"type": "BODY", "text": "Yo"}] + button_components("https://x.io/" + "b" * 200 + "/{{1}}", None)},
			]})

		with avail(), patch.object(frappe, "has_permission", return_value=True), patch.object(
			wb, "resolve_account", return_value=ACCT
		), patch.object(frappe.db, "exists", return_value=False), patch.object(
			wb, "_local_template", return_value=None
		), patch.object(frappe, "new_doc", side_effect=lambda dt: Doc()), patch.object(
			frappe.utils, "now", return_value="2026-01-01 00:00:00"
		), patch.object(wb, "_language_link", return_value="en"), patch.object(
			frappe.db, "savepoint"
		) as sp, patch.object(frappe.db, "rollback") as rb:
			res = wb.sync_templates("ACC", http_get=http_get)
		self.assertTrue(res["success"])
		self.assertEqual((res["seen"], res["imported"], res["skipped"]), (2, 1, 1))
		self.assertEqual(inserted, ["good"])
		self.assertEqual(len(res["skipped_reasons"]), 1)
		reason = res["skipped_reasons"][0]
		self.assertTrue(reason.startswith("bad: import failed"))
		self.assertIn("website_url", reason)
		self.assertNotIn("https://", reason)
		self.assertEqual(sp.call_count, 2)  # one savepoint per import attempt
		rb.assert_called_once()  # only the failing one is rolled back

	def test_import_template_maps_components_without_hooks(self):
		class Doc:
			doctype = "WhatsApp Templates"

			def __init__(self):
				self.rows = []
				self.inserted = False

			def append(self, field, row):
				child = SimpleNamespace(db_insert=lambda: None, **row)
				self.rows.append(child)

			def get(self, field):
				return self.rows

			def db_insert(self):
				self.inserted = True

		doc = Doc()
		tpl = {
			"name": "promo", "language": "en_US", "status": "APPROVED", "category": "MARKETING", "id": "55",
			"components": [
				{"type": "HEADER", "format": "TEXT", "text": "Hi"},
				{"type": "BODY", "text": "Hello {{1}}", "example": {"body_text": [["Ann"]]}},
				{"type": "FOOTER", "text": "Bye"},
				{"type": "BUTTONS", "buttons": [
					{"type": "URL", "text": "Go", "url": "https://x.io/{{1}}", "example": ["https://x.io/a"]},
					{"type": "QUICK_REPLY", "text": "Ok"},
				]},
			],
		}
		with patch.object(frappe.utils, "now", return_value="2026-01-01 00:00:00"), patch.object(frappe, "new_doc", return_value=doc), patch.object(
			wb, "_language_link", return_value="en"
		), patch.object(frappe, "get_doc") as gd:
			name = wb._import_template("ACC", tpl)
		self.assertEqual(name, "promo-en_US")
		self.assertTrue(doc.inserted)
		gd.assert_not_called()
		self.assertEqual(
			(doc.template_name, doc.actual_name, doc.id, doc.status, doc.category, doc.whatsapp_account, doc.language_code),
			("promo", "promo", "55", "APPROVED", "MARKETING", "ACC", "en_US"),
		)
		self.assertEqual((doc.header_type, doc.header, doc.template, doc.sample_values, doc.footer), ("TEXT", "Hi", "Hello {{1}}", "Ann", "Bye"))
		self.assertEqual([(r.button_type, r.sequence) for r in doc.rows], [("Visit Website", 1), ("Quick Reply", 2)])
		self.assertEqual((doc.rows[0].url_type, doc.rows[0].example_url, doc.rows[0].parent), ("Dynamic", "https://x.io/a", "promo-en_US"))

	def test_forward_status(self):
		mod = ModuleType("frappe_whatsapp.utils.webhook")
		mod.update_status = MagicMock()
		msg_change = {"field": "messages", "value": {"statuses": [{"id": "w1"}]}}
		tpl_change = {"field": "message_template_status_update", "value": {}}
		with avail(), patch.dict(sys.modules, {"frappe_whatsapp.utils.webhook": mod}):
			with patch.object(frappe.db, "exists", return_value=False), patch.object(frappe, "enqueue") as enq:
				self.assertFalse(wb.forward_status(msg_change))
				# unknown wamid: exactly one delayed retry is queued, not a drop
				enq.assert_called_once()
				self.assertTrue(enq.call_args.kwargs["enqueue_after_commit"])
				self.assertEqual(enq.call_args.kwargs["change"], msg_change)
				enq.reset_mock()
				self.assertFalse(wb.forward_status(msg_change, _retry=True))
				enq.assert_not_called()  # the retry never re-enqueues
			mod.update_status.assert_not_called()
			with patch.object(frappe.db, "exists", return_value=True):
				self.assertTrue(wb.forward_status(msg_change))
			self.assertTrue(wb.forward_status(tpl_change))
			mod.update_status.side_effect = RuntimeError("x")
			self.assertFalse(wb.forward_status(tpl_change))
		with avail(False):
			self.assertFalse(wb.forward_status(tpl_change))
		with avail():  # module missing -> ImportError swallowed
			with patch.object(wb.importlib, "import_module", side_effect=ImportError):
				self.assertFalse(wb.forward_status(tpl_change))

	def test_retry_forward_status_waits_then_forwards_once(self):
		change = {"field": "messages", "value": {"statuses": [{"id": "w1"}]}}
		with patch("time.sleep") as sleep, patch.object(wb, "forward_status", return_value=True) as fwd:
			self.assertTrue(wb.retry_forward_status(change))
		sleep.assert_called_once_with(wb.FORWARD_RETRY_DELAY_SECONDS)
		fwd.assert_called_once_with(change, _retry=True)

	def _media_get(self, meta, content=b"data"):
		def http_get(url, **kw):
			if url.endswith("/M1"):
				return FakeResp(meta)
			return FakeResp(content=content)

		return http_get

	def test_download_media(self):
		meta = {"mime_type": "image/jpeg", "url": "https://lookaside.fbsbx.com/x", "file_size": 4, "filename": "../a b.jpg"}
		with patch.object(wb, "resolve_account", return_value=ACCT):
			res = wb.download_media("ACC", "M1", http_get=self._media_get(meta))
			self.assertEqual(res["content"], b"data")
			self.assertEqual(res["mime_type"], "image/jpeg")
			self.assertNotIn("/", res["filename"])
			with self.assertRaises(ValueError):
				wb.download_media("ACC", "M1", http_get=self._media_get({**meta, "mime_type": "application/x-msdownload"}))
			with self.assertRaises(ValueError):
				wb.download_media("ACC", "M1", max_bytes=2, http_get=self._media_get(meta))
			with self.assertRaises(ValueError):
				wb.download_media("ACC", "M1", max_bytes=2, http_get=self._media_get({**meta, "file_size": None}))
		with patch.object(wb, "resolve_account", return_value={"error": "no_account"}):
			with self.assertRaises(ValueError):
				wb.download_media("ACC", "M1", http_get=self._media_get(meta))

	def test_download_media_per_kind_limits_and_mimes(self):
		def meta(mime, size, **kw):
			return {"mime_type": mime, "url": "https://lookaside.fbsbx.com/x", "file_size": size, **kw}

		mb = 1024 * 1024
		self.assertEqual(wb.MEDIA_LIMITS_BY_KIND, {"document": 100 * mb, "image": 5 * mb, "audio": 16 * mb, "video": 16 * mb, "sticker": 500 * 1024})
		with patch.object(wb, "resolve_account", return_value=ACCT):
			dl = lambda m, **kw: wb.download_media("ACC", "M1", http_get=self._media_get(m), **kw)
			self.assertEqual(dl(meta("application/pdf", 50 * mb))["mime_type"], "application/pdf")
			for mime in (
				"application/msword",
				"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
				"application/vnd.ms-excel",
				"application/vnd.ms-powerpoint",
			):
				self.assertEqual(dl(meta(mime, 1))["mime_type"], mime)
			for mime, size in (("image/jpeg", 6 * mb), ("audio/ogg", 17 * mb), ("video/mp4", 17 * mb), ("application/pdf", 101 * mb)):
				with self.assertRaisesRegex(ValueError, "media_too_large"):
					dl(meta(mime, size))
			self.assertEqual(dl(meta("image/jpeg", 5 * mb))["mime_type"], "image/jpeg")
			with self.assertRaisesRegex(ValueError, "media_too_large"):
				dl(meta("image/webp", 600 * 1024), kind="sticker")
			for mime in ("image/svg+xml", "text/html", "application/x-msdownload", "application/x-sh"):
				with self.assertRaisesRegex(ValueError, "mime_not_allowed"):
					dl(meta(mime, 1))

	def test_download_media_rejects_bad_hosts(self):
		meta = {"mime_type": "image/jpeg", "file_size": 4}
		with patch.object(wb, "resolve_account", return_value=ACCT):
			for bad in ("http://lookaside.fbsbx.com/x", "https://evil.example.com/x", "https://fbcdn.net.evil.com/x"):
				with self.assertRaises(ValueError) as ctx:
					wb.download_media("ACC", "M1", http_get=self._media_get({**meta, "url": bad}))
				self.assertEqual(str(ctx.exception), "media_url_host_not_allowed")

	def test_download_media_no_redirects_and_quoted_id(self):
		seen = []

		def http_get(url, **kw):
			seen.append((url, kw))
			if "/v25.0/" in url:
				return FakeResp({"mime_type": "image/jpeg", "url": "https://x.fbcdn.net/a"})
			return FakeResp(content=b"ab")

		with patch.object(wb, "resolve_account", return_value=ACCT):
			wb.download_media("ACC", "a/../b", http_get=http_get)
		self.assertTrue(seen[0][0].endswith("/a%2F..%2Fb"))
		self.assertTrue(all(kw["allow_redirects"] is False for _, kw in seen))
		self.assertTrue(seen[1][1]["stream"])

	def test_sync_templates_rejects_foreign_paging_host(self):
		def http_get(url, **kw):
			return FakeResp({"data": [], "paging": {"next": "https://evil.example.com/next?access_token=SECRET"}})

		with avail(), patch.object(frappe, "has_permission", return_value=True), patch.object(
			wb, "resolve_account", return_value=ACCT
		):
			res = wb.sync_templates("ACC", http_get=http_get)
		self.assertEqual(res["error"], "sync_failed")
		self.assertNotIn("SECRET", json.dumps(res))

	def test_redact_strips_tokens_and_urls(self):
		out = wb._redact("boom https://graph.facebook.com/x?access_token=SECRET&a=1 token=ABC")
		self.assertNotIn("SECRET", out)
		self.assertNotIn("ABC", out)
		self.assertNotIn("graph.facebook.com", out)

	def test_list_messages_and_conversations(self):
		with avail(False):
			self.assertEqual(wb.list_messages(), {"success": False, "error": "bridge_unavailable"})
			self.assertEqual(wb.list_conversations(), {"success": False, "error": "bridge_unavailable"})
		rows = [
			{"type": "Incoming", "from": "111", "to": "", "profile_name": "Al"},
			{"type": "Outgoing", "from": "", "to": "111"},
			{"type": "Outgoing", "from": "", "to": "222"},
		]
		with avail(), patch.object(frappe, "get_list", return_value=rows) as gl:
			res = wb.list_messages("ACC", "+111", 10)
			self.assertEqual(len(res["messages"]), 3)
			self.assertEqual(gl.call_args.kwargs["or_filters"], {"to": "111", "from": "111"})
			convs = wb.list_conversations("ACC", 10)["conversations"]
			self.assertEqual({c["phone"]: c["count"] for c in convs}, {"111": 2, "222": 1})
			self.assertEqual(convs[0]["profile_name"], "Al")

LIVE_2388039 = {
	"error": {
		"message": "Invalid parameter",
		"type": "OAuthException",
		"code": 100,
		"error_subcode": 2388039,
		"is_transient": False,
		"error_user_title": "Message template status can't be changed",
		"error_user_msg": "The status for this message template can't be changed. You can only delete or add templates.",
		"fbtrace_id": "AbC123xyz",
	}
}


class ErrResp:
	def __init__(self, body, status=400):
		self._b, self.status_code, self.text = body, status, json.dumps(body)

	def json(self):
		return self._b


class TestGraphErrorDetail(unittest.TestCase):
	def test_live_edit_refusal(self):
		d = wb.graph_error_detail(ErrResp(LIVE_2388039))
		self.assertEqual((d["code"], d["subcode"], d["trace_id"]), (100, 2388039, "AbC123xyz"))
		self.assertEqual(d["user_title"], "Message template status can't be changed")
		self.assertIn("can't be changed", d["user_msg"])
		self.assertEqual(d["kind"], "edit_blocked")
		self.assertFalse(d["retryable"])
		self.assertTrue(d["message"].startswith("Meta won't let this template be edited right now"))
		self.assertIn("create a new version", d["message"])

	def test_user_msg_wins_then_meta_message_with_advice(self):
		body = {"error": {"code": 100, "message": "Invalid parameter", "error_user_msg": "Body text is too long.", "error_subcode": 2388001}}
		self.assertEqual(wb.graph_error_detail(ErrResp(body))["message"], "Body text is too long.")
		d = wb.graph_error_detail(ErrResp({"error": {"code": 100, "message": "Invalid parameter"}}))
		self.assertIn("Invalid parameter", d["message"])
		d = wb.graph_error_detail(ErrResp({"error": {"code": 4, "message": "rate", "fbtrace_id": "T1"}}, 429))
		self.assertEqual((d["kind"], d["retryable"], d["trace_id"]), ("rate_limited", True, "T1"))
		self.assertIn("Retry with backoff", d["message"])

	def test_always_redacted(self):
		body = {"error": {"code": 100, "message": "bad", "error_user_msg": "See https://x.example/a?access_token=EAAB1234567890abcd and Bearer EAAB1234567890abcd"}}
		d = wb.graph_error_detail(ErrResp(body))
		blob = json.dumps(d)
		self.assertNotIn("EAAB1234567890abcd", blob)
		self.assertNotIn("x.example", blob)

	def test_exception_without_body_keeps_its_text(self):
		d = wb.graph_error_detail(RuntimeError("disk exploded token=SECRET123"))
		self.assertIn("disk exploded", d["message"])
		self.assertNotIn("SECRET123", d["message"])
		self.assertIsNone(d["code"])

	def test_http_error_exception_uses_the_response_body(self):
		import requests

		exc = requests.HTTPError("400 Client Error", response=SimpleNamespace(status_code=400, json=lambda: LIVE_2388039, text="", headers={}))
		self.assertEqual(wb.graph_error_detail(exc)["subcode"], 2388039)

	def test_error_dict_carries_all_fields(self):
		out = wb._graph_err("edit_failed", ErrResp(LIVE_2388039))
		for key in ("message", "user_title", "user_msg", "graph_code", "subcode", "kind", "retryable", "operator_text", "trace_id"):
			self.assertIn(key, out)
		self.assertEqual((out["success"], out["error"], out["graph_code"]), (False, "edit_failed", 100))


class HopResp:
	def __init__(self, status=200, location=None, content=b"\x89PNGdata", ctype="image/png"):
		self.status_code, self.content = status, content
		self.headers = {"Content-Type": ctype, **({"Location": location} if location else {})}


class TestSampleRedirects(unittest.TestCase):
	def _get(self, routes, calls):
		def get(url, **kw):
			calls.append((url, kw.get("allow_redirects")))
			return routes[url]
		return get

	def _read(self, routes, start="https://a.example/s.png", header="IMAGE"):
		calls = []
		with patch.object(wb, "_is_private_host", side_effect=lambda h: h.startswith(("10.", "127.", "internal"))):
			try:
				return wb._read_header_sample(start, header, self._get(routes, calls)), calls
			except wb.BridgeError as exc:
				return exc.payload, calls

	def test_no_redirect(self):
		(content, mime), calls = self._read({"https://a.example/s.png": HopResp()})
		self.assertEqual((mime, calls), ("image/png", [("https://a.example/s.png", False)]))

	def test_one_and_three_hops_are_followed(self):
		routes = {"https://a.example/s.png": HopResp(302, "https://b.example/x"), "https://b.example/x": HopResp()}
		(_, mime), calls = self._read(routes)
		self.assertEqual((mime, len(calls)), ("image/png", 2))
		routes = {
			"https://a.example/s.png": HopResp(301, "/p1"), "https://a.example/p1": HopResp(307, "https://b.example/p2"),
			"https://b.example/p2": HopResp(308, "https://c.example/p3"), "https://c.example/p3": HopResp(),
		}
		(_, mime), calls = self._read(routes)
		self.assertEqual((mime, len(calls)), ("image/png", 4))

	def test_four_hops_are_refused(self):
		routes = {f"https://a.example/{i}": HopResp(302, f"https://a.example/{i + 1}") for i in range(5)}
		routes["https://a.example/4"] = HopResp()
		out, calls = self._read(routes, start="https://a.example/0")
		self.assertEqual(out["errors"][0]["code"], "sample_unreachable")
		self.assertIn("more than 3 times", out["errors"][0]["message"])
		self.assertEqual(len(calls), 4)

	def test_redirect_to_private_ip_is_refused_before_fetching_it(self):
		out, calls = self._read({"https://a.example/s.png": HopResp(302, "https://10.0.0.1/secret"), "https://10.0.0.1/secret": HopResp()})
		self.assertEqual(out["errors"][0]["code"], "sample_private_host")
		self.assertEqual(len(calls), 1)

	def test_redirect_to_http_is_refused(self):
		out, calls = self._read({"https://a.example/s.png": HopResp(302, "http://b.example/x"), "http://b.example/x": HopResp()})
		self.assertEqual(out["errors"][0]["code"], "sample_not_https")
		self.assertEqual(len(calls), 1)

	def test_first_hop_http_or_private_is_refused(self):
		out, calls = self._read({}, start="http://a.example/s.png")
		self.assertEqual((out["errors"][0]["code"], calls), ("sample_not_https", []))
		out, calls = self._read({}, start="https://internal.corp/s.png")
		self.assertEqual((out["errors"][0]["code"], calls), ("sample_private_host", []))

	def test_redirect_loop(self):
		routes = {"https://a.example/s.png": HopResp(302, "https://b.example/x"), "https://b.example/x": HopResp(302, "https://a.example/s.png")}
		out, calls = self._read(routes)
		self.assertEqual(out["errors"][0]["code"], "sample_unreachable")
		self.assertIn("loop", out["errors"][0]["message"])

	def test_final_status_is_in_the_message(self):
		routes = {"https://a.example/s.png": HopResp(302, "https://b.example/x"), "https://b.example/x": HopResp(404)}
		out, _ = self._read(routes)
		self.assertEqual(out["errors"][0]["code"], "sample_unreachable")
		self.assertIn("HTTP 404 after 1 redirect", out["errors"][0]["message"])

	def test_redirect_without_location(self):
		out, _ = self._read({"https://a.example/s.png": HopResp(302)})
		self.assertIn("without a Location", out["errors"][0]["message"])

	def test_final_content_type_and_size_still_apply(self):
		routes = {"https://a.example/s.png": HopResp(302, "https://b.example/x"), "https://b.example/x": HopResp(ctype="text/html")}
		out, _ = self._read(routes)
		self.assertEqual(out["errors"][0]["code"], "invalid_sample")
		routes = {"https://a.example/s.png": HopResp(content=b"x" * (5 * 1024 * 1024 + 1))}
		out, _ = self._read(routes)
		self.assertEqual(out["errors"][0]["code"], "sample_too_large")


if __name__ == "__main__":
	unittest.main()


class LinkResp:
	def __init__(self, status=200, ctype="audio/mpeg", content=b"ID3data", location=None, length=None):
		self.status_code, self.content = status, content
		self.headers = {"Content-Type": ctype}
		if location:
			self.headers["Location"] = location
		if length is not None:
			self.headers["Content-Length"] = str(length)
		self.closed = False

	def iter_content(self, chunk_size=1):
		yield self.content

	def close(self):
		self.closed = True


class TestMediaLinkPreflight(unittest.TestCase):
	"""Meta fetches links asynchronously, so an unfetchable link must be refused before any Graph call."""

	def _run(self, routes, kind="audio", start="https://a.example/horse.mp3"):
		calls = []

		def get(url, **kw):
			calls.append((url, kw.get("allow_redirects")))
			return routes[url]

		with patch.object(wb, "_is_private_host", side_effect=lambda h: h.startswith(("10.", "127.", "internal"))):
			try:
				wb.preflight_media_link(kind, start, get)
				return None, calls
			except wb.BridgeError as exc:
				return exc.payload, calls

	def test_good_link_passes_and_closes_response(self):
		resp = LinkResp()
		out, calls = self._run({"https://a.example/horse.mp3": resp})
		self.assertIsNone(out)
		self.assertEqual(calls, [("https://a.example/horse.mp3", False)])
		self.assertTrue(resp.closed)

	def test_octet_stream_with_matching_extension_passes(self):
		out, _ = self._run({"https://a.example/horse.mp3": LinkResp(ctype="application/octet-stream")})
		self.assertIsNone(out)
		out, _ = self._run({"https://a.example/horse": LinkResp(ctype="application/octet-stream")}, start="https://a.example/horse")
		self.assertEqual(out["error"], "media_link_wrong_type")

	def test_document_pdf_passes(self):
		out, _ = self._run({"https://a.example/a.pdf": LinkResp(ctype="application/pdf", content=b"%PDF")}, "document", "https://a.example/a.pdf")
		self.assertIsNone(out)

	def test_403_is_unreachable_without_http_internals(self):
		out, _ = self._run({"https://a.example/horse.mp3": LinkResp(status=403, ctype="text/html", content=b"<html>no</html>")})
		self.assertEqual((out["success"], out["error"]), (False, "media_link_unreachable"))
		self.assertNotIn("403", out["message"])
		self.assertIn("file_url", out["hint"])

	def test_html_body_with_audio_content_type_is_wrong_type(self):
		out, _ = self._run({"https://a.example/horse.mp3": LinkResp(content=b"  <!DOCTYPE html><html>")})
		self.assertEqual(out["error"], "media_link_wrong_type")

	def test_html_content_type_is_wrong_type(self):
		out, _ = self._run({"https://a.example/horse.mp3": LinkResp(ctype="text/html; charset=utf-8", content=b"hi")})
		self.assertEqual(out["error"], "media_link_wrong_type")

	def test_wrong_media_family_is_wrong_type(self):
		out, _ = self._run({"https://a.example/p.png": LinkResp(ctype="image/png", content=b"\x89PNG")}, "audio", "https://a.example/p.png")
		self.assertEqual(out["error"], "media_link_wrong_type")

	def test_oversize_by_content_length(self):
		out, _ = self._run({"https://a.example/horse.mp3": LinkResp(length=17 * 1024 * 1024)})
		self.assertEqual(out["error"], "media_link_too_large")
		self.assertIn("16 MB", out["message"])

	def test_oversize_image_without_length_header(self):
		resp = LinkResp(ctype="image/png", content=b"x" * (5 * 1024 * 1024 + 1))
		out, _ = self._run({"https://a.example/p.png": resp}, "image", "https://a.example/p.png")
		self.assertEqual(out["error"], "media_link_too_large")

	def test_sticker_static_limit(self):
		resp = LinkResp(ctype="image/webp", content=b"RIFF" + b"\0" * 10, length=101 * 1024)
		out, _ = self._run({"https://a.example/s.webp": resp}, "sticker", "https://a.example/s.webp")
		self.assertEqual(out["error"], "media_link_too_large")

	def test_redirect_to_private_ip_is_refused_before_fetching_it(self):
		routes = {"https://a.example/horse.mp3": LinkResp(302, location="https://10.0.0.1/x"), "https://10.0.0.1/x": LinkResp()}
		out, calls = self._run(routes)
		self.assertEqual(out["error"], "media_link_unreachable")
		self.assertEqual(len(calls), 1)

	def test_redirect_is_followed_to_a_good_file(self):
		routes = {"https://a.example/horse.mp3": LinkResp(302, location="https://b.example/h.mp3"), "https://b.example/h.mp3": LinkResp()}
		out, calls = self._run(routes)
		self.assertIsNone(out)
		self.assertEqual(len(calls), 2)

	def test_plain_http_link_is_refused(self):
		out, calls = self._run({}, start="http://a.example/horse.mp3")
		self.assertEqual((out["error"], calls), ("media_link_unreachable", []))

	def test_network_error_is_unreachable(self):
		def boom(url, **kw):
			raise OSError("connection reset https://a.example/horse.mp3?access_token=SECRET")

		with patch.object(wb, "_is_private_host", return_value=False):
			with self.assertRaises(wb.BridgeError) as ctx:
				wb.preflight_media_link("audio", "https://a.example/horse.mp3", boom)
		self.assertEqual(ctx.exception.payload["error"], "media_link_unreachable")
		self.assertNotIn("SECRET", json.dumps(ctx.exception.payload))

	def test_send_media_refuses_before_any_graph_call(self):
		post = MagicMock()
		get = lambda url, **kw: LinkResp(status=403, ctype="text/html", content=b"<html>")  # noqa: E731
		with patch.object(wb, "_account_or_error", return_value=ACCT), patch.object(wb, "_is_private_host", return_value=False):
			with self.assertRaises(wb.BridgeError) as ctx:
				wb.send_media("ACC", "15551234567", "audio", link="https://a.example/horse.mp3", http_post=post, http_get=get)
		self.assertEqual(ctx.exception.payload["error"], "media_link_unreachable")
		post.assert_not_called()

	def test_send_sticker_refuses_before_any_graph_call(self):
		post = MagicMock()
		get = lambda url, **kw: LinkResp(ctype="text/html", content=b"<html>")  # noqa: E731
		with patch.object(wb, "_account_or_error", return_value=ACCT), patch.object(wb, "_is_private_host", return_value=False):
			with self.assertRaises(wb.BridgeError) as ctx:
				wb.send_sticker("ACC", "15551234567", link="https://a.example/s.webp", http_post=post, http_get=get)
		self.assertEqual(ctx.exception.payload["error"], "media_link_wrong_type")
		post.assert_not_called()
