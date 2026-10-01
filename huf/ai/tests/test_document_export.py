# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Document export end to end: real PDF/DOCX bytes, no mocks of the renderer.

Covers the three entry points the Export menu and the agent use:

- ``export_artifact``          (a saved Artifact row, right-pane toolbar)
- ``export_document_content``  (an inline chat card with no row, stateless)
- ``handle_export_document``   (the agent tool, by content, id or title)

Bytes are validated for real: %PDF header and a countable page tree, a DOCX that is
a zip with word/document.xml containing the document's text, and the markdown
format returning the source untouched.

Run with:
	bench --site <site> run-tests --app huf --module huf.ai.tests.test_document_export
"""

import base64
import io
import json
import re
import unittest
import zipfile

import frappe

from huf.ai.artifact_export_api import (
	_FORMATS,
	export_artifact,
	export_document_content,
	export_filename,
)
from huf.ai.tools.document_artifact import handle_export_document

DOC = "# Quarterly Report\n\nRevenue grew **18.4%** in the quarter.\n\n| Region | Sales |\n|---|---|\n| North | 120 |\n"


def _read_file(file_url: str) -> bytes:
	name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	content = frappe.get_doc("File", name).get_content()
	return content.encode("utf-8") if isinstance(content, str) else content


def _pdf_pages(data: bytes) -> int:
	try:
		from pypdf import PdfReader
	except ImportError:
		# Uncompressed page tree only: the /Count of the root /Pages node.
		counts = re.findall(rb"/Count\s+(\d+)", data)
		return max((int(c) for c in counts), default=0)
	return len(PdfReader(io.BytesIO(data)).pages)


def _docx_body(data: bytes) -> str:
	with zipfile.ZipFile(io.BytesIO(data)) as z:
		return z.read("word/document.xml").decode("utf-8")


class TestDocumentExport(unittest.TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._conversations = []
		self._artifacts = []
		self.conversation = self._make_conversation()
		self.artifact = self._make_artifact(self.conversation, "Quarterly Report", DOC)

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in self._artifacts:
			for f in frappe.get_all("File", filters={"attached_to_doctype": "Artifact", "attached_to_name": name}, pluck="name"):
				frappe.delete_doc("File", f, ignore_permissions=True, force=True)
			frappe.delete_doc("Artifact", name, ignore_permissions=True, force=True)
		for name in self._conversations:
			for f in frappe.get_all("File", filters={"attached_to_doctype": "Agent Conversation", "attached_to_name": name}, pluck="name"):
				frappe.delete_doc("File", f, ignore_permissions=True, force=True)
			frappe.delete_doc("Agent Conversation", name, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _make_conversation(self):
		doc = frappe.get_doc(
			{
				"doctype": "Agent Conversation",
				"title": f"export-test-{frappe.generate_hash(length=6)}",
				"session_id": f"test-session-{frappe.generate_hash(length=10)}",
				"is_active": 1,
			}
		).insert(ignore_permissions=True)
		self._conversations.append(doc.name)
		return doc.name

	def _make_artifact(self, conversation, title, content, artifact_type="document"):
		doc = frappe.get_doc(
			{
				"doctype": "Artifact",
				"conversation": conversation,
				"artifact_type": artifact_type,
				"title": title,
				"content": content,
			}
		).insert(ignore_permissions=True)
		self._artifacts.append(doc.name)
		return doc.name

	# -- saved artifact ------------------------------------------------------

	def test_formats_include_markdown(self):
		self.assertEqual(_FORMATS[:3], ("pdf", "docx", "html"))
		self.assertIn("md", _FORMATS)

	def test_export_artifact_pdf_is_a_real_pdf(self):
		result = export_artifact(self.artifact, "pdf")
		data = _read_file(result["file_url"])
		self.assertTrue(data.startswith(b"%PDF-"), data[:20])
		self.assertIn(b"%%EOF", data[-64:])
		self.assertGreaterEqual(_pdf_pages(data), 1)
		try:
			from pypdf import PdfReader
		except ImportError:
			return
		text = "".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages)
		self.assertIn("Quarterly Report", text)
		self.assertIn("18.4%", text)

	def test_export_artifact_docx_is_a_zip_with_the_text(self):
		result = export_artifact(self.artifact, "docx")
		data = _read_file(result["file_url"])
		self.assertTrue(zipfile.is_zipfile(io.BytesIO(data)))
		body = _docx_body(data)
		self.assertIn("Quarterly Report", body)
		self.assertIn("18.4%", body)
		self.assertIn("North", body)

	def test_export_artifact_markdown_is_the_source(self):
		result = export_artifact(self.artifact, "md")
		self.assertEqual(_read_file(result["file_url"]).decode("utf-8"), DOC)

	def test_export_artifact_html_is_a_full_document(self):
		html = _read_file(export_artifact(self.artifact, "html")["file_url"]).decode("utf-8")
		self.assertIn("<html", html.lower())
		self.assertIn("Quarterly Report", html)

	def test_unsupported_format_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			export_artifact(self.artifact, "exe")

	# -- stateless content export (inline chat card) ---------------------------

	def test_content_export_pdf_and_docx(self):
		pdf = export_document_content(DOC, "pdf", "markdown", "Q3: Report/../x")
		self.assertEqual(pdf["file_name"], "Q3 Reportx.pdf")
		self.assertEqual(pdf["mime_type"], "application/pdf")
		raw = base64.b64decode(pdf["content_base64"])
		self.assertTrue(raw.startswith(b"%PDF-"))
		docx = export_document_content(DOC, "docx", "markdown", "Q3")
		self.assertIn("18.4%", _docx_body(base64.b64decode(docx["content_base64"])))

	def test_content_export_writes_no_file_rows(self):
		before = frappe.db.count("File")
		export_document_content(DOC, "pdf", "markdown", "x")
		self.assertEqual(frappe.db.count("File"), before)

	def test_content_export_html_language_is_not_mangled(self):
		out = export_document_content('<div class="callout"><strong>Summary:</strong> up 18%.</div>', "docx", "html", "Designed")
		self.assertIn("up 18%", _docx_body(base64.b64decode(out["content_base64"])))

	def test_content_export_guards(self):
		with self.assertRaises(frappe.ValidationError):
			export_document_content("", "pdf")
		with self.assertRaises(frappe.ValidationError):
			export_document_content("x", "zip")
		with self.assertRaises(frappe.ValidationError):
			export_document_content("x" * 250_000, "pdf")

	def test_export_filename_is_safe_and_forces_extension(self):
		self.assertEqual(export_filename("../../etc/passwd", "pdf"), "etcpasswd.pdf")
		self.assertEqual(export_filename("", "docx"), "document.docx")
		self.assertEqual(export_filename("a.b.exe", "md"), "abexe.md")
		self.assertTrue(export_filename("x" * 500, "pdf").endswith(".pdf"))
		self.assertLessEqual(len(export_filename("x" * 500, "pdf")), 84)

	# -- agent tool ------------------------------------------------------------

	def _tool(self, **kw):
		return json.loads(handle_export_document(**kw))

	def test_tool_from_content_returns_a_downloadable_pdf(self):
		res = self._tool(format="pdf", content=DOC, title="Agent Report", conversation_id=self.conversation)
		self.assertTrue(res["success"], res)
		self.assertEqual(res["file_name"], "Agent Report.pdf")
		self.assertIn(res["file_url"], res["markdown_link"])
		self.assertTrue(res["markdown_link"].startswith("[Agent Report.pdf]("))
		self.assertTrue(_read_file(res["file_url"]).startswith(b"%PDF-"))

	def test_tool_from_content_docx_without_a_conversation(self):
		res = self._tool(format="docx", content=DOC, title="No Conv")
		self.assertTrue(res["success"], res)
		self.assertIn("18.4%", _docx_body(_read_file(res["file_url"])))
		frappe.delete_doc("File", frappe.db.get_value("File", {"file_url": res["file_url"]}, "name"), ignore_permissions=True, force=True)

	def test_tool_by_artifact_id(self):
		res = self._tool(format="docx", artifact_id_or_title=self.artifact)
		self.assertTrue(res["success"], res)
		self.assertIn("Quarterly Report", _docx_body(_read_file(res["file_url"])))

	def test_tool_by_title_is_scoped_to_the_conversation(self):
		res = self._tool(format="pdf", artifact_id_or_title="quarterly report", conversation_id=self.conversation)
		self.assertTrue(res["success"], res)
		other = self._make_conversation()
		res = self._tool(format="pdf", artifact_id_or_title="quarterly report", conversation_id=other)
		self.assertFalse(res["success"])
		self.assertIn("No document artifact", res["error"])

	def test_tool_by_partial_title(self):
		res = self._tool(format="md", artifact_id_or_title="Quarterly", conversation_id=self.conversation)
		self.assertTrue(res["success"], res)

	def test_tool_bad_input_is_a_structured_error(self):
		self.assertFalse(self._tool(format="exe", content="x")["success"])
		self.assertFalse(self._tool(format="pdf")["success"])
		self.assertFalse(self._tool(format="pdf", artifact_id_or_title="does-not-exist-zzz")["success"])

	def test_tool_is_registered_and_gated_like_its_siblings(self):
		from huf.ai.document_artifact_instructions import (
			DOCUMENT_EXPORT_TOOL_INSTRUCTIONS,
			DOCUMENT_TOOL_NAME,
		)
		from huf.ai.tools._registry import DOCUMENT_ARTIFACT_TOOLS

		names = [t["tool_name"] for t in DOCUMENT_ARTIFACT_TOOLS]
		self.assertIn("export_document", names)
		self.assertTrue(DOCUMENT_TOOL_NAME.search("export_document"))
		self.assertIn("export_document", DOCUMENT_EXPORT_TOOL_INSTRUCTIONS)
		self.assertIn("Do NOT paste", DOCUMENT_EXPORT_TOOL_INSTRUCTIONS)


class TestDesktopDocumentGuidance(unittest.TestCase):
	def test_with_skills_points_at_local_office_skills_and_outputs(self):
		from huf.ai.document_artifact_instructions import DESKTOP_DOCUMENT_FILE_INSTRUCTIONS_WITH_SKILLS as text

		for needle in ("huf-office", "typst-doc", "docx", "desktop_skill_run", "outputs/", "Activity", "not uploaded"):
			self.assertIn(needle, text)

	def test_without_skills_says_so_and_does_not_promise_a_file(self):
		from huf.ai.document_artifact_instructions import DESKTOP_DOCUMENT_FILE_INSTRUCTIONS_NO_SKILLS as text

		self.assertIn("not enabled", text)
		self.assertIn("Do not pretend", text)
		self.assertNotIn("desktop_skill_run", text)

	def test_agent_integration_injects_by_skill_tool_presence(self):
		import inspect

		from huf.ai import agent_integration

		src = inspect.getsource(agent_integration)
		self.assertIn('"desktop_skill_run" in {tool.name for tool in self.tools}', src)
		self.assertIn("DESKTOP_DOCUMENT_FILE_INSTRUCTIONS_NO_SKILLS", src)
