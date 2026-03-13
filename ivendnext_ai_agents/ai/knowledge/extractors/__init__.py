"""Text extraction from various file formats."""

from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass


@dataclass
class ExtractedText:
	"""Result of text extraction."""
	text: str
	title: Optional[str] = None
	metadata: Optional[dict] = None
	character_count: int = 0
	
	def __post_init__(self):
		if self.character_count == 0:
			self.character_count = len(self.text)


class TextExtractor(ABC):
	"""Abstract base class for text extractors."""
	
	@abstractmethod
	def extract(self, file_path: str) -> ExtractedText:
		"""Extract text from file."""
		pass
	
	@staticmethod
	def get_extractor(file_type: str) -> "TextExtractor":
		"""Get appropriate extractor for file type."""
		if not file_type:
			file_type = "text/plain"
			
		file_type = file_type.lower().strip()
		
		extractors = {
			# PDF
			"application/pdf": "ivendnext_ai_agents.ai.knowledge.extractors.pdf.PDFExtractor",
			"pdf": "ivendnext_ai_agents.ai.knowledge.extractors.pdf.PDFExtractor",
			".pdf": "ivendnext_ai_agents.ai.knowledge.extractors.pdf.PDFExtractor",
			
			# Word
			"application/vnd.openxmlformats-officedocument.wordprocessingml.document": 
				"ivendnext_ai_agents.ai.knowledge.extractors.docx.DocxExtractor",
			"docx": "ivendnext_ai_agents.ai.knowledge.extractors.docx.DocxExtractor",
			".docx": "ivendnext_ai_agents.ai.knowledge.extractors.docx.DocxExtractor",
			
			# Text
			"text/plain": "ivendnext_ai_agents.ai.knowledge.extractors.text.TextExtractor",
			"txt": "ivendnext_ai_agents.ai.knowledge.extractors.text.TextExtractor",
			".txt": "ivendnext_ai_agents.ai.knowledge.extractors.text.TextExtractor",
			
			# Markdown
			"text/markdown": "ivendnext_ai_agents.ai.knowledge.extractors.text.TextExtractor",
			"md": "ivendnext_ai_agents.ai.knowledge.extractors.text.TextExtractor",
			".md": "ivendnext_ai_agents.ai.knowledge.extractors.text.TextExtractor",
			"markdown": "ivendnext_ai_agents.ai.knowledge.extractors.text.TextExtractor",
			
			# HTML
			"text/html": "ivendnext_ai_agents.ai.knowledge.extractors.html.HTMLExtractor",
			"html": "ivendnext_ai_agents.ai.knowledge.extractors.html.HTMLExtractor",
			".html": "ivendnext_ai_agents.ai.knowledge.extractors.html.HTMLExtractor",
			"htm": "ivendnext_ai_agents.ai.knowledge.extractors.html.HTMLExtractor",
			".htm": "ivendnext_ai_agents.ai.knowledge.extractors.html.HTMLExtractor",
			
			# URL
			"url": "ivendnext_ai_agents.ai.knowledge.extractors.url.URLExtractor",
		}
		
		import frappe
		extractor_path = extractors.get(file_type, extractors["text/plain"])
		try:
			return frappe.get_attr(extractor_path)()
		except Exception:
			# Fallback to text extractor if specific extractor fails
			return frappe.get_attr(extractors["text/plain"])()