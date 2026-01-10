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
		extractors = {
			"application/pdf": "huf.ai.knowledge.extractors.pdf.PDFExtractor",
			"application/vnd.openxmlformats-officedocument.wordprocessingml.document": 
				"huf.ai.knowledge.extractors.docx.DocxExtractor",
			"text/plain": "huf.ai.knowledge.extractors.text.TextExtractor",
			"text/markdown": "huf.ai.knowledge.extractors.text.TextExtractor",
			"text/html": "huf.ai.knowledge.extractors.html.HTMLExtractor",
			"url": "huf.ai.knowledge.extractors.url.URLExtractor",
		}
		
		import frappe
		extractor_path = extractors.get(file_type, extractors["text/plain"])
		try:
			return frappe.get_attr(extractor_path)()
		except Exception:
			# Fallback to text extractor if specific extractor fails
			return frappe.get_attr(extractors["text/plain"])()
