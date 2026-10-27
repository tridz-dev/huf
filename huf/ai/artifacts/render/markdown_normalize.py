# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Deterministic markdown block normalizer.

python-markdown (unlike CommonMark) needs a blank line before a table, before a
list that follows paragraph text, and after a table. LLM output routinely omits
them, especially inside HTML containers. ``normalize_markdown_blocks`` inserts
exactly the missing blank lines and nothing else (it never edits a line), so a
well-formed text is returned byte-identical and the function is idempotent.

Never touched: fenced-code bodies, <pre>/<code>/<script>/<style>/<textarea>
bodies, HTML comments, multi-line HTML tag attributes. Inline spans are never
touched because only line boundaries are modified.
"""

import re

_RAW_REGION_RE = re.compile(
	r"<(pre|code|script|style|textarea)\b.*?</\1\s*>|<!--.*?-->|<[a-zA-Z][^<>]*\n[^<>]*>",
	re.IGNORECASE | re.DOTALL,
)
_FENCE_OPEN = re.compile(r"^([ \t]*)(`{3,}|~{3,})(.*)$")
_HEADING = re.compile(r"^[ \t]{0,3}#{1,6}(?:[ \t]+\S|[ \t]*$)")
_ITEM = re.compile(r"^([ \t]*)([-*+]|\d{1,3}[.)])[ \t]+(\S.*)$")
_HR_REST = re.compile(r"^[-*+ \t_]*$")
_QUOTE = re.compile(r"^[ \t]{0,3}>")
_SEP = re.compile(r"^[ \t]*\|?[ \t]*:?-{3,}:?[ \t]*(?:\|[ \t]*:?-{3,}:?[ \t]*)*\|?[ \t]*$")
_HTML_BLOCK = re.compile(
	r"^[ \t]*</?(?:div|section|aside|article|details|summary|main|figure|figcaption|blockquote|ul|ol|li|table|thead|tbody|tfoot|tr|td|th|p|h[1-6]|pre|hr|nav|header|footer)\b",
	re.IGNORECASE,
)
_ATTR_LINE = re.compile(r"^[ \t]*\{:")


def _indent(line: str) -> int:
	n = 0
	for ch in line:
		if ch == " ":
			n += 1
		elif ch == "\t":
			n += 4
		else:
			break
	return n


def normalize_markdown_blocks(text: str) -> str:
	"""Insert the blank lines python-markdown needs between block constructs."""
	if not text or "\n" not in text:
		return text
	lines = text.split("\n")
	n = len(lines)

	# -- raw-region line flags (by line start offset) --
	raw = [False] * n
	spans = [(m.start(), m.end()) for m in _RAW_REGION_RE.finditer(text)]
	if spans:
		off = 0
		si = 0
		for i, ln in enumerate(lines):
			while si < len(spans) and spans[si][1] <= off:
				si += 1
			if si < len(spans) and spans[si][0] <= off < spans[si][1]:
				raw[i] = True
			off += len(ln) + 1

	# -- classify --
	kind = ["text"] * n
	fence = None  # (char, length)
	for i, ln in enumerate(lines):
		if fence is not None:
			m = _FENCE_OPEN.match(ln)
			if m and m.group(2)[0] == fence[0] and len(m.group(2)) >= fence[1] and not m.group(3).strip():
				kind[i] = "fence_close"
				fence = None
			else:
				kind[i] = "fence"
			continue
		if raw[i]:
			kind[i] = "raw"
			continue
		if not ln.strip():
			kind[i] = "blank"
			continue
		m = _FENCE_OPEN.match(ln)
		if m and _indent(ln) <= 3 + 4 and not (m.group(2)[0] == "`" and "`" in m.group(3)):
			kind[i] = "fence_open"
			fence = (m.group(2)[0], len(m.group(2)))
			continue
		if _HEADING.match(ln):
			kind[i] = "heading"
		elif _QUOTE.match(ln):
			kind[i] = "quote"
		elif _HTML_BLOCK.match(ln):
			kind[i] = "html"
		else:
			m = _ITEM.match(ln)
			if m and not _HR_REST.match(m.group(3)):
				kind[i] = "item"
	# tables
	for i in range(1, n):
		if kind[i] == "text" and "|" in lines[i] and _SEP.match(lines[i]) and kind[i - 1] in ("text", "item"):
			if "|" in lines[i - 1] and not _SEP.match(lines[i - 1]):
				if kind[i - 1] == "item" and _indent(lines[i - 1]) > 3:
					continue
				kind[i - 1] = "table_head"
				kind[i] = "table_sep"
				j = i + 1
				while j < n and kind[j] == "text" and "|" in lines[j] and lines[j].strip():
					kind[j] = "table_row"
					j += 1

	# -- decide blank insertions --
	out = []
	in_list = False
	base_indent = 0
	base_ordered = False
	lazy_seen = False
	prev = "blank"  # effective kind of the previous output line
	prev_line = ""
	for i, ln in enumerate(lines):
		k = kind[i]
		if k == "blank":
			out.append(ln)
			prev = "blank"
			lazy_seen = False
			continue
		ind = _indent(ln)
		if k == "item" and not in_list and ind > 3:
			k = "text"
		need = False
		if prev != "blank":
			listy = prev in ("item", "list_cont") and in_list
			if prev == "raw" or k == "raw":
				need = False
			elif k in ("fence", "fence_close"):
				need = False
			elif k == "fence_open" or prev == "fence_close":
				need = True
			elif k == "heading":
				need = True
			elif prev == "heading":
				need = not _ATTR_LINE.match(ln)
			elif k == "table_head":
				need = True
			elif prev in ("table_row", "table_sep") and k != "table_row":
				need = True
			elif k == "quote":
				need = prev != "quote"
			elif prev == "quote":
				need = True
			elif k == "item":
				mi = _ITEM.match(ln)
				ordered = mi.group(2)[0].isdigit()
				if listy:
					need = ind <= base_indent and ordered != base_ordered
				elif prev == "html":
					need = True
				else:
					need = (not ordered) or mi.group(2)[:-1] == "1" or prev_line.rstrip().endswith(":")
			elif k == "html" and listy:
				need = True
			elif k == "text" and listy and ind <= base_indent:
				if lazy_seen:
					need = False
				else:
					need = True
					for j in range(i + 1, n):
						if kind[j] in ("blank", "heading", "table_head", "quote", "fence_open", "html"):
							break
						if kind[j] == "item":
							mj = _ITEM.match(lines[j])
							if _indent(lines[j]) <= base_indent and mj.group(2)[0].isdigit() != base_ordered:
								break
							if _indent(lines[j]) <= base_indent + 3:
								need = False
								lazy_seen = True
								break
		adj = "blank" if need else prev
		if need:
			out.append("")
			lazy_seen = False
		# state / effective kind
		if k == "item":
			mi = _ITEM.match(ln)
			ordered = mi.group(2)[0].isdigit()
			if not in_list or (adj == "blank" and ind <= base_indent) or (need and ind <= base_indent):
				base_indent = ind
				base_ordered = ordered
			in_list = True
			eff = "item"
		elif k == "text":
			if in_list and ((adj in ("item", "list_cont")) or (adj == "blank" and ind > base_indent)):
				eff = "list_cont"
			else:
				in_list = False
				eff = "text"
		else:
			in_list = False
			eff = k
		out.append(ln)
		prev = eff
		prev_line = ln
	return "\n".join(out)
