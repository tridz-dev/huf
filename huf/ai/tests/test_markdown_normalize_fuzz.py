"""Markdown block normalizer + structural fuzz of the leak guard.

Run with:
	bench --site <site> run-tests --app huf --module huf.ai.tests.test_markdown_normalize_fuzz
"""

import html as _html
import random
import re
import time
import unittest

from huf.ai.artifacts.render.html import render_document_html_with_report
from huf.ai.artifacts.render.markdown_guard import find_markdown_leaks, repair_markdown_leaks
from huf.ai.artifacts.render.markdown_normalize import normalize_markdown_blocks as norm

N_DOCS = 450

LEAK1 = (
	'<div class="split">\n<div class="split-main">\n\n## Key Quarterly Achievements\n'
	"* **Enterprise Expansion:** Secured 14 new contracts.\n* **Core Platform:** done.\n\n"
	"| Region | Accounts | Status |\n| :--- | :---: | :---: |\n"
	'| **North America** | 84,200 | <span class="status-badge">EXCEEDED</span> |\n\n</div>\n'
	'<div class="split-side">\n\n### Q1 2025 Priorities\n1. **Scale APAC Sales**\n- [x] **SOC 2**\n\n</div>\n</div>'
)
LEAK2 = (
	'<div class="split">\n<div class="split-main">\n## Phase 1: Foundations & Architecture\nThe first phase.\n'
	"1. **Digital Brand Audit**\nA complete evaluation.\n2. **Unified Core**\nConsolidating systems.\n"
	"## Growth Roadmap\nThe following schedule lists milestones.\n"
	"| Initiative | Target Date | Status |\n| :--- | :---: | :---: |\n"
	'| **Brand Identity** | Feb 15, 2025 | <span class="status-badge">COMPLETED</span> |\n'
	'| **Headless CMS** | Apr 01, 2025 | <span class="status-badge">IN PROGRESS</span> |\n</div>\n'
	'<div class="split-side">\n### Strategic Priorities\n* **Modernized CX** Move away.\n* **Unified Messaging** Align.\n'
	"### Key Milestones\n- [x] Technical discovery\n- [ ] Wireframe signoff\n</div>\n</div>"
)
LEAK3 = (
	'<div class="callout">\nIntro paragraph line\n- bullet one\n- bullet two\nMiddle paragraph\n'
	"1. first\n2. second\nTail paragraph\n- [x] done item\n- [ ] open item\nFinal words\n</div>"
)


def _text(body):
	t = re.sub(r"<(script|style)\b.*?</\1>", "", body, flags=re.S)
	return _html.unescape(re.sub(r"<[^>]+>", " ", t))


def _body(doc):
	return doc[doc.index("<body>") + 6 : doc.rindex("</body>")].strip()


class TestNormalizer(unittest.TestCase):
	def test_table_after_paragraph(self):
		out = norm("Intro\n| a | b |\n| :--- | :---: |\n| 1 | 2 |\nAfter")
		self.assertEqual(out, "Intro\n\n| a | b |\n| :--- | :---: |\n| 1 | 2 |\n\nAfter")

	def test_noop_on_wellformed(self):
		src = "# T\n\nPara\n\n- a\n  - b\n- c\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n```\n## x\n- y\n```\n\n> q\n\nEnd\n"
		self.assertEqual(norm(src), src)

	def test_prose_pipes_untouched(self):
		for src in ("a | b alone\nnext line", "run `ls | grep x`\nthen cat f | wc\ndone", "x | y\n---\nz"):
			self.assertEqual(norm(src), src)

	def test_code_regions_untouched(self):
		src = "Para\n```\n## h\n- a\n| a | b |\n|---|---|\n```\nEnd\n<pre>\n## h\n- a\n</pre>\n<!--\n- x\n-->\n"
		out = norm(src)
		self.assertIn("```\n## h\n- a\n| a | b |\n|---|---|\n```", out)
		self.assertIn("<pre>\n## h\n- a\n</pre>", out)
		self.assertIn("<!--\n- x\n-->", out)

	def test_lists(self):
		self.assertEqual(norm("Text\n- a\n- b\nMore"), "Text\n\n- a\n- b\n\nMore")
		# lazy continuation inside a list is not split
		src = "1. A\ndesc\n2. B\ndesc2"
		self.assertEqual(norm(src), src)
		# nested and indented continuation are not split
		src = "- a\n  - b\n    cont\n  - c\n- d"
		self.assertEqual(norm(src), src)
		# a year-like number does not start a list
		self.assertEqual(norm("in the year\n2023. was good"), "in the year\n2023. was good")

	def test_idempotent_on_corpus(self):
		for src in (LEAK1, LEAK2, LEAK3, "a\n# h\nb\n> q\nc\n- x\ny\n```\nz\n```\nw"):
			once = norm(src)
			self.assertEqual(norm(once), once)


