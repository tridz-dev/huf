import frappe
from frappe.tests import IntegrationTestCase

from huf.ai import document_api

USER_A = "hufdoc_a@example.com"
USER_B = "hufdoc_b@example.com"


def _ensure_user(email):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)


def _make_doc(title, user=None, **kw):
	prev = frappe.session.user
	if user:
		frappe.set_user(user)
	try:
		d = frappe.get_doc({"doctype": "HUF Document", "title": title, **kw})
		d.insert()
		return d
	finally:
		frappe.set_user(prev)


class TestHUFDocument(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		_ensure_user(USER_A)
		_ensure_user(USER_B)
		if not frappe.db.exists("Agent", "HD Test Agent"):
			frappe.get_doc(
				{"doctype": "Agent", "agent_name": "HD Test Agent", "agent_modality": "Both",
				 "instructions": "fixture"}
			).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")

	def _conversation(self, owner):
		c = frappe.new_doc("Agent Conversation")
		c.agent = "HD Test Agent"
		c.session_id = frappe.generate_hash(length=10)
		c.insert(ignore_permissions=True)
		c.db_set("owner", owner, update_modified=False)
		return c

	def _artifact(self, conv, **kw):
		data = {"doctype": "Artifact", "title": "Spec", "artifact_type": "markdown", "language": "markdown",
			"content": "# Hi\n\nbody text zebra", "conversation": conv.name, "agent": "HD Test Agent"}
		data.update(kw)
		a = frappe.get_doc(data)
		a.insert(ignore_permissions=True)
		return a

	def test_self_parent_and_cycle_rejected(self):
		a = _make_doc("A")
		b = _make_doc("B", parent_document=a.name)
		a.parent_document = a.name
		self.assertRaises(frappe.ValidationError, a.save)
		a.reload()
		a.parent_document = b.name
		self.assertRaises(frappe.ValidationError, a.save)

	def test_blank_title_rejected(self):
		d = _make_doc("x")
		d.title = "   "
		self.assertRaises(frappe.ValidationError, d.save)

	def test_delete_with_children_blocked(self):
		a = _make_doc("P")
		b = _make_doc("C", parent_document=a.name)
		self.assertRaises(frappe.ValidationError, a.delete)
		b.delete()
		a.delete()

	def test_idempotent_save(self):
		conv = self._conversation("Administrator")
		art = self._artifact(conv)
		r1 = document_api.save_artifact_as_document(art.name)
		art.db_set("content", "# Hi v2")
		r2 = document_api.save_artifact_as_document(art.name)
		self.assertEqual(r1["name"], r2["name"])
		self.assertEqual(frappe.db.count("HUF Document", {"source_artifact": art.name}), 1)
		d = frappe.get_doc("HUF Document", r1["name"])
		self.assertEqual(d.body_markdown, "# Hi v2")
		self.assertEqual(d.source_conversation, conv.name)
		self.assertEqual(d.created_by_agent, "HD Test Agent")

	def test_html_artifact_refused(self):
		conv = self._conversation("Administrator")
		art = self._artifact(conv, artifact_type="html", language="html", content="<p>x</p>")
		self.assertRaises(frappe.ValidationError, document_api.save_artifact_as_document, art.name)

	def test_save_requires_conversation_access(self):
		conv = self._conversation(USER_A)
		art = self._artifact(conv)
		frappe.set_user(USER_B)
		self.assertRaises(frappe.PermissionError, document_api.save_artifact_as_document, art.name)

	def test_permission_isolation_and_share(self):
		d = _make_doc("Private", user=USER_A)
		frappe.set_user(USER_B)
		self.assertNotIn(d.name, [r.name for r in document_api.list_documents()])
		self.assertRaises(frappe.PermissionError, document_api.get_document_html, d.name)
		frappe.set_user("Administrator")
		frappe.share.add("HUF Document", d.name, USER_B, read=1)
		frappe.set_user(USER_B)
		self.assertIn(d.name, [r.name for r in document_api.list_documents()])
		self.assertTrue(document_api.get_document_html(d.name))
		frappe.set_user("Administrator")
		frappe.share.remove("HUF Document", d.name, USER_B)

	def test_list_tree_and_search(self):
		p = _make_doc("Root zzq")
		c = _make_doc("Child", parent_document=p.name, keywords="kiwiword", body_markdown="needle123")
		roots = {r.name: r for r in document_api.list_documents()}
		self.assertEqual(roots[p.name]["child_count"], 1)
		self.assertNotIn(c.name, roots)
		kids = document_api.list_documents(parent=p.name)
		self.assertEqual([k.name for k in kids], [c.name])
		for q in ("kiwiword", "needle123", "Root zzq"):
			self.assertTrue(document_api.list_documents(q=q), q)
		self.assertEqual(document_api.list_documents(q="nomatchxyz"), [])

	def test_html_cache(self):
		d = _make_doc("H", body_markdown="# Title here")
		html = document_api.get_document_html(d.name)
		self.assertIn("Title here", html)
		self.assertEqual(frappe.db.get_value("HUF Document", d.name, "body_html"), html)
		d.reload()
		d.body_markdown = "# Changed"
		d.save()
		self.assertFalse(frappe.db.get_value("HUF Document", d.name, "body_html"))
		self.assertIn("Changed", document_api.get_document_html(d.name))

	def test_client_body_html_dropped(self):
		d = _make_doc("Cache", body_markdown="# x", body_html="<script>evil()</script>")
		self.assertFalse(frappe.db.get_value("HUF Document", d.name, "body_html"))
		html = document_api.get_document_html(d.name)
		d.reload()
		d.body_html = "<b>forged</b>"
		d.title = "Cache2"
		d.save()
		self.assertFalse(frappe.db.get_value("HUF Document", d.name, "body_html"))
		self.assertIn("<h1>x</h1>", document_api.get_document_html(d.name))

	def test_save_artifact_per_owner(self):
		conv = self._conversation("Administrator")
		art = self._artifact(conv)
		frappe.set_user("Administrator")
		r_admin = document_api.save_artifact_as_document(art.name)
		# make the artifact reachable by USER_B
		conv.db_set("owner", USER_B, update_modified=False)
		frappe.set_user(USER_B)
		r_b = document_api.save_artifact_as_document(art.name)
		self.assertNotEqual(r_admin["name"], r_b["name"])
		self.assertEqual(frappe.db.get_value("HUF Document", r_b["name"], "owner"), USER_B)
		self.assertEqual(frappe.db.get_value("HUF Document", r_admin["name"], "owner"), "Administrator")
		self.assertEqual(document_api.save_artifact_as_document(art.name)["name"], r_b["name"])

	def test_shared_child_listed_as_root(self):
		p = _make_doc("PrivParent", user=USER_A)
		c = _make_doc("SharedChild", user=USER_A, parent_document=p.name)
		frappe.set_user("Administrator")
		frappe.share.add("HUF Document", c.name, USER_B, read=1)
		frappe.set_user(USER_B)
		roots = [r.name for r in document_api.list_documents()]
		self.assertIn(c.name, roots)
		self.assertNotIn(p.name, roots)
		frappe.set_user("Administrator")
		frappe.share.remove("HUF Document", c.name, USER_B)

	def test_like_wildcards_escaped(self):
		_make_doc("Plain wildcard test")
		self.assertEqual(document_api.list_documents(q="%"), [])
		self.assertEqual(document_api.list_documents(q="_"), [])
		self.assertEqual(document_api.list_documents(q="\\"), [])
		self.assertTrue(document_api.list_documents(q="x" * 500) == [])

	def test_parent_must_be_readable(self):
		p = _make_doc("OtherPrivate", user=USER_A)
		with self.assertRaises(frappe.ValidationError):
			_make_doc("Sneaky", user=USER_B, parent_document=p.name)

	def _share(self, doc, user, write=0):
		frappe.set_user("Administrator")
		frappe.share.add("HUF Document", doc.name, user, read=1, write=write)

	def test_create_workspace_document(self):
		frappe.set_user(USER_A)
		r = document_api.create_workspace_document("  Fresh  ")
		self.assertEqual(r["title"], "Fresh")
		self.assertFalse(r["parent_document"])
		d = frappe.get_doc("HUF Document", r["name"])
		self.assertEqual(d.owner, USER_A)
		self.assertFalse(d.body_markdown)
		child = document_api.create_workspace_document("Kid", r["name"])
		self.assertEqual(child["parent_document"], r["name"])
		with self.assertRaises(frappe.ValidationError):
			document_api.create_workspace_document("   ")

	def test_create_under_parent_permissions(self):
		p = _make_doc("P", user=USER_A)
		self._share(p, USER_B, write=0)
		frappe.set_user(USER_B)
		with self.assertRaises(frappe.PermissionError):
			document_api.create_workspace_document("Nope", p.name)
		self._share(p, USER_B, write=1)
		frappe.set_user(USER_B)
		r = document_api.create_workspace_document("Allowed", p.name)
		self.assertEqual(r["parent_document"], p.name)
		self.assertEqual(frappe.db.get_value("HUF Document", r["name"], "owner"), USER_B)
		# unrelated private parent
		q = _make_doc("Q", user=USER_A)
		with self.assertRaises((frappe.PermissionError, frappe.ValidationError)):
			document_api.create_workspace_document("Sneak", q.name)

	def test_rename_document(self):
		d = _make_doc("Old", user=USER_A)
		frappe.set_user(USER_A)
		self.assertEqual(document_api.rename_document(d.name, " New ")["title"], "New")
		with self.assertRaises(frappe.ValidationError):
			document_api.rename_document(d.name, "  ")
		self.assertEqual(frappe.db.get_value("HUF Document", d.name, "title"), "New")
		self._share(d, USER_B, write=0)
		frappe.set_user(USER_B)
		with self.assertRaises(frappe.PermissionError):
			document_api.rename_document(d.name, "Hijack")
		self._share(d, USER_B, write=1)
		frappe.set_user(USER_B)
		self.assertEqual(document_api.rename_document(d.name, "ByB")["title"], "ByB")

	def test_move_document(self):
		a = _make_doc("A", user=USER_A)
		b = _make_doc("B", user=USER_A, parent_document=a.name)
		frappe.set_user(USER_A)
		with self.assertRaises(frappe.ValidationError):
			document_api.move_document(a.name, a.name)
		with self.assertRaises(frappe.ValidationError):
			document_api.move_document(a.name, b.name)  # cycle
		r = document_api.move_document(b.name, None)
		self.assertFalse(r["parent_document"])
		self.assertFalse(frappe.db.get_value("HUF Document", b.name, "parent_document"))
		r = document_api.move_document(b.name, a.name)
		self.assertEqual(r["parent_document"], a.name)

	def test_move_permissions(self):
		doc = _make_doc("Doc", user=USER_A)
		target = _make_doc("Target", user=USER_A)
		self._share(doc, USER_B, write=1)
		self._share(target, USER_B, write=0)
		frappe.set_user(USER_B)
		with self.assertRaises(frappe.PermissionError):
			document_api.move_document(doc.name, target.name)  # no write on new parent
		self._share(target, USER_B, write=1)
		frappe.set_user(USER_B)
		self.assertEqual(document_api.move_document(doc.name, target.name)["parent_document"], target.name)
		# read-only share cannot move
		ro = _make_doc("RO", user=USER_A)
		self._share(ro, USER_B, write=0)
		frappe.set_user(USER_B)
		with self.assertRaises(frappe.PermissionError):
			document_api.move_document(ro.name, None)

	def test_delete_orphan_safe(self):
		p = _make_doc("P", user=USER_A)
		self._share(p, USER_B, write=1)
		frappe.set_user(USER_B)
		r = document_api.create_workspace_document("BKid", p.name)
		frappe.set_user(USER_A)
		self.assertFalse(frappe.has_permission("HUF Document", "read", r["name"]))
		frappe.delete_doc("HUF Document", p.name)
		self.assertFalse(frappe.db.exists("HUF Document", p.name))
		self.assertTrue(frappe.db.exists("HUF Document", r["name"]))
		self.assertFalse(frappe.db.get_value("HUF Document", r["name"], "parent_document"))
		self.assertEqual(frappe.db.get_value("HUF Document", r["name"], "owner"), USER_B)

	def test_delete_blocked_by_readable_child(self):
		p = _make_doc("P2", user=USER_A)
		c = _make_doc("Mine", user=USER_A, parent_document=p.name)
		frappe.set_user(USER_A)
		with self.assertRaises(frappe.ValidationError):
			frappe.delete_doc("HUF Document", p.name)
		self.assertEqual(frappe.db.get_value("HUF Document", c.name, "parent_document"), p.name)

	def test_move_requires_write_on_old_parent(self):
		old = _make_doc("Old", user=USER_A)
		doc = _make_doc("Doc", user=USER_A, parent_document=old.name)
		new = _make_doc("New", user=USER_A)
		self._share(doc, USER_B, write=1)
		self._share(new, USER_B, write=1)
		self._share(old, USER_B, write=0)
		frappe.set_user(USER_B)
		with self.assertRaises(frappe.PermissionError):
			document_api.move_document(doc.name, new.name)
		frappe.set_user(USER_A)
		self.assertEqual(document_api.move_document(doc.name, new.name)["parent_document"], new.name)

	def test_list_can_write_flag(self):
		d = _make_doc("Flag", user=USER_A)
		self._share(d, USER_B, write=0)
		frappe.set_user(USER_B)
		rows = [r for r in document_api.list_documents() if r["name"] == d.name]
		self.assertFalse(rows[0]["can_write"])
		frappe.set_user(USER_A)
		rows = [r for r in document_api.list_documents() if r["name"] == d.name]
		self.assertTrue(rows[0]["can_write"])
