# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _


class KnowledgeSource(Document):
	def validate(self):
		self.validate_chunk_settings()
		
	def validate_chunk_settings(self):
		if self.chunk_size and self.chunk_size < 100:
			frappe.throw(_("Chunk size must be at least 100 characters"))
		if self.chunk_overlap and self.chunk_overlap >= self.chunk_size:
			frappe.throw(_("Chunk overlap must be less than chunk size"))
	
	def before_save(self):
		if not self.chunk_size:
			self.chunk_size = 512
		if not self.chunk_overlap:
			self.chunk_overlap = 50
		if not self.status:
			self.status = "Pending"
	
	def on_trash(self):
		# Delete SQLite artifact file
		if self.sqlite_file:
			try:
				file_doc = frappe.get_doc("File", {"file_url": self.sqlite_file})
				file_doc.delete(ignore_permissions=True)
			except Exception:
				pass
		
		# Delete all related inputs
		frappe.db.delete("Knowledge Input", {"knowledge_source": self.name})


@frappe.whitelist()
def rebuild_index(knowledge_source: str):
	"""Trigger a full index rebuild for the knowledge source."""
	from huf.ai.knowledge.indexer import rebuild_knowledge_index
	
	doc = frappe.get_doc("Knowledge Source", knowledge_source)
	doc.status = "Rebuilding"
	doc.save()
	
	frappe.enqueue(
		rebuild_knowledge_index,
		queue="long",
		knowledge_source=knowledge_source,
		job_id=f"rebuild_index_{knowledge_source}",
		deduplicate=True,
	)
	
	return {"status": "queued", "message": _("Index rebuild has been queued")}


@frappe.whitelist()
def test_search(knowledge_source: str, query: str, top_k: int = 5):
	"""Test search against a knowledge source."""
	from huf.ai.knowledge.retriever import knowledge_search
	
	results = knowledge_search(
		query=query,
		knowledge_source=knowledge_source,
		top_k=int(top_k)
	)
	
	return results
