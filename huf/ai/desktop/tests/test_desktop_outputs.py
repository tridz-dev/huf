# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""REAL DB tests for ``upload_desktop_output`` and ``search_skills_and_agents`` (huf.ai.desktop_outputs).

A real desktop lease (registered through the real endpoint, secret held in ``desktop_test_helpers``), real
users, a real Agent and desktop-hosted Agent Conversation; the whitelisted functions are called directly.

Run with:
	bench --site <site> run-tests --app huf --module huf.ai.tests.test_desktop_outputs
"""

import base64
import json

import frappe

from huf.ai import desktop_output_rules as rules
from huf.ai import desktop_outputs as do
from huf.testing import desktop_test_helpers as h
from huf.ai.desktop.tests.test_desktop_remote_sessions import RemoteBase

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def b64(raw):
	return base64.b64encode(raw).decode("ascii")


class TestUploadDesktopOutput(RemoteBase):
	def setUp(self):
		super().setUp()
		self.make_agent()
		self.register()
		self.conv = self.hosted_conversation()
		self.secret = h.secret_of(self.exec_id)

	def up(self, user=None, filename="notes.txt", content=None, **over):
		frappe.set_user(user or self.owner)
		kw = {
			"executor_id": self.exec_id,
			"conversation": self.conv,
			"filename": filename,
			"content_b64": b64(b"hello") if content is None else content,
			"lease_secret": self.secret,
		}
		kw.update(over)
		return do.upload_desktop_output(**kw)

	def test_guest_rejected(self):
		with self.assertRaises(frappe.PermissionError):
			self.up(user="Guest")

	def test_wrong_user_rejected(self):
		with self.assertRaises(frappe.PermissionError):
			self.up(user=self.other)

	def test_secret_missing_wrong_and_unknown_lease(self):
		for secret in (None, "", "x" * 43, self.secret[:-1] + ("A" if self.secret[-1] != "A" else "B")):
			with self.assertRaises(frappe.PermissionError, msg=repr(secret)):
				self.up(lease_secret=secret)
		with self.assertRaises(frappe.PermissionError):
			self.up(executor_id="exec-nope-0000")
		with self.assertRaises(frappe.PermissionError):
			self.up(executor_id=None)

	def test_expired_lease_rejected(self):
		frappe.set_user(self.owner)
		h.unregister_desktop_executor(executor_id=self.exec_id)
		with self.assertRaises(frappe.PermissionError):
			self.up()

	def assert_not_hosted(self, r):
		self.assertEqual(r["ok"], False)
		self.assertEqual(r["code"], "not_hosted")

	def test_conversation_not_hosted_by_device(self):
		frappe.set_user(self.owner)
		web = frappe.get_doc(
			{
				"doctype": "Agent Conversation",
				"agent": self.agent,
				"title": "web",
				"session_id": frappe.generate_hash(length=12),
			}
		)
		web.insert(ignore_permissions=True)
		self.track_conversation(web.name)
		for conv in (web.name, "does-not-exist", None):
			self.assert_not_hosted(self.up(conversation=conv))
		# a desktop conversation hosted by a different device
		frappe.db.set_value("Agent Conversation", self.conv, "host_device_id", "0" * 16)
		self.assert_not_hosted(self.up())

	def test_other_users_conversation(self):
		frappe.set_user("Administrator")
		frappe.db.set_value("Agent Conversation", self.conv, "owner", self.other)
		someone_else = self.up()
		self.assert_not_hosted(someone_else)
		# indistinguishable from a conversation that does not exist (no existence leak)
		self.assertEqual(someone_else, self.up(conversation="does-not-exist"))

	def test_bad_filenames(self):
		cases = {
			"../../etc/passwd": "secret_name",
			"..\\..\\id_rsa": "secret_name",
			".hidden.txt": "bad_filename",
			"..": "bad_filename",
			"": "bad_filename",
			"a\x00.txt": "bad_filename",
			"prod.env": "secret_name",
			"my-credentials.json": "secret_name",
			"x.exe": "type_not_allowed",
			"noext": "type_not_allowed",
			("a" * 200) + ".txt": "bad_filename",
		}
		for name, code in cases.items():
			out = self.up(filename=name)
			self.assertEqual((out["ok"], out["code"]), (False, code), name)
		self.assertFalse(frappe.db.exists("Artifact", {"conversation": self.conv}))

	def test_traversal_keeps_basename_only(self):
		out = self.up(filename="../../dir/report.txt")
		self.assertTrue(out["ok"])
		self.assertEqual(frappe.db.get_value("Artifact", out["artifact"], "title"), "report.txt")

	def test_oversize_and_bad_payloads(self):
		big = b64(b"a" * (rules.MAX_UPLOAD_BYTES + 1))
		self.assertEqual(self.up(content=big)["code"], "too_large")
		self.assertEqual(self.up(content="!!not base64!!")["code"], "bad_encoding")
		self.assertEqual(self.up(content="")["code"], "empty")
		self.assertEqual(self.up(filename="a.png", content=b64(b"%PDF-1"))["code"], "type_mismatch")
		self.assertEqual(self.up(filename="a.pdf", content=b64(PNG))["code"], "type_mismatch")
		self.assertFalse(frappe.db.exists("Artifact", {"conversation": self.conv}))

	def test_max_size_fits_request_limit(self):
		# encoded body must fit Frappe's default 25 MiB request cap with headroom
		self.assertLess((rules.MAX_UPLOAD_BYTES * 4 + 2) // 3, 22 * 1024 * 1024)

	def test_text_happy_path(self):
		out = self.up(filename="notes.md", content=b64("# Hi ☃".encode()))
		self.assertTrue(out["ok"])
		self.assertIsNone(out["file_url"])
		self.assertEqual(out["content_type"], "text/markdown")
		doc = frappe.get_doc("Artifact", out["artifact"])
		self.assertEqual(
			(doc.title, doc.artifact_type, doc.language, doc.conversation, doc.content),
			("notes.md", "markdown", "md", self.conv, "# Hi ☃"),
		)
		self.assertEqual(doc.owner, self.owner)
		self.assertGreater(doc.size_bytes, 0)
		self.assertTrue(doc.content_hash)

	def test_html_stored_as_html_type(self):
		out = self.up(filename="page.html", content=b64(b"<script>alert(1)</script>"))
		# Rendered by the frontend in a sandboxed iframe (sandbox="" / no scripts); the server stores it verbatim.
		self.assertEqual(frappe.db.get_value("Artifact", out["artifact"], "artifact_type"), "html")

	def test_binary_happy_path(self):
		out = self.up(filename="shot.png", content=b64(PNG))
		self.assertTrue(out["ok"])
		self.assertEqual((out["size"], out["content_type"]), (len(PNG), "image/png"))
		doc = frappe.get_doc("Artifact", out["artifact"])
		self.assertEqual(doc.artifact_type, "image")
		ptr = json.loads(doc.content)
		self.assertEqual(
			ptr,
			{
				"file_url": out["file_url"],
				"filename": "shot.png",
				"content_type": "image/png",
				"size": len(PNG),
			},
		)
		f = frappe.get_doc("File", {"attached_to_doctype": "Artifact", "attached_to_name": doc.name})
		self.assertEqual(f.is_private, 1)
		self.assertEqual(f.file_url, out["file_url"])
		self.assertEqual(f.get_content(), PNG)


class TestSearchSkillsAndAgents(RemoteBase):
	def setUp(self):
		super().setUp()
		self.tag = "zq" + frappe.generate_hash(length=6)
		self.public = self.make_agent(agent_name=f"{self.tag} public")
		self.hidden = self.make_agent(agent_name=f"{self.tag} hidden", allow_all_users=0)
		self.off = self.make_agent(agent_name=f"{self.tag} off", disabled=1)
		for status in ("Active", "Draft", "Error", "Disabled"):
			frappe.get_doc(
				{
					"doctype": "Skill",
					"skill_name": f"{self.tag}-{status.lower()}",
					"title": f"{self.tag} {status}",
					"description": f"{self.tag} skill",
					"status": status,
					"source_type": "Local",
				}
			).insert(ignore_permissions=True)
			self.made.append(("Skill", f"{self.tag}-{status.lower()}"))
		frappe.db.commit()

	def search(self, user=None, **kw):
		frappe.set_user(user or self.owner)
		return do.search_skills_and_agents(**kw)

	def test_guest_rejected(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			frappe.is_whitelisted(do.search_skills_and_agents)

	def test_status_and_permission_filtering(self):
		rows = self.search(query=self.tag)
		names = {(r["kind"], r["id"]) for r in rows}
		self.assertIn(("agent", self.public.name), names)
		self.assertIn(("skill", f"{self.tag}-active"), names)
		self.assertNotIn(("agent", self.hidden.name), names)  # restricted agent, caller not allowed
		self.assertNotIn(("agent", self.off.name), names)  # disabled
		for st in ("draft", "error", "disabled"):
			self.assertNotIn(("skill", f"{self.tag}-{st}"), names)
		self.assertTrue(all(r["enabled"] for r in rows if r["kind"] == "skill"))

	def test_kind_filter_and_bad_kind(self):
		self.assertEqual({r["kind"] for r in self.search(query=self.tag, kind="skill")}, {"skill"})
		self.assertEqual({r["kind"] for r in self.search(query=self.tag, kind="agent")}, {"agent"})
		self.assertEqual({r["kind"] for r in self.search(query=self.tag, kind="bogus")}, {"agent", "skill"})

	def test_ranking_name_before_description(self):
		frappe.set_user("Administrator")
		self.make_agent(agent_name="other name", description=f"mentions {self.tag}x only in description")
		frappe.db.commit()
		rows = self.search(query=f"{self.tag}", kind="agent")
		self.assertEqual(rows[0]["id"], self.public.name)
		self.assertEqual(rows[-1]["name"], "other name")
		self.assertEqual(self.search(query=f"{self.tag} nomatchterm"), [])

	def test_limit_and_garbage_input(self):
		self.assertEqual(len(self.search(query=self.tag, limit=1)), 1)
		self.assertEqual(len(self.search(query=self.tag, limit="junk")) >= 1, True)
		self.assertLessEqual(len(self.search(limit=100000)), rules.MAX_RESULTS)
		self.assertEqual(self.search(query="%'; drop table tabAgent; --"), [])
		self.assertTrue(frappe.db.exists("DocType", "Agent"))
		self.assertEqual(self.search(query="a" * 100000), [])
