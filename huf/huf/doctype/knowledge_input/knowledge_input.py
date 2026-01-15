# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

import hashlib
import os
import frappe
from frappe.model.document import Document
from frappe import _


class KnowledgeInput(Document):
	def validate(self):
		self.validate_input()
		self.compute_source_hash()
		self.check_duplicate()
	
	def validate_input(self):
		if self.input_type == "File" and not self.file:
			frappe.throw(_("File is required for File input type"))
		elif self.input_type == "Text" and not self.text:
			frappe.throw(_("Text content is required for Text input type"))
		elif self.input_type == "URL" and not self.url:
			frappe.throw(_("URL is required for URL input type"))
	
	def compute_source_hash(self):
		"""Compute SHA-256 hash for deduplication."""
		content = ""
		if self.input_type == "File" and self.file:
			# Hash the file URL as we can't read content during validate
			content = self.file
		elif self.input_type == "Text":
			content = self.text or ""
		elif self.input_type == "URL":
			content = self.url or ""
		
		if content:
			self.source_hash = hashlib.sha256(content.encode()).hexdigest()
	
	def check_duplicate(self):
		"""Check if this content already exists in the knowledge source."""
		if self.source_hash and not self.is_new():
			return
			
		if self.source_hash:
			existing = frappe.db.exists("Knowledge Input", {
				"knowledge_source": self.knowledge_source,
				"source_hash": self.source_hash,
				"name": ("!=", self.name or "")
			})
			if existing:
				frappe.throw(_("This content already exists in the knowledge source"))
	
	def before_save(self):
		if not self.status:
			self.status = "Pending"
		
		# Extract file metadata
		if self.input_type == "File" and self.file:
			try:
				file_doc = frappe.get_doc("File", {"file_url": self.file})
				self.file_name = file_doc.file_name
				self.file_type = file_doc.file_type or self.get_file_type_from_name(file_doc.file_name)
			except Exception:
				pass
	
	def get_file_type_from_name(self, filename):
		"""Infer file type from extension."""
		ext_map = {
			".pdf": "application/pdf",
			".txt": "text/plain",
			".md": "text/markdown",
			".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
			".doc": "application/msword",
			".html": "text/html",
			".htm": "text/html",
			".json": "application/json",
			".csv": "text/csv",
		}
		_, ext = os.path.splitext(filename.lower())
		return ext_map.get(ext, "application/octet-stream")
	
	def after_insert(self):
		"""Queue processing after insert."""
		self.queue_processing()
	
	def queue_processing(self):
		"""Queue the input for processing."""
		from huf.ai.knowledge.indexer import process_knowledge_input
		
		frappe.enqueue(
			process_knowledge_input,
			queue="default",
			knowledge_input=self.name,
			job_id=f"process_input_{self.name}",
			deduplicate=True,
		)


@frappe.whitelist()
def reprocess_input(knowledge_input: str):
	"""Reprocess a failed or pending input."""
	doc = frappe.get_doc("Knowledge Input", knowledge_input)
	doc.status = "Pending"
	doc.error_message = None
	doc.save()
	doc.queue_processing()
	
	return {"status": "queued", "message": _("Input has been queued for reprocessing")}
