import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from huf.ai.gateway_adapters import whatsapp_templates as wt
from huf.ai.whatsapp import media_upload as mu
from huf.ai.whatsapp.broadcast import params as bp

ACCT = {"url": "https://graph.facebook.com", "version": "v21.0", "phone_id": "111", "token": "SECRET_TOKEN"}
PDF = b"%PDF-1.4 body"


def _file(name="a.pdf", data=PDF, size=None, private=1):
	f = MagicMock()
	f.is_folder = 0
	f.file_name = name
	f.file_size = len(data) if size is None else size
	f.is_private = private
	f.get_content.return_value = data
	return f


def _resp(body, status=200):
	return SimpleNamespace(status_code=status, json=lambda: body)


class FakeCache:
	def __init__(self):
		self.d = {}

	def hget(self, k, f):
		return self.d.get((k, f))

	def hset(self, k, f, v):
		self.d[(k, f)] = v

	def hdel(self, k, f):
		self.d.pop((k, f), None)


class TestMediaUpload(unittest.TestCase):
	def setUp(self):
		self.cache = FakeCache()
		self.patches = [
			patch.object(mu.frappe, "cache", lambda: self.cache),
			patch.object(mu.frappe, "has_permission", lambda *a, **k: True),
		]
		for p in self.patches:
			p.start()
		self.addCleanup(lambda: [p.stop() for p in self.patches])

	def _run(self, doc, post, perm=True):
		with patch.object(mu, "_find_file", return_value=doc), patch.object(mu.frappe, "has_permission", lambda *a, **k: perm):
			return mu.upload_private_pdf(ACCT, "x", "u@x.test", http_post=post)

	def test_happy_private_multipart(self):
		post = MagicMock(return_value=_resp({"id": "M1"}))
		doc = _file()
		self.assertEqual(self._run(doc, post), "M1")
		kw = post.call_args.kwargs
		self.assertTrue(post.call_args.args[0].endswith("/111/media"))
		self.assertEqual(kw["data"]["messaging_product"], "whatsapp")
		self.assertEqual(kw["files"]["file"][2], "application/pdf")
		self.assertEqual(doc.is_private, 1)  # never altered
		doc.save.assert_not_called()

	def test_forbidden(self):
		with self.assertRaises(mu.MediaUploadError) as c:
			self._run(_file(), MagicMock(), perm=False)
		self.assertEqual(c.exception.code, "file_forbidden")

	def test_not_pdf(self):
		for doc in (_file(name="a.png"), _file(data=b"GIF89a")):
			with self.assertRaises(mu.MediaUploadError) as c:
				self._run(doc, MagicMock())
			self.assertEqual(c.exception.code, "not_pdf")

	def test_too_large(self):
		with self.assertRaises(mu.MediaUploadError) as c:
			self._run(_file(size=mu.MAX_PDF_BYTES + 1), MagicMock())
		self.assertEqual(c.exception.code, "file_too_large")

	def test_not_found(self):
		with patch.object(mu.frappe.db, "exists", return_value=False), patch.object(mu.frappe.db, "get_value", return_value=None):
			with self.assertRaises(mu.MediaUploadError) as c:
				mu.upload_private_pdf(ACCT, "nope", "u@x.test")
		self.assertEqual(c.exception.code, "file_not_found")

	def test_cache_hit_and_force_reupload(self):
		post = MagicMock(side_effect=[_resp({"id": "M1"}), _resp({"id": "M2"})])
		doc = _file()
		self.assertEqual(self._run(doc, post), "M1")
		self.assertEqual(self._run(doc, post), "M1")
		self.assertEqual(post.call_count, 1)
		with patch.object(mu, "_find_file", return_value=doc):
			self.assertEqual(mu.upload_private_pdf(ACCT, "x", "u", http_post=post, force=True), "M2")

	def test_upload_failure_leaks_nothing(self):
		post = MagicMock(return_value=_resp({"error": {"message": "SECRET_TOKEN"}}, 400))
		with self.assertRaises(mu.MediaUploadError) as c:
			self._run(_file(), post)
		self.assertEqual(c.exception.code, "upload_failed")
		self.assertNotIn("SECRET_TOKEN", c.exception.message)

	def test_expired_detection(self):
		self.assertTrue(mu.is_expired_media_error({"graph_code": 131009, "message": "Parameter value is not valid: media not found"}))
		self.assertTrue(mu.is_expired_media_error({"graph_code": 100, "message": "Invalid parameter: media id"}))
		self.assertFalse(mu.is_expired_media_error({"graph_code": 131009, "message": "Parameter value is not valid"}))
		self.assertFalse(mu.is_expired_media_error({"graph_code": 131052}))
		self.assertFalse(mu.is_expired_media_error({"graph_code": 131053}))
		self.assertTrue(mu.is_expired_media_error({"message": "Media not found"}))
		self.assertFalse(mu.is_expired_media_error({"message": "rate limit"}))

	def test_resolve_header_uses_id_not_link(self):
		items, errs = wt.normalize_header_params([{"type": "document", "file": "F-1", "filename": "bill.pdf"}])
		self.assertEqual(errs, [])
		comps = wt.build_template_components(None, items, None, "document")
		with patch.object(mu, "upload_private_pdf", return_value="M9"):
			self.assertTrue(mu.resolve_file_headers(ACCT, comps))
		doc = comps[0]["parameters"][0]["document"]
		self.assertEqual(doc, {"id": "M9", "filename": "bill.pdf"})
		self.assertNotIn("link", doc)

	def test_broadcast_header_accepts_file(self):
		self.assertIsNone(bp.header_error({"type": "document", "file": "F-1"}))
		self.assertIn("document", bp.header_error({"type": "image", "file": "F-1"}))
