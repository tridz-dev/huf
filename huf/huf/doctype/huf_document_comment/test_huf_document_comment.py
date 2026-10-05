import frappe
from frappe.tests import IntegrationTestCase

from huf.ai import document_comment_api as api

AUTHOR = "hufcm_author@example.com"
RO = "hufcm_ro@example.com"
RW = "hufcm_rw@example.com"
STRANGER = "hufcm_stranger@example.com"


def _ensure_user(email):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)


class TestHUFDocumentComment(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		for u in (AUTHOR, RO, RW, STRANGER):
			_ensure_user(u)
		frappe.set_user(AUTHOR)
		self.doc = frappe.get_doc({"doctype": "HUF Document", "title": "Commented"}).insert()
		frappe.set_user("Administrator")
		frappe.share.add("HUF Document", self.doc.name, RO, read=1)
		frappe.share.add("HUF Document", self.doc.name, RW, read=1, write=1)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def as_user(self, user, fn, *a, **kw):
		frappe.set_user(user)
		try:
			return fn(*a, **kw)
		finally:
			frappe.set_user("Administrator")

	def test_stranger_cannot_list_or_add(self):
		with self.assertRaises(frappe.PermissionError):
			self.as_user(STRANGER, api.list_document_comments, self.doc.name)
		with self.assertRaises(frappe.PermissionError):
			self.as_user(STRANGER, api.add_document_comment, self.doc.name, "hi")

	def test_readonly_sharee_can_add_and_list(self):
		c = self.as_user(RO, api.add_document_comment, self.doc.name, "from ro")
		self.assertEqual(c["author"], RO)
		self.assertFalse(c["resolved"])
		self.assertEqual(set(c), {"name", "document", "body", "author", "author_full_name", "creation", "resolved"})
		items = self.as_user(RO, api.list_document_comments, self.doc.name)
		self.assertEqual([i["name"] for i in items], [c["name"]])
		self.assertEqual(len(self.as_user(AUTHOR, api.list_document_comments, self.doc.name)), 1)

	def test_oldest_first(self):
		a = self.as_user(AUTHOR, api.add_document_comment, self.doc.name, "one")
		b = self.as_user(RO, api.add_document_comment, self.doc.name, "two")
		frappe.db.set_value("HUF Document Comment", a["name"], "creation", "2020-01-01 00:00:00")
		names = [i["name"] for i in self.as_user(AUTHOR, api.list_document_comments, self.doc.name)]
		self.assertEqual(names, [a["name"], b["name"]])

	def test_delete_permissions(self):
		c = self.as_user(AUTHOR, api.add_document_comment, self.doc.name, "mine")
		r = self.as_user(RO, api.add_document_comment, self.doc.name, "ro's")
		with self.assertRaises(frappe.PermissionError):
			self.as_user(RO, api.delete_document_comment, c["name"])
		with self.assertRaises(frappe.PermissionError):
			self.as_user(STRANGER, api.delete_document_comment, c["name"])
		self.assertEqual(self.as_user(RO, api.delete_document_comment, r["name"]), {"name": r["name"]})
		self.assertEqual(self.as_user(RW, api.delete_document_comment, c["name"]), {"name": c["name"]})
		w = self.as_user(RW, api.add_document_comment, self.doc.name, "rw's")
		self.as_user(AUTHOR, api.delete_document_comment, w["name"])  # doc owner has write
		self.assertFalse(frappe.db.exists("HUF Document Comment", w["name"]))

	def test_resolved_permissions(self):
		c = self.as_user(RO, api.add_document_comment, self.doc.name, "ro's")
		o = self.as_user(AUTHOR, api.add_document_comment, self.doc.name, "owner's")
		# comment author may resolve own
		r = self.as_user(RO, api.set_comment_resolved, c["name"], True)
		self.assertTrue(r["resolved"])
		self.assertEqual(frappe.db.get_value("HUF Document Comment", c["name"], "resolved_by"), RO)
		# read-only sharee cannot resolve someone else's
		with self.assertRaises(frappe.PermissionError):
			self.as_user(RO, api.set_comment_resolved, o["name"], True)
		with self.assertRaises(frappe.PermissionError):
			self.as_user(STRANGER, api.set_comment_resolved, c["name"], False)
		# write sharee can; string values accepted
		self.assertTrue(self.as_user(RW, api.set_comment_resolved, o["name"], "1")["resolved"])
		self.assertTrue(self.as_user(RW, api.set_comment_resolved, o["name"], "true")["resolved"])
		self.assertFalse(self.as_user(RW, api.set_comment_resolved, o["name"], "0")["resolved"])
		self.assertFalse(self.as_user(RW, api.set_comment_resolved, c["name"], "false")["resolved"])
		self.assertIsNone(frappe.db.get_value("HUF Document Comment", c["name"], "resolved_by"))

	def test_html_stripped(self):
		c = self.as_user(AUTHOR, api.add_document_comment, self.doc.name, "<b>hi</b><script>x()</script> there")
		self.assertNotIn("<", c["body"])
		self.assertIn("hi", c["body"])

	def test_blank_and_oversize_rejected(self):
		for bad in ("", "   ", "<br>"):
			with self.assertRaises(frappe.ValidationError):
				self.as_user(AUTHOR, api.add_document_comment, self.doc.name, bad)
		with self.assertRaises(frappe.ValidationError):
			self.as_user(AUTHOR, api.add_document_comment, self.doc.name, "x" * 5001)
		self.as_user(AUTHOR, api.add_document_comment, self.doc.name, "x" * 5000)

	def test_framework_permission_hooks(self):
		c = self.as_user(RO, api.add_document_comment, self.doc.name, "ro's")
		doc = frappe.get_doc("HUF Document Comment", c["name"])
		from huf.huf.doctype.huf_document_comment.huf_document_comment import (
			get_permission_query_conditions,
			has_permission,
		)

		# Hook logic (the API enforces via the same function; generic REST is role-gated
		# to System Manager because the DocType has no other role rows).
		self.assertTrue(has_permission(doc, "read", RO))
		self.assertFalse(has_permission(doc, "read", STRANGER))
		self.assertTrue(has_permission(doc, "delete", RO))  # author
		self.assertFalse(has_permission(doc, "delete", STRANGER))
		self.assertTrue(has_permission(doc, "delete", RW))
		self.assertEqual(get_permission_query_conditions("Administrator"), "")
		ids = frappe.db.sql_list(
			f"select name from `tabHUF Document Comment` where {get_permission_query_conditions(STRANGER)}"
		)
		self.assertNotIn(c["name"], ids)
		ids = frappe.db.sql_list(
			f"select name from `tabHUF Document Comment` where {get_permission_query_conditions(RO)}"
		)
		self.assertIn(c["name"], ids)

	def test_deleting_document_removes_comments(self):
		c = self.as_user(RO, api.add_document_comment, self.doc.name, "bye")
		frappe.delete_doc("HUF Document", self.doc.name)
		self.assertFalse(frappe.db.exists("HUF Document Comment", c["name"]))
