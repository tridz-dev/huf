# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import hashlib

import frappe

from huf.tests.utils import HufTestSuite


class TestKnowledgeInput(HufTestSuite):
	def _make_knowledge_source(self, source_name="_Test Knowledge Source"):
		# get_or_create: some tests call this indirectly twice in one test
		# (e.g. once directly, once via _make_input) with the default name —
		# source_name is unique, so a bare insert() would collide.
		if frappe.db.exists("Knowledge Source", source_name):
			return frappe.get_doc("Knowledge Source", source_name)
		return frappe.get_doc({
			"doctype": "Knowledge Source",
			"source_name": source_name,
			"knowledge_type": "sqlite_fts",
		}).insert(ignore_permissions=True)

	def _make_input(self, **overrides):
		source = self._make_knowledge_source()
		doc = {
			"doctype": "Knowledge Input",
			"knowledge_source": source.name,
			"input_type": "Text",
			"text": "Some test knowledge content",
		}
		doc.update(overrides)
		return frappe.get_doc(doc).insert(ignore_permissions=True)

	def test_create_text_input(self):
		text = "Some test knowledge content"
		ki = self._make_input(text=text)

		self.assertEqual(ki.status, "Pending")
		# compute_source_hash() hashes the text content for deduplication
		self.assertEqual(ki.source_hash, hashlib.sha256(text.encode()).hexdigest())

	def test_text_content_required(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_input(text=None)

	def test_file_required_for_file_input_type(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_input(input_type="File", text=None, file=None)

	def test_url_required_for_url_input_type(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_input(input_type="URL", text=None, url=None)

	def test_invalid_url_scheme_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_input(input_type="URL", text=None, url="ftp://example.com/file.txt")

	def test_private_url_rejected(self):
		# validate_url() blocks requests to private/internal addresses (SSRF)
		with self.assertRaises(frappe.ValidationError):
			self._make_input(input_type="URL", text=None, url="http://127.0.0.1/internal")

	def test_duplicate_content_rejected(self):
		source = self._make_knowledge_source()
		text = "Duplicate knowledge content"
		self._make_input(text=text)

		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "Knowledge Input",
				"knowledge_source": source.name,
				"input_type": "Text",
				"text": text,
			}).insert(ignore_permissions=True)

	def test_file_input_extracts_metadata(self):
		file_doc = frappe.get_doc({
			"doctype": "File",
			"file_name": "_test_knowledge_input.txt",
			"content": "file content for knowledge input test",
		}).insert(ignore_permissions=True)

		ki = self._make_input(input_type="File", text=None, file=file_doc.file_url)

		# before_save() resolves the File record and copies its metadata.
		# File.file_type in Frappe is the uppercased extension, not a MIME
		# type (verified against a live bench) — get_file_type_from_name's
		# fallback matches that convention.
		self.assertEqual(ki.file_name, "_test_knowledge_input.txt")
		self.assertEqual(ki.file_type, "TXT")
