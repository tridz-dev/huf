# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Shared path rules of Telegram web access (pure)."""

import unittest

from huf.ai import telegram_web_access_paths as P


class TestNormalizePath(unittest.TestCase):
	def test_canonical_form(self):
		self.assertEqual(P.normalize_path("/App//ToDo/"), "/app/todo")
		self.assertEqual(P.normalize_path("/a/./b?x=1#f"), "/a/b")
		self.assertEqual(P.normalize_path("/"), "/")

	def test_rejects_unsafe(self):
		for bad in (
			"/a/../b",
			"/a\\b",
			"/a%2f..%2fb",
			"/a%5Cb",
			"/a%00b",
			"/a\x00b",
			"/%252e%252e/x",
			"/%25252525",
			"/a/ b ",
			"",
			None,
			5,
		):
			self.assertIsNone(P.normalize_path(bad), bad)

	def test_encoded_slash_is_decoded_not_trusted(self):
		self.assertEqual(P.normalize_path("/app%2Ftodo"), "/app/todo")

	def test_keep_case(self):
		self.assertEqual(P.normalize_path_keep_case("/api/method/Foo.Bar?x=1"), "/api/method/Foo.Bar")
		self.assertEqual(P.normalize_path_keep_case("//a//B/"), "/a/B")
		self.assertIsNone(P.normalize_path_keep_case("/a/../b"))
		self.assertIsNone(P.normalize_path_keep_case("/a%5Cb"))


class TestNormalizeTarget(unittest.TestCase):
	def test_keeps_case_query_drops_fragment(self):
		self.assertEqual(P.normalize_target("/App/ToDo?x=Y#frag"), "/App/ToDo?x=Y")

	def test_rejects_unsafe(self):
		for bad in (
			"//evil.com",
			"/a//b",
			"/a\\b",
			"/%2F%2Fevil",
			"/a\x01b",
			"/a\nb",
			"/a/../b",
			"/a/%2e%2e/b",
			"https://x",
			"/a@b",
			"x/y",
			"/a?q=\\x",
			"/a?q=%0a",
			"/" + "a" * P.MAX_TARGET_LEN,
		):
			self.assertIsNone(P.normalize_target(bad), bad)

	def test_trailing_slash_kept(self):
		self.assertEqual(P.normalize_target("/huf/"), "/huf/")


class TestAliasesAndPrefixes(unittest.TestCase):
	def test_aliases_both_directions(self):
		self.assertEqual(P.desk_aliases("/app/x"), ["/app/x", "/desk/x"])
		self.assertEqual(P.desk_aliases("/desk/x"), ["/desk/x", "/app/x"])
		self.assertEqual(P.desk_aliases("/app"), ["/app", "/desk"])
		self.assertEqual(P.desk_aliases("/apple"), ["/apple"])
		self.assertEqual(P.desk_aliases("/huf"), ["/huf"])

	def test_parse_prefixes_lowercase(self):
		text = " /App/ToDo/ \n/\n\n/a?b\n/huf\n/desk/todo"
		self.assertEqual(P.parse_prefixes(text), ["/app/todo", "/desk/todo", "/huf"])

	def test_parse_prefixes_keep_case(self):
		self.assertEqual(
			P.parse_prefixes("/app/query-report/ToDo\n//x\nhttps://a", keep_case=True),
			["/app/query-report/ToDo", "/desk/query-report/ToDo"],
		)
		self.assertEqual(P.parse_prefixes(None), [])


class TestMatching(unittest.TestCase):
	def test_segment_boundary(self):
		prefixes = P.parse_prefixes("/app/query-report/ToDo", keep_case=True)
		self.assertTrue(P.path_matches("/app/query-report/ToDo", prefixes))
		self.assertTrue(P.path_matches("/desk/query-report/ToDo/x", prefixes))
		self.assertFalse(P.path_matches("/app/query-report/ToDoX", prefixes))
		self.assertFalse(P.path_matches("/app/query-report", prefixes))

	def test_target_allowed_ignores_query(self):
		self.assertTrue(P.target_allowed("/huf/chat?x=/other", ["/huf"]))
		self.assertFalse(P.target_allowed("/hufx?x=/huf", ["/huf"]))
