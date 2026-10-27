# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Path rules shared by the Telegram web-access exchange and the request guard (pure; no frappe import).

Two normal forms exist on purpose:

* ``normalize_target``: case-preserving, relative, optional ``?query``; used to validate a redirect target.
* ``normalize_path``: lower-cased, canonical, query-less; used to match a request path against the allow-list.
  ``normalize_path_keep_case`` is the same decoding without lower-casing (method names are case-sensitive).

Frappe 16 serves the desk under ``/desk`` and redirects ``/app`` to it, so ``/app/x`` and ``/desk/x`` are
aliases; ``desk_aliases`` is the single place that rule lives.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import unquote

MARKER_KEY = "tg_origin"
MAX_TARGET_LEN = 512
# Roles denied web access unless the gateway explicitly allows privileged users.
PRIVILEGED_ROLES = frozenset({"System Manager", "Administrator"})

_CONTROL = re.compile("[\x00-\x1f\x7f-\x9f  ]")
_DESK_PAIRS = (("/app", "/desk"), ("/desk", "/app"))


def decoded_variants(text: str) -> list[str]:
	"""``text`` and its successive percent-decodings; ends with ``"%"`` when still encoded after 3 rounds."""
	out, cur = [text], text
	for _i in range(3):
		nxt = unquote(cur)
		if nxt == cur:
			return out
		out.append(nxt)
		cur = nxt
	out.append("%")
	return out


def _path_ok(path: str) -> bool:
	for variant in decoded_variants(path):
		if variant == "%" or _CONTROL.search(variant):
			return False
		if "\\" in variant or "@" in variant or "//" in variant or "://" in variant:
			return False
		if not variant.startswith("/"):
			return False
		if any(seg in ("..", ".") for seg in variant.split("/")):
			return False
	return True


def normalize_target(path: Any) -> str | None:
	"""Return a safe relative path (optional ``?query``) or None. Fragment is dropped; case is preserved."""
	if not isinstance(path, str) or not path or len(path) > MAX_TARGET_LEN:
		return None
	text = path.split("#", 1)[0]
	base, sep, query = text.partition("?")
	if not base.startswith("/") or not _path_ok(base):
		return None
	if sep:
		for variant in decoded_variants(query):
			if variant == "%" or _CONTROL.search(variant) or "\\" in variant:
				return None
	return base + (sep + query if sep else "")


def _decode_for_match(path: Any, *, drop_fragment: bool) -> str | None:
	if not isinstance(path, str) or not path or "\x00" in path:
		return None
	p = path.split("?", 1)[0]
	if drop_fragment:
		p = p.split("#", 1)[0]
	for _i in range(3):
		d = unquote(p)
		if d == p:
			break
		p = d
	else:
		return None
	if "%" in p or "\\" in p or "\x00" in p:
		return None
	return p


def normalize_path(path: Any) -> str | None:
	"""Canonical lower-case absolute path (no query/fragment), or None when unsafe (traversal, odd encoding)."""
	p = _decode_for_match(path, drop_fragment=True)
	if p is None:
		return None
	segs = []
	for s in p.split("/"):
		if s in ("", "."):
			continue
		if s == ".." or s != s.strip():
			return None
		segs.append(s.lower())
	return "/" + "/".join(segs)


def normalize_path_keep_case(path: Any) -> str | None:
	"""Decoded absolute path without query; case kept. None on traversal or leftover encoding."""
	p = _decode_for_match(path, drop_fragment=False)
	if p is None or ".." in p.split("/"):
		return None
	return "/" + "/".join(s for s in p.split("/") if s)


def desk_aliases(path: str) -> list[str]:
	"""``/app/x`` <-> ``/desk/x``: both spellings of a desk path, the given one first."""
	for here, there in _DESK_PAIRS:
		if path == here or path.startswith(here + "/"):
			return [path, there + path[len(here) :]]
	return [path]


def parse_prefixes(text: Any, *, keep_case: bool = False) -> list[str]:
	"""Route prefixes from one-per-line settings text (``/``, query and unsafe lines dropped, desk aliases
	included, de-duplicated). Lower-cased for guard matching; ``keep_case=True`` keeps the configured spelling
	for redirect-target matching."""
	out: list[str] = []
	for line in str(text or "").splitlines():
		line = line.strip()
		if not line or "?" in line:
			continue
		norm = normalize_target(line) if keep_case else normalize_path(line)
		norm = (norm or "").rstrip("/")
		if not norm:
			continue
		for variant in desk_aliases(norm):
			if variant not in out:
				out.append(variant)
	return out


def path_matches(path: str, prefixes: Any) -> bool:
	"""Segment-boundary prefix match: ``/a/b`` matches ``/a/b`` and ``/a/b/c`` but not ``/a/bc``."""
	return any(path == p or path.startswith(p + "/") for p in prefixes)


def target_allowed(target: str, prefixes: Any) -> bool:
	"""A ``normalize_target`` result (may carry ``?query``) lies under one of the ``keep_case`` prefixes."""
	return path_matches(target.split("?", 1)[0], prefixes)
