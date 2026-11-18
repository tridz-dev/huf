"""media_upload._find_file: URL resolution checks every File row; traversal rejected. Unit tests."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from huf.ai.whatsapp import media_upload as mu


def _row(name, url="/private/files/a.pdf", private=1, owner="u1", folder=0):
	return NS(name=name, file_url=url, is_private=private, owner=owner, is_folder=folder)


class TestFindFile(unittest.TestCase):
	def _run(self, ref, rows, user="u1", exists=True):
		by = {r.name: r for r in rows}
		with patch.object(mu.frappe, "get_all", return_value=[r.name for r in rows]), \
			patch.object(mu.frappe, "get_doc", side_effect=lambda dt, n: by[n]), \
			patch.object(mu.frappe.db, "exists", return_value=exists), \
			patch.object(mu.frappe, "has_permission", side_effect=lambda dt, ptype, doc, user: doc.owner == user):
			return mu._find_file(ref, user)

	def test_url_single_owned_ok(self):
		self.assertEqual(self._run("/private/files/a.pdf", [_row("F1")]).name, "F1")

	def test_name_ok(self):
		self.assertEqual(self._run("F1", [_row("F1")]).name, "F1")

	def test_mixed_owner_rows_forbidden(self):
		with self.assertRaises(mu.MediaUploadError) as c:
			self._run("/private/files/a.pdf", [_row("F1"), _row("F2", owner="victim")])
		self.assertEqual(c.exception.code, "file_forbidden")

	def test_public_row_forbidden(self):
		with self.assertRaises(mu.MediaUploadError) as c:
			self._run("/private/files/a.pdf", [_row("F1"), _row("F2", private=0)])
		self.assertEqual(c.exception.code, "file_forbidden")

	def test_traversal_and_absolute_forbidden(self):
		for bad in ("/private/files/../../etc/passwd.pdf", "/private/files/%2e%2e/x.pdf",
			"/etc/passwd", "/files/a.pdf", "/private/files/..%2fsites/x.pdf", "/private/files/a\\b.pdf"):
			with self.assertRaises(mu.MediaUploadError, msg=bad) as c:
				self._run(bad, [_row("F1", url=bad)])
			self.assertEqual(c.exception.code, "file_forbidden", bad)

	def test_name_row_with_bad_url_forbidden(self):
		with self.assertRaises(mu.MediaUploadError) as c:
			self._run("F1", [_row("F1", url="/private/files/../x.pdf")])
		self.assertEqual(c.exception.code, "file_forbidden")

	def test_not_found(self):
		with self.assertRaises(mu.MediaUploadError) as c:
			self._run("/private/files/none.pdf", [])
		self.assertEqual(c.exception.code, "file_not_found")
