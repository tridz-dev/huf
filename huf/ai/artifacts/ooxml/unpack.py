"""Unpack a .docx file into its raw XML parts for inspection and modification."""

import io
import zipfile


def unpack_docx(docx_bytes: bytes) -> dict[str, bytes]:
	"""Extract a .docx zip into {internal_path: raw_bytes} for every part.

	Args:
		docx_bytes: Raw bytes of a valid .docx file.

	Returns:
		A dictionary mapping internal zip paths (e.g. "word/document.xml",
		"[Content_Types].xml") to their raw bytes content.
	"""
	parts = {}
	with zipfile.ZipFile(io.BytesIO(docx_bytes)) as zf:
		for name in zf.namelist():
			parts[name] = zf.read(name)
	return parts
