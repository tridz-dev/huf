# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.tests.utils import HufTestSuite


class TestKnowledgeSource(HufTestSuite):
	def _make_source(self, **overrides):
		doc = {
			"doctype": "Knowledge Source",
			"source_name": "_Test Knowledge Source",
			"knowledge_type": "sqlite_fts",
		}
		doc.update(overrides)
		return frappe.get_doc(doc).insert(ignore_permissions=True)

	def test_create_sqlite_fts_source_applies_defaults(self):
		source = self._make_source()

		self.assertEqual(source.name, "_Test Knowledge Source")
		# before_save() fills in chunking defaults and initial status
		self.assertEqual(source.chunk_size, 512)
		self.assertEqual(source.chunk_overlap, 50)
		self.assertEqual(source.status, "Pending")

	def test_explicit_chunk_settings_preserved(self):
		source = self._make_source(chunk_size=1000, chunk_overlap=100)

		self.assertEqual(source.chunk_size, 1000)
		self.assertEqual(source.chunk_overlap, 100)

	def test_source_name_required(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "Knowledge Source",
				"knowledge_type": "sqlite_fts",
			}).insert(ignore_permissions=True)

	def test_knowledge_type_required(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "Knowledge Source",
				"source_name": "_Test Knowledge Source",
			}).insert(ignore_permissions=True)

	def test_source_name_unique(self):
		self._make_source()

		with self.assertRaises(frappe.DuplicateEntryError):
			self._make_source()

	def test_chunk_size_minimum(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_source(chunk_size=50)

	def test_chunk_overlap_must_be_less_than_chunk_size(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_source(chunk_size=200, chunk_overlap=200)

	def test_sqlite_vec_requires_embedding_model(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_source(
				source_name="_Test Vector Source",
				knowledge_type="sqlite_vec",
				embedding_model=None,
				vector_dimension=1536,
			)

	def test_sqlite_vec_requires_positive_vector_dimension(self):
		# embedding_model is set, so the controller's vector_dimension check
		# fires before the sqlite-vec extension availability check.
		with self.assertRaises(frappe.ValidationError):
			self._make_source(
				source_name="_Test Vector Source",
				knowledge_type="sqlite_vec",
				embedding_model="openai/text-embedding-3-small",
				vector_dimension=0,
			)
