"""Repack raw XML parts back into a valid .docx file."""

import io
import zipfile


def pack_docx(parts: dict[str, bytes]) -> bytes:
	"""Rezip a {internal_path: raw_bytes} dict produced by unpack_docx (optionally
	modified) back into valid .docx bytes.

	Preserves the iteration order of the input dict — if you pass the dict from
	unpack_docx with only values modified, the output .docx will have its parts
	in the same order as the original (Python 3.7+ dict order is insertion order).

	Args:
		parts: Dictionary mapping internal zip paths to raw bytes.

	Returns:
		Raw bytes of a valid .docx file.
	"""
	buffer = io.BytesIO()
	with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
		for path, data in parts.items():
			zf.writestr(path, data)
	return buffer.getvalue()
