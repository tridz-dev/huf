"""Unit tests for whatsapp_format (pure Python; loadable without frappe)."""

import importlib.util
import os
import unittest


def _load(name):
	try:
		import importlib

		return importlib.import_module(f"huf.ai.gateway_adapters.{name}")
	except Exception:
		path = os.path.join(os.path.dirname(__file__), "..", "..", "gateway_adapters", f"{name}.py")
		spec = importlib.util.spec_from_file_location(name, path)
		mod = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(mod)
		return mod


wf = _load("whatsapp_format")
FENCE = "```"


class TestToWhatsapp(unittest.TestCase):
	CASES = [
		("bold_star", "a **b** c", "a *b* c"),
		("bold_under", "a __b__ c", "a *b* c"),
		("italic_star", "a *b* c", "a _b_ c"),
		("bold_italic", "***x***", "*_x_*"),
		("bold_and_italic", "**b** and *i*", "*b* and _i_"),
		("strike", "~~gone~~", "~gone~"),
		("h1", "# Title", "*Title*"),
		("h6", "###### Deep", "*Deep*"),
		("heading_closing_hashes", "## Hi ##", "*Hi*"),
		("heading_with_bold", "## **Hi** there", "*Hi there*"),
		("link", "see [docs](https://a.com/x)", "see docs (https://a.com/x)"),
		("link_same", "[https://a.com](https://a.com)", "https://a.com"),
		("image", "![alt](https://a.com/i.png)", "https://a.com/i.png"),
		("bare_url_kept", "go to https://a.com/a_b__c.", "go to https://a.com/a_b__c."),
		("snake_case_kept", "use snake_case_name here", "use snake_case_name here"),
		("dash_bullets", "- a\n- b", "• a\n• b"),
		("star_bullets", "* a\n* b", "• a\n• b"),
		("nested_bullet", "- a\n  - b", "• a\n  • b"),
		("numbered_kept", "1. a\n2. b", "1. a\n2. b"),
		("blockquote_kept", "> quote", "> quote"),
		("hr_removed", "a\n\n---\n\nb", "a\n\nb"),
		("inline_code_kept", "run `**x**` now", "run `**x**` now"),
		("html_stripped", "<b>hi</b> <i>x</i>", "hi x"),
		("br_newline", "a<br>b", "a\nb"),
		("blank_collapse", "a\n\n\n\n\nb", "a\n\nb"),
		("trailing_spaces", "a   \nb \t", "a\nb"),
		("crlf", "a\r\nb", "a\nb"),
		("table", "| a | b |\n|---|---|\n| 1 | 2 |", "a | b\n1 | 2"),
		("table_bold_cell", "| a | b |\n| --- | :-: |\n| 1 | **2** |", "a | b\n1 | *2*"),
		("unicode_emoji", "**héllo** 😀 *wörld*", "*héllo* 😀 _wörld_"),
		("rtl", "**مرحبا** بالعالم", "*مرحبا* بالعالم"),
		("math_stars_untouched", "2 * 3 * 4", "2 * 3 * 4"),
		("unclosed_bold", "a **b", "a **b"),
		("less_than_text", "if a < b and c > d", "if a < b and c > d"),
		("autolink", "<https://a.com/x>", "https://a.com/x"),
	]

	def test_table(self):
		for name, src, want in self.CASES:
			with self.subTest(name):
				self.assertEqual(wf.to_whatsapp(src), want)

	def test_fenced_code_verbatim(self):
		src = f"**b**\n{FENCE}py\n**x** # y\n- z\n  \n\n\n{FENCE}\n- after"
		out = wf.to_whatsapp(src)
		self.assertIn(f"{FENCE}py\n**x** # y\n- z\n  \n\n\n{FENCE}", out)
		self.assertTrue(out.startswith("*b*\n"))
		self.assertTrue(out.endswith("• after"))

	def test_tilde_fence_verbatim(self):
		out = wf.to_whatsapp("~~~\n# not heading\n~~~")
		self.assertEqual(out, "~~~\n# not heading\n~~~")

	def test_unclosed_fence_kept(self):
		self.assertEqual(wf.to_whatsapp(f"{FENCE}\n**x**\n"), f"{FENCE}\n**x**")

	def test_none_and_empty(self):
		for v in (None, "", "   \n\n ", b""):
			self.assertEqual(wf.to_whatsapp(v), "")

	def test_non_string_input(self):
		self.assertEqual(wf.to_whatsapp(123), "123")
		self.assertEqual(wf.to_whatsapp(b"**x**"), "*x*")

	def test_adversarial_no_raise(self):
		nasty = [
			"*" * 5000,
			"**" * 3000,
			"[" * 2000 + "](" * 2000,
			"|" * 3000,
			"`" * 4001,
			"_" * 5000,
			"~" * 5001,
			"<" * 1000 + ">" * 1000,
			"" + "0" + " **x**",
			"- " * 2000,
			"# " * 2000,
			"![](" * 500,
		]
		for s in nasty:
			with self.subTest(s[:20]):
				self.assertIsInstance(wf.to_whatsapp(s), str)

	def test_private_use_input_stripped(self):
		self.assertEqual(wf.to_whatsapp("abc"), "abc")

	def test_nested_markdown(self):
		self.assertEqual(wf.to_whatsapp("- **bold [l](http://a.b)**"), "• *bold l (http://a.b)*")

	def test_idempotent_on_whatsapp_text(self):
		for s in ("_i_ ~s~ `c` > q", "• a\n• b\n1. x", "https://a.com/a_b", f"{FENCE}\n*x*\n{FENCE}", "plain text"):
			with self.subTest(s):
				self.assertEqual(wf.to_whatsapp(wf.to_whatsapp(s)), wf.to_whatsapp(s))

	def test_very_long_text(self):
		src = ("**bold** text. " * 20000)
		out = wf.to_whatsapp(src)
		self.assertTrue(out.startswith("*bold* text."))

	def test_blank_line_kept_before_code_fence(self):
		out = wf.to_whatsapp(f"intro\n\n{FENCE}\nx\n{FENCE}")
		self.assertEqual(out, f"intro\n\n{FENCE}\nx\n{FENCE}")


