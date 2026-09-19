"""URL content extractor using requests and BeautifulSoup."""

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
import os
import tempfile

import requests
from bs4 import BeautifulSoup

from . import ExtractedText, TextExtractor


def normalize_google_sheets_url(url: str) -> str:
	"""Convert a public Google Sheets share/edit URL to a CSV export URL."""
	parsed = urlparse(url)
	if parsed.netloc.lower() not in {"docs.google.com", "www.docs.google.com"}:
		return url

	parts = parsed.path.strip("/").split("/")
	if len(parts) < 3 or parts[0] != "spreadsheets" or parts[1] != "d":
		return url

	spreadsheet_id = parts[2]
	if not spreadsheet_id:
		return url

	query = parse_qs(parsed.query)
	fragment_query = parse_qs(parsed.fragment)
	gid = (query.get("gid") or fragment_query.get("gid") or [None])[0]
	export_query = {"format": "csv"}
	if gid:
		export_query["gid"] = gid

	return urlunparse((
		"https",
		"docs.google.com",
		f"/spreadsheets/d/{spreadsheet_id}/export",
		"",
		urlencode(export_query),
		"",
	))


class URLExtractor(TextExtractor):
	"""Extractor for URL content."""

	def extract(self, url: str) -> ExtractedText:
		"""Extract text from URL."""
		try:
			# Fetch URL content
			headers = {
				"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
			}
			from huf.ai.http_handler import validate_url

			fetch_url = normalize_google_sheets_url(url)
			is_valid, error_msg = validate_url(fetch_url)
			if not is_valid:
				raise ValueError(f"URL blocked: {error_msg}")

			current_url = fetch_url
			response = None
			for _hop in range(6):  # initial + up to 5 redirects
				response = requests.get(
					current_url, headers=headers, timeout=30, allow_redirects=False
				)
				if response.status_code not in (301, 302, 303, 307, 308):
					break
				location = response.headers.get("Location")
				if not location:
					break
				next_url = requests.compat.urljoin(current_url, location)
				is_valid, error_msg = validate_url(next_url)
				if not is_valid:
					raise ValueError(f"Redirect blocked: {error_msg}")
				current_url = next_url
			else:
				raise ValueError("Too many redirects")
			response.raise_for_status()

			content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
			path_suffix = os.path.splitext(urlparse(current_url).path)[1].lower()
			is_pdf = content_type == "application/pdf" or response.content.startswith(b"%PDF-")
			if is_pdf or content_type not in ("", "text/html", "application/xhtml+xml"):
				file_type = "pdf" if is_pdf else content_type
				if content_type == "application/octet-stream":
					file_type = path_suffix
				extractor = TextExtractor.get_extractor(file_type)
				with tempfile.NamedTemporaryFile(
					mode="wb", suffix=path_suffix
				) as temporary_file:
					temporary_file.write(response.content)
					temporary_file.flush()
					return extractor.extract(temporary_file.name)

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
			raise ValueError(f"Failed to fetch URL: {e!s}")
		except Exception as e:
			raise ValueError(f"Error extracting text from URL: {e!s}")
