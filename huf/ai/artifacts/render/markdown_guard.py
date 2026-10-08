# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Guards against raw markdown leaking into rendered document HTML.

Agents routinely write markdown inside HTML component containers
(``<div class="split-main">## Heading ...</div>``). python-markdown's
``md_in_html`` extension leaves such content verbatim unless the container
carries a ``markdown`` attribute, so the reader sees literal ``##`` / ``**``.

Three layers live here:

1. ``enable_markdown_in_containers`` (root fix, applied BEFORE conversion):
   adds ``markdown="1"`` to block containers whose own content shows markdown
   block/inline syntax.
2. ``find_markdown_leaks`` (detector, applied to the FINAL sanitized HTML).
3. ``repair_markdown_leaks`` (safety net): re-renders the offending element's
   content through markdown and re-sanitizes with the pipeline's bleach config.
"""

import html as _html
import re
from collections import namedtuple

import markdown

from huf.ai.artifacts.render.markdown_normalize import normalize_markdown_blocks

Leak = namedtuple("Leak", ["kind", "sample", "tag"])

MARKDOWN_EXTENSIONS = ["tables", "fenced_code", "attr_list", "sane_lists", "md_in_html"]

#: Containers that may receive markdown="1".
_CONTAINER_TAGS = frozenset({"div", "section", "aside", "article", "details", "main", "figure", "blockquote"})

#: Purely structural components: never auto-marked (inline text would be
#: wrapped in <p>, changing their layout/DOCX recipes).
_STRUCTURAL_CLASSES = frozenset({
	"doc-header", "doc-meta", "metric-grid", "metric", "status-badge", "page-break", "doc-footer",
})

#: Regions whose text is never markdown.
_RAW_REGION_RE = re.compile(r"<(pre|code|script|style|textarea)\b.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
_FENCE_RE = re.compile(r"^[ \t]*(```|~~~).*?^[ \t]*\1[ \t]*$", re.MULTILINE | re.DOTALL)

_TAG_RE = re.compile(r"<(?P<closing>/?)(?P<tag>[a-zA-Z][a-zA-Z0-9]*)\b(?P<attrs>[^>]*?)(?P<selfclose>/?)>")
_VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"})

_BOLD = r"(?<![\w*])\*\*[^\s*](?:[^*\n]*[^\s*])?\*\*(?![\w*])"
_UBOLD = r"(?<![\w_])__[^\s_](?:[^_\n]*[^\s_])?__(?![\w_])"

#: Signals that a container's own content is markdown (used by the root fix).
_SIGNAL_RE = re.compile(
	r"^[ \t]*(?:#{1,6}[ \t]+\S|[-*+][ \t]+\S|\d{1,3}[.)][ \t]+\S|\|.*\||```|~~~)|" + _BOLD + "|" + _UBOLD,
	re.MULTILINE,
)


def _mask(source: str) -> str:
	"""Blank out raw regions (pre/code/script/style, fenced blocks), same length."""

	def blank(m):
		return re.sub(r"[^\n]", " ", m.group(0))

	return _FENCE_RE.sub(blank, _RAW_REGION_RE.sub(blank, source))


_TASK_LINE_RE = re.compile(r"^([ \t]{0,3}[-*+][ \t]+)\[([ xX])\]([ \t]+)", re.MULTILINE)


def convert_task_markers(source: str) -> str:
	"""Turn GFM task markers (``- [x] item``) into ballot-box glyphs.

	python-markdown has no task-list support, so the literal ``[x]`` would
	otherwise show. Raw regions (code, fences) are left untouched.
	"""
	if "[" not in source:
		return source
	masked = _mask(source)
	out = []
	last = 0
	for m in _TASK_LINE_RE.finditer(masked):
		glyph = "\u2611" if m.group(2) in "xX" else "\u2610"
		out.append(source[last : m.start()])
		out.append(m.group(1) + glyph + m.group(3))
		last = m.end()
	if not out:
		return source
	out.append(source[last:])
	return "".join(out)


def enable_markdown_in_containers(source: str) -> str:
	"""Add ``markdown="1"`` to block containers whose content contains markdown.

	Containers that already carry a ``markdown`` attribute, structural
	components, unclosed containers and anything inside pre/code/script/style
	or fenced code are left alone. Idempotent.
	"""
	if "<" not in source:
		return source
	masked = _mask(source)
	stack = []
	inserts = []  # offsets in source at which to insert ' markdown="1"'
	for m in _TAG_RE.finditer(masked):
		tag = m.group("tag").lower()
		if tag in _VOID or m.group("selfclose"):
			continue
		if not m.group("closing"):
			stack.append((tag, m))
			continue
		# Pop to the matching opener (ignore stray closers).
		idx = next((i for i in range(len(stack) - 1, -1, -1) if stack[i][0] == tag), None)
		if idx is None:
			continue
		_, opener = stack[idx]
		del stack[idx:]
		if tag not in _CONTAINER_TAGS:
			continue
		attrs = opener.group("attrs")
		if re.search(r"\bmarkdown\s*=", attrs, re.IGNORECASE):
			continue
		cls = re.search(r"""\bclass\s*=\s*["']([^"']*)["']""", attrs, re.IGNORECASE)
		if cls and _STRUCTURAL_CLASSES.intersection(cls.group(1).split()):
			continue
		inner = masked[opener.end() : m.start()]
		if _SIGNAL_RE.search(inner):
			inserts.append(opener.start("attrs"))
	if not inserts:
		return source
	out = source
	for pos in sorted(inserts, reverse=True):
		out = out[:pos] + ' markdown="1"' + out[pos:]
	return out


# --------------------------------------------------------------------------
# Detector
# --------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"<!--.*?-->|</?[a-zA-Z][^>]*>|[^<]+|<", re.DOTALL)
_RAW_TAGS = frozenset({"pre", "code", "script", "style", "textarea"})

_RE_HEADING = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+\S", re.MULTILINE)
_RE_BULLET = re.compile(r"^[ \t]{0,3}[*+-][ \t]+\S", re.MULTILINE)
_RE_ORDERED = re.compile(r"^[ \t]{0,3}\d{1,3}[.)][ \t]+\S", re.MULTILINE)
_RE_TABLE_SEP = re.compile(r"^[ \t]*\|?[ \t]*:?-{3,}:?[ \t]*(?:\|[ \t]*:?-{3,}:?[ \t]*)*\|?[ \t]*$", re.MULTILINE)
_RE_TABLE_ROW = re.compile(r"^[ \t]*\|.*\|[ \t]*$", re.MULTILINE)
_RE_BOLD = re.compile(_BOLD + "|" + _UBOLD)
_RE_TASK = re.compile(r"^[ \t]{0,3}[-*+][ \t]+\[[ xX]\][ \t]+\S", re.MULTILINE)
_RE_LINK = re.compile(r"\[[^\]\n]+\]\((?:https?://|/|#|mailto:)[^)\s]+\)")
_RE_FENCE = re.compile(r"^[ \t]*(?:```|~~~)", re.MULTILINE)


class _Node:
	__slots__ = ("tag", "start", "end", "open_end", "close_start", "children", "parent", "texts", "spans")

	def __init__(self, tag, start, parent):
		self.tag = tag
		self.start = start  # char offset of the opening tag
		self.open_end = start
		self.close_start = None
		self.end = None
		self.children = []
		self.parent = parent
		self.spans = []  # (start, end) offsets of each direct text piece
		self.texts = []  # (kind, string) pieces in order: ("t", text) or ("c", None)


def _parse(html: str):
	"""Tiny tree over well-formed (bleach-normalised) HTML. Returns root."""
	root = _Node("#root", 0, None)
	root.open_end = 0
	cur = root
	pos = 0
	raw_until = None
	for m in _TOKEN_RE.finditer(html):
		tok = m.group(0)
		start = m.start()
		if raw_until:
			# Inside raw element: only look for its closer.
			if tok.lower().startswith("</" + raw_until):
				raw_until = None
			else:
				continue
		if tok.startswith("<!--"):
			continue
		tm = _TAG_RE.fullmatch(tok) if tok.startswith("<") else None
		if tm is None:
			cur.texts.append(("t", tok))
			cur.spans.append((start, start + len(tok)))
			continue
		tag = tm.group("tag").lower()
		if tm.group("closing"):
			node = cur
			while node is not root and node.tag != tag:
				node = node.parent
			if node is root:
				continue
			node.close_start = start
			node.end = m.end()
			cur = node.parent
			continue
		child = _Node(tag, start, cur)
		child.open_end = m.end()
		cur.children.append(child)
		cur.texts.append(("c", None))
		if tag in _VOID or tm.group("selfclose"):
			child.close_start = child.end = m.end()
			continue
		cur = child
		if tag in ("script", "style"):
			raw_until = tag
	return root


def _in_raw(node) -> bool:
	while node is not None:
		if node.tag in _RAW_TAGS:
			return True
		node = node.parent
	return False


def _direct_text(node) -> str:
	return _html.unescape("".join(s if k == "t" else "\x00" for k, s in node.texts))


def _scan(text: str):
	"""Return list of (kind, sample) leaks found in one element's direct text."""
	found = []

	def add(kind, m):
		found.append((kind, text[m.start() : m.end()].strip()[:60]))

	m = _RE_HEADING.search(text)
	if m:
		add("heading", m)
	tasks = list(_RE_TASK.finditer(text))
	if tasks:
		add("task-list", tasks[0])
	bullets = list(_RE_BULLET.finditer(text))
	glued = [b for b in bullets if text[: b.start()].strip(" \t\n")]
	if len(bullets) >= 2 or glued:
		add("bullet-list", bullets[0])
	ordered = list(_RE_ORDERED.finditer(text))
	if len(ordered) >= 2:
		add("ordered-list", ordered[0])
	m = _RE_TABLE_SEP.search(text)
	if m and "-" in m.group(0) and ("|" in m.group(0) or m.group(0).strip().count("-") >= 3):
		# A bare "---" line is a rule, not a table: demand a pipe.
		if "|" in m.group(0):
			add("table", m)
	rows = list(_RE_TABLE_ROW.finditer(text))
	if len(rows) >= 2 and not m:
		add("table", rows[0])
	m = _RE_BOLD.search(text)
	if m:
		add("bold", m)
	m = _RE_LINK.search(text)
	if m:
		add("link", m)
	m = _RE_FENCE.search(text)
	if m:
		add("fence", m)
	return found


def _walk(node):
	yield node
	for c in node.children:
		yield from _walk(c)


def _leaky_nodes(root):
	out = []
	for node in _walk(root):
		if _in_raw(node):
			continue
		leaks = _scan(_direct_text(node))
		if leaks:
			out.append((node, leaks))
	return out


def find_markdown_leaks(html: str) -> list:
	"""Return residual-markdown findings in the TEXT of rendered HTML.

	Text inside pre/code/script/style is ignored. Conservative: a lone ``*``,
	``C#``, hashtags, ``snake_case``, a single pipe or a single list-looking
	line are not reported.
	"""
	root = _parse(html)
	leaks = []
	for node, found in _leaky_nodes(root):
		for kind, sample in found:
			leaks.append(Leak(kind, sample, "" if node is root else node.tag))
	return leaks


# --------------------------------------------------------------------------
# Repair
# --------------------------------------------------------------------------

_INLINE_PARENTS = frozenset({"span", "strong", "em", "a", "small", "li", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6", "figcaption"})


def _render(inner: str) -> str:
	from huf.ai.artifacts.render.html import sanitize_html

	inner = normalize_markdown_blocks(convert_task_markers(inner))
	return sanitize_html(markdown.markdown(inner, extensions=MARKDOWN_EXTENSIONS))


# --------------------------------------------------------------------------
# Fail-safe fallback
# --------------------------------------------------------------------------

_FB_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
_FB_ITEM = re.compile(r"^(\s*)([-*+]|\d{1,3}[.)])\s+(?:\[([ xX])\]\s+)?(.*)$")
_FB_FENCE = re.compile(r"^\s*(```|~~~)")


def _fb_inline(t: str) -> str:
	t = re.sub(r"\[([^\]\n]+)\]\(((?:https?://|/|#|mailto:)[^)\s]+)\)", r"\1 (\2)", t)
	t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
	t = re.sub(r"(?<![\w_])__(.+?)__(?![\w_])", r"\1", t)
	return t.replace("**", "").replace("__", "")


def _fallback_text(text: str) -> str:
	"""Minimal deterministic markdown -> plain text-with-<br> conversion.

	``text`` is already HTML-escaped sanitized output, so it is kept verbatim
	apart from the stripped markers.
	"""
	out = []
	# Whitespace at the edges of the piece separates it from neighbouring
	# inline elements (``## Head <strong>x</strong>``); keep it.
	trail = text[len(text.rstrip(" \t")) :]
	lines = text.split("\n")
	last_idx = max((i for i, ln in enumerate(lines) if ln.strip()), default=-1)
	for idx, raw in enumerate(lines):
		line = raw.rstrip()
		gap = trail if idx == last_idx else ""
		if not line.strip() or _FB_FENCE.match(line):
			continue
		if _RE_TABLE_SEP.match(line) and "|" in line:
			continue
		m = _FB_HEADING.match(line)
		if m:
			# Own block: <strong> on its own line, then a break.
			out.append("<strong>" + _fb_inline(m.group(1)).strip() + "</strong>" + gap + "<br>")
			continue
		m = _FB_ITEM.match(line)
		if m:
			pad = "\u00a0" * min(len(m.group(1)), 8)
			if m.group(3) is not None:
				mark = "\u2611" if m.group(3) in "xX" else "\u2610"
			elif m.group(2)[0].isdigit():
				mark = "(" + m.group(2)[:-1] + ")"
			else:
				mark = "\u2022"
			out.append(pad + mark + " " + _fb_inline(m.group(4)) + gap)
			continue
		if re.match(r"^\s*\|.*\|\s*$", line):
			cells = [c.strip() for c in line.strip().strip("|").split("|")]
			out.append(" ".join(_fb_inline(c) for c in cells if c) + gap)
			continue
		out.append(_fb_inline(re.sub(r"^\s{0,3}(?:&gt;\s?)+", "", line)) + gap)
	# Headings already end in <br>; other lines are joined with <br>.
	res = ""
	for i, o in enumerate(out):
		res += o
		if i < len(out) - 1:
			res += ("" if o.endswith("<br>") else "<br>") + "\n"
	return res


def fallback_markdown_leaks(html: str):
	"""Last resort: strip markdown syntax from still-leaking elements' text.

	Returns ``(html, count)`` where count is the number of elements converted.
	"""
	count = 0
	for _ in range(2):
		root = _parse(html)
		leaky = _leaky_nodes(root)
		if not leaky:
			break
		edits = []
		for node, _ in leaky:
			block = node.tag not in _INLINE_PARENTS and node.tag != "p" and node is not root
			for (a, b), (kind, piece) in zip(node.spans, [t for t in node.texts if t[0] == "t"]):
				if not _scan(_html.unescape(piece)):
					continue
				conv = _fallback_text(piece)
				if block:
					conv = '<div class="md-fallback">' + conv + "</div>"
				edits.append((a, b, conv))
			count += 1
		for a, b, r in sorted(edits, reverse=True):
			html = html[:a] + r + html[b:]
	return html, count


def repair_markdown_leaks(html: str, max_passes: int = 4):
	"""Re-render leaking elements through markdown. Returns ``(html, count)``.

	A clean document is returned byte-identical with count 0.
	"""
	total = 0
	for _ in range(max_passes):
		root = _parse(html)
		leaky = _leaky_nodes(root)
		if not leaky:
			break
		picked = []
		leaky_ids = {id(n) for n, _ in leaky}
		for node, _ in leaky:
			anc = node.parent
			skip = False
			while anc is not None:
				if id(anc) in leaky_ids:
					skip = True
					break
				anc = anc.parent
			if not skip:
				picked.append(node)
		edits = []
		for node in picked:
			if node is root:
				a, b = 0, len(html)
				inner = html
				rendered = _render(inner)
				edits.append((a, b, rendered))
				continue
			inner = html[node.open_end : node.close_start]
			rendered = _render(inner)
			if node.tag == "p":
				edits.append((node.start, node.end, rendered))
			else:
				lone = re.fullmatch(r"\s*<p>(.*)</p>\s*", rendered, re.DOTALL)
				if lone and "<p>" not in lone.group(1):
					rendered = lone.group(1)
				elif node.tag in _INLINE_PARENTS - {"li", "td", "th"}:
					continue  # cannot hold blocks; leave rather than corrupt
				edits.append((node.open_end, node.close_start, rendered))
		if not edits:
			break
		new = html
		for a, b, r in sorted(edits, reverse=True):
			new = new[:a] + r + new[b:]
		total += len(edits)
		if new == html:
			break
		html = new
	return html, total
