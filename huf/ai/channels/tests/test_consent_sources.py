"""BE-OPTIN: explicit opt-in capture sources on Gateway Consent (inbound START, import with attestation, API)."""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai import gateway_service as gsvc
from huf.ai.channels import consent_api
from huf.ai.gateway_adapters.tests.test_gateway_pairing_hardening import _GatewayFixture

PHONE = "15551230001"  # STOPs in the fixtures below
FRESH = "15551230002"
OTHER = "15551230003"
NOTE = "Collected at the 2026 store opening, signed paper form"


class _Fixture(_GatewayFixture):
	def tearDown(self):
		for name in self.gateways:
			frappe.db.delete("Gateway Consent", {"gateway": name})
		super().tearDown()

	def gateway_with_stopped_sender(self):
		gateway = self.make_gateway("P", policy="Allow list")
		self.make_entry(gateway, PHONE, state="Approved")
		self.ingest(gateway, PHONE, "STOP")
		self.assertTrue(gsvc.is_opted_out(gateway, PHONE))
		return gateway

	def consent_rows(self, gateway, sender):
		return frappe.get_all(
			"Gateway Consent",
			filters={"gateway": gateway, "sender_id": sender, "category": "marketing_messages"},
			fields=["value", "source", "attested_by", "attestation_note", "captured_at"],
			order_by="creation asc",
		)


class TestConsentSchema(IntegrationTestCase):
	def test_source_is_select_with_capture_sources(self):
		meta = frappe.get_meta("Gateway Consent")
		source = meta.get_field("source")
		self.assertEqual(source.fieldtype, "Select")
		options = set((source.options or "").split("\n"))
		for option in ("inbound", "import", "api", "manual", "widget"):
			self.assertIn(option, options)

	def test_attestation_and_capture_fields_exist(self):
		meta = frappe.get_meta("Gateway Consent")
		self.assertEqual(meta.get_field("attested_by").fieldtype, "Link")
		self.assertEqual(meta.get_field("attested_by").options, "User")
		self.assertEqual(meta.get_field("attestation_note").fieldtype, "Small Text")
		self.assertEqual(meta.get_field("captured_at").fieldtype, "Datetime")
		for name in ("attested_by", "attestation_note", "captured_at"):
			self.assertIn(name, meta.field_order or [], f"{name} missing from field_order")


class TestInboundOptIn(_Fixture, IntegrationTestCase):
	def test_inbound_start_from_opted_out_sender_records_inbound_row(self):
		gateway = self.gateway_with_stopped_sender()
		self.ingest(gateway, PHONE, "START")
		self.assertFalse(gsvc.is_opted_out(gateway, PHONE))
		rows = self.consent_rows(gateway, PHONE)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["value"], "resume")
		self.assertEqual(rows[0]["source"], "inbound")
		self.assertIsNotNone(rows[0]["captured_at"])

	def test_plain_inbound_message_records_no_consent(self):
		gateway = self.make_gateway("P", policy="Open")
		self.ingest(gateway, FRESH, "hello there")
		self.assertEqual(self.consent_rows(gateway, FRESH), [])

	def test_inbound_start_does_not_override_meta_marketing_stop(self):
		gateway = self.gateway_with_stopped_sender()
		frappe.get_doc(
			{"doctype": "Gateway Consent", "gateway": gateway, "sender_id": PHONE, "category": "marketing_messages",
			 "value": "stop", "source": "user_preferences", "changed_at": frappe.utils.now_datetime(),
			 "meta_timestamp": 1_700_000_000}
		).insert(ignore_permissions=True)
		self.ingest(gateway, PHONE, "START")
		values = [r["value"] for r in self.consent_rows(gateway, PHONE)]
		self.assertEqual(values, ["stop"])


