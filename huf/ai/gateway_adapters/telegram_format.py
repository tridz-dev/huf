# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Agent markdown -> Telegram HTML / MarkdownV2 / plain text, plus 4096-char splitting.

Pure; no Frappe and no WhatsApp imports. Markdown is parsed once into a small tree and
rendered by three renderers, so escaping is done in exactly one place per target. Splitting
happens on the *source* markdown (fence-aware) and each part is converted independently, so a
split can never cut through an entity; parts whose converted form exceeds the limit are re-split
smaller.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any, Union

TELEGRAM_TEXT_LIMIT = 4096
TELEGRAM_CAPTION_LIMIT = 1024

MODE_HTML = "HTML"
MODE_MARKDOWN_V2 = "MarkdownV2"
MODE_PLAIN = ""

def escape_html(text: str) -> str:
	return html.escape(text, quote=False)


def escape_markdown_v2(text: str) -> str:
	"""Escape every character Telegram reserves in MarkdownV2 normal text."""
	return re.sub(r"([_*\[\]()~`>#+\-=|{}.!\\])", r"\\\1", text)


def _escape_mdv2_code(text: str) -> str:
	return text.replace("\\", "\\\\").replace("`", "\\`")


def _escape_mdv2_url(url: str) -> str:
	return url.replace("\\", "\\\\").replace(")", "\\)")


# -- inline tree -------------------------------------------------------------------------------

Node = Union[str, tuple]  # str = text; tuple = (kind, children|text, extra)

_INLINE = re.compile(
	r"(?P<code>`(?P<code_t>[^`\n]+)`)"
	r"|(?P<link>\[(?P<link_t>[^\]\n]+)\]\((?P<link_u>(?:[^()\s]|\([^()\s]*\))+)\))"
	r"|(?P<bi>\*\*\*(?=\S)(?P<bi_t>.+?)(?<=\S)\*\*\*)"
	r"|(?P<bold>\*\*(?=\S)(?P<bold_t>.+?)(?<=\S)\*\*|(?<![\w_])__(?=\S)(?P<bold2_t>.+?)(?<=\S)__(?![\w_]))"
	r"|(?P<strike>~~(?=\S)(?P<strike_t>.+?)(?<=\S)~~)"
	r"|(?P<spoiler>\|\|(?=\S)(?P<spoiler_t>.+?)(?<=\S)\|\|)"
	r"|(?P<ital>(?<![\w*])\*(?=[^\s*])(?P<ital_t>[^*\n]+?)(?<=[^\s*])\*(?![\w*])"
	r"|(?<![\w_])_(?=[^\s_])(?P<ital2_t>[^_\n]+?)(?<=[^\s_])_(?![\w_]))",
	re.S,
)
_SAFE_URL = re.compile(r"^(https?://|tg://|mailto:)", re.I)


def parse_inline(text: str) -> list[Node]:
	nodes: list[Node] = []
	pos = 0
	for m in _INLINE.finditer(text):
		if m.start() > pos:
			nodes.append(text[pos : m.start()])
		pos = m.end()
		if m.group("code"):
			nodes.append(("code", m.group("code_t"), None))
		elif m.group("link"):
			url = m.group("link_u")
			label = parse_inline(m.group("link_t"))
			nodes.append(("link", label, url) if _SAFE_URL.match(url) else m.group(0))
		elif m.group("bi"):
			nodes.append(("b", [("i", parse_inline(m.group("bi_t")), None)], None))
		elif m.group("bold"):
			nodes.append(("b", parse_inline(m.group("bold_t") or m.group("bold2_t")), None))
		elif m.group("strike"):
			nodes.append(("s", parse_inline(m.group("strike_t")), None))
		elif m.group("spoiler"):
			nodes.append(("spoiler", parse_inline(m.group("spoiler_t")), None))
		else:
			nodes.append(("i", parse_inline(m.group("ital_t") or m.group("ital2_t")), None))
	if pos < len(text):
		nodes.append(text[pos:])
	return nodes


# -- block tree --------------------------------------------------------------------------------

