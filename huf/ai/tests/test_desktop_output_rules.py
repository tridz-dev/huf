# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
"""Bench-free tests: ``python3 -m unittest huf/ai/tests/test_desktop_output_rules.py`` (pure module, loaded by path)."""

import base64
import importlib.util
import pathlib
import unittest

_p = pathlib.Path(__file__).resolve().parents[1] / "desktop_output_rules.py"
_spec = importlib.util.spec_from_file_location("desktop_output_rules", _p)
r = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(r)

b64 = lambda b: base64.b64encode(b).decode()


class TestValidate(unittest.TestCase):
	def test_ok_pdf_and_text(self):
		n, ext, ct, at, data, text = r.validate_upload("a.pdf", b64(b"%PDF-1.4 x"))
		self.assertEqual((n, ext, ct, at, text), ("a.pdf", "pdf", "application/pdf", "document", None))
		self.assertEqual(r.validate_upload("n.md", b64(b"# hi"))[5], "# hi")

	def test_rejections(self):
		cases = [
			(("../etc/passwd", b64(b"x")), "secret_name"),  # basename is passwd
			((".env", b64(b"x")), "bad_filename"),
			(("server.pem", b64(b"x")), "secret_name"),
			(("id_rsa.txt", b64(b"x")), "secret_name"),
			(("a.exe", b64(b"x")), "type_not_allowed"),
			(("a.pdf", b64(b"not a pdf")), "type_mismatch"),
			(("a.png", b64(b"%PDF-")), "type_mismatch"),
			(("a.csv", b64(b"\xff\xfe\x00")), "type_mismatch"),
			(("a.csv", "!!!"), "bad_encoding"),
			(("a.csv", ""), "empty"),
		]
		for args, code in cases:
			with self.assertRaises(r.UploadRejected, msg=args) as cm:
				r.validate_upload(*args)
			self.assertEqual(cm.exception.code, code, args)

	def test_size_cap(self):
		big = b64(b"a" * (r.MAX_UPLOAD_BYTES + 1))
		with self.assertRaises(r.UploadRejected) as cm:
			r.validate_upload("a.txt", big)
		self.assertEqual(cm.exception.code, "too_large")
		self.assertEqual(r.clean_filename("dir/sub\\x.txt"), "x.txt")


class TestRank(unittest.TestCase):
	items = [
		{"kind": "skill", "name": "docx", "description": "Word documents"},
		{"kind": "agent", "name": "Report Writer", "description": "writes docx reports"},
		{"kind": "skill", "name": "xlsx", "description": "Spreadsheets"},
	]

	def test_rank_and_filter(self):
		self.assertEqual([i["name"] for i in r.rank_catalog(self.items, "docx")], ["docx", "Report Writer"])
		self.assertEqual([i["name"] for i in r.rank_catalog(self.items, "", kind="agent")], ["Report Writer"])
		self.assertEqual(r.rank_catalog(self.items, "zzz"), [])
		self.assertEqual(len(r.rank_catalog(self.items, "", limit=1)), 1)


if __name__ == "__main__":
	unittest.main()
