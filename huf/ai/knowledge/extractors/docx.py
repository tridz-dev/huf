"""DOCX text extractor using python-docx."""

from . import TextExtractor, ExtractedText


class DocxExtractor(TextExtractor):
	"""Extractor for DOCX files."""
	
	def extract(self, file_path: str) -> ExtractedText:
		"""Extract text from DOCX file."""
		try:
			from docx import Document
		except ImportError:
			raise ImportError(
				"DOCX extraction requires 'python-docx'. "
				"Install with: pip install python-docx"
			)
		
		doc = Document(file_path)
		text_parts = []
		
		for paragraph in doc.paragraphs:
			if paragraph.text.strip():
				text_parts.append(paragraph.text)
		
		text = "\n\n".join(text_parts)
		
		import os
		title = os.path.basename(file_path)
		
		return ExtractedText(
			text=text,
			title=title,
			metadata={"file_type": "docx"},
		)
