"""HTML text extractor."""

import re
from . import TextExtractor, ExtractedText


class HTMLExtractor(TextExtractor):
	"""Extractor for HTML files."""
	
	def extract(self, file_path: str) -> ExtractedText:
		"""Extract text from HTML file."""
		with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
			html_content = f.read()
		
		# Simple HTML tag removal
		# Remove script and style tags
		html_content = re.sub(r"<script[^>]*>.*?</script>", "", html_content, flags=re.DOTALL | re.IGNORECASE)
		html_content = re.sub(r"<style[^>]*>.*?</style>", "", html_content, flags=re.DOTALL | re.IGNORECASE)
		
		# Extract title
		title_match = re.search(r"<title[^>]*>(.*?)</title>", html_content, re.IGNORECASE | re.DOTALL)
		title = title_match.group(1).strip() if title_match else None
		
		# Remove HTML tags
		text = re.sub(r"<[^>]+>", "", html_content)
		
		# Clean up whitespace
		text = re.sub(r"\s+", " ", text)
		text = text.strip()
		
		import os
		if not title:
			title = os.path.basename(file_path)
		
		return ExtractedText(
			text=text,
			title=title,
			metadata={"file_type": "html"},
		)
