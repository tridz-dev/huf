"""Map character offsets to PDF page numbers."""

from bisect import bisect_right


def page_for_offset(page_offsets, char_start):
	"""Return the 1-based page for char_start, given sorted [start_char, page_no] pairs.

	Returns None when there are no offsets.
	"""
	if not page_offsets:
		return None
	starts = [int(o[0]) for o in page_offsets]
	i = bisect_right(starts, int(char_start or 0)) - 1
	return int(page_offsets[max(i, 0)][1])


def chunk_metadata(extracted_metadata, char_start, char_end=None):
	"""Per-chunk metadata: drop page_offsets, add page (and page_end when the
	chunk runs onto a later page) when known."""
	meta = dict(extracted_metadata or {})
	offsets = meta.pop("page_offsets", None)
	page = page_for_offset(offsets, char_start)
	if page is not None:
		meta["page"] = page
		if char_end is not None:
			end = page_for_offset(offsets, max(int(char_end) - 1, int(char_start or 0)))
			if end and end > page:
				meta["page_end"] = end
	return meta