class TestImportOptIns(_Fixture, IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")

	def test_import_requires_attestation(self):
		gateway = self.make_gateway("P", policy="Open")
		for note in ("", "   ", None):
			with self.assertRaises(frappe.ValidationError):
				consent_api.import_opt_ins(gateway=gateway, rows=[FRESH], attestation_note=note)
		self.assertEqual(self.consent_rows(gateway, FRESH), [])

	def test_import_records_import_source_and_attester(self):
		gateway = self.make_gateway("P", policy="Open")
		result = consent_api.import_opt_ins(gateway=gateway, rows=[FRESH], attestation_note=NOTE)
		self.assertEqual(result["created"], 1)
		rows = self.consent_rows(gateway, FRESH)
		self.assertEqual(rows[0]["value"], "resume")
		self.assertEqual(rows[0]["source"], "import")
		self.assertEqual(rows[0]["attested_by"], "Administrator")
		self.assertEqual(rows[0]["attestation_note"], NOTE)

	def test_stopped_numbers_are_skipped_never_reopted(self):
		gateway = self.gateway_with_stopped_sender()
		result = consent_api.import_opt_ins(gateway=gateway, rows=[PHONE, FRESH], attestation_note=NOTE)
		self.assertEqual(result["skipped_opted_out"], 1)
		self.assertEqual(result["created"], 1)
		self.assertEqual(self.consent_rows(gateway, PHONE), [])
		self.assertTrue(gsvc.is_opted_out(gateway, PHONE))

	def test_csv_string_with_header_and_counts(self):
		gateway = self.make_gateway("P", policy="Open")
		csv_text = f"phone\n{FRESH}\n{OTHER}\nnot-a-number\n"
		result = consent_api.import_opt_ins(gateway=gateway, rows=csv_text, attestation_note=NOTE)
		self.assertEqual(result["created"], 2)
		self.assertEqual(result["invalid"], 1)
		self.assertEqual(result["updated"], 0)
		self.assertEqual(result["skipped_opted_out"], 0)

	def test_second_import_counts_as_updated(self):
		gateway = self.make_gateway("P", policy="Open")
		consent_api.import_opt_ins(gateway=gateway, rows=[FRESH], attestation_note=NOTE)
		result = consent_api.import_opt_ins(gateway=gateway, rows=[{"phone": FRESH}], attestation_note=NOTE)
		self.assertEqual((result["created"], result["updated"]), (0, 1))

	def test_import_permission_gate(self):
		gateway = self.make_gateway("P", policy="Open")
		with patch("huf.ai.channels.consent_api.has_capability", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				consent_api.import_opt_ins(gateway=gateway, rows=[FRESH], attestation_note=NOTE)
		self.assertEqual(self.consent_rows(gateway, FRESH), [])


class TestRecordOptIn(_Fixture, IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")

	def test_api_source_default(self):
		gateway = self.make_gateway("P", policy="Open")
		result = consent_api.record_opt_in(gateway=gateway, phone=FRESH)
		self.assertEqual(result["status"], "created")
		rows = self.consent_rows(gateway, FRESH)
		self.assertEqual(rows[0]["source"], "api")
		self.assertEqual(rows[0]["attested_by"], "Administrator")

	def test_api_note_is_stored(self):
		gateway = self.make_gateway("P", policy="Open")
		consent_api.record_opt_in(gateway=gateway, phone=FRESH, note="web form")
		self.assertEqual(self.consent_rows(gateway, FRESH)[0]["attestation_note"], "web form")

	def test_stopped_sender_refused(self):
		gateway = self.gateway_with_stopped_sender()
		result = consent_api.record_opt_in(gateway=gateway, phone=PHONE)
		self.assertEqual(result["status"], "skipped_opted_out")
		self.assertEqual(self.consent_rows(gateway, PHONE), [])

	def test_invalid_phone_reported(self):
		gateway = self.make_gateway("P", policy="Open")
		result = consent_api.record_opt_in(gateway=gateway, phone="abc")
		self.assertEqual(result["status"], "invalid")

	def test_unknown_source_rejected(self):
		gateway = self.make_gateway("P", policy="Open")
		with self.assertRaises(frappe.ValidationError):
			consent_api.record_opt_in(gateway=gateway, phone=FRESH, source="inbound")

	def test_api_permission_gate(self):
		gateway = self.make_gateway("P", policy="Open")
		with patch("huf.ai.channels.consent_api.has_capability", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				consent_api.record_opt_in(gateway=gateway, phone=FRESH)
		self.assertEqual(self.consent_rows(gateway, FRESH), [])
