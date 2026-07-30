"""HTML text extractor."""

import os
from html.parser import HTMLParser
from . import TextExtractor, ExtractedText


class _HTMLTextExtractorParser(HTMLParser):
	def __init__(self):
		super().__init__()
		self.text_parts = []
		self.title = None
		self._in_script_or_style = False
		self._in_title = False

	def handle_starttag(self, tag, attrs):
		tag_lower = tag.lower()
		if tag_lower in ("script", "style"):
			self._in_script_or_style = True
		elif tag_lower == "title":
			self._in_title = True

	def handle_endtag(self, tag):
		tag_lower = tag.lower()
		if tag_lower in ("script", "style"):
			self._in_script_or_style = False
		elif tag_lower == "title":
			self._in_title = False

	def handle_data(self, data):
		if self._in_title and not self.title:
			self.title = data.strip()
		elif not self._in_script_or_style:
			if data.strip():
				self.text_parts.append(data)


class HTMLExtractor(TextExtractor):
	"""Extractor for HTML files."""

	def extract(self, file_path: str) -> ExtractedText:
		"""Extract text from HTML file."""
		with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
			html_content = f.read()

		parser = _HTMLTextExtractorParser()
		try:
			parser.feed(html_content)
		except Exception:
			pass

		text = " ".join(parser.text_parts)
		text = " ".join(text.split())

		title = parser.title or os.path.basename(file_path)

		return ExtractedText(
			text=text,
			title=title,
			metadata={"file_type": "html"},
		)