class TestSplitBody(unittest.TestCase):
	def check(self, parts, limit):
		self.assertTrue(parts)
		for p in parts:
			self.assertTrue(p.strip(), "empty part")
			self.assertLessEqual(len(p), limit)

	def test_empty_none(self):
		for v in (None, "", "  \n "):
			self.assertEqual(wf.split_body(v), [])

	def test_short_single(self):
		self.assertEqual(wf.split_body("hello"), ["hello"])

	def test_boundary_4096_exact(self):
		s = "a" * 4096
		self.assertEqual(wf.split_body(s), [s])

	def test_boundary_4097(self):
		parts = wf.split_body("a" * 4097)
		self.check(parts, 4096)
		self.assertEqual(len(parts), 2)
		self.assertEqual("".join(parts), "a" * 4097)

	def test_9000_chars_three_parts_in_order(self):
		paras = [f"P{i} " + "x" * 2998 for i in range(3)]
		parts = wf.split_body("\n\n".join(paras))
		self.check(parts, 4096)
		self.assertEqual(len(parts), 3)
		for i, p in enumerate(parts):
			self.assertTrue(p.startswith(f"P{i} "))

	def test_paragraph_boundaries_preferred(self):
		a, b = "a" * 3000, "b" * 3000
		self.assertEqual(wf.split_body(f"{a}\n\n{b}"), [a, b])

	def test_paragraphs_packed(self):
		text = "\n\n".join(["para %d" % i for i in range(10)])
		self.assertEqual(wf.split_body(text), [text])

	def test_line_fallback(self):
		lines = [("l%d " % i) + "y" * 97 for i in range(100)]
		parts = wf.split_body("\n".join(lines), 1000)
		self.check(parts, 1000)
		self.assertEqual("\n".join(parts).split("\n"), lines)

	def test_sentence_fallback(self):
		s = " ".join("Sentence number %d is here." % i for i in range(200))
		parts = wf.split_body(s, 300)
		self.check(parts, 300)
		for p in parts:
			self.assertTrue(p.endswith("."))
		self.assertEqual(" ".join(parts), s)

	def test_space_fallback(self):
		s = " ".join(["word"] * 500)
		parts = wf.split_body(s, 101)
		self.check(parts, 101)
		self.assertEqual(" ".join(parts), s)

	def test_hard_cut_fallback(self):
		s = "z" * 10000
		parts = wf.split_body(s, 1000)
		self.check(parts, 1000)
		self.assertEqual("".join(parts), s)
		self.assertEqual(len(parts), 10)

	def test_order_preserved(self):
		s = " ".join(str(i) for i in range(5000))
		parts = wf.split_body(s, 500)
		self.check(parts, 500)
		self.assertEqual(" ".join(parts).split(), s.split())

	def test_fence_not_cut_when_fits(self):
		code = f"{FENCE}\n" + "\n".join("code line %d" % i for i in range(40)) + f"\n{FENCE}"
		text = "intro " * 200 + "\n\n" + code
		parts = wf.split_body(text, 1500)
		self.check(parts, 1500)
		hits = [p for p in parts if FENCE in p]
		self.assertEqual(len(hits), 1)
		self.assertEqual(hits[0].count(FENCE), 2)

	def test_fence_moves_whole_to_next_part(self):
		code = f"{FENCE}\n" + "c" * 400 + f"\n{FENCE}"
		parts = wf.split_body("a" * 700 + "\n\n" + code, 800)
		self.assertEqual(parts[0], "a" * 700)
		self.assertEqual(parts[1], code)

	def test_oversized_fence_reopened(self):
		body = "\n".join("line %04d" % i for i in range(300))
		parts = wf.split_body(f"{FENCE}py\n{body}\n{FENCE}", 500)
		self.check(parts, 500)
		self.assertGreater(len(parts), 1)
		for p in parts:
			self.assertTrue(p.startswith(f"{FENCE}py\n"))
			self.assertTrue(p.endswith(f"\n{FENCE}"))
		rebuilt = "\n".join(p.split("\n", 1)[1].rsplit("\n", 1)[0] for p in parts)
		self.assertEqual(rebuilt, body)

	def test_oversized_fence_long_line_hard_cut(self):
		parts = wf.split_body(f"{FENCE}\n" + "q" * 3000 + f"\n{FENCE}", 500)
		self.check(parts, 500)
		for p in parts:
			self.assertTrue(p.startswith(FENCE) and p.endswith(FENCE))
		self.assertEqual(sum(p.count("q") for p in parts), 3000)

	def test_unclosed_fence(self):
		parts = wf.split_body(f"{FENCE}\n" + "\n".join(["row"] * 400), 300)
		self.check(parts, 300)
		self.assertTrue(all(p.startswith(FENCE) for p in parts))

	def test_text_after_oversized_fence(self):
		body = "\n".join("l%03d" % i for i in range(200))
		parts = wf.split_body(f"{FENCE}\n{body}\n{FENCE}\n\nthe end", 400)
		self.check(parts, 400)
		self.assertIn("the end", parts[-1])

	def test_unicode_emoji_rtl(self):
		s = "😀 مرحبا " * 1000
		parts = wf.split_body(s, 200)
		self.check(parts, 200)
		self.assertEqual(" ".join(parts).split(), s.split())

	def test_tiny_limit_and_bad_limit(self):
		parts = wf.split_body("abcdef", 1)
		self.assertEqual(parts, list("abcdef"))
		self.assertEqual(wf.split_body("abc", 0), list("abc"))
		self.assertEqual(wf.split_body("abc", None), ["abc"])

	def test_no_numbering_added(self):
		for p in wf.split_body("a" * 5000):
			self.assertNotIn("(1/", p)

	def test_whitespace_only_edges_trimmed(self):
		parts = wf.split_body("\n\n" + "a" * 3000 + "\n\n\n\n" + "b" * 3000 + "\n\n")
		self.assertEqual(parts, ["a" * 3000, "b" * 3000])


if __name__ == "__main__":
	unittest.main()
