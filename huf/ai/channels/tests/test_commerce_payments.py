"""Commerce payments: provider links (mocked HTTP), webhook signatures, paid flow, cart recovery, templates pack."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import timedelta
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime

from huf.ai.channels import conversation as conv, reply_api
from huf.ai.channels.commerce import cart_recovery, payments, templates_pack

ORDER = "WhatsApp Order"
RZP_SECRET, STRIPE_SECRET = "rzp-whsec", "whsec_test"
_STUB = {"made": False}


def _ensure_order_doctype():
	if frappe.db.exists("DocType", ORDER):
		return
	fields = [("status", "Select", "Draft\nPaid"), ("payment_status", "Data", None), ("payment_link", "Data", None),
		("conversation", "Data", None), ("gateway", "Data", None), ("total", "Currency", None), ("currency", "Data", None),
		("reminder_sent_at", "Datetime", None)]
	frappe.get_doc({
		"doctype": "DocType", "name": ORDER, "module": "Huf", "custom": 1, "autoname": "hash",
		"fields": [{"fieldname": f, "label": f, "fieldtype": t, **({"options": o} if o else {})} for f, t, o in fields],
		"permissions": [{"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1}],
	}).insert(ignore_permissions=True)
	_STUB["made"] = True
	frappe.db.commit()


def _resp(status=200, data=None):
	r = MagicMock()
	r.status_code = status
	r.json.return_value = data or {}
	return r


class TestCommercePayments(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		_ensure_order_doctype()

	@classmethod
	def tearDownClass(cls):
		if _STUB["made"]:
			frappe.delete_doc("DocType", ORDER, force=True, ignore_permissions=True)
			frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.db.rollback)
		phone = "555" + str(int(frappe.generate_hash(length=7), 16) % 10**8).zfill(8)
		settings = frappe.get_doc({"doctype": "Integration Settings", "service": "whatsapp", "credentials": [
			{"key": "phone_number_id", "value": phone}, {"key": "access_token", "value": "tok"},
			{"key": "webhook_verify_token", "value": "v"}, {"key": "app_secret", "value": "s"},
			{"key": "razorpay_key_id", "value": "rzp_key"}, {"key": "razorpay_key_secret", "value": "rzp_secret"},
			{"key": "razorpay_webhook_secret", "value": RZP_SECRET},
			{"key": "stripe_secret_key", "value": "sk_test"}, {"key": "stripe_webhook_secret", "value": STRIPE_SECRET},
		]}).insert(ignore_permissions=True)
		self.gw = frappe.get_doc({
			"doctype": "Gateway", "gateway_name": f"Pay {frappe.generate_hash(length=6)}", "provider": "WhatsApp",
			"is_enabled": 1, "integration_settings": settings.name, "execution_user": "Administrator",
			"direct_policy": "Allow list", "payment_provider": "razorpay", "order_confirmed_template": "order_confirmed",
			"cart_recovery_hours": 2,
		}).insert(ignore_permissions=True)
		self.conv = conv.get_or_create_conversation(self.gw.name, "15550001111")

	def _order(self, **kw):
		vals = {"doctype": ORDER, "status": "Draft", "payment_status": "Unpaid", "gateway": self.gw.name, "conversation": self.conv.name, "total": 100, "currency": "INR"}
		vals.update(kw)
		return frappe.get_doc(vals).insert(ignore_permissions=True)

	# ---------------------------------------------------------------- links
	def test_razorpay_link(self):
		with patch("huf.ai.channels.commerce.payments.requests.post", return_value=_resp(200, {"id": "plink_1", "short_url": "https://rzp.io/x"})) as post:
			link = payments.RazorpayProvider(self.gw).create_link(100, "INR", "ORD1", {"phone": "15550001111"})
		self.assertEqual(link, {"url": "https://rzp.io/x", "provider_ref": "plink_1"})
		self.assertEqual(post.call_args.kwargs["json"]["amount"], 10000)
		self.assertEqual(post.call_args.kwargs["auth"], ("rzp_key", "rzp_secret"))

	def test_stripe_link(self):
		with patch("huf.ai.channels.commerce.payments.requests.post", return_value=_resp(200, {"id": "cs_1", "url": "https://stripe/pay"})) as post:
			link = payments.StripeProvider(self.gw).create_link(12.5, "USD", "ORD1")
		self.assertEqual(link, {"url": "https://stripe/pay", "provider_ref": "cs_1"})
		self.assertEqual(post.call_args.kwargs["data"]["line_items[0][price_data][unit_amount]"], 1250)
		self.assertEqual(post.call_args.kwargs["data"]["metadata[reference]"], "ORD1")

	def test_erpnext_guarded_and_patched(self):
		with self.assertRaises(payments.PaymentError):
			payments.ERPNextProvider().create_link(1, "INR", "SO-1")
		pr = MagicMock(payment_url="https://erp/pay", )
		pr.name = "PR-1"
		fake = MagicMock()
		fake.make_payment_request.return_value = pr
		with patch.dict("sys.modules", {"erpnext": MagicMock(), "erpnext.accounts": MagicMock(), "erpnext.accounts.doctype": MagicMock(),
				"erpnext.accounts.doctype.payment_request": MagicMock(payment_request=fake)}):
			link = payments.ERPNextProvider().create_link(1, "INR", "SO-1")
		self.assertEqual(link, {"url": "https://erp/pay", "provider_ref": "PR-1"})

	def test_missing_credentials_and_http_error(self):
		with patch("huf.ai.channels.commerce.payments._cred", return_value=""):
			with self.assertRaises(payments.PaymentError):
				payments.StripeProvider(self.gw).create_link(1, "USD", "R")
		with patch("huf.ai.channels.commerce.payments.requests.post", return_value=_resp(400)):
			with self.assertRaises(payments.PaymentError):
				payments.RazorpayProvider(self.gw).create_link(1, "INR", "R")

	def test_create_payment_link_stores_url(self):
		o = self._order()
		with patch("huf.ai.channels.commerce.payments.requests.post", return_value=_resp(200, {"id": "p", "short_url": "https://rzp.io/y"})):
			payments.create_payment_link(o.name)
		self.assertEqual(frappe.db.get_value(ORDER, o.name, "payment_link"), "https://rzp.io/y")

	# ---------------------------------------------------------------- signatures
	def test_razorpay_signature(self):
		body = b'{"a":1}'
		good = hmac.new(RZP_SECRET.encode(), body, hashlib.sha256).hexdigest()
		self.assertTrue(payments.verify_razorpay_signature(body, good, RZP_SECRET))
		self.assertFalse(payments.verify_razorpay_signature(body, "0" * 64, RZP_SECRET))
		self.assertFalse(payments.verify_razorpay_signature(body, good, ""))

	def test_stripe_signature(self):
		body, ts = b'{"a":1}', int(time.time())
		sig = hmac.new(STRIPE_SECRET.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
		self.assertTrue(payments.verify_stripe_signature(body, f"t={ts},v1={sig}", STRIPE_SECRET))
		self.assertFalse(payments.verify_stripe_signature(body, f"t={ts},v1={'0' * 64}", STRIPE_SECRET))
		old = ts - 10_000
		old_sig = hmac.new(STRIPE_SECRET.encode(), f"{old}.".encode() + body, hashlib.sha256).hexdigest()
		self.assertFalse(payments.verify_stripe_signature(body, f"t={old},v1={old_sig}", STRIPE_SECRET))

	# ---------------------------------------------------------------- paid
	def test_razorpay_paid_marks_and_confirms_with_template(self):
		o = self._order()
		body = json.dumps({"event": "payment_link.paid", "payload": {"payment_link": {"entity": {"reference_id": o.name}}}}).encode()
		sig = hmac.new(RZP_SECRET.encode(), body, hashlib.sha256).hexdigest()
		with patch.object(reply_api, "deliver_reply", return_value={"status": "sent"}) as send:
			res = payments.process_razorpay(body, sig, self.gw.name)
			again = payments.process_razorpay(body, sig, self.gw.name)
		self.assertEqual(res["status"], "paid")
		self.assertEqual(again["status"], "already_paid")
		self.assertEqual(send.call_count, 1)
		self.assertEqual(send.call_args.kwargs["template"], "order_confirmed")
		row = frappe.db.get_value(ORDER, o.name, ["status", "payment_status"], as_dict=True)
		self.assertEqual((row.status, row.payment_status), ("Paid", "Paid"))

	def test_bad_signature_does_not_mark(self):
		o = self._order()
		body = json.dumps({"event": "payment_link.paid", "payload": {"payment_link": {"entity": {"reference_id": o.name}}}}).encode()
		res = payments.process_razorpay(body, "bad", self.gw.name)
		self.assertFalse(res["ok"])
		self.assertEqual(frappe.db.get_value(ORDER, o.name, "payment_status"), "Unpaid")

	def test_stripe_paid_free_text_when_no_template(self):
		self.gw.db_set("order_confirmed_template", "")
		o = self._order()
		body = json.dumps({"type": "checkout.session.completed", "data": {"object": {"payment_status": "paid", "metadata": {"reference": o.name}}}}).encode()
		ts = int(time.time())
		sig = hmac.new(STRIPE_SECRET.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
		with patch.object(reply_api, "deliver_reply", return_value={"status": "sent"}) as send:
			res = payments.process_stripe(body, f"t={ts},v1={sig}", self.gw.name)
		self.assertEqual(res["status"], "paid")
		self.assertIn(o.name, send.call_args.kwargs["text"])

	# ---------------------------------------------------------------- cart recovery
	def _age(self, order, hours=5):
		frappe.db.set_value(ORDER, order.name, "creation", add_to_date(now_datetime(), hours=-hours), update_modified=False)

	def test_cart_recovery_once_only(self):
		o = self._order()
		self._age(o)
		with patch.object(reply_api, "deliver_reply", return_value={"status": "sent"}) as send:
			first = cart_recovery.run_cart_recovery()
			second = cart_recovery.run_cart_recovery()
		self.assertGreaterEqual(first, 1)
		self.assertEqual(second, 0)
		self.assertEqual(send.call_args.kwargs["template"], "cart_reminder")
		self.assertTrue(frappe.db.get_value(ORDER, o.name, "reminder_sent_at"))

	def test_cart_recovery_skips_opted_out_young_and_off(self):
		o = self._order()
		self._age(o)
		young = self._order()
		with patch("huf.ai.gateway_service.is_opted_out", return_value=True), patch.object(reply_api, "deliver_reply") as send:
			cart_recovery.run_cart_recovery()
		send.assert_not_called()
		self.assertFalse(frappe.db.get_value(ORDER, o.name, "reminder_sent_at"))
		self.gw.db_set("cart_recovery_hours", 0)
		with patch.object(reply_api, "deliver_reply") as send:
			cart_recovery.run_cart_recovery()
		send.assert_not_called()
		self.assertFalse(frappe.db.get_value(ORDER, young.name, "reminder_sent_at"))

	# ---------------------------------------------------------------- templates pack
	def test_templates_pack_shape(self):
		from huf.ai.gateway_adapters import whatsapp_templates as wt

		names = [t["name"] for t in templates_pack.TEMPLATES_PACK]
		self.assertEqual(names, ["order_confirmed", "order_shipped", "payment_reminder", "invoice_ready", "cart_reminder"])
		for spec in templates_pack.TEMPLATES_PACK:
			p = templates_pack.template_payload(spec)
			self.assertEqual((p["category"], p["language_code"]), ("UTILITY", "en"))
			self.assertIn("{{1}}", p["template"])
			_, errors = wt.validate_template_spec(p)
			self.assertEqual(errors, [], spec["name"])

	def test_submit_templates_pack_calls_create_path(self):
		from huf.ai.whatsapp import management

		with patch.object(management, "create_template", return_value={"success": True}) as create:
			res = templates_pack.submit_templates_pack(self.gw.name)
		self.assertTrue(res["success"])
		self.assertEqual(create.call_count, 5)
		self.assertEqual(cre