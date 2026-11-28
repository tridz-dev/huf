"""CSV extractor: emits "column: value" per cell so chunks keep their headers."""

import csv
import io
import os

from . import ExtractedText
from . import TextExtractor as BaseTextExtractor


def decode_bytes(raw: bytes) -> str:
	"""Decode bytes without raising: BOM-aware, then UTF-8, then latin-1."""
	if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
		return raw.decode("utf-16", errors="replace")
	if raw.startswith(b"\xef\xbb\xbf"):
		return raw.decode("utf-8-sig", errors="replace")
	try:
		return raw.decode("utf-8")
	except UnicodeDecodeError:
		return raw.decode("latin-1", errors="replace")


def csv_to_text(content: str) -> str:
	content = content.replace("\x00", "")
	try:
		dialect = csv.Sniffer().sniff(content[:4096], delimiters=",;\t|")
	except csv.Error:
		dialect = csv.excel
	reader = csv.reader(io.StringIO(content, newline=""), dialect)
	rows = [r for r in reader if any(c.strip() for c in r)]
	if not rows:
		return ""
	header = [h.strip() for h in rows[0]]
	lines = []
	for row in rows[1:]:
		cells = []
		for i, value in enumerate(row):
			value = value.strip()
			if not value:
				continue
			name = header[i] if i < len(header) and header[i] else f"column_{i + 1}"
			cells.append(f"{name}: {value}")
		if cells:
			lines.append("\n".join(cells))
	if not lines:  # header-only file
		return "\n".join(h for h in header if h)
	return "\n\n".join(lines)


class CSVExtractor(BaseTextExtractor):
	"""Extractor for CSV files."""

	def extract(self, file_path: str) -> ExtractedText:
		with open(file_path, "rb") as f:
			text = csv_to_text(decode_bytes(f.read()))
		return ExtractedText(
			text=text,
			title=os.path.basename(file_path),
			metadata={"file_type": "csv"},
		)
