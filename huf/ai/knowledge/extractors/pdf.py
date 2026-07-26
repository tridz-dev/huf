"""PDF text extractor using PyPDF2 or pypdf."""

from . import TextExtractor, ExtractedText


class PDFExtractor(TextExtractor):
	"""Extractor for PDF files."""
	
	def extract(self, file_path: str) -> ExtractedText:
		"""Extract text from PDF file."""
		text_parts = []
		
		try:
			# Try pypdf first (newer library)
			import pypdf
			with open(file_path, "rb") as f:
				reader = pypdf.PdfReader(f)
				for page in reader.pages:
					text_parts.append(page.extract_text())
		except ImportError:
			try:
				# Fallback to PyPDF2
				import PyPDF2
				with open(file_path, "rb") as f:
					reader = PyPDF2.PdfReader(f)
					for page in reader.pages:
						text_parts.append(page.extract_text())
			except ImportError:
				raise ImportError(
					"PDF extraction requires either 'pypdf' or 'PyPDF2'. "
					"Install with: pip install pypdf"
				)
		
		text = "\n\n".join(text_parts)
		
		import os
		title = os.path.basename(file_path)
		
		return ExtractedText(
			text=text,
			title=title,
			metadata={"file_type": "pdf", "pages": len(text_parts)},
		)
