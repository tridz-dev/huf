"""Markdown to WhatsApp text conversion and body splitting (pure Python, no frappe).

``to_whatsapp(text)``  converts the Markdown an LLM tends to produce into WhatsApp's
own formatting (``*bold*``, ``_italic_``, ``~strike~``, ``> quote``, backtick code).

``split_body(text, limit=4096)``  splits a reply into ordered parts of at most
``limit`` characters (WhatsApp Cloud API text body limit is 4096; Graph returns error
100 above it). Split priority: paragraph, line, sentence end, space, hard cut. A
fenced code block is never cut unless it alone exceeds ``limit``; then it is split at
line boundaries and the fence is closed and re-opened on every part.

Idempotency note: ``*x*`` is Markdown italic and therefore becomes ``_x_``. Text that
already uses WhatsApp ``*bold*`` is not preserved by a second pass, so call
``to_whatsapp`` once on model output only. Everything else (``_i_``, ``~s~``, ``• ``,
code, URLs, ``> quote``) is stable.
"""

from __future__ import annotations

import re
from typing import Any

WHATSAPP_BODY_LIMIT = 4096

# Private-use characters used as placeholders / sentinels while converting.
_PH_OPEN = ""
_PH_CLOSE = ""
_BOLD = ""
_HEAD = ""
_PRIVATE_RE = re.compile("[-]")