_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})\s*([\w+#.-]*)\s*$")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
_BULLET = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_ORDERED = re.compile(r"^(\s*)(\d{1,9})[.)]\s+(.*)$")
_QUOTE = re.compile(r"^\s{0,3}>\s?(.*)$")
_HR = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


@dataclass
class Block:
	kind: str  # para | code | quote | table
	text: str = ""
	lang: str = ""
	lines: tuple[str, ...] = ()


def parse_blocks(text: str) -> list[Block]:
	lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
	blocks: list[Block] = []
	i = 0
	para: list[str] = []

	def flush() -> None:
		if para:
			blocks.append(Block("para", lines=tuple(para)))
			para.clear()

	while i < len(lines):
		line = lines[i]
		fm = _FENCE.match(line)
		if fm:
			flush()
			char, n, lang = fm.group(1)[0], len(fm.group(1)), fm.group(2)
			i += 1
			body: list[str] = []
			while i < len(lines):
				close = re.match(r"^\s{0,3}(" + re.escape(char) + "{" + str(n) + r",})\s*$", lines[i])
				if close:
					break
				body.append(lines[i])
				i += 1
			i += 1
			blocks.append(Block("code", text="\n".join(body), lang=lang))
			continue
		if _QUOTE.match(line):
			flush()
			q: list[str] = []
			while i < len(lines) and _QUOTE.match(lines[i]):
				q.append(_QUOTE.match(lines[i]).group(1))
				i += 1
			blocks.append(Block("quote", lines=tuple(q)))
			continue
		if "|" in line and i + 1 < len(lines) and _TABLE_SEP.match(lines[i + 1]) and "|" in lines[i + 1]:
			flush()
			rows = [line]
			i += 2
			while i < len(lines) and "|" in lines[i] and lines[i].strip():
				rows.append(lines[i])
				i += 1
			blocks.append(Block("table", lines=tuple(r.strip().strip("|").strip() for r in rows)))
			continue
		if not line.strip():
			flush()
			i += 1
			continue
		para.append(line)
		i += 1
	flush()
	return blocks


def _line_prefix(line: str) -> tuple[str, str, str, bool]:
	"""Return (kind, indent/marker, content, is_special) for one paragraph line."""
	if _HR.match(line):
		return "hr", "", "", True
	m = _HEADING.match(line)
	if m:
		return "heading", "", m.group(1), True
	m = _BULLET.match(line)
	if m:
		return "bullet", "  " * (len(m.group(1)) // 2), m.group(2), True
	m = _ORDERED.match(line)
	if m:
		return "ordered", m.group(1) + m.group(2) + ".", m.group(3), True
	return "text", "", line, False


# -- renderers ---------------------------------------------------------------------------------


class _Renderer:
	mode = MODE_PLAIN

	def text(self, s: str) -> str:
		return s

	def code(self, s: str) -> str:
		return s

	def wrap(self, kind: str, inner: str, extra: Any = None) -> str:
		return inner

	def pre(self, s: str, lang: str) -> str:
		return s

	def quote(self, inner: str) -> str:
		return inner

	def bullet(self) -> str:
		return "• "

	def marker(self, m: str) -> str:
		return m

	def hr(self) -> str:
		return "——————"

	def inline(self, nodes: list[Node]) -> str:
		out = []
		for n in nodes:
			if isinstance(n, str):
				out.append(self.text(n))
			elif n[0] == "code":
				out.append(self.wrap("code", self.code(n[1])))
			else:
				out.append(self.wrap(n[0], self.inline(n[1]), n[2]))
		return "".join(out)

	def render(self, markdown: str) -> str:
		parts: list[str] = []
		for b in parse_blocks(markdown):
			if b.kind == "code":
				parts.append(self.pre(b.text, b.lang))
			elif b.kind == "table":
				parts.append(self.pre("\n".join(b.lines), ""))
			elif b.kind == "quote":
				parts.append(self.quote("\n".join(self.inline(parse_inline(x)) for x in b.lines)))
			else:
				parts.append("\n".join(self._para_line(x) for x in b.lines))
		return "\n\n".join(p for p in parts if p.strip()).strip()

	def _para_line(self, line: str) -> str:
		kind, marker, content, special = _line_prefix(line)
		if kind == "hr":
			return self.hr()
		if kind == "heading":
			return self.wrap("b", self.inline(parse_inline(content)))
		if kind == "bullet":
			return self.marker(marker) + self.bullet() + self.inline(parse_inline(content))
		if kind == "ordered":
			num = marker.lstrip()
			indent = marker[: len(marker) - len(num)]
			return indent + self.ordered_marker(num) + " " + self.inline(parse_inline(content))
		return self.inline(parse_inline(line))

	def ordered_marker(self, marker: str) -> str:
		return marker.strip()


class _PlainRenderer(_Renderer):
	def wrap(self, kind: str, inner: str, extra: Any = None) -> str:
		if kind == "link":
			return f"{inner} ({extra})" if inner.strip() != str(extra) else inner
		return inner

	def pre(self, s: str, lang: str) -> str:
		return s

	def quote(self, inner: str) -> str:
		return "\n".join("> " + ln for ln in inner.split("\n"))


class _HtmlRenderer(_Renderer):
	mode = MODE_HTML
	_TAGS = {"b": "b", "i": "i", "s": "s", "spoiler": "tg-spoiler", "code": "code"}

	def text(self, s: str) -> str:
		return escape_html(s)

	def code(self, s: str) -> str:
		return escape_html(s)

	def wrap(self, kind: str, inner: str, extra: Any = None) -> str:
		if kind == "link":
			return f'<a href="{html.escape(str(extra), quote=True)}">{inner}</a>'
		tag = self._TAGS[kind]
		return f"<{tag}>{inner}</{tag}>"

	def pre(self, s: str, lang: str) -> str:
		body = escape_html(s)
		if lang:
			return f'<pre><code class="language-{html.escape(lang, quote=True)}">{body}</code></pre>'
		return f"<pre>{body}</pre>"

	def quote(self, inner: str) -> str:
		return f"<blockquote>{inner}</blockquote>"


class _MarkdownV2Renderer(_Renderer):
	mode = MODE_MARKDOWN_V2
	_MARKS = {"b": "*", "i": "_", "s": "~", "spoiler": "||"}

	def text(self, s: str) -> str:
		return escape_markdown_v2(s)

	def code(self, s: str) -> str:
		return _escape_mdv2_code(s)

	def wrap(self, kind: str, inner: str, extra: Any = None) -> str:
		if kind == "link":
			return f"[{inner}]({_escape_mdv2_url(str(extra))})"
		if kind == "code":
			return f"`{inner}`"
		mark = self._MARKS[kind]
		return f"{mark}{inner}{mark}"

	def pre(self, s: str, lang: str) -> str:
		return f"```{lang}\n{_escape_mdv2_code(s)}\n```"

	def quote(self, inner: str) -> str:
		return "\n".join(">" + ln for ln in inner.split("\n"))

	def bullet(self) -> str:
		return "• "

	def marker(self, m: str) -> str:
		return m

	def ordered_marker(self, marker: str) -> str:
		return escape_markdown_v2(marker)

	def hr(self) -> str:
		return escape_markdown_v2("——————")


_RENDERERS = {MODE_HTML: _HtmlRenderer(), MODE_MARKDOWN_V2: _MarkdownV2Renderer(), MODE_PLAIN: _PlainRenderer()}


def to_telegram_html(markdown: str) -> str:
	return _RENDERERS[MODE_HTML].render(str(markdown or ""))


def to_markdown_v2(markdown: str) -> str:
	return _RENDERERS[MODE_MARKDOWN_V2].render(str(markdown or ""))


def to_plain(markdown: str) -> str:
	return _RENDERERS[MODE_PLAIN].render(str(markdown or ""))


# -- splitting ---------------------------------------------------------------------------------


def _hard_cut(s: str, limit: int) -> list[str]:
	return [s[i : i + limit] for i in range(0, len(s), limit)]


def _pack(pieces: list[str], sep: str, limit: int, deeper) -> list[str]:
	out: list[str] = []
	cur = ""
	for p in pieces:
		if len(p) > limit:
			if cur:
				out.append(cur)
				cur = ""
			sub = deeper(p, limit)
			out.extend(sub[:-1])
			cur = sub[-1] if sub else ""
		elif not cur:
			cur = p
		elif len(cur) + len(sep) + len(p) <= limit:
			cur += sep + p
		else:
			out.append(cur)
			cur = p
	if cur:
		out.append(cur)
	return out


def _split_words(s: str, limit: int) -> list[str]:
	return _pack(s.split(" "), " ", limit, _hard_cut)


def _split_lines(s: str, limit: int) -> list[str]:
	return _pack(s.split("\n"), "\n", limit, _split_words)


def _split_fence(block: str, limit: int) -> list[str]:
	"""Split an over-long fenced block into several complete fences (each re-opened/closed)."""
	lines = block.split("\n")
	head = lines[0]
	closing = lines[-1] if len(lines) > 1 and _FENCE.match(lines[-1]) else "```"
	body = lines[1:-1] if len(lines) > 1 and _FENCE.match(lines[-1]) else lines[1:]
	room = max(1, limit - len(head) - len(closing) - 2)
	chunks = _pack(body, "\n", room, _hard_cut)
	return [f"{head}\n{c}\n{closing}" for c in chunks] or [block]


def _units(text: str) -> list[tuple[str, bool]]:
	"""Split source into blank-line separated units, keeping fenced blocks whole."""
	units: list[tuple[str, bool]] = []
	cur: list[str] = []
	fence: tuple[str, int] | None = None
	for line in text.split("\n"):
		if fence is None:
			fm = _FENCE.match(line)
			if fm:
				if cur and any(x.strip() for x in cur):
					units.append(("\n".join(cur), False))
				cur = [line]
				fence = (fm.group(1)[0], len(fm.group(1)))
				continue
			if not line.strip():
				if cur and any(x.strip() for x in cur):
					units.append(("\n".join(cur), False))
				cur = []
				continue
			cur.append(line)
		else:
			cur.append(line)
			fm = _FENCE.match(line)
			if fm and fm.group(1)[0] == fence[0] and len(fm.group(1)) >= fence[1] and not fm.group(2):
				units.append(("\n".join(cur), True))
				cur = []
				fence = None
	if cur and any(x.strip() for x in cur):
		units.append(("\n".join(cur), fence is not None))
	return units


def split_message(text: str, limit: int = TELEGRAM_TEXT_LIMIT) -> list[str]:
	"""Split source text into ordered parts of at most ``limit`` chars; never splits inside a fence
	unless a single fence exceeds the limit (then each part is a complete fence)."""
	src = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
	limit = max(1, int(limit))
	if not src.strip():
		return []
	if len(src) <= limit:
		return [src]
	parts: list[str] = []
	cur = ""
	for body, is_fence in _units(src):
		if len(body) > limit:
			if cur:
				parts.append(cur)
				cur = ""
			sub = _split_fence(body, limit) if is_fence and _FENCE.match(body.split("\n")[0]) else _split_lines(body, limit)
			parts.extend(sub[:-1])
			cur = sub[-1] if sub else ""
		elif not cur:
			cur = body
		elif len(cur) + 2 + len(body) <= limit:
			cur += "\n\n" + body
		else:
			parts.append(cur)
			cur = body
	if cur:
		parts.append(cur)
	return [p for p in parts if p.strip()]


@dataclass(frozen=True)
class RenderedPart:
	"""One sendable message: ``text`` under ``parse_mode`` ("" = none) plus its plain fallback."""

	text: str
	parse_mode: str
	plain: str


def render_parts(markdown: str, mode: str = MODE_HTML, limit: int = TELEGRAM_TEXT_LIMIT) -> list[RenderedPart]:
	"""Convert and split. ``mode`` "" means send the source text verbatim (no parse_mode)."""
	if mode == MODE_PLAIN:
		return [RenderedPart(p, "", p) for p in split_message(markdown, limit)]
	renderer = _RENDERERS[mode]
	out: list[RenderedPart] = []
	work = split_message(markdown, limit)
	while work:
		src = work.pop(0)
		rendered = renderer.render(src)
		if not rendered:
			continue
		if len(rendered) > limit and len(src) > 32:
			# Escaping/tags inflated the part: re-split the source smaller (preserves entity safety).
			smaller = split_message(src, max(16, min(len(src) - 1, int(limit * len(src) / len(rendered)) - 8)))
			if len(smaller) > 1:
				work = smaller + work
				continue
		if len(rendered) > limit:
			out.extend(RenderedPart(c, "", c) for c in _hard_cut(to_plain(src), limit))
			continue
		out.append(RenderedPart(rendered, mode, _fit_plain(to_plain(src), limit)))
	return out


def _fit_plain(plain: str, limit: int) -> str:
	return plain if len(plain) <= limit else plain[: limit - 1] + "…"