class TestRegressionFixtures(unittest.TestCase):
	def _check(self, src, language="html"):
		doc, rep = render_document_html_with_report(src, language=language)
		body = _body(doc)
		self.assertEqual(find_markdown_leaks(body), [])
		self.assertEqual(rep["fallback_used"], 0)
		self.assertEqual(rep["leaks_remaining"], 0)
		return body

	def test_leak1(self):
		body = self._check(LEAK1)
		self.assertIn("<table>", body)

	def test_leak2_table_after_paragraph(self):
		body = self._check(LEAK2)
		self.assertEqual(body.count("<table>"), 1)
		self.assertNotIn("| :---", body)
		self.assertIn("<h2>", body)

	def test_lists_after_paragraphs(self):
		body = self._check(LEAK3)
		self.assertIn("<ul>", body)
		self.assertIn("<ol>", body)

	def test_markdown_language_without_blank_lines(self):
		body = self._check("Intro\n| a | b |\n|---|---|\n| 1 | 2 |\nAfter\n- x\n- y\n", "markdown")
		self.assertIn("<table>", body)


class TestCollapsedTableParagraph(unittest.TestCase):
	HTML = '<div><p>Intro\n| a | b |\n| :--- | :---: |\n| 1 | <span class="status-badge">OK</span> |</p></div>'

	def test_detected_and_repaired(self):
		kinds = {lk.kind for lk in find_markdown_leaks(self.HTML)}
		self.assertIn("table", kinds)
		fixed, count = repair_markdown_leaks(self.HTML)
		self.assertGreaterEqual(count, 1)
		self.assertEqual(find_markdown_leaks(fixed), [])
		self.assertIn("<table>", fixed)
		self.assertIn("status-badge", fixed)


class TestFallback(unittest.TestCase):
	def test_fallback_strips_markers(self):
		from huf.ai.artifacts.render.markdown_guard import fallback_markdown_leaks

		leaky = "<td>## Head\n- **a**\n- b\n| x | y |\n| --- | --- |\n</td>"
		self.assertTrue(find_markdown_leaks(leaky))
		out, n = fallback_markdown_leaks(leaky)
		self.assertEqual(n, 1)
		self.assertEqual(find_markdown_leaks(out), [])
		for bad in ("##", "**", "| ---"):
			self.assertNotIn(bad, out)
		self.assertIn("•", out)


# ---------------------------------------------------------------- fuzz

_EMOJI = ["\U0001F680", "✅", "\U0001F389"]
_ARABIC = ["المبيعات", "مرحبا"]