_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})(.*)$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$")
_HR_RE = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
_BULLET_RE = re.compile(r"^(\s*)[-*+]\s+(?=\S)")
_CODE_SPAN_RE = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")
_AUTOLINK_RE = re.compile(r"<((?:https?://|mailto:)[^>\s]+)>", re.I)
_BR_RE = re.compile(r"<br\s*/?>", re.I)
_TAG_RE = re.compile(r"</?[a-zA-Z][a-zA-Z0-9-]*(?:\s[^<>]*)?/?>")
_IMAGE_RE = re.compile(r"!\[[^\]\n]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
_LINK_RE = re.compile(r"\[([^\]\n]*)\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
_URL_RE = re.compile(r"https?://[^\s<>-]+", re.I)
_BOLD_ITALIC_RE = re.compile(r"\*\*\*(?=\S)(.+?)(?<=\S)\*\*\*")
_BOLD_STAR_RE = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
_BOLD_UNDER_RE = re.compile(r"(?<![\w_])__(?=\S)(.+?)(?<=\S)__(?![\w_])")
_ITALIC_RE = re.compile(r"(?<![\*\w])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![\*\w])")
_STRIKE_RE = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~")
_PH_RE = re.compile(_PH_OPEN + r"(\d+)" + _PH_CLOSE)


# ---------------------------------------------------------------- helpers


def _as_text(text: Any) -> str:
	if text is None:
		return ""
	if isinstance(text, bytes):
		try:
			return text.decode("utf-8", "replace")
		except Exception:
			return ""
	if not isinstance(text, str):
		try:
			return str(text)
		except Exception:
			return ""
	return text


def _fence_open(line: str):
	"""Return (marker_char, marker_len) when ``line`` opens a fence, else None."""
	m = _FENCE_RE.match(line)
	if not m:
		return None
	marker = m.group(1)
	if marker[0] == "`" and "`" in m.group(2):
		return None  # inline code such as ```x``` on one line
	return marker[0], len(marker)


def _fence_closes(line: str, char: str, length: int) -> bool:
	m = _FENCE_RE.match(line)
	if not m:
		return False
	marker = m.group(1)
	return marker[0] == char and len(marker) >= length and not m.group(2).strip()


def _segments(lines: list[str]) -> list[tuple[bool, list[str]]]:
	"""Split lines into (is_code, lines) segments; an unclosed fence runs to the end."""
	out: list[tuple[bool, list[str]]] = []
	cur: list[str] = []
	i, n = 0, len(lines)
	while i < n:
		opener = _fence_open(lines[i])
		if opener is None:
			cur.append(lines[i])
			i += 1
			continue
		if cur:
			out.append((False, cur))
			cur = []
		block = [lines[i]]
		i += 1
		while i < n:
			block.append(lines[i])
			closed = _fence_closes(lines[i], *opener)
			i += 1
			if closed:
				break
		out.append((True, block))
	if cur:
		out.append((False, cur))
	return out


# ---------------------------------------------------------------- to_whatsapp


def _table_row(line: str) -> str:
	s = line.strip()
	if s.startswith("|"):
		s = s[1:]
	if s.endswith("|"):
		s = s[:-1]
	return " | ".join(c.strip() for c in s.split("|"))


def _convert_tables(lines: list[str]) -> list[str]:
	out: list[str] = []
	i, n = 0, len(lines)
	while i < n:
		line = lines[i]
		if "|" in line and i + 1 < n and "|" in lines[i + 1] and _TABLE_SEP_RE.match(lines[i + 1]) and "-" in lines[i + 1]:
			out.append(_table_row(line))
			i += 2
			while i < n and "|" in lines[i] and lines[i].strip():
				out.append(_table_row(lines[i]))
				i += 1
			continue
		out.append(line)
		i += 1
	return out


def _convert_text(lines: list[str]) -> str:
	stash: list[str] = []

	def hold(value: str) -> str:
		stash.append(value)
		return f"{_PH_OPEN}{len(stash) - 1}{_PH_CLOSE}"

	text = "\n".join(_convert_tables(lines))
	text = _CODE_SPAN_RE.sub(lambda m: hold(m.group(0)), text)
	text = _AUTOLINK_RE.sub(lambda m: m.group(1), text)
	text = _BR_RE.sub("\n", text)
	text = _TAG_RE.sub("", text)
	text = _IMAGE_RE.sub(lambda m: hold(m.group(1)), text)

	def link(m: re.Match) -> str:
		label, url = m.group(1).strip(), m.group(2)
		if not label or label == url:
			return hold(url)
		return f"{label} ({hold(url)})"

	text = _LINK_RE.sub(link, text)

	def bare(m: re.Match) -> str:
		url = m.group(0)
		trail = ""
		while url and url[-1] in ".,;:!?)]}'\"":
			trail = url[-1] + trail
			url = url[:-1]
		return hold(url) + trail if url else m.group(0)

	text = _URL_RE.sub(bare, text)

	out: list[str] = []
	for line in text.split("\n"):
		if _HR_RE.match(line):
			out.append("")
			continue
		h = _HEADING_RE.match(line)
		if h:
			out.append(_HEAD + h.group(1))
			continue
		out.append(_BULLET_RE.sub(lambda m: m.group(1) + "• ", line))
	text = "\n".join(out)

	text = _BOLD_ITALIC_RE.sub(lambda m: f"{_BOLD}_{m.group(1)}_{_BOLD}", text)
	text = _BOLD_STAR_RE.sub(lambda m: f"{_BOLD}{m.group(1)}{_BOLD}", text)
	text = _BOLD_UNDER_RE.sub(lambda m: f"{_BOLD}{m.group(1)}{_BOLD}", text)
	text = _STRIKE_RE.sub(lambda m: f"~{m.group(1)}~", text)
	text = _ITALIC_RE.sub(lambda m: f"_{m.group(1)}_", text)

	final: list[str] = []
	for line in text.split("\n"):
		if line.startswith(_HEAD):
			body = line[1:].replace(_BOLD, "").strip()
			line = f"{_BOLD}{body}{_BOLD}" if body else ""
		final.append(line.replace(_BOLD, "*").rstrip())
	text = "\n".join(final)

	for _ in range(4):
		if _PH_OPEN not in text:
			break
		text = _PH_RE.sub(lambda m: stash[int(m.group(1))], text)

	text = re.sub(r"\n{3,}", "\n\n", text)
	return text.strip("\n")


def to_whatsapp(text: str) -> str:
	"""Convert Markdown (LLM output) to WhatsApp formatting. Never raises."""
	try:
		src = _PRIVATE_RE.sub("", _as_text(text)).replace("\r\n", "\n").replace("\r", "\n")
		if not src.strip():
			return ""
		out = ""
		blank = False
		for is_code, lines in _segments(src.split("\n")):
			if is_code:
				chunk = "\n".join(lines)
				lead = False
				trail = False
			else:
				chunk = _convert_text(lines)
				if not chunk.strip():
					blank = blank or bool(lines)
					continue
				lead = not lines[0].strip()
				trail = not lines[-1].strip()
			if out:
				out += "\n\n" if (blank or lead) else "\n"
			out += chunk
			blank = trail
		out = out.strip("\n").rstrip()
		return out
	except Exception:
		return _as_text(text).strip()


# ---------------------------------------------------------------- split_body


def _hard_cut(s: str, limit: int) -> list[str]:
	return [s[i : i + limit] for i in range(0, len(s), limit)]


def _pack(pieces: list[str], sep: str, limit: int, deeper) -> list[str]:
	parts: list[str] = []
	cur = ""
	for piece in pieces:
		piece = piece.strip()
		if not piece:
			continue
		if len(piece) > limit:
			if cur:
				parts.append(cur)
				cur = ""
			sub = deeper(piece, limit)
			parts.extend(sub[:-1])
			cur = sub[-1] if sub else ""
			continue
		if not cur:
			cur = piece
		elif len(cur) + len(sep) + len(piece) <= limit:
			cur = cur + sep + piece
		else:
			parts.append(cur)
			cur = piece
	if cur:
		parts.append(cur)
	return parts


def _split_words(s: str, limit: int) -> list[str]:
	def deeper(piece: str, lim: int) -> list[str]:
		return [p for p in (x.strip() for x in _hard_cut(piece, lim)) if p]

	return _pack(s.split(" "), " ", limit, deeper)


def _split_sentences(s: str, limit: int) -> list[str]:
	return _pack(re.split(r"(?<=[.!?])\s+", s), " ", limit, _split_words)


def _split_lines(s: str, limit: int) -> list[str]:
	return _pack(s.split("\n"), "\n", limit, _split_sentences)


def _split_fence(block: str, limit: int) -> list[str]:
	lines = block.split("\n")
	opener = _fence_open(lines[0])
	if opener is None or len(lines) < 2:
		return _split_lines(block, limit)
	closed = len(lines) > 1 and _fence_closes(lines[-1], *opener)
	body = lines[1:-1] if closed else lines[1:]
	open_line = lines[0].strip()
	close_line = opener[0] * opener[1]
	budget = limit - len(open_line) - len(close_line) - 2
	if budget < 1:
		return _split_lines(block, limit)
	chunks: list[str] = []
	cur: list[str] = []
	size = 0
	for ln in body:
		pieces = _hard_cut(ln, budget) if len(ln) > budget else [ln]
		for piece in pieces:
			add = len(piece) + (1 if cur else 0)
			if cur and size + add > budget:
				chunks.append("\n".join(cur))
				cur, size = [], 0
				add = len(piece)
			cur.append(piece)
			size += add
	if cur:
		chunks.append("\n".join(cur))
	return [f"{open_line}\n{c}\n{close_line}" for c in chunks if c.strip() or c]


def _units(text: str) -> list[tuple[str, str, bool]]:
	"""Break text into (separator_before, text, is_fence) units."""
	units: list[tuple[str, str, bool]] = []
	pending_blank = False
	for is_code, lines in _segments(text.split("\n")):
		if is_code:
			sep = "\n\n" if pending_blank else "\n"
			units.append((sep, "\n".join(lines).strip("\n"), True))
			pending_blank = False
			continue
		blob = "\n".join(lines)
		if not blob.strip():
			pending_blank = True
			continue
		if lines and not lines[0].strip():
			pending_blank = True
		paras = [p.strip() for p in re.split(r"\n[ \t]*\n", blob) if p.strip()]
		for idx, para in enumerate(paras):
			sep = ("\n\n" if pending_blank else "\n") if idx == 0 else "\n\n"
			units.append((sep, para, False))
			pending_blank = False
		pending_blank = not lines[-1].strip()
	return units


def split_body(text: str, limit: int = WHATSAPP_BODY_LIMIT) -> list[str]:
	"""Split ``text`` into ordered non-empty parts of at most ``limit`` characters."""
	try:
		src = _as_text(text).replace("\r\n", "\n").replace("\r", "\n")
		try:
			limit = int(limit)
		except Exception:
			limit = WHATSAPP_BODY_LIMIT
		limit = max(1, limit)
		if not src.strip():
			return []
		if len(src.strip()) <= limit:
			return [src.strip()]
		parts: list[str] = []
		cur = ""
		for sep, body, is_fence in _units(src):
			if not body.strip():
				continue
			if len(body) > limit:
				if cur:
					parts.append(cur)
					cur = ""
				sub = _split_fence(body, limit) if is_fence else _split_lines(body, limit)
				parts.extend(sub[:-1])
				cur = sub[-1] if sub else ""
				continue
			if not cur:
				cur = body
			elif len(cur) + len(sep) + len(body) <= limit:
				cur = cur + sep + body
			else:
				parts.append(cur)
				cur = body
		if cur:
			parts.append(cur)
		return [p for p in (x.strip("\n").rstrip() for x in parts) if p.strip()]
	except Exception:
		s = _as_text(text).strip()
		return [s[i : i + max(1, limit)] for i in range(0, len(s), max(1, limit))] if s else []
