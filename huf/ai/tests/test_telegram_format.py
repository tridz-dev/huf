"""Golden corpus for markdown -> Telegram HTML / MarkdownV2 / plain, and 4096-char splitting."""

from __future__ import annotations

import html.parser
import re
import unittest

from huf.ai.gateway_adapters.telegram_format import (
	TELEGRAM_TEXT_LIMIT,
	escape_html,
	escape_markdown_v2,
	render_parts,
	split_message,
	to_markdown_v2,
	to_plain,
	to_telegram_html,
)

HTML_CASES = [
	("plain & <tag>", "plain &amp; &lt;tag&gt;"),
	("**bold** and *it* and ~~gone~~", "<b>bold</b> and <i>it</i> and <s>gone</s>"),
	("**bold *nested* more**", "<b>bold <i>nested</i> more</b>"),
	("***both***", "<b><i>both</i></b>"),
	("`a<b>&c`", "<code>a&lt;b&gt;&amp;c</code>"),
	("snake_case_name stays", "snake_case_name stays"),
	("2*3*4 math", "2*3*4 math"),
	("[ex](https://e.com/a?b=1&c=2)", '<a href="https://e.com/a?b=1&amp;c=2">ex</a>'),
	("[bad](javascript:alert(1))", "[bad](javascript:alert(1))"),
	("[w](https://x.com/a_(b))", '<a href="https://x.com/a_(b)">w</a>'),
	("# Head\ntext", "<b>Head</b>\ntext"),
	("- a\n- b\n  - c", "• a\n• b\n  • c"),
	("1. one\n2. two", "1. one\n2. two"),
	("> quoted *x*", "<blockquote>quoted <i>x</i></blockquote>"),
	("```py\nx = 1 < 2\n```", '<pre><code class="language-py">x = 1 &lt; 2</code></pre>'),
	("```\nno lang\n```", "<pre>no lang</pre>"),
	("||secret||", "<tg-spoiler>secret</tg-spoiler>"),
	("| a | b |\n|---|---|\n| 1 | 2 |", "<pre>a | b\n1 | 2</pre>"),
]

MDV2_CASES = [
	("1.5 + 2 = 3!", r"1\.5 \+ 2 \= 3\!"),
	("**bold** and *it*", "*bold* and _it_"),
	("**b *i* b**", "*b _i_ b*"),
	("`co_de.x`", "`co_de.x`"),
	("`back\\slash`", "`back\\\\slash`"),
	("[a](https://x.com/a_(b))", r"[a](https://x.com/a_(b\))"),
	("(parens) [br] {c} #h |p| ~t~ >g -d", r"\(parens\) \[br\] \{c\} \#h \|p\| \~t\~ \>g \-d"),
	("# H", "*H*"),
	("- x\n1. y", "• x\n1\\. y"),
	("```py\nprint('`')\n```", "```py\nprint('\\`')\n```"),
	("> q.", ">q\\."),
]


class _Balanced(html.parser.HTMLParser):
	def __init__(self):
		super().__init__()
		self.stack = []
		self.ok = True

	def handle_starttag(self, tag, attrs):
		self.stack.append(tag)

	def handle_endtag(self, tag):
		if not self.stack or self.stack.pop() != tag:
			self.ok = False


def balanced(markup):
	p = _Balanced()
	p.feed(markup)
	return p.ok and not p.stack


class TestEscaping(unittest.TestCase):
	def test_escape_html(self):
		self.assertEqual(escape_html('<a href="x">&</a>'), '&lt;a href="x"&gt;&amp;&lt;/a&gt;')

	def test_escape_markdown_v2_all_specials(self):
		specials = "_*[]()~`>#+-=|{}.!\\"
		self.assertEqual(escape_markdown_v2(specials), "".join("\\" + c for c in specials))


class TestGolden(unittest.TestCase):
	def test_html_corpus(self):
		for src, want in HTML_CASES:
			with self.subTest(src):
				self.assertEqual(to_telegram_html(src), want)

	def test_markdown_v2_corpus(self):
		for src, want in MDV2_CASES:
			with self.subTest(src):
				self.assertEqual(to_markdown_v2(src), want)

	def test_plain_strips_markup_and_keeps_link_target(self):
		self.assertEqual(to_plain("**b** `c` [t](https://x.y)"), "b c t (https://x.y)")
		self.assertEqual(to_plain("```\ncode\n```"), "code")

	def test_empty(self):
		self.assertEqual(to_telegram_html(""), "")
		self.assertEqual(render_parts("   "), [])


class TestSplitting(unittest.TestCase):
	def test_short_text_unchanged(self):
		self.assertEqual(split_message("hello"), ["hello"])

	def test_long_paragraphs_split_on_boundaries(self):
		text = "\n\n".join(f"para {i} " + "word " * 200 for i in range(10))
		parts = split_message(text)
		self.assertGreater(len(parts), 1)
		self.assertTrue(all(len(p) <= TELEGRAM_TEXT_LIMIT for p in parts))
		self.assertEqual(re.sub(r"\s+", " ", " ".join(parts)).strip(), re.sub(r"\s+", " ", text).strip())

	def test_huge_unbroken_text_hard_cut(self):
		parts = split_message("x" * 10000)
		self.assertEqual([len(p) for p in parts], [4096, 4096, 1808])

	def test_oversized_fence_split_into_complete_fences(self):
		code = "\n".join(f"line {i}" for i in range(1500))
		parts = split_message("```py\n" + code + "\n```")
		self.assertGreater(len(parts), 1)
		for p in parts:
			self.assertTrue(p.startswith("```py\n") and p.endswith("\n```"))
			self.assertLessEqual(len(p), TELEGRAM_TEXT_LIMIT)

	def test_fence_never_split_when_it_fits(self):
		fence = "```\n" + "a\n" * 1000 + "```"
		text = "intro " * 400 + "\n\n" + fence + "\n\n" + "outro " * 400
		for p in split_message(text):
			self.assertEqual(p.count("```") % 2, 0)

	def test_rendered_parts_respect_limit_and_entities_html(self):
		text = "\n\n".join(f"**bold {i}** & <x> " + "w<> " * 300 for i in range(12))
		parts = render_parts(text, "HTML")
		self.assertGreater(len(parts), 1)
		for part in parts:
			self.assertLessEqual(len(part.text), TELEGRAM_TEXT_LIMIT)
			self.assertEqual(part.parse_mode, "HTML")
			self.assertTrue(balanced(part.text), part.text[:80])

	def test_escape_heavy_markdown_v2_resplits_under_limit(self):
		text = ("1.5+2=3! " * 600).strip()
		parts = render_parts(text, "MarkdownV2")
		self.assertGreater(len(parts), 1)
		for part in parts:
			self.assertLessEqual(len(part.text), TELEGRAM_TEXT_LIMIT)
			self.assertNotRegex(part.text, r"(?<!\\)[!+=](?<!\\)")  # every special is escaped (no bare ones)

	def test_long_code_block_html_stays_balanced(self):
		code = "\n".join(f"if a < {i} && b > {i}: pass" for i in range(900))
		parts = render_parts("```py\n" + code + "\n```", "HTML")
		self.assertGreater(len(parts), 1)
		for part in parts:
			self.assertTrue(balanced(part.text))
			self.assertLessEqual(len(part.text), TELEGRAM_TEXT_LIMIT)

	def test_plain_mode_is_verbatim(self):
		parts = render_parts("**not converted** <b>", "")
		self.assertEqual([(p.text, p.parse_mode) for p in parts], [("**not converted** <b>", "")])
