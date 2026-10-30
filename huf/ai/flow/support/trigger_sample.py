"""The sample request a webhook trigger remembers (``node._sample``) and the "last received request" it offers.

A sample is only there to show people which fields their later steps can use, so it is trimmed hard: secrets and
passwords are blanked, long text is shortened, nesting is limited and the whole thing stays under ``MAX_SAMPLE_BYTES``.
Pure functions (no database).
"""

from __future__ import annotations

import json
import re

MAX_SAMPLE_BYTES = 8 * 1024
MAX_DEPTH = 6
MAX_TEXT = 200
MAX_LIST = 20
# Tried in order until the sample fits in MAX_SAMPLE_BYTES: (items kept per list, characters kept per text). A list of 20 items
# keeps all 20 whenever they fit, so a picker can say "Agents (20)".
LIMITS = ((MAX_LIST, MAX_TEXT), (10, 120), (5, 80))
MAX_KEYS = 40

_SECRET_KEY = re.compile(
	r"pass(word|wd)?|secret|token|authorization|api[_-]?key|credential|cookie|signature|private|bearer|jwt|csrf|xsrf"
	r"|session[_-]?(id|key)|access[_-]?key|(^|[_\-\s.])auth($|[_\-\s.])|^sid$",
	re.I,
)
# Values that look like credentials even when the key around them is harmless ("value": "sk-...", "note": "Bearer ...").
_SECRET_VALUE = re.compile(
	r"(sk-[A-Za-z0-9_\-]{16,}|xox[abprs]-[A-Za-z0-9\-]{10,}|gh[pousr]_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_\-]{30,}"
	r"|Bearer\s+[A-Za-z0-9._\-]{16,}|Basic\s+[A-Za-z0-9+/=]{16,}|eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,})"
)
MASK = "(hidden)"
# Header-style names that only ever carry a credential: the key is removed from a sample altogether (not just its value).
HEADER_KEYS = frozenset(
	{
		"authorization", "proxy-authorization", "cookie", "set-cookie", "x-huf-secret", "x-api-key", "api-key", "apikey",
		"x-auth-token", "x-access-token", "x-csrf-token", "x-xsrf-token", "x-session-id", "x-slack-signature",
	}
)
_PAIR_NAME_KEYS = ("name", "key", "header", "field", "id")


def is_header_key(key) -> bool:
	return str(key).strip().lower().replace("_", "-") in HEADER_KEYS


def is_secret_key(key) -> bool:
	return bool(_SECRET_KEY.search(str(key)))


def secret_pair(value) -> bool:
	"""``{"name": "Authorization", "value": "Bearer ..."}``: a header or setting written as a name/value pair."""
	if not isinstance(value, dict) or "value" not in value:
		return False
	return any(isinstance(value.get(k), str) and (is_header_key(value[k]) or is_secret_key(value[k])) for k in _PAIR_NAME_KEYS)


def hide_secret_values(text: str) -> str:
	return _SECRET_VALUE.sub(MASK, text)


def _trim(value, depth: int, max_list: int = MAX_LIST, max_text: int = MAX_TEXT):
	if depth > MAX_DEPTH:
		return "..."
	if isinstance(value, dict):
		out = {}
		pair = secret_pair(value)
		for i, (key, item) in enumerate(value.items()):
			if i >= MAX_KEYS:
				break
			if is_header_key(key):
				continue  # credential headers are removed, at any depth
			if is_secret_key(key) or (pair and key == "value"):
				out[str(key)] = MASK
			else:
				out[str(key)] = _trim(item, depth + 1, max_list, max_text)
		return out
	if isinstance(value, (list, tuple)):
		return [_trim(item, depth + 1, max_list, max_text) for item in list(value)[:max_list]]
	if isinstance(value, str):
		value = hide_secret_values(value)
		return value if len(value) <= max_text else value[: max_text - 3] + "..."
	if value is None or isinstance(value, (bool, int, float)):
		return value
	return str(value)[:max_text]


def redact_sample(value):
	"""A safe, small copy of a request body: hidden secrets, shortened text, limited depth, <= 8 KB as JSON."""
	for max_list, max_text in LIMITS:
		trimmed = _trim(value, 0, max_list, max_text)
		if len(json.dumps(trimmed, default=str).encode()) <= MAX_SAMPLE_BYTES:
			return trimmed
	if isinstance(trimmed, dict):
		# Still too large: keep the first keys that fit, so the field names (the point of a sample) survive.
		kept: dict = {}
		for key, item in trimmed.items():
			candidate = {**kept, key: item}
			if len(json.dumps(candidate, default=str).encode()) > MAX_SAMPLE_BYTES:
				break
			kept = candidate
		return kept
	return str(trimmed)[:MAX_TEXT]


def drop_samples(graph):
	"""A copy of ``graph`` whose nodes carry no ``_sample`` (people who cannot edit the flow never see request data)."""
	import copy

	if not isinstance(graph, dict):
		return graph
	stripped = copy.deepcopy(graph)
	nodes = stripped.get("nodes")
	for node in (list(nodes.values()) if isinstance(nodes, dict) else nodes or []):
		if isinstance(node, dict):
			node.pop("_sample", None)
			node.pop("_sample_at", None)
	return stripped


def cap_node_samples(graph) -> bool:
	"""Shrink any ``_sample`` that is over the limit or holds a secret, in place. True when something changed.

	Samples arrive from the editor, which already trims them; this is the server's own guarantee that no definition
	stores more than 8 KB per step or a password someone pasted in.
	"""
	nodes = graph.get("nodes") if isinstance(graph, dict) else None
	changed = False
	for node in (list(nodes.values()) if isinstance(nodes, dict) else nodes or []):
		if not isinstance(node, dict) or node.get("_sample") is None:
			continue
		safe = redact_sample(node["_sample"])
		if safe != node["_sample"]:
			node["_sample"] = safe
			changed = True
	return changed
