"""URL content extractor using requests and BeautifulSoup."""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from . import TextExtractor, ExtractedText


class URLExtractor(TextExtractor):
	"""Extractor for URL content."""
	
	def extract(self, url: str) -> ExtractedText:
		"""Extract text from URL."""
		try:
			# Fetch URL content
			headers = {
				"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
			}
			response = requests.get(url, headers=headers, timeout=30)
			response.raise_for_status()
			
			# Parse HTML
			soup = BeautifulSoup(response.content, "html.parser")
			
			# Remove script and style elements
			for script in soup(["script", "style"]):
				script.decompose()
			
			# Extract title
			title_tag = soup.find("title")
			title = title_tag.get_text().strip() if title_tag else None
			
			# Extract main content (prefer article, main, or body)
			content_selectors = ["article", "main", "[role='main']", "body"]
			content = None
			
			for selector in content_selectors:
				element = soup.select_one(selector)
				if element:
					content = element.get_text(separator="\n", strip=True)
					break
			
			if not content:
				# Fallback to all text
				content = soup.get_text(separator="\n", strip=True)
			
			# Clean up whitespace
			lines = [line.strip() for line in content.split("\n") if line.strip()]
			text = "\n".join(lines)
			
			# Use URL domain as title if no title found
			if not title:
				parsed_url = urlparse(url)
				title = parsed_url.netloc or url
			
			return ExtractedText(
				text=text,
				title=title,
				metadata={
					"file_type": "url",
					"url": url,
					"status_code": response.status_code,
				},
			)
			
		except requests.exceptions.RequestException as e:
			raise ValueError(f"Failed to fetch URL: {str(e)}")
		except Exception as e:
			raise ValueError(f"Error extracting text from URL: {str(e)}")