class _Gen:
	def __init__(self, seed):
		self.r = random.Random(seed)
		self.seed = seed
		self.n = 0
		self.words = []
		self.code = []

	def w(self):
		self.n += 1
		t = f"tk{self.seed}x{self.n}"
		self.words.append(t)
		return t

	def inline(self):
		r = self.r
		k = r.choice(["plain", "plain", "bold", "ital", "link", "code", "emoji", "arabic", "ubold"])
		a, b = self.w(), self.w()
		return {
			"plain": f"{a} {b}",
			"bold": f"**{a}** {b}",
			"ital": f"*{a}* {b}",
			"link": f"[{a} {b}](https://example.com/page)",
			"code": f"{a} `**{b}**`",
			"emoji": f"{r.choice(_EMOJI)} {a} {b}",
			"arabic": f"{a} {r.choice(_ARABIC)} {b}",
			"ubold": f"__{a}__ {b}",
		}[k]

	def block(self):
		r = self.r
		k = r.choice(["h", "p", "ul", "ol", "nested", "task", "table", "quote", "fence", "p", "ul", "table"])
		if k == "h":
			return "#" * r.randint(1, 4) + " " + self.inline()
		if k == "p":
			return "\n".join(self.inline() for _ in range(r.randint(1, 3)))
		if k == "ul":
			m = r.choice("-*+")
			return "\n".join(f"{m} {self.inline()}" for _ in range(r.randint(2, 4)))
		if k == "ol":
			lines = []
			for i in range(r.randint(2, 4)):
				lines.append(f"{i + 1}. {self.inline()}")
				if r.random() < 0.3:
					lines.append(self.w() + " desc")
			return "\n".join(lines)
		if k == "nested":
			return f"- {self.inline()}\n  - {self.inline()}\n  - {self.inline()}\n- {self.inline()}"
		if k == "task":
			return "\n".join(f"- [{r.choice(' x')}] {self.inline()}" for _ in range(r.randint(2, 3)))
		if k == "table":
			cols = r.randint(2, 4)
			align = r.choice(["|" + "|".join(["---"] * cols) + "|", "| " + " | ".join(r.choice([":---", ":---:", "---:", "---"]) for _ in range(cols)) + " |"])
			rows = ["| " + " | ".join(self.w() for _ in range(cols)) + " |", align]
			for _ in range(r.randint(1, 3)):
				cells = []
				for _ in range(cols):
					c = self.w()
					if r.random() < 0.25:
						cells.append(f'<span class="status-badge">{c.upper()}</span>')
						self.words.remove(c)
						self.words.append(c.upper())
					elif r.random() < 0.3:
						cells.append(f"**{c}**")
					else:
						cells.append(c)
				rows.append("| " + " | ".join(cells) + " |")
			return "\n".join(rows)
		if k == "quote":
			return "\n".join("> " + self.inline() for _ in range(r.randint(1, 2)))
		body = [r.choice(["## not heading **x**", "- not list", "| a | b |", "|---|---|", "**bold** `c`", "plain"]) for _ in range(r.randint(1, 3))]
		self.code.append(body)
		return "```" + r.choice(["", "python", "text"]) + "\n" + "\n".join(body) + "\n```"

	def container(self, blocks, indent):
		r = self.r
		sep = lambda: "\n\n" if r.random() < 0.4 else "\n"  # noqa: E731

		def join(bs):
			out = ""
			for i, b in enumerate(bs):
				if "```" not in b and indent:
					b = "\n".join("  " + ln for ln in b.split("\n"))
				out += (sep() if i else "") + b
			return out

		kind = r.choice(["none", "split", "callout", "section", "details", "aside", "bq", "nested"])
		if kind == "none":
			return sep().join(blocks)
		if kind == "split":
			h = max(1, len(blocks) // 2)
			return (
				'<div class="split">\n<div class="split-main">\n' + join(blocks[:h]) + '\n</div>\n<div class="split-side">\n'
				+ join(blocks[h:] or [self.block()]) + "\n</div>\n</div>"
			)
		if kind == "details":
			return "<details>\n<summary>Sum</summary>\n" + join(blocks) + "\n</details>"
		if kind == "bq":
			return "<div>\n<blockquote>\n" + join(blocks) + "\n</blockquote>\n</div>"
		if kind == "nested":
			d = r.randint(1, 3)
			return "<div>\n" * d + join(blocks) + "\n</div>" * d
		tag, cls = {"callout": ("div", ' class="callout"'), "section": ("section", ""), "aside": ("aside", "")}[kind]
		return f"<{tag}{cls}>\n" + join(blocks) + f"\n</{tag}>"

	def doc(self):
		r = self.r
		blocks = [self.block() for _ in range(r.randint(2, 7))]
		# two tables with no blank line between are ambiguous by definition
		for i in range(1, len(blocks)):
			if blocks[i].startswith("| ") and blocks[i - 1].startswith("| "):
				blocks[i - 1] += "\n"
		lang = r.choice(["markdown", "html"])
		indent = r.random() < 0.3
		src = self.container(blocks, indent)
		if lang == "markdown" and r.random() < 0.5:
			src = "\n\n".join(blocks) if r.random() < 0.5 else "\n".join(blocks)
		return lang, src


class TestFuzz(unittest.TestCase):
	def test_fuzz_documents(self):
		fallbacks = []
		for seed in range(N_DOCS):
			g = _Gen(seed)
			lang, src = g.doc()
			ctx = f"seed={seed} lang={lang}\n{src}"
			t0 = time.perf_counter()
			doc, rep = render_document_html_with_report(src, language=lang)
			dt = time.perf_counter() - t0
			body = _body(doc)
			# Generous: guards against pathological blow-ups only; loaded CI runners must not flake.
			self.assertLess(dt, 8.0, ctx)
			self.assertEqual(find_markdown_leaks(body), [], ctx)
			if rep["fallback_used"]:
				fallbacks.append(seed)
			text = _text(body)
			for w in g.words:
				self.assertIn(w, text, f"lost word {w}\n{ctx}\n{body}")
			plain = _html.unescape(body)
			for code in g.code:
				self.assertIn("\n".join(code), plain, f"code altered\n{ctx}\n{body}")
			# stable on second render
			doc2, rep2 = render_document_html_with_report(body, language="html")
			self.assertEqual(_body(doc2), body, f"unstable second render\n{ctx}")
		print(f"\n[fuzz] {N_DOCS} docs, fallback seeds: {fallbacks}")
		self.assertEqual(fallbacks, [], "fallback_used for seeds (see output)")

	def test_normalizer_idempotent_and_noop(self):
		for seed in range(N_DOCS):
			g = _Gen(seed)
			_, src = g.doc()
			once = norm(src)
			self.assertEqual(norm(once), once, f"seed={seed}\n{src}")
			self.assertEqual(norm(norm(once)), once)
