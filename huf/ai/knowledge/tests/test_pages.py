import unittest

from huf.ai.knowledge.pages import chunk_metadata, page_for_offset

OFFSETS = [[0, 1], [100, 2], [250, 3]]


class TestPageMapping(unittest.TestCase):
	def test_page_for_offset(self):
		self.assertEqual(page_for_offset(OFFSETS, 0), 1)
		self.assertEqual(page_for_offset(OFFSETS, 99), 1)
		self.assertEqual(page_for_offset(OFFSETS, 100), 2)
		self.assertEqual(page_for_offset(OFFSETS, 9999), 3)

	def test_no_offsets(self):
		self.assertIsNone(page_for_offset(None, 5))

	def test_chunk_metadata_pdf(self):
		m = chunk_metadata({"file_type": "pdf", "page_offsets": OFFSETS}, 120)
		self.assertEqual(m["page"], 2)
		self.assertNotIn("page_offsets", m)

	def test_chunk_metadata_non_pdf_unchanged(self):
		src = {"file_type": "txt"}
		self.assertEqual(chunk_metadata(src, 5), {"file_type": "txt"})
		self.assertEqual(chunk_metadata(None, 5), {})


def test_chunk_spanning_pages_records_page_end():
	from huf.ai.knowledge.pages import chunk_metadata

	meta = {"file_type": "pdf", "page_offsets": [[0, 1], [100, 2], [200, 3]]}
	out = chunk_metadata(meta, 150, 260)
	assert out["page"] == 2 and out["page_end"] == 3 and "page_offsets" not in out
	same = chunk_metadata(meta, 110, 190)
	assert same["page"] == 2 and "page_end" not in same
