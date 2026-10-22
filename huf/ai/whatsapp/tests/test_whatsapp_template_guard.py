"""Tests for the Huf-owned WhatsApp template guard and the Template Extra sidecar."""

import unittest
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.gateway_adapters import whatsapp_template_guard as g

ACC = "GUARD-ACC"
TPL = "guard_tpl-en"


def has_connector():
	return bool(frappe.db.exists("DocType", "WhatsApp Templates"))


class TestExtra(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		g.delete_extra(ACC, TPL)

	def tearDown(self):
		g.delete_extra(ACC, TPL)
		frappe.db.rollback()

	def test_roundtrip(self):
		self.assertIsNone(g.get_extra(ACC, TPL))
		g.upsert_extra(
			ACC,
			TPL,
			parameter_format="NAMED",
			named_samples={"name": "Ann, Jr"},
			ttl_seconds=600,
			header_format="VIDEO",
			components_json=[{"type": "BODY", "text": "Hi {{name}}"}],
			created_via="Huf",
			template_id="123",
		)
		e = g.get_extra(ACC, TPL)
		self.assertEqual(e["parameter_format"], "NAMED")
		self.assertEqual(e["named_samples"], {"name": "Ann, Jr"})
		self.assertEqual(e["ttl_seconds"], 600)
		self.assertEqual(e["header_format"], "VIDEO")
		self.assertEqual(e["components_json"][0]["type"], "BODY")
		self.assertTrue(e["last_synced_at"])
		g.upsert_extra(ACC, TPL, ttl_seconds=60)
		e = g.get_extra(ACC, TPL)
		self.assertEqual((e["ttl_seconds"], e["header_format"]), (60, "VIDEO"))
		self.assertEqual(frappe.db.count("WhatsApp Template Extra", {"template": TPL}), 1)

	def test_unknown_field_and_account_scoping(self):
		with self.assertRaises(frappe.ValidationError):
			g.upsert_extra(ACC, TPL, bogus=1)
		g.upsert_extra(ACC, TPL, created_via="Huf")
		self.assertIsNone(g.get_extra("OTHER", TPL))

	def test_ownership(self):
		doc = frappe._dict(name=TPL, whatsapp_account=ACC, flags=frappe._dict())
		self.assertFalse(g.is_huf_owned(doc))
		g.upsert_extra(ACC, TPL, created_via="Meta sync")
		self.assertFalse(g.is_huf_owned(doc))
		g.upsert_extra(ACC, TPL, created_via="Huf")
		self.assertTrue(g.is_huf_owned(doc))
		g.delete_extra(ACC, TPL)
		doc.flags.huf_mirror = True
		self.assertTrue(g.is_huf_owned(doc))

	def test_permissions(self):
		perms = {p.role: p for p in frappe.get_meta("WhatsApp Template Extra").permissions}
		self.assertEqual(set(perms), {"System Manager", "Huf Admin"})
		self.assertTrue(all(p.read and p.write and p.create for p in perms.values()))

	def test_guard_function_unit(self):
		g.upsert_extra(ACC, TPL, created_via="Huf")
		doc = frappe.get_doc({"doctype": "ToDo", "description": "x"})
		doc.name, doc.whatsapp_account = TPL, ACC
		with patch.object(type(doc), "is_new", return_value=False):
			with self.assertRaises(frappe.ValidationError) as cm:
				g.guard_template_write(doc, "validate")
			self.assertIn("managed by Huf", str(cm.exception))
			with g.huf_template_write():
				g.guard_template_write(doc, "validate")
			self.assertFalse(frappe.flags.get(g.WRITE_FLAG))
			with self.assertRaises(frappe.ValidationError):
				g.guard_template_write(doc, "on_trash")


class TestHooksNoConnector(unittest.TestCase):
	def test_hooks_registered_and_import_safe(self):
		hooks = frappe.get_hooks("doc_events")["WhatsApp Templates"]
		for ev in ("before_validate", "validate", "before_save", "on_trash"):
			self.assertTrue(frappe.get_attr(hooks[ev][0]))
		if not has_connector():
			self.assertNotIn("WhatsApp Templates", frappe.get_doc_hooks().get("ToDo", {}))
			frappe.get_doc({"doctype": "ToDo", "description": "no connector ok"}).insert(ignore_permissions=True)
			frappe.db.rollback()


class TestDeskGuard(IntegrationTestCase):
	def setUp(self):
		if not has_connector():
			self.skipTest("frappe_whatsapp not installed")
		frappe.set_user("Administrator")
		self.name = "guardtest-en"
		for dt in ("WhatsApp Templates",):
			if frappe.db.exists(dt, self.name):
				frappe.delete_doc(dt, self.name, force=True, ignore_on_trash=True)
		doc = frappe.new_doc("WhatsApp Templates")
		doc.template_name = "guardtest"
		doc.language_code = "en"
		doc.category = "UTILITY"
		doc.template = "Hello"
		doc.name = self.name
		doc.whatsapp_account = ACC
		doc.owner = doc.modified_by = "Administrator"
		doc.creation = doc.modified = frappe.utils.now()
		doc.docstatus = 0
		doc.db_insert()
		g.upsert_extra(ACC, self.name, created_via="Huf")

	def tearDown(self):
		g.delete_extra(ACC, self.name)
		frappe.db.rollback()

	def _no_graph(self):
		return (
			patch("frappe.integrations.utils.make_request", side_effect=AssertionError("graph call")),
			patch("frappe.integrations.utils.make_post_request", side_effect=AssertionError("graph call")),
			patch("requests.request", side_effect=AssertionError("graph call")),
			patch("requests.post", side_effect=AssertionError("graph call")),
			patch("requests.get", side_effect=AssertionError("graph call")),
		)

	def test_desk_save_refused_without_graph_call(self):
		ps = self._no_graph()
		for p in ps:
			p.start()
		self.addCleanup(lambda: [p.stop() for p in ps])
		doc = frappe.get_doc("WhatsApp Templates", self.name)
		doc.flags.ignore_links = True
		doc.flags.ignore_mandatory = True
		doc.template = "Changed"
		with self.assertRaises(frappe.ValidationError) as cm:
			doc.save()
		self.assertIn("managed by Huf", str(cm.exception))

	def test_desk_delete_refused_via_subclass(self):
		ps = self._no_graph()
		for p in ps:
			p.start()
		self.addCleanup(lambda: [p.stop() for p in ps])
		doc = g.GuardedWhatsAppTemplates(frappe.get_doc("WhatsApp Templates", self.name).as_dict())
		with self.assertRaises(frappe.ValidationError):
			doc.on_trash()
		with self.assertRaises(frappe.ValidationError):
			doc.run_method("on_trash")
		self.assertTrue(frappe.db.exists("WhatsApp Templates", self.name))

	def test_save_allowed_under_flag(self):
		doc = frappe.get_doc("WhatsApp Templates", self.name)
		doc.flags.ignore_links = True
		doc.flags.ignore_mandatory = True
		doc.template = "Changed"
		with g.huf_template_write(), patch.object(type(doc), "update_template", return_value=None):
			doc.save()
		self.assertEqual(frappe.db.get_value("WhatsApp Templates", self.name, "template"), "Changed")

	def test_non_huf_row_unaffected(self):
		g.upsert_extra(ACC, self.name, created_via="Meta sync")
		doc = frappe.get_doc("WhatsApp Templates", self.name)
		doc.flags.ignore_links = True
		doc.flags.ignore_mandatory = True
		doc.template = "Changed"
		with patch.object(type(doc), "update_template", return_value=None):
			doc.save()
