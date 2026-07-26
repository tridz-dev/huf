"""Plain text and markdown extractor."""

import os
from . import TextExtractor as BaseTextExtractor, ExtractedText


class TextExtractor(BaseTextExtractor):
	"""Extractor for plain text and markdown files."""
	
	def extract(self, file_path: str) -> ExtractedText:
		"""Extract text from file."""
		with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
			text = f.read()
		
		title = os.path.basename(file_path)
		
		return ExtractedText(
			text=text,
			title=title,
			metadata={"file_type": "text"},
		)
